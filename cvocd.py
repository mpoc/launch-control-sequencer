from utils import remap_clamped_int

CV_OCD_MIDI_0V = 24
CV_OCD_MIDI_8V = 120

def get_cv_ocd_midi_value(volts: float):
    return remap_clamped_int(volts, 0, 8, CV_OCD_MIDI_0V, CV_OCD_MIDI_8V)
