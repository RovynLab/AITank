"""Step 4: 综合硬件冒烟测试（在树莓派上直接跑）"""
import paramiko

HOST, USER, PASS = "192.168.0.100", "pi", "raspberry"

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
        print(f"[ERR] {err.strip()[:200]}")
    if check and code != 0: print(f"  [WARN] exit={code}")
    else: print(f"  (exit={code})")
    return code, out, err

SMOKE = r'''
import sys, os, time
# === 自动注入 deps 路径 ===
_here = os.path.dirname(os.path.abspath(__file__))
for _up in range(5):
    _d = os.path.join(_here, '..' * _up, 'deps')
    if os.path.isdir(_d):
        if _d not in sys.path:
            sys.path.insert(0, _d)
        break

print("=" * 55)
print("  AITank Hardware Smoke Test")
print("=" * 55)
errors = 0

# ---- 1. Adafruit_MotorHAT import ----
print("\n[1] Importing Adafruit_MotorHAT...")
try:
    from Adafruit_MotorHAT import Adafruit_MotorHAT, Adafruit_DCMotor
    from Adafruit_MotorHAT.Adafruit_PWM_Servo_Driver import PWM
    print("    ✅ Adafruit_MotorHAT import OK")
except Exception as e:
    print(f"    ❌ Import FAILED: {e}")
    errors += 1
    sys.exit(1)

# ---- 2. Init MotorHAT (PCA9685 @ 0x60) ----
print("\n[2] Initializing MotorHAT (PCA9685 @ 0x60)...")
try:
    mh = Adafruit_MotorHAT(addr=0x60)
    print("    ✅ MotorHAT init OK")
except Exception as e:
    print(f"    ❌ MotorHAT init FAILED: {e}")
    errors += 1
    sys.exit(1)

# ---- 3. Init 4 DC Motors ----
print("\n[3] DC Motor init (M1-M4)...")
motors = []
for i in range(1, 5):
    try:
        m = mh.getMotor(i)
        motors.append(m)
        print(f"    M{i} ✅")
    except Exception as e:
        print(f"    M{i} ❌: {e}")
        errors += 1

# ---- 4. PWM freq set ----
print("\n[4] Setting PWM frequency to 60Hz...")
try:
    mh.getMotor(1)._pwm.setPWMFreq(60)
    print("    ✅ PWM freq set OK")
except Exception as e:
    print(f"    ❌ PWM freq FAILED: {e}")
    errors += 1

# ---- 5. Test M1 forward 1 sec ----
print("\n[5] Motor M1 forward (speed=150) for 0.5s...")
try:
    motors[0].setSpeed(150)
    motors[0].run(Adafruit_MotorHAT.FORWARD)
    time.sleep(0.5)
    motors[0].run(Adafruit_MotorHAT.RELEASE)
    print("    ✅ M1 forward test OK (listen for motor hum!)")
except Exception as e:
    print(f"    ❌ M1 test FAILED: {e}")
    errors += 1

# ---- 6. Test Servo P0 (PAN) ----
print("\n[6] Servo test (P0) — 0° → 90° → 180°...")
try:
    pwm = mh.getMotor(1)._pwm
    def set_angle(ch, deg):
        # 50Hz PWM: 0.5ms-2.5ms → 0-180°
        pulse = 102  # 0.5ms → 102
        if deg > 0:
            pulse = int(102 + (deg / 180.0) * 408)  # 102 + deg*2.27
        pwm.setPWM(ch, 0, pulse)
    
    set_angle(0, 0);   time.sleep(0.3)
    set_angle(0, 90);  time.sleep(0.3)
    set_angle(0, 180); time.sleep(0.3)
    set_angle(0, 90);  time.sleep(0.3)
    pwm.setPWM(0, 0, 0)  # 关闭
    print("    ✅ Servo sweep OK (watch for movement!)")
except Exception as e:
    print(f"    ❌ Servo test FAILED: {e}")
    import traceback; traceback.print_exc()
    errors += 1

# ---- 7. Read PCA9685 registers back ----
print("\n[7] Read PCA9685 registers...")
try:
    from Adafruit_GPIO.I2C import Device as I2CDevice
    dev = I2CDevice(0x60, 1)
    mode1 = dev.readU8(0x00)
    mode2 = dev.readU8(0x01)
    prescale = dev.readU8(0xFE)
    print(f"    MODE1=0x{mode1:02X}, MODE2=0x{mode2:02X}, PRESCALE={prescale}")
    print("    ✅ Register read OK")
except Exception as e:
    print(f"    ❌ Register read FAILED: {e}")
    errors += 1

# ---- 8. All stop ----
print("\n[8] Emergency stop (all motors released)...")
try:
    for m in motors:
        m.run(Adafruit_MotorHAT.RELEASE)
    # All PWM channels off
    mh.getMotor(1)._pwm.setAllPWM(0, 0)
    print("    ✅ All stopped")
except Exception as e:
    print(f"    ⚠️  Stop: {e}")

# ---- Summary ----
print("\n" + "=" * 55)
if errors == 0:
    print("  🎉 ALL HARDWARE TESTS PASSED!")
else:
    print(f"  ⚠️  {errors} error(s) found")
print("=" * 55)
'''

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, username=USER, password=PASS, timeout=10)
print("=== CONNECTED ===\n")

# 先写测试脚本到远端
sftp = client.open_sftp()
with sftp.open("/home/pi/AITank/smoke_test.py", "w") as f:
    f.write(SMOKE)
sftp.close()
print("[OK] smoke_test.py uploaded\n")

# 运行测试 (需要 sudo 才能访问 /dev/i2c-1)
print("--- Running smoke test ---")
run(client, f"cd /home/pi/AITank && echo '{PASS}' | sudo -S timeout 20 python3 smoke_test.py", timeout=30, check=False)

client.close()
print("\n=== DONE ===")
