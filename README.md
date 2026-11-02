# ============================================================================
# AI Tank —— 麦轮四驱 AI 小车 课程代码
# ============================================================================

基于树莓派 4B + 自研 PCA9685 驱动板的 AI 教育机器人。

## 硬件

| 模块 | 型号 | 接口 |
|------|------|------|
| 主控 | 树莓派 4B 2GB | - |
| 底盘电机 | 4 × TT 直流减速电机 | 自研板 (L9110S) |
| 云台 | 2 × PWM 舵机 | PCA9685 CH0/CH1 |
| 摄像头 | 720P USB | USB |
| 驱动板 | 自研 (PCA9685 + L9110S) | I2C @ 0x60 |

**PCA9685 电机编号映射 (重要！按实物接线)**:
```
CH1 → 前右电机  (Front Right)
CH2 → 前左电机  (Front Left)
CH3 → 后左电机  (Tail  Left)
CH4 → 后右电机  (Tail  Right)
CH0 → 水平舵机  (云台 Pan)
CH1 → 垂直舵机  (云台 Tilt)
I2C 地址 → 0x60
```

## 快速开始

```bash
# 1. 启用 I2C
sudo raspi-config nonint do_i2c 0
sudo reboot

# 2. 装依赖
pip3 install -r requirements.txt

# 3. 跑实验 (按顺序)
cd labs/
python3 lab01_led_blink.py        # LED 闪烁
python3 lab02_motor_direction.py  # 电机方向
python3 lab06_mecanum_class.py    # 麦轮运动
python3 lab10_ptz_control.py     # 云台控制

# 4. 跑综合实验
cd demos/flask_web_control/
python3 app.py                    # 浏览器访问 http://<树莓派IP>:5000

cd demos/object_tracking/
python3 ball_track.py             # 颜色目标追踪 + 云台 + 底盘

# 5. AI 实验
cd ai/
python3 ball_track_simple.py      # OpenCV 颜色追踪
python3 face_recognition.py       # Haar 人脸检测
python3 finger_v2.py              # MediaPipe 手势识别 ★推荐
```

## 目录结构

```
AITank/
├── .gitignore
├── README.md
├── LICENSE
├── requirements.txt        ← 一份完整依赖
├── config.py               ← 硬件配置 (I2C 地址 / 速度 / 方向)
│
├── core/                   ← (预留) 重构后的统一驱动层
├── deps/                   ← Adafruit_GPIO / Adafruit_PureIO 依赖
│
├── labs/                   ← 教学实验 (按序号排列)
│   ├── lab01_led_blink.py
│   ├── lab02_motor_direction.py
│   ├── lab03_motor_pwm.py
│   ├── lab04_pwm_servo.py
│   ├── lab05_wheel_test.py
│   ├── lab06_mecanum_class.py
│   ├── lab07_mecanum_global.py
│   ├── lab08_kinematic.py
│   ├── lab09_joystick.py
│   ├── lab10_ptz_control.py
│   └── lab11_servo_test.py
│
├── demos/                  ← 综合实验
│   ├── flask_web_control/  ← Flask Web 控制 + 视频流
│   ├── object_tracking/    ← 云台 + 底盘 + 颜色追踪
│   ├── traffic_sign/       ← SVM 交通标志识别
│   └── tflite_detect/      ← TensorFlow Lite 目标检测
│
├── ai/                     ← AI 视觉实验
│   ├── ball_track_simple.py
│   ├── face_recognition.py
│   ├── finger.py           ← 原 OpenCV 凸包缺陷版
│   ├── finger_v2.py        ← MediaPipe Hands 新版 ★
│   └── haarcascade_*.xml
│
├── student_api/            ← 学生编程接口 (AI-PetCar 升级)
└── docs/                   ← 升级方案 / 优化建议
```

## 版本历史

| 版本 | 说明 |
|------|------|
| v4 (当前) | 基于 v4 课程代码整理，清理冗余、规范目录 |
| v3 | 历史版本，保留在 archive/ 或 release 附件 |

## License

MIT — 教学使用自由。
