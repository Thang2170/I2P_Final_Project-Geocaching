"""StepQuest band: the program that runs on the ESP32 (MicroPython). Owner: A.

Every 20 ms it reads the accelerometer (steps) and the MAX30102's light samples (heart).
Every 5 s it works out heart rate and blood oxygen (health_math.py, the SAME file the
server's tests check) and stores one reading. Every minute it tries to upload the waiting
readings to StepQuest over Wi-Fi. No signal? It keeps them (up to about 2 hours) and sends
them later; "age_s" tells the server how long ago each one was measured.

Put these files on the ESP32 (Thonny: View > Files, right-click > Upload):
    main.py, health_math.py, max30102.py, mpu6050.py, config.py
"""

import gc
import time

import network
import urequests
from machine import I2C, Pin

import config
from health_math import StepCounter, heart_rate_bpm, spo2_percent
from max30102 import MAX30102
from mpu6050 import MPU6050

RATE_HZ = 50
READING_EVERY_MS = 5000
UPLOAD_EVERY_MS = 60000
PPG_WINDOW = RATE_HZ * 8          # the last 8 seconds of light samples
MAX_WAITING = 1500                # readings kept while offline (1500 x 5 s = about 2 hours)
FINGER_LEVEL = 50000              # infrared below this: no finger on the sensor


def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        wlan.connect(config.WIFI_SSID, config.WIFI_PASSWORD)  # keeps trying in the background
    return wlan


def upload(waiting, now_ms):
    """Send the waiting readings. Returns True if the server saved them."""
    body = {"readings": [{
        "age_s": time.ticks_diff(now_ms, r["t"]) // 1000,
        "hr": r["hr"], "spo2": r["spo2"], "steps": r["steps"],
    } for r in waiting]}
    try:
        answer = urequests.post(config.SERVER_URL + "/api/health/readings", json=body,
                                headers={"Authorization": "Bearer " + config.DEVICE_TOKEN})
        ok = answer.status_code == 201
        answer.close()
        return ok
    except OSError:
        return False   # no signal: try again next minute


def main():
    i2c = I2C(0, sda=Pin(config.I2C_SDA), scl=Pin(config.I2C_SCL), freq=400000)
    heart = MAX30102(i2c)
    motion = MPU6050(i2c)
    steps = StepCounter(RATE_HZ)
    wlan = connect_wifi()

    red, infrared = [], []
    waiting = []
    steps_at_last_reading = 0
    last_reading = last_upload = time.ticks_ms()

    while True:
        tick = time.ticks_ms()
        x, y, z = motion.acceleration_g()
        steps.add((x * x + y * y + z * z) ** 0.5)
        for r, ir in heart.read_samples():
            red.append(r)
            infrared.append(ir)
        del red[:-PPG_WINDOW], infrared[:-PPG_WINDOW]   # keep only the last 8 seconds

        now = time.ticks_ms()
        if time.ticks_diff(now, last_reading) >= READING_EVERY_MS:
            last_reading = now
            finger = infrared and sum(infrared) / len(infrared) > FINGER_LEVEL
            waiting.append({
                "t": now,
                "hr": heart_rate_bpm(infrared, RATE_HZ) if finger else None,
                "spo2": spo2_percent(red[-RATE_HZ * 5:], infrared[-RATE_HZ * 5:]) if finger else None,
                "steps": steps.steps - steps_at_last_reading,
            })
            steps_at_last_reading = steps.steps
            del waiting[:-MAX_WAITING]
            gc.collect()

        if waiting and time.ticks_diff(now, last_upload) >= UPLOAD_EVERY_MS:
            last_upload = now
            if wlan.isconnected() and upload(waiting, now):
                waiting = []
            elif not wlan.isconnected():
                wlan = connect_wifi()

        time.sleep_ms(max(0, 1000 // RATE_HZ - time.ticks_diff(time.ticks_ms(), tick)))


main()
