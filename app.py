import mido
import time
import os
import serial
import collections
from controller_config import *
from colors import *

DEBUG = os.environ.get('DEBUG')
BPM = int(os.environ.get('BPM', 240))

def debug_print(*args, **kwargs):
    if not DEBUG:
        return
    print(*args, **kwargs)

def noop(*args, **kwargs):
    pass

def color_components_to_color_byte(components):
    return components['red'] + (components['green'] << 4)

def color_byte_to_color_components(byte):
    return {
        'red': byte & 15,
        'green': byte >> 4,
    }

def send_usb_midi_message(message: mido.Message):
    try:
        inport, outport = get_ports()
        if outport:
            outport.send(message)
    except Exception as e:
        print(e)
        reset_ports()

def set_led_color(led_index, color):
    color_byte = color_components_to_color_byte(color)
    template_index = 0
    message = mido.Message('sysex', data=[0, 32, 41, 2, 17, 120, template_index, led_index, color_byte])
    send_usb_midi_message(message)

CV1_CC = 52
CV2_CC = 53
CV3_CC = 54
GATE_CC = 61
TRIGGER_CC = 62
RUN_CC = 63
RESET_CC = 64
END_OF_SEQUENCE_CC = 65

def send_midi_message(message: mido.Message):
    if midi_out is None:
        debug_print('OUT:', message)
    else:
        midi_out.write(message.bytes())

if_step_played = lambda played_color: lambda button: played_color if button.is_step_played() else COLORS['OFF']

GATE_LINE_MODES = [
    {
        'name': 'HALF',
        'active_color': if_step_played(COLORS['GREEN_3']),
        'inactive_color': if_step_played(COLORS['GREEN_1']),
        'active_field': 'is_gate_active',
        'duty_cycle': 0.5,
    },
    {
        'name': 'TIE',
        'active_color': if_step_played(COLORS['YELLOW_3']),
        'inactive_color': if_step_played(COLORS['YELLOW_2']),
        'active_field': 'is_gate_active',
        'duty_cycle': 1,
    },
    {
        'name': 'SILENT',
        'active_color': if_step_played(COLORS['OFF']),
        'inactive_color': if_step_played(COLORS['RED_2']),
        'active_field': 'is_current_step',
        'duty_cycle': 0,
    },
]

STEP_LINE_MODES = [
    {
        'name': 'STEP',
        'active_color': COLORS['GREEN_3'],
        'inactive_color': COLORS['OFF'],
        'active_field': 'is_current_step',
        'played': True,
    },
    {
        'name': 'SKIP',
        'active_color': COLORS['YELLOW_3'],
        'inactive_color': COLORS['YELLOW_2'],
        'active_field': 'is_current_step',
        'played': False,
    },
    {
        'name': 'RESET',
        'active_color': COLORS['RED_3'],
        'inactive_color': COLORS['RED_2'],
        'active_field': 'is_current_step',
        'played': False,
    },
    {
        'name': 'STOP',
        'active_color': COLORS['GREEN_3'],
        'inactive_color': COLORS['GREEN_1'],
        'active_field': 'is_current_step',
        'played': True,
    },
]

TEST_LINE_MODES = [
    {
        'name': 'OFF',
        'active_color': COLORS['RED_3'],
        'active_field': None,
    },
    {
        'name': 'ON',
        'active_color': COLORS['GREEN_3'],
        'active_field': None,
    },
]

