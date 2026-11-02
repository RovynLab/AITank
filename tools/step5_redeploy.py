"""Step 5: 推送修复后的代码 + 重新跑冒烟测试"""
import paramiko, tarfile, os, io

HOST, USER, PASS = "192.168.0.100", "pi", "raspberry"
LOCAL = r"e:\work\AITank"
REMOTE = "/home/pi"

def run(client, cmd, timeout=30, check=True):
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    if "sudo -S" in cmd:
        stdin.write(PASS + "\n")
        stdin.flush()
    out = stdout.read().decode(errors="replace")
    err = stderr.read().decode(errors="replace")
    code = stdout.channel.recv_exit_status()
    short = cmd.replace(PASS, "***").strip()[:120]
    print(f"\n>>> {short}")
    if out.strip(): print(out.strip())
    if err.strip() and "password" not in err.lower():
        print(f"[ERR] {err.strip()[:300]}")
    if check and code != 0: print(f"  [WARN] exit={code}")
    else: print(f"  (exit={code})")
    return code, out, err

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, username=USER, password=PASS, timeout=10)
print("=== CONNECTED ===\n")

# 1. 清理 + 打包 + 推送
print("--- Clean remote + tar push ---")
run(client, f"rm -rf {REMOTE}/AITank && rm -f {REMOTE}/aitank.tar.gz", check=False)

exclude = {".git", "__pycache__", ".venv", "tools", ".gitignore", "LICENSE", "README.md", "docs"}
buf = io.BytesIO()
with tarfile.open(fileobj=buf, mode="w:gz") as tar:
    for item in os.listdir(LOCAL):
        if item in exclude: continue
        tar.add(os.path.join(LOCAL, item), arcname=f"AITank/{item}")

buf.seek(0)
print(f"  Archive: {buf.tell()/(1024*1024):.1f} MB")
sftp = client.open_sftp()
sftp.putfo(buf, f"{REMOTE}/aitank.tar.gz")
sftp.close()
print("  ✅ Uploaded")

run(client, f"cd {REMOTE} && tar xzf aitank.tar.gz && rm aitank.tar.gz")

# 2. 先验证 Platform 探测
print("\n--- Quick verify: Platform detection ---")
run(client, f"cd {REMOTE}/AITank && echo '{PASS}' | sudo -S python3 -c \"\nimport sys\nsys.path.insert(0, 'deps')\nfrom Adafruit_GPIO import Platform\nprint(f'  platform_detect = {Platform.platform_detect()} (1=RPi)')\nprint(f'  pi_version = {Platform.pi_version()} (3=Pi3+)')\nprint(f'  pi_revision = {Platform.pi_revision()} (2=rev2+)')\nfrom Adafruit_GPIO.I2C import get_default_bus\nprint(f'  default I2C bus = {get_default_bus()}')\n\"", check=False)

# 3. 运行完整冒烟测试
print("\n--- Run full smoke test ---")
SMOKE = open(os.path.join(LOCAL, "tools", "step4_smoke.py")).read()
# 从 step4_smoke.py 里提取 SMOKE 变量内容
# 直接用 python 在远端跑
cmd = f'''cd {REMOTE}/AITank && echo '{PASS}' | sudo -S timeout 25 python3 smoke_test.py'''
# 但 smoke_test.py 还在旧版本，需要先重写它
# 直接在远端写一个新的
SMOKE_PY = r'''
import sys, os, time
_here = os.path.dirname(os.path.abspath(__file__))
for _up in range(5):
    _d = os.path.join(_here, '..' * _up, 'deps')
    if os.path.isdir(_d):
        if _d not in sys.path: sys.path.insert(0, _d)
        break

print("=" * 55)
print("  AITank Hardware Smoke Test v2")
print("=" * 55)

errors = 0
try:
    from Adafruit_MotorHAT import Adafruit_MotorHAT, Adafruit_DCMotor
    from Adafruit_MotorHAT.Adafruit_PWM_Servo_Driver import PWM
    from Adafruit_GPIO import Platform
    from Adafruit_GPIO.I2C import get_default_bus
    print(f"[OK] Imports OK | Platform={Platform.platform_detect()} | Bus={get_default_bus()}")
except Exception as e:
    print(f"[FAIL] Import: {e}")
    import traceback; traceback.print_exc()
    sys.exit(1)

# Init MotorHAT
print("\n[1] MotorHAT @ 0x60...")
try:
    mh = Adafruit_MotorHAT(addr=0x60)
    print("    ✅ init OK")
except Exception as e:
    print(f"    ❌ {e}"); errors += 1

# 4 motors
print("\n[2] DC Motors M1-M4...")
motors = []
for i in range(1, 5):
    try:
        motors.append(mh.getMotor(i))
        print(f"    M{i} ✅")
    except Exception as e:
        print(f"    M{i} ❌ {e}"); errors += 1

# M1 forward 0.5s
print("\n[3] M1 forward 0.5s (speed=150)...")
try:
    motors[0].setSpeed(150)
    motors[0].run(Adafruit_MotorHAT.FORWARD)
    time.sleep(0.5)
    motors[0].run(Adafruit_MotorHAT.RELEASE)
    print("    ✅ M1 ran (listen for motor hum!)")
except Exception as e:
    print(f"    ❌ {e}"); errors += 1

# Servo P0 sweep
print("\n[4] Servo P0 sweep 0°→90°→180°...")
try:
    pwm = motors[0]._pwm
    def set_servo(ch, deg):
        pulse = int(102 + (deg / 180.0) * 408)
        pwm.setPWM(ch, 0, pulse)
    set_servo(0, 0);   time.sleep(0.4)
    set_servo(0, 90);  time.sleep(0.4)
    set_servo(0, 180); time.sleep(0.4)
    set_servo(0, 90);  time.sleep(0.4)
    pwm.setPWM(0, 0, 0)
    print("    ✅ Servo sweep OK (watch movement!)")
except Exception as e:
    print(f"    ❌ {e}"); errors += 1

# Registers read back
print("\n[5] PCA9685 registers...")
try:
    from Adafruit_GPIO.I2C import Device as I2CDevice
    dev = I2CDevice(0x60, 1)
    print(f"    MODE1=0x{dev.readU8(0x00):02X}  MODE2=0x{dev.readU8(0x01):02X}  PRESCALE={dev.readU8(0xFE)}")
except Exception as e:
    print(f"    ❌ {e}"); errors += 1

# Emergency stop
print("\n[6] All stop...")
try:
    for m in motors:
        m.run(Adafruit_MotorHAT.RELEASE)
    mh.getMotor(1)._pwm.setAllPWM(0, 0)
    print("    ✅")
except Exception as e:
    print(f"    ⚠️  {e}")

print("\n" + "=" * 55)
print(f"  {'🎉 ALL PASSED!' if errors==0 else f'⚠️  {errors} error(s)'}")
print("=" * 55)
'''

sftp = client.open_sftp()
with sftp.open(f"{REMOTE}/AITank/smoke_test.py", "w") as f:
    f.write(SMOKE_PY)
sftp.close()

run(client, f"cd {REMOTE}/AITank && echo '{PASS}' | sudo -S timeout 30 python3 smoke_test.py", timeout=40, check=False)

client.close()
print("\n=== DONE ===")
