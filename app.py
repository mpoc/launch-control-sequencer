import mido
import time
from controller_config import *
from colors import *

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

GATE_LINE_MODES = [
    {
        'name': 'GATE',
        'current_step_color': COLORS['GREEN_3'],
        'other_step_color': COLORS['OFF'],
        'duty_cycle': 0.9,
    },
    {
        'name': 'TIE',
        'current_step_color': COLORS['YELLOW_3'],
        'other_step_color': COLORS['YELLOW_2'],
        'duty_cycle': 1,
    },
    {
        'name': 'SILENT',
        'current_step_color': COLORS['RED_3'],
        'other_step_color': COLORS['RED_2'],
        'duty_cycle': 0,
    },
]

STEP_LINE_MODES = [
    {
        'name': 'STEP',
        'current_step_color': COLORS['GREEN_3'],
        'other_step_color': COLORS['OFF'],
        'played': True,
    },
    {
        'name': 'SKIP',
        'current_step_color': COLORS['YELLOW_3'],
        'other_step_color': COLORS['YELLOW_2'],
        'played': False,
    },
    {
        'name': 'RESET',
        'current_step_color': COLORS['RED_3'],
        'other_step_color': COLORS['RED_2'],
        'played': False,
    },
    {
        'name': 'STOP',
        'current_step_color': COLORS['GREEN_3'],
        'other_step_color': COLORS['GREEN_1'],
        'played': True,
    },
]

TEST_LINE_MODES = [
    {
        'name': 'OFF',
        'current_step_color': COLORS['RED_3'],
        'other_step_color': COLORS['RED_3'],
    },
    {
        'name': 'ON',
        'current_step_color': COLORS['GREEN_3'],
        'other_step_color': COLORS['GREEN_3'],
    },
]

class Button:
    def __init__(self, cc_number, led_index, modesets={}, active_modeset_name=None, active_modes={}, cc_value=None, midi_channel=0, is_current_step=False):
        controllers.append(self)
        self.midi_channel = midi_channel
        self.cc_number = cc_number
        self.cc_value = cc_value
        self.led_index = led_index

        self.is_current_step = is_current_step

        self.on_button_down = []
        self.on_button_up = []
        self.on_step_change = []

        self.modesets = modesets
        self.active_modeset_name = active_modeset_name
        self.active_modes = {}

        for modeset_name in modesets:
            self.set_active_mode_index(modeset_name, active_modes[modeset_name] if modeset_name in active_modes else 0)

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
        modeset = self.get_modeset(modeset_name)
        active_mode_index = self.get_active_mode_index_for_modeset(modeset_name)
        self.set_active_mode_index(modeset_name, (active_mode_index + 1) % len(modeset))

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

    def get_led_color(self):
        active_mode = self.get_active_mode()
        return active_mode['current_step_color'] if self.is_current_step else active_mode['other_step_color']

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
    def __init__(self, cc_number, led_index, cc_value=None, midi_channel=0, is_current_step=False):
        controllers.append(self)
        self.cc_number = cc_number
        self.led_index = led_index
        self.cc_value = cc_value
        self.midi_channel = midi_channel
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

        self.step_controllers: list[list[Controller | Button]] = [[] for i in range(total_steps)]
        self.note_controllers: list[Controller] = []
        self.cv_controllers: list[list[Controller]] = [[] for i in range(total_steps)]
        self.buttons: list[Button] = []

        for i in range(total_steps):
            note_controller = note_controller_row[i]
            controller_obj = Controller(
                cc_number=note_controller['cc_number'],
                led_index=note_controller['led_index'],
                is_current_step=i == current_step,
            )
            self.step_controllers[i].append(controller_obj)
            self.note_controllers.append(controller_obj)

            button = button_row[i]
            button_obj = Button(
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
        note_controller = self.note_controllers[step]
        cv1_controller = self.cv_controllers[step][1:2] and self.cv_controllers[step][1][0] or None
        cv2_controller = self.cv_controllers[step][2:3] and self.cv_controllers[step][2][0] or None
        cv3_controller = self.cv_controllers[step][3:4] and self.cv_controllers[step][3][0] or None
        button = self.buttons[step]
        return {
            'note': 64 if note_controller.cc_value is None else note_controller.cc_value,
            'cv1': cv1_controller.cc_value if cv1_controller else 0,
            'cv2': cv2_controller.cc_value if cv2_controller else 0,
            'cv3': cv3_controller.cc_value if cv3_controller else 0,
            'duty_cycle': button.get_active_mode_for_modeset('gate')['duty_cycle'],
        }

    def trigger(self, info):
        print('trigger on')
        self.clock.once_time(0, lambda: print('trigger off'))

    def gate(self, info):
        if info['duty_cycle'] == 0:
            return

        # TODO: Scale and quantize
        print(f'gate on with note {info["note"]}, cv1: {info["cv1"]}, cv2: {info["cv2"]}, cv3: {info["cv3"]}, duty cycle: {info["duty_cycle"]}')
        self.clock.once_time(info['duty_cycle'] * self.clock.interval, lambda: print('gate off'))

    def output(self, info):
        self.trigger(info)
        self.gate(info)

    def step(self, step=None):
        if step is None:
            step = self.get_next_step(self.current_step)
        self.current_step = step

        self.output(self.get_step_info(step))

        for i, step_controllers in enumerate(self.step_controllers):
            for controller in step_controllers:
                controller.set_is_current_step(i == step)

print('Output ports:', mido.get_output_names())
launch_control_xl_output = [port for port in mido.get_output_names() if "Launch Control XL" in port][0]
print('Launch Control XL output:', launch_control_xl_output)
outport = mido.open_output(launch_control_xl_output)

print('Input ports:', mido.get_input_names())
launch_control_xl_input = [port for port in mido.get_input_names() if 'Launch Control XL' in port][0]
print('Launch Control XL input:', launch_control_xl_input)
inport = mido.open_input(launch_control_xl_input)

def receive_midi_message():
    msg = inport.poll()
    if msg is None:
        return
    print(msg)
    if msg.is_cc():
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