class Button:
    def __init__(self, cc_number, led_index, modesets={}, active_modeset_name=None, active_modes={}, cc_value=None, midi_channel=0, is_current_step=False, is_gate_active=False, sequencer=None, step_index=None):
        controllers.append(self)
        self.midi_channel = midi_channel
        self.cc_number = cc_number
        self.cc_value = cc_value
        self.led_index = led_index

        self.sequencer = sequencer
        self.step_index = step_index

        self.is_current_step = is_current_step
        self.is_gate_active = is_gate_active

        self.on_button_down = []
        self.on_button_up = []
        self.on_step_change = []

        self.modesets = modesets
        self.active_modeset_name = active_modeset_name
        self.active_modes = {}

        for modeset_name in modesets:
            self.set_active_mode_index(modeset_name, active_modes[modeset_name] if modeset_name in active_modes else 0)

    def __str__(self):
        return f'Button(is_current_step={self.is_current_step} step_index={self.step_index}, is_gate_active={self.is_gate_active}, active_modeset_name={self.active_modeset_name})'

    def get_modeset(self, modeset_name: str):
        return self.modesets[modeset_name]

    def get_active_modeset(self):
        return self.get_modeset(self.active_modeset_name)

    def get_active_mode_index(self):
        return self.active_modes[self.active_modeset_name]

    def get_active_mode(self):
        return self.get_active_modeset()[self.get_active_mode_index()]

    def get_active_mode_index_for_modeset(self, modeset_name: str):
        return self.active_modes[modeset_name]

    def get_active_mode_for_modeset(self, modeset_name: str):
        return self.get_modeset(modeset_name)[self.get_active_mode_index_for_modeset(modeset_name)]

    def set_active_modeset(self, modeset_name: str):
        self.active_modeset_name = modeset_name
        self.set_led_color(self.get_led_color())

    def set_active_mode_index(self, modeset_name: str, active_mode_index: int):
        self.active_modes[modeset_name] = active_mode_index
        self.set_led_color(self.get_led_color())

    def set_next_active_mode(self, modeset_name: str=None):
        if modeset_name is None:
            modeset_name = self.active_modeset_name

        # Disable changing gate mode with button press when step is not played
        if modeset_name == 'gate' and not self.is_step_played():
            return

        modeset = self.get_modeset(modeset_name)
        active_mode_index = self.get_active_mode_index_for_modeset(modeset_name)
        self.set_active_mode_index(modeset_name, (active_mode_index + 1) % len(modeset))

    def is_step_played(self):
        first_reset_index = self.sequencer.get_first_reset_index()
        is_after_reset = self.step_index > first_reset_index if first_reset_index is not None else False
        if is_after_reset:
            return False

        return self.get_active_mode_for_modeset('step')['played']

    def set_value(self, midi_channel, cc_number, cc_value):
        if midi_channel != self.midi_channel:
            return

        if cc_number != self.cc_number:
            return

        self.cc_value = cc_value
        if cc_value < 64:
            for callback in self.on_button_up:
                callback(self)
        elif cc_value >= 64:
            for callback in self.on_button_down:
                callback(self)

    # This should probably be done by the Sequencer class
    def set_is_current_step(self, is_current_step):
        old_is_current_step = self.is_current_step
        self.is_current_step = is_current_step
        self.set_led_color(self.get_led_color())
        if old_is_current_step != is_current_step:
            for callback in self.on_step_change:
                callback(self)

    def set_is_gate_active(self, is_gate_active):
        old_is_gate_active = self.is_gate_active
        self.is_gate_active = is_gate_active
        if old_is_gate_active != is_gate_active:
            self.set_led_color(self.get_led_color())

    def get_led_color(self):
        active_mode = self.get_active_mode()
        active_field_value = getattr(self, active_mode['active_field']) if active_mode['active_field'] else True
        if active_field_value:
            return callable(active_mode['active_color']) and active_mode['active_color'](self) or active_mode['active_color']
        else:
            return callable(active_mode['inactive_color']) and active_mode['inactive_color'](self) or active_mode['inactive_color']

    def set_led_color(self, color=None):
        if self.led_index is None:
            return

        if color is None:
            return

        set_led_color(self.led_index, color)

