"""查新版 HandLandmarker + GestureRecognizer 用法, 以及模型文件位置"""
import paramiko

HOST, USER, PASS = "192.168.0.100", "pi", "raspberry"
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=USER, password=PASS, timeout=10)

# 先下载模型文件 (用 curl 下载 mediapipe 官方模型)
print("=== Step 1: 下载模型 ===")
models_dir = "/home/pi/AITank/models"
cmd = f"""mkdir -p {models_dir} && cd {models_dir} && \
curl -sL -o hand_landmarker.task "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task" && \
curl -sL -o gesture_recognizer.task "https://storage.googleapis.com/mediapipe-models/gesture_recognizer/gesture_recognizer/float16/1/gesture_recognizer.task" && \
ls -la *.task"""
stdin, stdout, stderr = c.exec_command(cmd, timeout=60)
out = stdout.read().decode(); err = stderr.read().decode()
print(out[:600])
if err: print("STDERR:", err[:300])

# 测试 HandLandmarker 基本用法 (没有摄像头, 跳过图片处理, 只验证创建)
print("\n=== Step 2: HandLandmarker 创建测试 ===")
cmd = f"""python3 << 'PYEOF'
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

base_options = python.BaseOptions(model_asset_path='/home/pi/AITank/models/hand_landmarker.task')
options = vision.HandLandmarkerOptions(
    base_options=base_options,
    num_hands=2,
    min_hand_detection_confidence=0.5,
    min_hand_presence_confidence=0.5,
    min_tracking_confidence=0.5,
)
detector = vision.HandLandmarker.create_from_options(options)
print("✅ HandLandmarker 创建成功:", detector)

# 测试 GestureRecognizer
base_options2 = python.BaseOptions(model_asset_path='/home/pi/AITank/models/gesture_recognizer.task')
options2 = vision.GestureRecognizerOptions(
    base_options=base_options2,
    running_mode=vision.RunningMode.IMAGE,
    num_hands=2,
)
recognizer = vision.GestureRecognizer.create_from_options(options2)
print("✅ GestureRecognizer 创建成功:", recognizer)

# 看 GestureRecognizerResult 结构
import inspect
sig = inspect.signature(recognizer.recognize)
print("recognize 方法签名:", sig)
PYEOF
"""
stdin, stdout, stderr = c.exec_command(cmd, timeout=15)
print(stdout.read().decode()[:800])
err = stderr.read().decode()
if err: print("STDERR:", err[-300:])

c.close()
