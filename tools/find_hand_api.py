import paramiko

HOST, USER, PASS = "192.168.0.100", "pi", "raspberry"
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=USER, password=PASS, timeout=10)

# 查 cv2 里所有 hand/gesture/Hand 相关的属性
cmd = r"""python3 -c "
import cv2
print('=== cv2 top-level ===')
attrs = sorted([a for a in dir(cv2) if 'and' in a.lower() or 'esture' in a.lower()])
print(attrs)
print()
# 检查 cv2.HandDetector 可能的位置
for mod_name in ['cv2', 'cv2.HandDetector', 'cv2.hand', 'cv2.xfeatures2d', 'cv2.ximgproc']:
    try:
        mod = eval(mod_name)
        haves = [a for a in dir(mod) if 'and' in a.lower() or 'esture' in a.lower()]
        if haves:
            print(f'{mod_name}: {haves}')
    except:
        pass
print()
print('=== 检查 cv2.contrib ===')
try:
    import cv2.contrib
    print('cv2.contrib exists')
except ImportError:
    print('no cv2.contrib')
print()
print('=== pip show opencv-contrib ===')
" 2>&1"""
stdin, stdout, stderr = c.exec_command(cmd, timeout=15)
print(stdout.read().decode())

c.close()