class RadioButtons():
    def __init__(self, buttons: list[Button], selected_index=0, selected_color=COLORS['GREEN_3'], unselected_color=COLORS['OFF']):
        self.buttons = buttons
        self.selected_index = selected_index
        self.selected_color = selected_color
        self.unselected_color = unselected_color
        self.selected_index_callbacks = []
        self.set_led_colors()

        for i, button in enumerate(buttons):
            def on_button_down_callback(button, i=i):
                self.set_selected_index(i)
            button.on_button_down.append(on_button_down_callback)

    def set_selected_index(self, selected_index):
        old_selected_index = self.selected_index
        self.selected_index = selected_index
        self.set_led_colors()
        if old_selected_index != selected_index:
            for callback in self.selected_index_callbacks:
                callback(self, selected_index)

    def set_led_colors(self):
        for i, button in enumerate(self.buttons):
            if i == self.selected_index:
                button.set_led_color(self.selected_color)
            else:
                button.set_led_color(self.unselected_color)

class Controller:
    def __init__(self, cc_number, led_index, cc_value=None, midi_channel=0, is_current_step=False, sequencer=None, step_index=None):
        controllers.append(self)
        self.cc_number = cc_number
        self.led_index = led_index
        self.cc_value = cc_value
        self.midi_channel = midi_channel
        self.sequencer = sequencer
        self.step_index = step_index
        self.is_current_step = is_current_step
        self.set_led_color(self.get_led_color())

    def set_value(self, midi_channel, cc_number, cc_value):
        if midi_channel != self.midi_channel:
            return

        if cc_number != self.cc_number:
            return

        old_cc_value = self.cc_value
        self.cc_value = cc_value
        if old_cc_value is None and cc_value is not None:
            self.set_led_color(self.get_led_color())

    def set_is_current_step(self, is_current_step):
        old_is_current_step = self.is_current_step
        self.is_current_step = is_current_step
        if old_is_current_step != is_current_step:
            self.set_led_color(self.get_led_color())

    def get_led_color(self):
        if self.cc_value is None:
            return COLORS['RED_3'] if self.is_current_step else COLORS['RED_1']
        else:
            return COLORS['GREEN_3'] if self.is_current_step else COLORS['GREEN_1']

    def set_led_color(self, color=None):
        if self.led_index is None:
            return

        if color is None:
            return

        set_led_color(self.led_index, color)

controllers = []

