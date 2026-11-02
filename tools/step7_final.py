"""Fix getkey sudo path + re-run labs"""
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
    print(f">>> {cmd.replace(PASS, '***').strip()[:120]}")
    if out: print(out[:800])
    if err and "password" not in err.lower(): print(f"[ERR] {err[:400]}")
    print(f"  (exit={code})\n")
    return code

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, username=USER, password=PASS, timeout=10)

# 1. 检查 getkey 安装位置
print("--- Check getkey ---")
run(client, "pip3 show getkey 2>&1", timeout=10)
run(client, "python3 -c 'import getkey; print(getkey.__file__)' 2>&1", timeout=5)
run(client, f"echo '{PASS}' | sudo -S python3 -c 'import sys; print(\"\\n\".join(sys.path))' 2>&1", timeout=5)

# 2. 给 root 也装一遍 (--break-system-packages)
print("--- Install getkey for root (sudo pip3) ---")
run(client, f"echo '{PASS}' | sudo -S pip3 install --break-system-packages getkey", timeout=30)

# 3. 验证
print("--- Verify sudo import getkey ---")
run(client, f"echo '{PASS}' | sudo -S python3 -c 'import getkey; print(\"getkey OK\")'", timeout=5)

# 4. 跑 labs (sudo 方式)
print("\n========== LAB TESTS (sudo) ==========\n")

print("--- lab01_led_blink ---")
run(client, f"cd /home/pi/AITank && echo '{PASS}' | sudo -S timeout 5 python3 labs/lab01_led_blink.py 2>&1 || true", timeout=10)

print("--- lab02_motor_direction (2s) ---")
run(client, f"cd /home/pi/AITank && echo '{PASS}' | sudo -S timeout 3 python3 labs/lab02_motor_direction.py 2>&1 || true", timeout=10)

print("--- lab03_motor_pwm (2s) ---")
run(client, f"cd /home/pi/AITank && echo '{PASS}' | sudo -S timeout 3 python3 labs/lab03_motor_pwm.py 2>&1 || true", timeout=10)

print("--- lab05_wheel_test (init check) ---")
run(client, f"cd /home/pi/AITank && echo '{PASS}' | sudo -S timeout 3 python3 -c \"\nimport sys, os\n_here = os.path.join('.', 'labs')\nfor _u in range(3):\n    _d = os.path.join(_here, '..' * _u, 'deps')\n    if os.path.isdir(_d) and _d not in sys.path: sys.path.insert(0, _d)\nfrom Adafruit_MotorHAT import Adafruit_MotorHAT, Adafruit_DCMotor\nprint('lab05 imports OK')\n_mh = Adafruit_MotorHAT(addr=0x60)\n_mh.getMotor(1); _mh.getMotor(2); _mh.getMotor(3); _mh.getMotor(4)\nprint('M1-M4 init OK')\n\" 2>&1 || true", timeout=15)

print("--- lab10_ptz_control (imports only) ---")
run(client, f"cd /home/pi/AITank && echo '{PASS}' | sudo -S timeout 3 python3 -c \"\nimport sys, os\n_here = os.path.join('.', 'labs')\nfor _u in range(3):\n    _d = os.path.join(_here, '..' * _u, 'deps')\n    if os.path.isdir(_d) and _d not in sys.path: sys.path.insert(0, _d)\nfrom Adafruit_MotorHAT.Adafruit_PWM_Servo_Driver import PWM\nprint('lab10 imports OK')\npwm = PWM(address=0x60)\nprint('Servo PWM init OK')\n\" 2>&1 || true", timeout=15)

client.close()
print("\n=== DONE ===")
