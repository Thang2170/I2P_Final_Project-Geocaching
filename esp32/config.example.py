# Copy this file to config.py ON THE ESP32 and fill it in. Never commit config.py:
# it holds your Wi-Fi password and your band's secret token.

WIFI_SSID = "your-phone-hotspot"     # a phone hotspot works well while walking
WIFI_PASSWORD = "your-hotspot-password"

# Where StepQuest runs, e.g. "https://YOUR_USERNAME.pythonanywhere.com" (see DEPLOY.md)
SERVER_URL = "https://YOUR_USERNAME.pythonanywhere.com"

# From the Health page: "Pair a new band" shows it once
DEVICE_TOKEN = "paste-the-token-here"

# Wiring (ESP32 pin numbers): both sensors share the same two I2C wires
I2C_SDA = 21
I2C_SCL = 22

# Only for the treasure box (box_main.py): shown ONCE on the Box page when you make the box
BOX_SECRET = "paste-the-box-secret-here"