class Sequencer:
    def __init__(self, total_steps: int, clock, note_controller_row, button_row, cv_controller_rows=[], current_step=0):
        self.total_steps = total_steps
        self.clock = clock
        self.current_step = current_step
        self.is_gate_active = False
        self.is_running = False

        self.step_controllers: list[list[Controller | Button]] = [[] for i in range(total_steps)]
        self.note_controllers: list[Controller] = []
        self.cv_controllers: list[list[Controller]] = [[] for i in range(total_steps)]
        self.buttons: list[Button] = []

        for i in range(total_steps):
            note_controller = note_controller_row[i]
            controller_obj = Controller(
                sequencer=self,
                step_index=i,
                cc_number=note_controller['cc_number'],
                led_index=note_controller['led_index'],
                is_current_step=i == current_step,
            )
            self.step_controllers[i].append(controller_obj)
            self.note_controllers.append(controller_obj)

            button = button_row[i]
            button_obj = Button(
                sequencer=self,
                step_index=i,
                cc_number=button['cc_number'],
                led_index=button['led_index'],
                modesets={'step': STEP_LINE_MODES, 'gate': GATE_LINE_MODES, 'test': TEST_LINE_MODES},
                active_modeset_name='step',
                is_current_step=i == current_step,
            )
            button_obj.on_button_down.append(lambda button: button.set_next_active_mode())
            self.step_controllers[i].append(button_obj)
            self.buttons.append(button_obj)

            for cv_controllers in cv_controller_rows:
                cv_controller = cv_controllers[i]
                controller_obj = Controller(
                    sequencer=self,
                    step_index=i,
                    cc_number=cv_controller['cc_number'],
                    led_index=cv_controller['led_index'],
                    is_current_step=i == current_step,
                )
                self.step_controllers[i].append(controller_obj)
                self.cv_controllers[i].append(controller_obj)

        mode_buttons = RadioButtons(
            buttons=[
                Button(
                    cc_number=DEVICE['cc_number'],
                    led_index=DEVICE['led_index'],
                ),
                Button(
                    cc_number=MUTE['cc_number'],
                    led_index=MUTE['led_index'],
                ),
                Button(
                    cc_number=SOLO['cc_number'],
                    led_index=SOLO['led_index'],
                ),
            ]
        )
        def on_selected_index_callback(buttons, selected_index):
            for button in self.buttons:
                button.set_active_modeset(['step', 'gate', 'test'][selected_index])
        mode_buttons.selected_index_callbacks.append(on_selected_index_callback)

        self.clock.on_tick(self.step)

        tempo_button = Button(
            cc_number=RIGHT['cc_number'],
            led_index=RIGHT['led_index'],
        )
        tempo_button.set_led_color(COLORS['RED_3'])
        self.clock.on_tick(lambda: tempo_button.set_led_color(COLORS['RED_3']))
        self.clock.on_interval_percent(0.2, lambda: tempo_button.set_led_color(COLORS['OFF']))

        self.TAP_COUNT = 4
        self.interval_shift_register = collections.deque([], self.TAP_COUNT)

        tempo_button.on_button_down.append(self.add_tempo_tap)

        self.run_button = Button(
            cc_number=UP['cc_number'],
            led_index=UP['led_index'],
        )
        self.run_button.set_led_color(COLORS['RED_3'] if self.is_running else COLORS['OFF'])
        self.run_button.on_button_down.append(self.run)

        reset_button = Button(
            cc_number=DOWN['cc_number'],
            led_index=DOWN['led_index'],
        )
        reset_button.set_led_color(COLORS['RED_3'])
        reset_button.on_button_down.append(self.reset)

        self.run()

    def add_tempo_tap(self, button):
        now = time.time()

        if len(self.interval_shift_register) > 0 and now - self.interval_shift_register[-1] > 3:
            print('clearing tempo register')
            self.interval_shift_register.clear()

        self.interval_shift_register.append(now)

        if len(self.interval_shift_register) < self.TAP_COUNT:
            return

        interval = (self.interval_shift_register[-1] - self.interval_shift_register[0]) / (self.TAP_COUNT - 1)
        bpm = 60 / interval

        print('bpm', bpm, 'interval', interval)

        self.clock.bpm = bpm
        self.clock.interval = interval

    def run(self, button=None):
        self.is_running = not self.is_running
        self.run_button.set_led_color(COLORS['RED_3'] if self.is_running else COLORS['OFF'])
        self.clock.run()

    def reset(self, button):
        self.is_gate_active = False
        self.clock.reset()
        self.step(0)
        self.output_gate_off()

    def get_first_reset_index(self):
        first_reset_index = None
        for i, seq_button in enumerate(self.buttons):
            if seq_button.get_active_mode_for_modeset('step')['name'] == 'RESET':
                first_reset_index = i
                break
        return first_reset_index

    def get_next_step(self, current_step: int, initial_step: int | None=None):
        if initial_step == current_step:
            return current_step

        if initial_step is None:
            initial_step = current_step

        next_step = (current_step + 1) % self.total_steps
        current_step_button = self.buttons[current_step]
        current_step_mode = current_step_button.get_active_mode_for_modeset('step')
        next_step_button = self.buttons[next_step]
        next_step_mode = next_step_button.get_active_mode_for_modeset('step')

        if current_step_mode['name'] == 'STOP':
            return current_step

        if next_step_mode['name'] == 'RESET':
            for step, step_line_button in enumerate(self.buttons):
                if step_line_button.get_active_mode_for_modeset('step')['played']:
                    return step
            return current_step
        elif next_step_mode['name'] == 'SKIP':
            return self.get_next_step(next_step, initial_step)
        elif next_step_mode['name'] == 'STOP':
            return next_step
        elif next_step_mode['name'] == 'STEP':
            return next_step
        else:
            return current_step

    def get_step_info(self, step: int):
        note = 0
        note_controller = self.note_controllers[step]
        if note_controller.cc_value is not None:
            note = note_controller.cc_value

        cvs = [0, 0, 0]
        for i, cv_controller in enumerate(self.cv_controllers[step]):
            value = cv_controller.cc_value
            if value is not None:
                cvs[i] = value

        button = self.buttons[step]
        return {
            'note': note,
            'cv1': cvs[0],
            'cv2': cvs[1],
            'cv3': cvs[2],
            'duty_cycle': button.get_active_mode_for_modeset('gate')['duty_cycle'],
        }

    def output_pulse(self, on_callback, off_callback, start_time=0, end_time=0):
        if start_time == 0:
            on_callback()
        else:
            self.clock.once_time(start_time, lambda: on_callback())
        self.clock.once_time(end_time, lambda: off_callback())

    def output_trigger(self, step_info):
        def trigger_on():
            debug_print('trigger on')
            send_midi_message(mido.Message('control_change', channel=0, control=TRIGGER_CC, value=127))

        def trigger_off():
            debug_print('trigger off')
            send_midi_message(mido.Message('control_change', channel=0, control=TRIGGER_CC, value=0))

        self.output_pulse(trigger_on, trigger_off)

    def output_gate_on(self, step_info):
        if self.is_gate_active:
            return
        self.output_trigger(step_info)
        self.is_gate_active = True

        debug_print('gate on')
        send_midi_message(mido.Message('control_change', channel=0, control=GATE_CC, value=127))

    def output_gate_off(self):
        if not self.is_gate_active:
            return
        self.is_gate_active = False

        debug_print('gate off')
        send_midi_message(mido.Message('control_change', channel=0, control=GATE_CC, value=0))

    def output_gate(self, step_info, step_index):
        if step_info['duty_cycle'] == 0:
            self.output_gate_off()
            for i, button in enumerate(self.buttons):
                button.set_is_gate_active(i == step_index)
            return

        if step_info['duty_cycle'] < 1:
            self.output_pulse(lambda: self.output_gate_on(step_info), self.output_gate_off, end_time=step_info['duty_cycle'] * self.clock.interval)
        else:
            self.output_gate_on(step_info)

        for i, button in enumerate(self.buttons):
            button.set_is_gate_active(i == step_index)
            if step_info['duty_cycle'] < 1:
                self.clock.once_time(step_info['duty_cycle'] * self.clock.interval, lambda button=button: button.set_is_gate_active(False))

    def output_note(self, step_info):
        if self.buttons[self.current_step].get_active_mode_for_modeset('gate')['name'] == 'SILENT':
            return

        def note_on():
            # TODO: Scale and quantize
            debug_print('note', step_info['note'])
            send_midi_message(mido.Message('note_on', channel=0, note=step_info['note'], velocity=127))

        def note_off():
            send_midi_message(mido.Message('note_off', channel=0, note=step_info['note'], velocity=127))

        self.output_pulse(note_on, note_off)

    def output_cvs(self, step_info):
        if self.buttons[self.current_step].get_active_mode_for_modeset('gate')['name'] == 'SILENT':
            return

        debug_print(f'cv1: {step_info["cv1"]}, cv2: {step_info["cv2"]}, cv3: {step_info["cv3"]}')
        send_midi_message(mido.Message('control_change', channel=0, control=CV1_CC, value=step_info['cv1']))
        send_midi_message(mido.Message('control_change', channel=0, control=CV2_CC, value=step_info['cv2']))
        send_midi_message(mido.Message('control_change', channel=0, control=CV3_CC, value=step_info['cv3']))

    def output_end_of_sequence(self):
        def end_of_sequence_on():
            debug_print('end of sequence on')
            send_midi_message(mido.Message('control_change', channel=0, control=END_OF_SEQUENCE_CC, value=127))

        def end_of_sequence_off():
            debug_print('end of sequence off')
            send_midi_message(mido.Message('control_change', channel=0, control=END_OF_SEQUENCE_CC, value=0))

        self.output_pulse(end_of_sequence_on, end_of_sequence_off)

    def step(self, step_index=None):
        if step_index is None:
            step_index = self.get_next_step(self.current_step)
        old_step = self.current_step
        self.current_step = step_index

        if step_index <= old_step:
            self.output_end_of_sequence()
        step_info = self.get_step_info(step_index)
        self.output_note(step_info)
        self.output_cvs(step_info)
        self.output_gate(step_info, step_index)

        for i, step_controllers in enumerate(self.step_controllers):
            for controller in step_controllers:
                controller.set_is_current_step(i == step_index)

