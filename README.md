# RovynLab (若问) — Open-Source Educational Robotics Workshop

[English](./README.md) · [中文](./README.zh-CN.md)

An open-source robotics workshop where hardware meets Python — built for teaching, tinkering, and making things move.

Current projects: a mecanum AI car with pan-tilt camera + LLM dialogue, an OpenCV vision toolbox for color / face / gesture detection, a full Flask dashboard with Blockly visual programming. Next up: 6-DOF robotic arm with inverse kinematics.

Every project ships with progressive labs, self-contained code, and zero proprietary lock-in. No black boxes. If the robot does something, you can read the code that makes it happen — and modify it to make it yours.

---

## Hardware

### Mecanum AI Car 

| Module | Spec | Interface |
|--------|------|-----------|
| Mainboard | Raspberry Pi 4B 2GB | — |
| Motors | 4 × TT DC gear | Custom L9110S board |
| Pan-Tilt | 2 × PWM servo | PCA9685 CH0 (Pan) / CH1 (Tilt) |
| Camera | 720P USB | USB |
| OLED | SH1106 128×64 | I2C @ 0x3C |
| Driver board(Self-designed) | PCA9685 + L9110S | I2C @ 0x60 |

**PCA9685 channel mapping (follow physical wiring!):**
```
CH0 → Pan servo   (horizontal)
CH1 → Tilt servo  (vertical)
CH1 → Front Right motor
CH2 → Front Left  motor
CH3 → Rear Left   motor
CH4 → Rear Right  motor
I2C address → 0x60
```

---

## Quick Start

```bash
# 1. Enable I2C
sudo raspi-config nonint do_i2c 0
sudo reboot

# 2. Install dependencies (root-level for labs, petcar has its own)
pip3 install -r requirements.txt
pip3 install -r petcar/requirements.txt

# 3. Run individual labs (teaching, self-contained, 按顺序)
cd labs/
python3 lab01_led_blink.py          # LED blink
python3 lab02_motor_direction.py    # Motor direction
python3 lab06_mecanum_class.py      # Mecanum kinematics (class version)
python3 lab07_mecanum_global.py     # Mecanum kinematics (global function version)
python3 lab10_ptz_control.py       # Pan-tilt control
python3 lab12_gesture_hull.py      # OpenCV convex-hull gesture

# 4. Run integrated demos
cd demos/flask_web_control/
python3 app.py                     # Web control panel → http://<Pi-IP>:5000

cd demos/object_tracking/
python3 ball_track.py              # Color tracking + pan-tilt + chassis

# 5. Run the full AI PetCar (recommended)
python3 -m petcar.main --flask --port 5000
# Flask panel with video stream, LLM dialogue, PID tracking, Blockly blocks
# Add --voice for full ASR/TTS loop
```

---

## Repository Layout

```
RovynLab/
├── README.md
├── LICENSE
├── requirements.txt           # shared deps for labs/ and ai/
├── config.py                  # hardware constants (I2C addr / speed / direction)
│
├── petcar/                    # 🏠 Main integrated application
│   ├── main.py                # entry point (--flask / --voice / --mock)
│   ├── api/                   # Flask server + Blockly visual programming
│   ├── core/                  # LLM chat, PID tracker, mood engine, skills
│   ├── drivers/               # hardware abstraction (mecanum / ptz / camera / oled / asr / tts)
│   ├── blocks/                # Blockly runtime, compiler, example programs
│   ├── skills/                # skill system (move / ptz / face_detect / express / photo / alarm ...)
│   ├── services/              # whisper systemd unit
│   ├── docs/                  # detailed design docs + UI screenshots
│   └── requirements.txt
│
├── labs/                      # 🎓 Teaching experiments (12 progressive lessons)
│   ├── lab01_led_blink.py
│   ├── lab02_motor_direction.py
│   ├── lab03_motor_pwm.py
│   ├── lab04_pwm_servo.py
│   ├── lab05_wheel_test.py
│   ├── lab06_mecanum_class.py     # OOP version
│   ├── lab07_mecanum_global.py    # global function version (intentionally kept separate)
│   ├── lab08_kinematic.py
│   ├── lab09_joystick.py
│   ├── lab10_ptz_control.py
│   ├── lab11_servo_test.py
│   └── lab12_gesture_hull.py      # OpenCV convex-hull gesture detection
│
├── demos/                     # 🔧 Integrated demo projects
│   ├── flask_web_control/      # Vue + Flask web control panel
│   ├── object_tracking/        # pan-tilt + chassis + color tracking
│   ├── traffic_sign/           # SVM traffic sign classification
│   └── tflite_detect/          # TFLite SSD object detection
│
├── ai/                        # 👁️ OpenCV vision experiments
│   ├── ball_track_simple.py
│   ├── face_recognition.py
│   ├── finger.py               # original OpenCV hull version
│   └── finger_v2.py            # MediaPipe Hands version ★
│
├── aitank_menu/               # 📟 OLED boot menu (SH1106 + 5-key)
├── deps/                      # Adafruit_GPIO / MotorHAT / PureIO (vendored)
├── core/                      # (reserved) unified driver refactor
├── docs/                      # design docs, course plans, deployment guides
└── tests/                     # regression tests for petcar modules
```

### Design principles

- **labs/ stay self-contained.** Each lab imports vendored `deps/` via path injection — no `pip install adafruit-*`, no petcar dependency. Clone + run.
- **Teaching gradient is intentional.** lab06 (class) and lab07 (global) are both kept — function-first for beginners, OOP as a second step. Don't merge them.
- **petcar/ is the product.** It combines everything (drivers + LLM + dashboard + skills + Blockly) and sits on top of the same hardware that labs teach piece by piece.

---

## Roadmap

| Status | Project | Description |
|--------|---------|-------------|
| ✅ Done | Mecanum AI car | Pan-tilt + LLM dialogue + PID tracking + Blockly |
| ✅ Done | OpenCV vision stack | Color / face / MediaPipe gesture / TFLite object detection |
| ✅ Done | Flask dashboard | Video stream, 7-color recognition, PIDs, object detect, LLM chat, Blockly |
| ✅ Done | OLED boot menu | SH1106, 5-key navigation, WiFi manager, app launcher |
| 🚧 Next | 4-DOF robotic arm | Inverse kinematics + servo control + vision pick-and-place lab |
| 🚧 Next | IMU integration | 6-DOF IMU + dead reckoning + closed-loop odometry lessons |

---

## License

Custom non-commercial license — free for personal use, teaching, and research. Commercial use requires prior written authorization. See [LICENSE](./LICENSE) for full terms (中 / EN).
