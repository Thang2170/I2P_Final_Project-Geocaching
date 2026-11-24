"""The ESP32 sensor drivers, tested on the PC with a pretend I2C bus (no hardware needed)."""

import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "esp32"))

import max30102  # noqa: E402
import mpu6050  # noqa: E402


class FakeI2C:
    """Pretends to be a chip: remembers writes, answers reads from a table."""

    def __init__(self, answers):
        self.answers = answers          # register -> bytes to return
        self.writes = []

    def writeto_mem(self, address, register, data):
        self.writes.append((address, register, bytes(data)))

    def readfrom_mem(self, address, register, count):
        return self.answers[register][:count]


class TestMPU6050(unittest.TestCase):
    def test_wakes_up_and_reads_g(self):
        # x = +0.5 g (8192), y = -0.25 g (-4096 = 0xF000), z = 1 g (16384)
        i2c = FakeI2C({mpu6050.WHO_AM_I: b"\x68",
                       mpu6050.ACCEL_XOUT_H: bytes([0x20, 0x00, 0xF0, 0x00, 0x40, 0x00])})
        sensor = mpu6050.MPU6050(i2c)
        self.assertIn((0x68, mpu6050.PWR_MGMT_1, b"\x00"), i2c.writes)
        self.assertEqual(sensor.acceleration_g(), (0.5, -0.25, 1.0))

    def test_missing_chip(self):
        with self.assertRaises(OSError):
            mpu6050.MPU6050(FakeI2C({mpu6050.WHO_AM_I: b"\x00"}))


class TestMAX30102(unittest.TestCase):
    def setUp(self):
        # MicroPython's time.sleep_ms doesn't exist on the PC: pretend it does
        patcher = patch.object(max30102, "time", SimpleNamespace(sleep_ms=lambda ms: None))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_starts_in_spo2_mode_and_reads_the_fifo(self):
        # Two samples waiting: (red 100000, ir 120000) and (red 70000, ir 262143 = the 18-bit maximum)
        def three(value):
            return bytes([(value >> 16) & 0xFF, (value >> 8) & 0xFF, value & 0xFF])
        fifo = three(100000) + three(120000) + three(70000) + three(262143)
        i2c = FakeI2C({max30102.PART_ID: b"\x15", max30102.FIFO_WR_PTR: b"\x07",
                       max30102.FIFO_RD_PTR: b"\x05", max30102.FIFO_DATA: fifo})
        sensor = max30102.MAX30102(i2c)
        self.assertEqual(i2c.writes[-1], (0x57, max30102.MODE_CONFIG, b"\x03"))  # SpO2 mode last
        self.assertEqual(sensor.read_samples(), [(100000, 120000), (70000, 262143)])

    def test_fifo_pointer_wraps_around(self):
        # The write pointer went past 31 back to 1 while the read pointer is at 31: 2 samples waiting
        i2c = FakeI2C({max30102.PART_ID: b"\x15", max30102.FIFO_WR_PTR: b"\x01",
                       max30102.FIFO_RD_PTR: b"\x1f", max30102.FIFO_DATA: b"\x00" * 12})
        self.assertEqual(len(max30102.MAX30102(i2c).read_samples()), 2)

    def test_missing_chip(self):
        with self.assertRaises(OSError):
            max30102.MAX30102(FakeI2C({max30102.PART_ID: b"\x00"}))


if __name__ == "__main__":
    unittest.main()
