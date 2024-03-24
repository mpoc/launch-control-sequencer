import os

def clamp(value: float, min_value: float, max_value: float):
    return max(min(value, max_value), min_value)

def remap(value: float, min1: float, max1: float, min2: float, max2: float):
    return min2 + ((max2 - min2) / (max1 - min1)) * (value - min1)

def remap_clamped(value: float, min1: float, max1: float, min2: float, max2: float):
    return clamp(remap(value, min1, max1, min2, max2), min2, max2)

def remap_clamped_int(value: float, min1: float, max1: float, min2: float, max2: float):
    return int(remap_clamped(value, min1, max1, min2, max2))

DEBUG = os.environ.get('DEBUG')

def debug_print(*args, **kwargs):
    if not DEBUG:
        return
    print(*args, **kwargs)

def noop(*args, **kwargs):
    pass
