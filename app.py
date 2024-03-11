import mido
import time
from controller_config import *
from colors import *

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

class Button:
    def __init__(self, cc_number, led_index, modes, mode_index=0, cc_value=None, is_current_step=False):
        controllers.append(self)
        self.cc_number = cc_number
        self.cc_value = cc_value
        self.led_index = led_index
        self.modes = modes
        self.mode_count = len(modes)
        self.mode_index = mode_index
        self.is_current_step = is_current_step
        self.set_led_color()

    def on_button_down(self):
        self.mode_index = (self.mode_index + 1) % self.mode_count
        self.set_led_color()

    def on_button_up(self):
        pass

    def set_value(self, cc_number, cc_value):
        if cc_number != self.cc_number:
            return

        self.cc_value = cc_value
        if cc_value < 64:
            self.on_button_up()
        elif cc_value >= 64:
            self.on_button_down()

    def set_is_current_step(self, is_current_step):
        old_is_current_step = self.is_current_step
        self.is_current_step = is_current_step
        if old_is_current_step != is_current_step:
            self.set_led_color()

    def get_led_color(self):
        if self.is_current_step:
            return self.modes[self.mode_index]['current_step_color']
        else:
            return self.modes[self.mode_index]['other_step_color']

    def set_led_color(self):
        if self.led_index is None:
            return

        setLedColor(outport, self.led_index, self.get_led_color())

class Controller:
    def __init__(self, cc_number, led_index, cc_value=None, is_current_step=False):
        controllers.append(self)
        self.cc_number = cc_number
        self.led_index = led_index
        self.cc_value = cc_value
        self.is_current_step = is_current_step
        self.set_led_color()

    def set_value(self, cc_number, cc_value):
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
            if self.is_current_step:
                return COLORS['RED_3']
            else:
                return COLORS['RED_1']
        else:
            if self.is_current_step:
                return COLORS['GREEN_3']
            else:
                return COLORS['GREEN_1']

    def set_led_color(self):
        if self.led_index is None:
            return

        setLedColor(outport, self.led_index, self.get_led_color())

controllers = []

class Sequencer:
    def __init__(self, total_steps, clock, current_step=0):
        self.total_steps = total_steps
        self.current_step = current_step

        self.step_controllers = [[] for i in range(total_steps)]

        self.controllers = []
        for i, controller in enumerate(SEND_A):
            controller_obj = Controller(
                cc_number=controller['cc_number'],
                led_index=controller['led_index'],
                is_current_step=i == current_step,
            )
            self.controllers.append(controller_obj)
            self.step_controllers[i].append(controller_obj)
        for i, controller in enumerate(SEND_B):
            controller_obj = Controller(
                cc_number=controller['cc_number'],
                led_index=controller['led_index'],
                is_current_step=i == current_step,
            )
            self.controllers.append(controller_obj)
            self.step_controllers[i].append(controller_obj)
        for i, controller in enumerate(PAN_DEVICE):
            controller_obj = Controller(
                cc_number=controller['cc_number'],
                led_index=controller['led_index'],
                is_current_step=i == current_step,
            )
            self.controllers.append(controller_obj)
            self.step_controllers[i].append(controller_obj)
        for i, controller in enumerate(FADERS):
            controller_obj = Controller(
                cc_number=controller['cc_number'],
                led_index=controller['led_index'],
                is_current_step=i == current_step,
            )
            self.controllers.append(controller_obj)
            self.step_controllers[i].append(controller_obj)

        self.buttons = []
        self.step_buttons = [[] for i in range(total_steps)]
        self.gate_line_buttons = []
        for i, button in enumerate(TRACK_FOCUS):
            button_obj = Button(
                cc_number=button['cc_number'],
                led_index=button['led_index'],
                modes=GATE_LINE_MODES,
                is_current_step=i == current_step,
            )
            self.buttons.append(button_obj)
            self.step_controllers[i].append(button_obj)
            self.gate_line_buttons.append(button_obj)
        self.step_line_buttons = []
        for i, button in enumerate(TRACK_CONTROL):
            button_obj = Button(
                cc_number=button['cc_number'],
                led_index=button['led_index'],
                modes=STEP_LINE_MODES,
                is_current_step=i == current_step,
            )
            self.buttons.append(button_obj)
            self.step_controllers[i].append(button_obj)
            self.step_line_buttons.append(button_obj)

        clock.on_tick(self.step)

    def get_next_step(self, current_step, initial_step=None):
        if initial_step == current_step:
            return current_step

        if initial_step is None:
            initial_step = current_step

        next_step = (current_step + 1) % self.total_steps
        current_step_button = self.step_line_buttons[current_step]
        current_step_mode = current_step_button.modes[current_step_button.mode_index]
        next_step_button = self.step_line_buttons[next_step]
        next_step_mode = next_step_button.modes[next_step_button.mode_index]

        if current_step_mode['name'] == 'STOP':
            return current_step

        if next_step_mode['name'] == 'RESET':
            for step, step_line_button in enumerate(self.step_line_buttons):
                if step_line_button.modes[step_line_button.mode_index]['played']:
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

    def step(self):
        new_step = self.get_next_step(self.current_step)
        self.current_step = new_step
        for i, step_controllers in enumerate(self.step_controllers):
            for controller in step_controllers:
                controller.set_is_current_step(i == new_step)

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
            controller.set_value(msg.control, msg.value)

class Clock:
    def __init__(self, bpm):
        self.bpm = bpm
        self.interval = 60 / bpm
        self.time = time.time()
        self.on_tick_callbacks = []

    def set_time(self):
        old_time = self.time
        new_time = time.time()
        if new_time - old_time >= self.interval:
            self.time = new_time
            for on_tick in self.on_tick_callbacks:
                on_tick()

    def on_tick(self, on_tick):
        self.on_tick_callbacks.append(on_tick)

clock = Clock(bpm=240)
sequencer = Sequencer(total_steps=8, clock=clock)

while True:
    receive_midi_message()
    clock.set_time()
