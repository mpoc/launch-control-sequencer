import mido
import time
import os
from controller_config import *
from colors import *

DEBUG = os.environ.get('DEBUG')
def debug_print(*args, **kwargs):
    if not DEBUG:
        return
    print(*args, **kwargs)

def noop(*args, **kwargs):
    pass

def colorComponentsToColorByte(components):
    return components['red'] + (components['green'] << 4)

def colorByteToColorComponents(byte):
    return {
        'red': byte & 15,
        'green': byte >> 4,
    }

def setLedColor(port, ledIndex, color):
    colorByte = colorComponentsToColorByte(color)
    templateIndex = 0
    msg = mido.Message('sysex', data=[0, 32, 41, 2, 17, 120, templateIndex, ledIndex, colorByte])
    port.send(msg)

if_step_played = lambda played_color: lambda button: played_color if button.is_step_played() else COLORS['OFF']

GATE_LINE_MODES = [
    {
        'name': 'LONG',
        'active_color': if_step_played(COLORS['GREEN_3']),
        'inactive_color': if_step_played(COLORS['GREEN_1']),
        'active_field': 'is_gate_active',
        'duty_cycle': 0.9,
    },
    {
        'name': 'HALF',
        'active_color': if_step_played(COLORS['AMBER_3']),
        'inactive_color': if_step_played(COLORS['AMBER_2']),
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

        setLedColor(outport, self.led_index, color)

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
        self.set_led_color()

    def set_value(self, midi_channel, cc_number, cc_value):
        if midi_channel != self.midi_channel:
            return

        if cc_number != self.cc_number:
            return

        old_cc_value = self.cc_value
        self.cc_value = cc_value
        if old_cc_value is None and cc_value is not None:
            self.set_led_color()

    def set_is_current_step(self, is_current_step):
        old_is_current_step = self.is_current_step
        self.is_current_step = is_current_step
        if old_is_current_step != is_current_step:
            self.set_led_color()

    def get_led_color(self):
        if self.cc_value is None:
            return COLORS['RED_3'] if self.is_current_step else COLORS['RED_1']
        else:
            return COLORS['GREEN_3'] if self.is_current_step else COLORS['GREEN_1']

    def set_led_color(self):
        if self.led_index is None:
            return

        setLedColor(outport, self.led_index, self.get_led_color())

controllers = []

class Sequencer:
    def __init__(self, total_steps: int, clock, note_controller_row, button_row, cv_controller_rows=[], current_step=0):
        self.total_steps = total_steps
        self.clock = clock
        self.current_step = current_step
        self.is_gate_active = False

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

    def get_first_reset_index(self):
        first_reset_index = None
        for i, seq_button in enumerate(self.buttons):
            if seq_button.get_active_mode_for_modeset('step')['name'] == 'RESET':
                first_reset_index = i
                break
        return first_reset_index

    def get_next_step(self, current_step: int, initial_step: int=None):
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
                cvs[i] = cv_controller.cc_value

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

        def trigger_off():
            debug_print('trigger off')

        self.output_pulse(trigger_on, trigger_off)

    def output_gate(self, step_info, step_index):
        def gate_on():
            if self.is_gate_active:
                return
            self.output_trigger(step_info)
            self.is_gate_active = True
            debug_print('gate on')

        def gate_off():
            if not self.is_gate_active:
                return
            self.is_gate_active = False
            debug_print('gate off')

        if step_info['duty_cycle'] == 0:
            gate_off()
            return

        if step_info['duty_cycle'] < 1:
            self.output_pulse(gate_on, gate_off, end_time=step_info['duty_cycle'] * self.clock.interval)
        else:
            gate_on()

        for i, button in enumerate(self.buttons):
            button.set_is_gate_active(i == step_index)
            self.clock.once_time(step_info['duty_cycle'] * self.clock.interval, lambda button=button: button.set_is_gate_active(False))

    def output_note(self, step_info):
        # TODO: Scale and quantize
        debug_print('note', step_info['note'])

    def output_cvs(self, step_info):
        debug_print(f'cv1: {step_info["cv1"]}, cv2: {step_info["cv2"]}, cv3: {step_info["cv3"]}')

    def output_end_of_sequence(self):
        def end_of_sequence_on():
            debug_print('end of sequence on')

        def end_of_sequence_off():
            debug_print('end of sequence off')

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

print('Output ports:', mido.get_output_names())
launch_control_xl_output = [port for port in mido.get_output_names() if "Launch Control XL" in port][0]
print('Launch Control XL output:', launch_control_xl_output)
outport = mido.open_output(launch_control_xl_output)

print('Input ports:', mido.get_input_names())
launch_control_xl_input = [port for port in mido.get_input_names() if 'Launch Control XL' in port][0]
print('Launch Control XL input:', launch_control_xl_input)
inport = mido.open_input(launch_control_xl_input)

def receive_midi_message():
    while msg := inport.poll():
        debug_print(msg)
        if not msg.is_cc():
            continue
        for controller in controllers:
            controller.set_value(msg.channel, msg.control, msg.value)

class Clock:
    def __init__(self, bpm):
        self.bpm = bpm
        self.interval = 60 / bpm
        self.time = time.time()
        self.on_tick_callbacks = []
        self.once_time_callbacks = []

    def set_time(self):
        old_time = self.time
        new_time = time.time()
        diff = new_time - old_time

        for at_time, callback in self.once_time_callbacks:
            if diff >= at_time:
                callback()
                self.once_time_callbacks.remove((at_time, callback))

        if diff >= self.interval:
            self.time = old_time + self.interval
            for callback in self.on_tick_callbacks:
                callback()

    def on_tick(self, callback):
        self.on_tick_callbacks.append(callback)

    def once_time(self, at_time, callback):
        self.once_time_callbacks.append((at_time, callback))

clock = Clock(bpm=120)
sequencer = Sequencer(
    total_steps=8,
    clock=clock,
    note_controller_row=SEND_A,
    button_row=TRACK_FOCUS,
    cv_controller_rows=[
        SEND_B,
        PAN_DEVICE,
        FADERS,
    ],
)

while True:
    receive_midi_message()
    clock.set_time()
    time.sleep(0.001)