def receive_midi_message(message: mido.Message):
    debug_print('IN:', message)

    if not message.is_cc():
        return

    for controller in controllers:
        controller.set_value(message.channel, message.control, message.value)

partial_input_name = 'Launch Control XL'
partial_output_name = 'Launch Control XL'
inport = None
outport = None

def get_ports():
    global inport, outport

    if inport and outport:
        return inport, outport

    inport = None
    outport = None

    try:
        input_port_names = mido.get_input_names()
        output_port_names = mido.get_output_names()
    except Exception as e:
        print('Failed to get ports')
        return None, None

    input_port_name = next((name for name in input_port_names if partial_input_name in name), None)
    output_port_name = next((name for name in output_port_names if partial_output_name in name), None)
    if input_port_name is None or output_port_name is None:
        return None, None

    inport = mido.open_input(input_port_name, callback=receive_midi_message)
    print('Opened MIDI input', inport.name)
    outport = mido.open_output(output_port_name)
    print('Opened MIDI output', outport.name)

    return inport, outport

def reset_ports():
    global inport, outport
    if inport:
        print('Closing MIDI input', inport.name)
        inport.close()
        inport = None
    if outport:
        print('Closing MIDI output', outport.name)
        outport.close()
        outport = None

inport, outport = get_ports()

