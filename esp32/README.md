# StepQuest band (ESP32)

A small wrist or finger band that measures your **steps, heart rate and blood oxygen (SpO2)**
while you walk, uploads it to StepQuest, and gets a coach-style summary afterwards (from a free
AI running on your own PC, or from StepQuest's Python rules).

> These are estimates from cheap sensors. StepQuest is a walking game, not a medical device.

The device code is **MicroPython**, so the band runs Python too. The maths (`health_math.py`) is
the same file the PC tests check (`tests/test_health_math.py`), using simulated sensor signals.

## Shopping list

| Part | Why | Notes |
|---|---|---|
| **ESP32 DevKit** (ESP32-WROOM-32 or ESP32-S3) | The brain: Wi-Fi to upload | Any ESP32 that MicroPython supports |
| **MAX30102** module | Heart rate + SpO2 (red/infrared light through your fingertip or wrist) | The purple "GY-MAX30102" boards are fine |
| **MPU6050** module (GY-521) | Accelerometer for counting steps | BMI160 or LSM6DS3 are more accurate (need a different small driver) |
| **3.7 V LiPo battery**, 500–1000 mAh + **TP4056 USB-C charger board** (with protection) | Power while walking | Or simply a small USB power bank |
| Breadboard / perfboard, jumper wires, a strap or 3D-printed case | Wearing it | Keep the MAX30102 pressed lightly against the skin |
| Optional: **MAX30205** (skin temperature), **SSD1306 0.96" OLED** | Extra metric / a small screen | Not used by the code yet |

**VO2max:** no cheap sensor measures it (that needs a lab breathing mask). StepQuest *estimates*
it from your heart rate (Uth formula: 15.3 x max HR / resting HR). Enter your resting heart rate
on the Health page for a better estimate.

## Wiring (both sensors share the same two I2C wires)

| Sensor pin | ESP32 pin |
|---|---|
| VIN / VCC | 3V3 |
| GND | GND |
| SDA | GPIO 21 |
| SCL | GPIO 22 |

(Change `I2C_SDA` / `I2C_SCL` in `config.py` if you use other pins. On an ESP32-S3 pick any two free GPIOs.)

## Setting it up

1. **Put MicroPython on the ESP32:** download the firmware for your board from micropython.org,
   then flash it, for example with Thonny (*Tools > Options > Interpreter > Install or update MicroPython*).
2. **Pair the band:** on StepQuest open **Health → Pair a new band**. Copy the token (it is shown once).
3. **Make `config.py`:** copy `config.example.py` to `config.py` and fill in your phone hotspot's
   Wi-Fi, the StepQuest address and the token. `config.py` is in `.gitignore`: never commit it.
4. **Upload these files to the ESP32** (Thonny: *View > Files*, right-click > *Upload to /*):
   `main.py`, `health_math.py`, `max30102.py`, `mpu6050.py`, `config.py`
5. Reset the board. It starts measuring; with Wi-Fi it uploads every minute. Without Wi-Fi it keeps
   about 2 hours of readings and sends them when the hotspot is back.

## No hardware yet? Simulate a walk

```bash
python esp32/simulate_walk.py --server http://127.0.0.1:5000 --token YOUR_TOKEN
```

It uploads a realistic 20-minute walk (warm-up, a hill, cool-down), so the Health page has data.

## The AI coach (free, local)

The Health page's **Ask the AI coach** button uses **Ollama** on your PC (installed in `D:\Ollama`,
model `qwen2.5:7b`, about 4.7 GB on `D:\Ollama\models`). Your health data never leaves your PC.
If Ollama isn't running (for example on PythonAnywhere), the page uses StepQuest's Python rules.
Settings: `OLLAMA_URL` (default `http://127.0.0.1:11434`) and `OLLAMA_MODEL` (default `qwen2.5:7b`).

## Honest status

- The maths and both drivers are tested on the PC with simulated signals and a pretend I2C bus.
- **It has not run on a real ESP32 yet** (no hardware tonight). Expect to tune `STEP_HIGH_G` /
  `STEP_LOW_G` (steps) and the LED current in `max30102.py` once it's on your wrist.

## The treasure box (a second use for an ESP32, owner: B)

The same ESP32 can be a **treasure box** instead of a band: it sits at a treasure and shows a
6-number code that changes every 30 seconds. Players type it on StepQuest's Box page to prove
they were really there (a faked GPS cannot get the code). It is the same maths as phone
authenticator apps; `box_math.py` is checked against the server by `tests/test_play_rules.py`.

1. On StepQuest, open **Menu > Treasure boxes** and make a box for one of your treasures.
   Copy the secret it shows (it is shown only once).
2. In `config.py`, set `BOX_SECRET`, `WIFI_SSID` and `WIFI_PASSWORD` (Wi-Fi is only used to set the clock).
3. Upload `box_main.py` (renamed to `main.py`), `box_math.py` and `config.py`.
   With a 128x64 SSD1306 OLED (about NT$100, on the I2C pins) also upload MicroPython's `ssd1306.py`;
   without one, the code is printed in Thonny's Shell.
4. No ESP32 at hand? `python simulate_box.py "Gate box"` on the laptop shows the same codes.
