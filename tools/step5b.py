"""Redeploy + smoke test — Platform.py fix for trixie"""
import paramiko, tarfile, os, io, sys

HOST, USER, PASS = "192.168.0.100", "pi", "raspberry"
LOCAL = r"e:\work\AITank"
REMOTE = "/home/pi"

def run(client, cmd, timeout=30):
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    if "sudo -S" in cmd:
        stdin.write(PASS + "\n")
        stdin.flush()
    out = stdout.read().decode(errors="replace").strip()
    err = stderr.read().decode(errors="replace").strip()
    code = stdout.channel.recv_exit_status()
    s = cmd.replace(PASS, "***").strip()[:120]
    print(f">>> {s}")
    if out: print(out[:800])
    if err and "password" not in err.lower(): print(f"[ERR] {err[:400]}")
    print(f"  (exit={code})\n")
    return code, out, err

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, username=USER, password=PASS, timeout=10)
print("=== CONNECTED ===\n")

# 1. 彻底清理 (sudo 删 root 权限的 pyc)
run(client, f"echo '{PASS}' | sudo -S rm -rf {REMOTE}/AITank {REMOTE}/aitank.tar.gz", timeout=15)

# 2. 打包推送
exclude = {".git", "__pycache__", ".venv", "tools", ".gitignore", "LICENSE", "README.md", "docs"}
buf = io.BytesIO()
with tarfile.open(fileobj=buf, mode="w:gz") as tar:
    for item in os.listdir(LOCAL):
        if item in exclude:
            continue
        tar.add(os.path.join(LOCAL, item), arcname=f"AITank/{item}")
buf.seek(0)
print(f"Archive size: {buf.tell()/(1024*1024):.1f} MB")
sftp = client.open_sftp()
sftp.putfo(buf, f"{REMOTE}/aitank.tar.gz")
sftp.close()

# 3. 解压
run(client, f"cd {REMOTE} && tar xzf aitank.tar.gz && rm aitank.tar.gz")

# 4. 验证 Platform.py 修复生效
print("--- Platform detection test ---")
check_cmd = f"""cd {REMOTE}/AITank && echo '{PASS}' | sudo -S python3 -c "
import sys; sys.path.insert(0, 'deps')
from Adafruit_GPIO import Platform
from Adafruit_GPIO.I2C import get_default_bus
print('platform_detect =', Platform.platform_detect(), '(expect 1)')
print('pi_version =', Platform.pi_version(), '(expect 3)')
print('pi_revision =', Platform.pi_revision(), '(expect 2)')
print('default I2C bus =', get_default_bus(), '(expect 1)')
"
"""
run(client, check_cmd, timeout=15)

# 5. 跑冒烟测试
print("=== SMOKE TEST ===")
smoke = r'''
import sys, os, time
_here = os.path.dirname(os.path.abspath(__file__))
for _up in range(5):
    _d = os.path.join(_here, '..' * _up, 'deps')
    if os.path.isdir(_d):
        if _d not in sys.path: sys.path.insert(0, _d)
        break

print("=" * 55)
print("  AITank Hardware Smoke Test")
print("=" * 55)
errors = 0

try:
    from Adafruit_MotorHAT import Adafruit_MotorHAT, Adafruit_DCMotor
    from Adafruit_MotorHAT.Adafruit_PWM_Servo_Driver import PWM
    print("[OK] All imports OK")
except Exception as e:
    print(f"[FAIL] Import: {e}")
    import traceback; traceback.print_exc()
    sys.exit(1)

print("\n[1] MotorHAT init @ 0x60 ...")
try:
    mh = Adafruit_MotorHAT(addr=0x60)
    print("    ✅ MotorHAT init OK")
except Exception as e:
    print(f"    ❌ {e}")
    sys.exit(1)

print("\n[2] DC Motors M1-M4 init ...")
motors = []
for i in range(1, 5):
    try:
        motors.append(mh.getMotor(i))
        print(f"    M{i} ✅")
    except Exception as e:
        print(f"    M{i} ❌ {e}"); errors += 1

print("\n[3] M1 forward 0.5s, speed=150 ...")
try:
    motors[0].setSpeed(150)
    motors[0].run(Adafruit_MotorHAT.FORWARD)
    time.sleep(0.5)
    motors[0].run(Adafruit_MotorHAT.RELEASE)
    print("    ✅ M1 ran (listen for motor hum!)")
except Exception as e:
    print(f"    ❌ {e}"); errors += 1

print("\n[4] Servo P0 sweep 0→90→180→90 ...")
try:
    pwm = motors[0]._pwm
    def servo(ch, deg):
        pulse = int(102 + (deg / 180.0) * 408)
        pwm.setPWM(ch, 0, pulse)
    servo(0, 0);   time.sleep(0.4)
    servo(0, 90);  time.sleep(0.4)
    servo(0, 180); time.sleep(0.4)
    servo(0, 90);  time.sleep(0.4)
    pwm.setPWM(0, 0, 0)
    print("    ✅ Servo sweep OK (watch movement!)")
except Exception as e:
    print(f"    ❌ {e}"); errors += 1

print("\n[5] PCA9685 registers read-back ...")
try:
    from Adafruit_GPIO.I2C import Device as I2CDevice
    dev = I2CDevice(0x60, 1)
    m1, m2, ps = dev.readU8(0x00), dev.readU8(0x01), dev.readU8(0xFE)
    print(f"    MODE1=0x{m1:02X} MODE2=0x{m2:02X} PRESCALE={ps} ✅")
except Exception as e:
    print(f"    ❌ {e}"); errors += 1

print("\n[6] All motors + PWM emergency stop ...")
try:
    for m in motors: m.run(Adafruit_MotorHAT.RELEASE)
    mh.getMotor(1)._pwm.setAllPWM(0, 0)
    print("    ✅ All stopped")
except Exception as e:
    print(f"    ⚠️ {e}")

print("\n" + "=" * 55)
print(f"  {'🎉 ALL PASSED!' if errors==0 else f'⚠️  {errors} error(s)'}")
print("=" * 55)
'''

sftp = client.open_sftp()
with sftp.open(f"{REMOTE}/AITank/smoke.py", "w") as f:
    f.write(smoke)
sftp.close()

run(client, f"cd {REMOTE}/AITank && echo '{PASS}' | sudo -S timeout 30 python3 smoke.py", timeout=40)

client.close()
print("\n=== DONE ===")
