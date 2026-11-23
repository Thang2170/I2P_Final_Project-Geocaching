"""Tiny MicroPython driver for the MPU6050 accelerometer (I2C address 0x68).

Only the accelerometer, at +-2 g (16384 steps per g). Register numbers from the datasheet.
"""

ADDRESS = 0x68
PWR_MGMT_1, ACCEL_CONFIG, ACCEL_XOUT_H, WHO_AM_I = 0x6B, 0x1C, 0x3B, 0x75
STEPS_PER_G = 16384


def _signed(high, low):
    value = (high << 8) | low
    return value - 65536 if value > 32767 else value


class MPU6050:
    def __init__(self, i2c):
        self.i2c = i2c
        if self.i2c.readfrom_mem(ADDRESS, WHO_AM_I, 1)[0] not in (0x68, 0x70, 0x72):
            raise OSError("MPU6050 not found: check the wires (SDA, SCL, 3.3V, GND)")
        self.i2c.writeto_mem(ADDRESS, PWR_MGMT_1, b"\x00")    # wake up (it starts asleep)
        self.i2c.writeto_mem(ADDRESS, ACCEL_CONFIG, b"\x00")  # +-2 g: walking never needs more

    def acceleration_g(self):
        """(x, y, z) in g. Lying still on a table: about (0, 0, 1)."""
        d = self.i2c.readfrom_mem(ADDRESS, ACCEL_XOUT_H, 6)
        return (_signed(d[0], d[1]) / STEPS_PER_G, _signed(d[2], d[3]) / STEPS_PER_G,
                _signed(d[4], d[5]) / STEPS_PER_G)
