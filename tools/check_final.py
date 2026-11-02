import paramiko

HOST, USER, PASS = "192.168.0.100", "pi", "raspberry"
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=USER, password=PASS, timeout=10)

# 忽略所有 numpy 警告, 直接查 HandDetector
cmd = "python3 -W ignore -c 'import warnings; warnings.filterwarnings(\"ignore\"); import numpy as np; print(\"numpy:\", np.__version__); import cv2; print(\"cv2:\", cv2.__version__); print(\"file:\", cv2.__file__); print(\"HandDetector:\", hasattr(cv2, \"HandDetector\")); print(\"HAND_CONNECTIONS:\", hasattr(cv2, \"HAND_CONNECTIONS\")); hd = cv2.HandDetector(); print(\"HandDetector() OK\")' 2>&1"
stdin, stdout, stderr = c.exec_command(cmd, timeout=15)
out = stdout.read().decode()
err = stderr.read().decode()
print("STDOUT:", out[:600])
print("STDERR:", err[:400])
c.close()
