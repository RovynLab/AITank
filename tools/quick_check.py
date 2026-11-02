import paramiko

HOST, USER, PASS = "192.168.0.100", "pi", "raspberry"
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=USER, password=PASS, timeout=10)

cmd = "python3 -c 'import cv2; print(\"cv2:\", cv2.__version__); print(\"file:\", cv2.__file__); print(\"HandDetector:\", hasattr(cv2, \"HandDetector\"))' 2>&1"
stdin, stdout, stderr = c.exec_command(cmd, timeout=10)
print(stdout.read().decode()[:400])
err = stderr.read().decode()
if err: print("STDERR:", err[:300])

c.close()
