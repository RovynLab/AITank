"""Quick servo + full lab test"""
import paramiko

HOST, USER, PASS = "192.168.0.100", "pi", "raspberry"

def run(client, cmd, timeout=30):
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    if "sudo -S" in cmd:
        stdin.write(PASS + "\n")
        stdin.flush()
    out = stdout.read().decode(errors="replace").strip()
    err = stderr.read().decode(errors="replace").strip()
    code = stdout.channel.recv_exit_status()
    print(f">>> {cmd.replace(PASS, '***').strip()[:100]}")
    if out: print(out[:600])
    if err and "password" not in err.lower(): print(f"[ERR] {err[:300]}")
    print(f"  (exit={code})\n")
    return code

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, username=USER, password=PASS, timeout=10)

# Test servo with correct PWM path
servo_test = r'''
import sys, os, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'deps'))
# 也用自动搜索方式
_here = os.path.dirname(os.path.abspath(__file__))
for _up in range(5):
    _d = os.path.join(_here, '..' * _up, 'deps')
    if os.path.isdir(_d):
        if _d not in sys.path: sys.path.insert(0, _d)
        break

from Adafruit_MotorHAT import Adafruit_MotorHAT

print("=== Servo Test ===")
mh = Adafruit_MotorHAT(addr=0x60)
pwm = mh._pwm  # MotorHAT 的 PWM 对象
pwm.setPWMFreq(60)

# 舵机通道: P0 = pan (水平), P1 = tilt (垂直)
def set_servo(channel, deg):
    pulse = int(102 + (deg / 180.0) * 408)  # 0.5ms-2.5ms PWM
    pwm.setPWM(channel, 0, pulse)
    print(f"  Channel P{channel} → {deg}° (pulse={pulse})")

print("\nP0 (Pan) sweep:")
set_servo(0, 0);   time.sleep(0.5)
set_servo(0, 90);  time.sleep(0.5)
set_servo(0, 180); time.sleep(0.5)
set_servo(0, 90);  time.sleep(0.5)

print("\nP1 (Tilt) sweep:")
set_servo(1, 0);   time.sleep(0.5)
set_servo(1, 90);  time.sleep(0.5)
set_servo(1, 180); time.sleep(0.5)
set_servo(1, 90);  time.sleep(0.5)

# 关闭 PWM
pwm.setPWM(0, 0, 0)
pwm.setPWM(1, 0, 0)
print("\n✅ Servo test done!")
'''

sftp = client.open_sftp()
with sftp.open("/home/pi/AITank/servo_test.py", "w") as f:
    f.write(servo_test)
sftp.close()
run(client, f"cd /home/pi/AITank && echo '{PASS}' | sudo -S timeout 15 python3 servo_test.py", timeout=25)

# Run official labs
print("\n\n========== OFFICIAL LAB TESTS ==========\n")

print("--- lab01_led_blink ---")
run(client, f"cd /home/pi/AITank && echo '{PASS}' | sudo -S timeout 5 python3 labs/lab01_led_blink.py 2>&1 || true", timeout=10)

print("--- lab05_wheel_test (stop after 3s) ---")
run(client, f"cd /home/pi/AITank && echo '{PASS}' | sudo -S timeout 4 python3 labs/lab05_wheel_test.py 2>&1 || true", timeout=10)

print("--- lab06_mecanum_class (just init, run 3s) ---")
run(client, f"cd /home/pi/AITank && echo '{PASS}' | sudo -S timeout 4 python3 -c \"\nimport sys, os\nsys.path.insert(0, 'deps')\nfor _u in range(3):\n    _d = os.path.join('.', '..' * _u, 'deps')\n    if os.path.isdir(_d) and _d not in sys.path: sys.path.insert(0, _d)\nfrom labs.lab06_mecanum_class import MecanumChasis\nmc = MecanumChasis()\nprint('MecanumChasis init OK')\nmc.run('forward')\nimport time; time.sleep(1)\nmc.run('stop')\nprint('OK')\n\" 2>&1 || true", timeout=15)

print("--- lab10_ptz_control ---")
run(client, f"cd /home/pi/AITank && echo '{PASS}' | sudo -S timeout 10 python3 -c \"\nimport sys, os\nsys.path.insert(0, 'deps')\nfor _u in range(3):\n    _d = os.path.join('.', '..' * _u, 'deps')\n    if os.path.isdir(_d) and _d not in sys.path: sys.path.insert(0, _d)\nfrom labs.lab10_ptz_control import PTZ\nimport time\nptz = PTZ()\nprint('PTZ init OK')\nptz.pan(90); time.sleep(0.5)\nptz.tilt(45); time.sleep(0.5)\nptz.pan(0);   time.sleep(0.5)\nptz.tilt(0);  time.sleep(0.5)\nptz.close()\nprint('PTZ sweep OK')\n\" 2>&1 || true", timeout=20)

client.close()
print("\n=== ALL TESTS DONE ===")
