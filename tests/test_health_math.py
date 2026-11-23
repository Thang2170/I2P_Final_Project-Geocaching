"""The ESP32's health maths, tested on the PC with made-up sensor signals (no hardware needed)."""

import math
import os
import random
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "esp32"))

from health_math import (StepCounter, find_beats, heart_rate_bpm, magnitude_g,  # noqa: E402
                         spo2_percent)

RATE = 50  # samples per second, like the ESP32 firmware


def walking_signal(steps_per_second, seconds, noise=0.03, seed=1):
    """Acceleration in g while walking: 1 g plus a bump of ~0.3 g at every step, plus shaking."""
    rng = random.Random(seed)
    return [1.0 + 0.3 * max(0.0, math.sin(2 * math.pi * steps_per_second * i / RATE)) + rng.uniform(-noise, noise)
            for i in range(int(seconds * RATE))]


def ppg_signal(bpm, seconds, level=50000, pulse=800, seed=2):
    """A PPG light signal: a steady level, a slow drift (breathing) and one pulse per heartbeat."""
    rng = random.Random(seed)
    beat_hz = bpm / 60
    return [level + 300 * math.sin(2 * math.pi * 0.25 * i / RATE)
            + pulse * max(0.0, math.sin(2 * math.pi * beat_hz * i / RATE)) ** 3
            + rng.uniform(-40, 40) for i in range(int(seconds * RATE))]


class TestSteps(unittest.TestCase):
    def count(self, samples):
        counter = StepCounter(RATE)
        for g in samples:
            counter.add(g)
        return counter.steps

    def test_counts_walking_steps(self):
        # 2 steps a second for 30 seconds = 60 steps (a normal walking pace)
        self.assertAlmostEqual(self.count(walking_signal(2.0, 30)), 60, delta=3)

    def test_standing_still_counts_nothing(self):
        self.assertEqual(self.count([1.0 + random.Random(3).uniform(-0.03, 0.03) for _ in range(RATE * 20)]), 0)

    def test_never_more_than_4_steps_a_second(self):
        self.assertLessEqual(self.count(walking_signal(8.0, 10, noise=0)), 41)

    def test_magnitude(self):
        self.assertAlmostEqual(magnitude_g(0, 0, 9.81), 1.0)
        self.assertAlmostEqual(magnitude_g(3, 4, 0), 5 / 9.81)


class TestHeartRate(unittest.TestCase):
    def test_resting_and_walking_heart_rates(self):
        for bpm in (60, 75, 110, 150):
            with self.subTest(bpm=bpm):
                self.assertAlmostEqual(heart_rate_bpm(ppg_signal(bpm, 10), RATE), bpm, delta=4)

    def test_beats_are_found(self):
        self.assertAlmostEqual(len(find_beats(ppg_signal(72, 10), RATE)), 12, delta=2)

    def test_no_finger_gives_none(self):
        # Only sensor noise (no pulse at all): never a heart rate, whatever the noise looks like
        for seed in range(20):
            with self.subTest(seed=seed):
                rng = random.Random(seed)
                flat = [50000 + rng.uniform(-5, 5) for _ in range(RATE * 10)]
                self.assertIsNone(heart_rate_bpm(flat, RATE))
        self.assertIsNone(heart_rate_bpm([1, 2, 3], RATE))  # too short

    def test_irregular_bumps_are_not_a_heartbeat(self):
        rng = random.Random(9)
        bumps = [50000 + (900 if rng.random() < 0.04 else 0) for _ in range(RATE * 10)]
        self.assertIsNone(heart_rate_bpm(bumps, RATE))


class TestSpO2(unittest.TestCase):
    def test_healthy_reading(self):
        # infrared pulses relatively stronger than red -> small R -> high oxygen
        red = [40000 + 200 * math.sin(i / 5) for i in range(500)]
        ir = [50000 + 600 * math.sin(i / 5) for i in range(500)]
        value = spo2_percent(red, ir)
        self.assertTrue(95 <= value <= 100, value)

    def test_impossible_or_missing_readings(self):
        self.assertIsNone(spo2_percent([], []))
        self.assertIsNone(spo2_percent([1, 2], [1]))
        self.assertIsNone(spo2_percent([0, 0, 0], [0, 0, 0]))
        red = [40000 + 3000 * math.sin(i / 5) for i in range(500)]   # red pulses far too strong
        ir = [50000 + 100 * math.sin(i / 5) for i in range(500)]
        self.assertIsNone(spo2_percent(red, ir))


if __name__ == "__main__":
    unittest.main()
