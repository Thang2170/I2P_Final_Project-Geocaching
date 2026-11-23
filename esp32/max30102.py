"""Tiny MicroPython driver for the MAX30102 heart-rate / SpO2 sensor (I2C address 0x57).

Only what StepQuest needs: start it in SpO2 mode at 50 samples a second and read the red
and infrared light samples waiting in its FIFO (a small queue inside the chip).
Register numbers are from the MAX30102 datasheet.
"""

import time

ADDRESS = 0x57
FIFO_WR_PTR, FIFO_OVF, FIFO_RD_PTR, FIFO_DATA = 0x04, 0x05, 0x06, 0x07
FIFO_CONFIG, MODE_CONFIG, SPO2_CONFIG = 0x08, 0x09, 0x0A
LED_RED, LED_IR = 0x0C, 0x0D
PART_ID = 0xFF


class MAX30102:
    def __init__(self, i2c, led_current=0x24):
        self.i2c = i2c
        if self._read(PART_ID, 1)[0] != 0x15:
            raise OSError("MAX30102 not found: check the wires (SDA, SCL, 3.3V, GND)")
        self._write(MODE_CONFIG, 0x40)          # reset
        time.sleep_ms(100)
        self._write(FIFO_CONFIG, 0x5F)          # average 4 samples, roll over when full
        self._write(SPO2_CONFIG, 0x2B)          # 4096 nA range, 200 Hz (/4 average = 50 Hz), 411 us pulses
        self._write(LED_RED, led_current)       # about 7 mA: enough through a fingertip
        self._write(LED_IR, led_current)
        for register in (FIFO_WR_PTR, FIFO_OVF, FIFO_RD_PTR):
            self._write(register, 0)
        self._write(MODE_CONFIG, 0x03)          # SpO2 mode: red + infrared

    def _write(self, register, value):
        self.i2c.writeto_mem(ADDRESS, register, bytes([value]))

    def _read(self, register, count):
        return self.i2c.readfrom_mem(ADDRESS, register, count)

    def read_samples(self):
        """Every (red, infrared) sample waiting in the FIFO, oldest first."""
        write_ptr = self._read(FIFO_WR_PTR, 1)[0]
        read_ptr = self._read(FIFO_RD_PTR, 1)[0]
        waiting = (write_ptr - read_ptr) & 0x1F
        samples = []
        if waiting:
            data = self._read(FIFO_DATA, waiting * 6)   # 3 bytes red + 3 bytes infrared each
            for i in range(waiting):
                b = data[i * 6:i * 6 + 6]
                red = ((b[0] << 16) | (b[1] << 8) | b[2]) & 0x3FFFF
                infrared = ((b[3] << 16) | (b[4] << 8) | b[5]) & 0x3FFFF
                samples.append((red, infrared))
        return samples