midi_out_device = '/dev/serial0'
midi_out = os.path.exists(midi_out_device) and serial.Serial(midi_out_device, baudrate=31250) or None

class Clock:
    def __init__(self, bpm):
        self.is_running = False
        self.bpm = bpm
        self.interval = 60 / bpm
        self.time = time.time()
        self.on_tick_callbacks = []
        self.once_time_callbacks = []
        self.on_interval_percent_callbacks = []
        self.on_interval_percent_callbacks_to_call = []

        self.on_tick(self.reset_on_interval_percent_callbacks)

    def run(self):
        self.is_running = not self.is_running
        self.reset()

    def reset(self):
        self.time = time.time()

    def set_time(self):
        if not self.is_running:
            return

        old_time = self.time
        new_time = time.time()
        diff = new_time - old_time

        for at_time, callback in self.once_time_callbacks:
            if diff >= at_time:
                callback()
                self.once_time_callbacks.remove((at_time, callback))

        for callback_tuple in self.on_interval_percent_callbacks:
            percent, callback = callback_tuple
            if diff >= self.interval * percent and callback_tuple in self.on_interval_percent_callbacks_to_call:
                callback()
                self.on_interval_percent_callbacks_to_call.remove(callback_tuple)

        if diff >= self.interval:
            self.time = old_time + self.interval
            for callback in self.on_tick_callbacks:
                callback()

    def on_tick(self, callback):
        self.on_tick_callbacks.append(callback)

    def once_time(self, at_time, callback):
        self.once_time_callbacks.append((at_time, callback))

    def on_interval_percent(self, percent, callback):
        self.on_interval_percent_callbacks.append((percent, callback))
        self.reset_on_interval_percent_callbacks()

    def reset_on_interval_percent_callbacks(self):
        self.on_interval_percent_callbacks_to_call = [callback for callback in self.on_interval_percent_callbacks if callback[0] * self.interval > time.time() - self.time]

clock = Clock(bpm=BPM)
sequencer = Sequencer(
    total_steps=16,
    clock=clock,
    note_controller_row=SEND_A + PAN_DEVICE,
    button_row=TRACK_FOCUS + TRACK_CONTROL,
    cv_controller_rows=[SEND_B + FADERS],
)

while True:
    clock.set_time()
    time.sleep(0.001)
