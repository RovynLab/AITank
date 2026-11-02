import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

models_dir = "/home/pi/AITank/models"

# HandLandmarker
base = python.BaseOptions(model_asset_path=f'{models_dir}/hand_landmarker.task')
opt = vision.HandLandmarkerOptions(base_options=base, num_hands=2)
detector = vision.HandLandmarker.create_from_options(opt)
print('✅ HandLandmarker OK')

# GestureRecognizer
base2 = python.BaseOptions(model_asset_path=f'{models_dir}/gesture_recognizer.task')
opt2 = vision.GestureRecognizerOptions(base_options=base2, num_hands=2)
rec = vision.GestureRecognizer.create_from_options(opt2)
print('✅ GestureRecognizer OK')

# API 结构探测
print('\n--- API 结构 ---')
print('RunningMode:', [x for x in dir(vision.RunningMode) if not x.startswith('_')])
print('HandLandmarkerResult:', [x for x in dir(vision.HandLandmarkerResult) if not x.startswith('_')])
print('GestureRecognizerResult:', [x for x in dir(vision.GestureRecognizerResult) if not x.startswith('_')])
print('Category:', [x for x in dir(vision.Category) if not x.startswith('_')])
print('NormalizedLandmark:', [x for x in dir(mp.components.landmark.NormalizedLandmark) if not x.startswith('_')])

# 测试 draw 相关工具
print('\n--- 绘制工具 ---')
print('HAND_CONNECTIONS:', type(mp.tasks.vision.HandLandmarksConnections.HAND_LANDMARKS).__name__)
print(dir(mp.tasks.vision.HandLandmarksConnections))
