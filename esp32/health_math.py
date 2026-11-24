"""Health maths for the StepQuest wearable (owner: A).

This one file runs in TWO places:
  * on the ESP32, under MicroPython (so no numpy and no `statistics` module here),
  * on the PC in the unit tests (tests/test_health_math.py), with made-up sensor signals.

Sensors:
  * MPU6050 / BMI160 accelerometer -> StepCounter (a step = one bump in how hard you move)
  * MAX30102 optical sensor -> heart_rate_bpm() (the beats in the red/infrared light)
                             -> spo2_percent()  (how much infrared vs red light the blood absorbs)

These are estimates from cheap sensors, good for a walking game, NOT medical measurements.
"""

GRAVITY = 9.81

# A step makes the acceleration jump above ~1.15 g and fall back. We need it to fall below
# 1.05 g again before counting the next one (so one wobbly step isn't counted twice), and we
# never count more than 4 steps a second (faster than a sprint).
STEP_HIGH_G = 1.15
STEP_LOW_G = 1.05
MIN_STEP_GAP_S = 0.25

MIN_BPM = 35
MAX_BPM = 220


def magnitude_g(ax, ay, az):
    """How hard the device is accelerating, in g (1.0 = standing still), from m/s^2 readings."""
    return (ax * ax + ay * ay + az * az) ** 0.5 / GRAVITY


class StepCounter:
    """Feed it acceleration samples one by one; it counts steps.

    Uses a small moving average to smooth the shaking, then waits for the smoothed value
    to go above STEP_HIGH_G (a step) and back below STEP_LOW_G (ready for the next one).
    """

    def __init__(self, sample_rate_hz, smooth=4):
        self.rate = sample_rate_hz
        self.window = []
        self.smooth = smooth
        self.steps = 0
        self.armed = True           # ready to count the next step
        self.samples_since_step = 10 ** 9

    def add(self, g):
        """Add one sample (in g). Returns True if this sample finished a step."""
        self.window.append(g)
        if len(self.window) > self.smooth:
            self.window.pop(0)
        level = sum(self.window) / len(self.window)
        self.samples_since_step += 1
        if self.armed and level >= STEP_HIGH_G and self.samples_since_step >= MIN_STEP_GAP_S * self.rate:
            self.steps += 1
            self.armed = False
            self.samples_since_step = 0
            return True
        if not self.armed and level <= STEP_LOW_G:
            self.armed = True
        return False


def _moving_average(values, size):
    out = []
    total = 0.0
    for i, v in enumerate(values):
        total += v
        if i >= size:
            total -= values[i - size]
        out.append(total / min(i + 1, size))
    return out


def _median(values):
    ordered = sorted(values)
    n = len(ordered)
    if n == 0:
        return None
    mid = n // 2
    return ordered[mid] if n % 2 else (ordered[mid - 1] + ordered[mid]) / 2


def find_beats(ppg, rate_hz):
    """The sample numbers where the heart beats, from a light (PPG) signal.

    1. Remove the slow drift (breathing, the finger moving) by subtracting a 1-second average.
    2. A beat is a local top that is above the signal's typical level and at least
       60/MAX_BPM seconds after the previous beat.
    """
    if len(ppg) < rate_hz * 2:
        return []
    baseline = _moving_average(ppg, int(rate_hz))
    wave = [p - b for p, b in zip(ppg, baseline)]
    wave = _moving_average(wave, max(1, int(rate_hz / 10)))   # smooth the sensor noise a little
    tops = sorted(wave)
    threshold = tops[int(len(tops) * 0.75)]                    # beats are in the top quarter
    min_gap = int(rate_hz * 60 / MAX_BPM)
    beats = []
    for i in range(1, len(wave) - 1):
        if wave[i] > threshold and wave[i] >= wave[i - 1] and wave[i] > wave[i + 1]:
            if not beats or i - beats[-1] >= min_gap:
                beats.append(i)
    return beats


MIN_PULSE_SHARE = 0.002   # a real pulse changes the light by at least 0.2 % of its level
MAX_GAP_SPREAD = 0.25     # time between beats may vary by about 25 % at most


def _has_pulse(ppg, rate_hz):
    """True if the signal moves clearly more than sensor noise does."""
    level = sum(ppg) / len(ppg)
    if level <= 0:
        return False
    baseline = _moving_average(ppg, int(rate_hz))
    wave = _moving_average([p - b for p, b in zip(ppg, baseline)], max(1, int(rate_hz / 10)))
    return (max(wave) - min(wave)) >= MIN_PULSE_SHARE * level


def _regular(gaps):
    """True if the times between beats are steady (spread at most MAX_GAP_SPREAD of the average)."""
    mean = sum(gaps) / len(gaps)
    spread = (sum((g - mean) ** 2 for g in gaps) / len(gaps)) ** 0.5
    return spread <= MAX_GAP_SPREAD * mean


def heart_rate_bpm(ppg, rate_hz):
    """Beats per minute from a few seconds of PPG samples, or None if it can't tell.

    Uses the MEDIAN time between beats, so one missed or extra beat doesn't spoil it.
    """
    if not _has_pulse(ppg, rate_hz):
        return None   # only sensor noise: no finger, or it isn't touching the sensor
    beats = find_beats(ppg, rate_hz)
    if len(beats) < 3:
        return None
    gaps = [(b - a) / rate_hz for a, b in zip(beats, beats[1:])]
    if not _regular(gaps):
        return None   # real heartbeats come at a steady pace; random noise doesn't
    bpm = 60 / _median(gaps)
    if bpm < MIN_BPM or bpm > MAX_BPM:
        return None
    return round(bpm)


def spo2_percent(red, infrared):
    """Blood oxygen (%) from the MAX30102's red and infrared light, or None.

    "Ratio of ratios": R = (red pulse / red level) / (infrared pulse / infrared level).
    Oxygen-rich blood absorbs more infrared, so a smaller R means more oxygen.
    SpO2 ~ 110 - 25 * R is the usual approximation for these sensors (not calibrated!).
    """
    if not red or not infrared or len(red) != len(infrared):
        return None
    red_dc = sum(red) / len(red)
    ir_dc = sum(infrared) / len(infrared)
    red_ac = max(red) - min(red)
    ir_ac = max(infrared) - min(infrared)
    if red_dc <= 0 or ir_dc <= 0 or ir_ac == 0:
        return None   # no finger on the sensor
    ratio = (red_ac / red_dc) / (ir_ac / ir_dc)
    value = 110 - 25 * ratio
    if value < 70:
        return None   # not believable: the finger probably moved
    return round(min(value, 100.0), 1)
