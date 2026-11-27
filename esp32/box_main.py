"""StepQuest treasure box: the ESP32 shows a 6-number code that changes every 30 seconds. Owner: B.

Players type the code on the Box page to prove they were really at the treasure. The server
works out the same code from the same secret (box_code.py), so the box never needs the internet
after it has set its clock once.

Put these files on the ESP32 (Thonny: View > Files, right-click > Upload):
    box_main.py (renamed to main.py), box_math.py, config.py
and, if you have the small OLED screen (SSD1306, 128x64, on the same I2C pins), ssd1306.py from
MicroPython's drivers. Without a screen it prints the code to Thonny's Shell instead.

config.py needs (see config.example.py):
    WIFI_SSID, WIFI_PASSWORD   only to set the clock at start-up (from the internet time servers)
    BOX_SECRET                 shown ONCE on the Box page when you make the box
    I2C_SDA, I2C_SCL           the screen's pins
"""

import time

import framebuf
import network
import ntptime
from machine import I2C, Pin

import config
from box_math import UNIX_FROM_2000, code_at, seconds_left

EPOCH_OFFSET = UNIX_FROM_2000 if time.gmtime(0)[0] == 2000 else 0  # some boards count from 2000


def set_clock():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.connect(config.WIFI_SSID, config.WIFI_PASSWORD)
    for _ in range(40):  # up to 20 seconds
        if wlan.isconnected():
            break
        time.sleep(0.5)
    for _ in range(5):
        try:
            ntptime.settime()  # UTC, which is what the codes use
            return True
        except OSError:
            time.sleep(1)
    return False


def open_screen():
    try:
        import ssd1306
        i2c = I2C(0, sda=Pin(config.I2C_SDA), scl=Pin(config.I2C_SCL), freq=400000)
        return ssd1306.SSD1306_I2C(128, 64, i2c)
    except (ImportError, OSError):
        return None  # no screen: print instead


def show(screen, code, left):
    if screen is None:
        print("STEPQUEST BOX  ", code[:3], code[3:], "  ", left, "s")
        return
    screen.fill(0)
    screen.text("STEPQUEST BOX", 12, 0)
    # the code twice as big: draw each 8x8 letter into a 2x2 block
    for i, digit in enumerate(code[:3] + " " + code[3:]):
        x0 = 4 + i * 17
        tiny = bytearray(8)
        letter = framebuf.FrameBuffer(tiny, 8, 8, framebuf.MONO_HLSB)
        letter.fill(0)
        letter.text(digit, 0, 0)
        for y in range(8):
            for x in range(8):
                if letter.pixel(x, y):
                    screen.fill_rect(x0 + x * 2, 22 + y * 2, 2, 2, 1)
    screen.fill_rect(4, 54, (120 * left) // 30, 6, 1)  # time left for this code
    screen.show()


def main():
    screen = open_screen()
    if not set_clock():
        print("Could not set the clock: check WIFI_SSID / WIFI_PASSWORD. The codes will be wrong.")
    last = None
    while True:
        now = time.time() + EPOCH_OFFSET
        state = (code_at(config.BOX_SECRET, now), seconds_left(now))
        if state != last:
            show(screen, *state)
            last = state
        time.sleep(0.2)


main()
