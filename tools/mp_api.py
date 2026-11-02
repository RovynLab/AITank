"""查 mediapipe 1.2.0 的新 API 结构"""
import paramiko

HOST, USER, PASS = "192.168.0.100", "pi", "raspberry"
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=USER, password=PASS, timeout=10)

cmd = r"""python3 << 'PYEOF'
import mediapipe as mp
print("mediapipe version:", mp.__version__)
print()
# 顶层属性
attrs = [a for a in dir(mp) if not a.startswith('_')]
print("mp 顶层:", attrs[:30])
print()
# tasks
try:
    from mediapipe import tasks
    print("mp.tasks:", [a for a in dir(tasks) if not a.startswith('_')][:20])
    from mediapipe.tasks import python as mpt_python
    print("mp.tasks.python:", [a for a in dir(mpt_python) if not a.startswith('_')][:20])
    from mediapipe.tasks.python import vision
    print("mp.tasks.python.vision:", [a for a in dir(vision) if not a.startswith('_')][:30])
    # 找 hand landmarker
    haves = [a for a in dir(vision) if 'and' in a.lower() or 'andmark' in a.lower()]
    print("vision 里 hand 相关:", haves)
except ImportError as e:
    print("tasks 导入失败:", e)

print()
# 旧 solutions 还在吗?
if hasattr(mp, 'solutions'):
    print("mp.solutions 存在!")
    print("  mp.solutions.hands:", dir(mp.solutions.hands)[:20])
else:
    print("mp.solutions 已移除")

# 有没有官方示例?
print()
print("--- tasks.vision.HandsLandmarker 示例 ---")
try:
    from mediapipe.tasks.python.vision import HandLandmarker, HandLandmarkerOptions
    print("✅ HandLandmarker 可用")
except Exception as e:
    print("❌ HandLandmarker:", e)
PYEOF
"""
stdin, stdout, stderr = c.exec_command(cmd, timeout=15)
print(stdout.read().decode()[:1200])
err = stderr.read().decode()
if err: print("STDERR:", err[-500:])
c.close()
