import paramiko

HOST, USER, PASS = "192.168.0.100", "pi", "raspberry"
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=USER, password=PASS, timeout=10)

models_dir = "/home/pi/AITank/models"

# 创建 HandLandmarker + GestureRecognizer
code = f"""
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

base = python.BaseOptions(model_asset_path='{models_dir}/hand_landmarker.task')
opt = vision.HandLandmarkerOptions(base_options=base, num_hands=2)
detector = vision.HandLandmarker.create_from_options(opt)
print('✅ HandLandmarker OK')

base2 = python.BaseOptions(model_asset_path='{models_dir}/gesture_recognizer.task')
opt2 = vision.GestureRecognizerOptions(base_options=base2, num_hands=2)
rec = vision.GestureRecognizer.create_from_options(opt2)
print('✅ GestureRecognizer OK')

# 看看有哪些常量
print('RunningMode:', [x for x in dir(vision.RunningMode) if not x.startswith('_')])
print()
print('HandLandmarkerResult attrs:', [x for x in dir(vision.HandLandmarkerResult) if not x.startswith('_')])
print('Handedness attrs:', [x for x in dir(vision.Handedness) if not x.startswith('_')])
print('GestureRecognizerResult attrs:', [x for x in dir(vision.GestureRecognizerResult) if not x.startswith('_')])
print('Category attrs:', [x for x in dir(vision.Category) if not x.startswith('_')])
print('NormalizedLandmark attrs:', [x for x in dir(mp.components.landmark.NormalizedLandmark) if not x.startswith('_')])
"""
cmd = f"python3 -c {repr(code)} 2>&1"
stdin, stdout, stderr = c.exec_command(cmd, timeout=15)
print(stdout.read().decode()[:1000])
err = stderr.read().decode()
if err: print("STDERR:", err[-400:])
c.close()
