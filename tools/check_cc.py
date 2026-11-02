import paramiko

HOST, USER, PASS = "192.168.0.100", "pi", "raspberry"
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=USER, password=PASS, timeout=10)

cmd = r"""python3 << 'EOF'
import cv2
print("cv2 version:", cv2.__version__)
print()
print("CascadeClassifier attr:", hasattr(cv2, "CascadeClassifier"))
print("CASCADE_CLASSIFIER: ", hasattr(cv2, "CASCADE_CLASSIFIER"))
# 看看有哪些 classifier 相关的
classifiers = [a for a in dir(cv2) if 'lass' in a or 'cascade' in a.lower()]
print("cascade related:", classifiers)
print()
# 看 opencv 5.0 face detection 可能在哪
for mod_name in ['cv2', 'cv2.data']:
    try:
        mod = eval(mod_name)
        attrs = [a for a in dir(mod) if 'face' in a.lower() or 'class' in a.lower()]
        if attrs:
            print(f"{mod_name}: {attrs}")
    except:
        pass
EOF
"""
stdin, stdout, stderr = c.exec_command(cmd, timeout=10)
print(stdout.read().decode()[:800])
err = stderr.read().decode()
if err: print("STDERR:", err[:400])
c.close()
