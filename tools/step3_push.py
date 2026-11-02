"""Step 3: 推送 AITank 代码到树莓派 + 运行硬件测试 + 冒烟测试"""
import paramiko, os, sys, time
from scp import SCPClient

HOST, USER, PASS = "192.168.0.100", "pi", "raspberry"
LOCAL = r"e:\work\AITank"
REMOTE = "/home/pi/AITank"

def run(client, cmd, timeout=120, check=True):
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    if "sudo -S" in cmd:
        stdin.write(PASS + "\n")
        stdin.flush()
    out = stdout.read().decode(errors="replace")
    err = stderr.read().decode(errors="replace")
    code = stdout.channel.recv_exit_status()
    short = cmd.replace(PASS, "***").strip()[:100]
    print(f"\n>>> {short}")
    if out.strip():
        for l in out.strip().split("\n")[-6:]: print(f"  {l}")
    if err.strip() and "password" not in err.lower():
        elines = [l for l in err.strip().split("\n") if l.strip()][-3:]
        print(f"  [ERR] " + " | ".join(elines))
    if check and code != 0: print(f"  [WARN] exit={code}")
    else: print(f"  (exit={code})")
    return code, out, err

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, username=USER, password=PASS, timeout=10)
print("=== CONNECTED ===\n")

# === Step 3.1: 创建远端目录结构 ===
print("--- Step 3.1: Setup remote dirs ---")
dirs = [REMOTE, f"{REMOTE}/deps", f"{REMOTE}/labs", f"{REMOTE}/demos", 
        f"{REMOTE}/ai", f"{REMOTE}/core", f"{REMOTE}/student_api"]
for d in dirs:
    run(client, f"mkdir -p {d}", check=False)

# === Step 3.2: 推送文件 ===
print("\n--- Step 3.2: SCP push ---")
sftp = client.open_sftp()
scp = SCPClient(client.get_transport(), socket_timeout=30)

# 先列出所有需要推送的文件
def collect_files(base_dir, rel="", skip_dirs=None):
    """递归收集文件列表，返回 (local_path, remote_path)"""
    files = []
    skip = set(skip_dirs or [".git", "__pycache__", ".venv", "tools"])
    full = os.path.join(base_dir, rel)
    if not os.path.isdir(full):
        return files
    for item in os.listdir(full):
        if item in skip: continue
        local_path = os.path.join(full, item)
        remote_path = f"{REMOTE}/{rel}/{item}" if rel else f"{REMOTE}/{item}"
        if os.path.isdir(local_path):
            run(client, f"mkdir -p {remote_path}", check=False)
            files.extend(collect_files(base_dir, 
                       os.path.join(rel, item) if rel else item, skip))
        else:
            files.append((local_path, remote_path))
    return files

all_files = collect_files(LOCAL, skip_dirs=[".git", "__pycache__", ".venv", "tools", ".gitignore", "LICENSE", "README.md", "docs"])
print(f"  共需推送 {len(all_files)} 个文件")

success = 0
failed = []
for i, (lp, rp) in enumerate(all_files):
    try:
        # 先在远端创建父目录
        run(client, f"mkdir -p $(dirname {rp})", check=False)
        scp.put(lp, rp)
        success += 1
    except Exception as e:
        failed.append((lp, str(e)))
    if (i+1) % 20 == 0:
        print(f"  [{i+1}/{len(all_files)}] sent...")

scp.close()
print(f"\n  ✅ 成功: {success}/{len(all_files)}")
if failed:
    print(f"  ❌ 失败 {len(failed)} 个:")
    for f, e in failed[:5]:
        print(f"    {f}: {e}")

# === Step 3.3: 验证远端文件 ===
print("\n--- Step 3.3: Verify remote ---")
run(client, f"ls -la {REMOTE}/")
run(client, f"find {REMOTE} -name '*.py' | wc -l", check=False)

# === Step 4: 硬件测试 ===
print("\n" + "="*60)
print("=== Step 4: Hardware Test — PCA9685 Register Read ===")
print("="*60)

# 直接用 i2cget 读 PCA9685 MODE1 寄存器
print("\n  Reading PCA9685 MODE1 (0x00) on bus 1, addr 0x60...")
run(client, f"echo '{PASS}' | sudo -S i2cget -y 1 0x60 0x00", check=False)
run(client, f"echo '{PASS}' | sudo -S i2cget -y 1 0x60 0x01", check=False)

# 写测试: set LED0 ON_L = 0x00
print("\n  Writing test values...")
run(client, f"echo '{PASS}' | sudo -S i2cset -y 1 0x60 0x06 0x00", check=False)
run(client, f"echo '{PASS}' | sudo -S i2cget -y 1 0x60 0x06", check=False)

# === Step 5: Python 冒烟测试 ===
print("\n" + "="*60)
print("=== Step 5: Python Smoke Test — PCA9685 Init ===")
print("="*60)

smoke_test = '''
import sys, time
sys.path.insert(0, "./deps")
from Adafruit_MotorHAT import Adafruit_PWM_Servo_Driver

print("[SMOKE] Initializing PCA9685...")
try:
    pwm = Adafruit_PWM_Servo_Driver.PWM(address=0x60)
    pwm.setPWMFreq(60)
    print(f"[SMOKE] ✅ PCA9685 init OK at 0x60, freq=60Hz")
    
    # 验证寄存器
    import Adafruit_GPIO.I2C as I2C
    dev = I2C.get_i2c_device(0x60, busnum=1)
    mode1 = dev.readU8(0x00)
    mode2 = dev.readU8(0x01)
    print(f"[SMOKE] MODE1=0x{mode1:02X}, MODE2=0x{mode2:02X}")
    
    # 让舵机通道 P0 亮一下 (PWM 测试)
    print("[SMOKE] Blinking LED (P0 on)...")
    pwm.setPWM(0, 0, 2048)  # 50% duty
    time.sleep(0.5)
    pwm.setPWM(0, 0, 0)
    print("[SMOKE] ✅ PWM output OK")
    
except Exception as e:
    print(f"[SMOKE] ❌ FAILED: {type(e).__name__}: {e}")
    import traceback; traceback.print_exc()
    sys.exit(1)

print("[SMOKE] ALL PASSED 🎉")
'''

# 写到远端文件
with sftp.open(f"{REMOTE}/smoke_test.py", "w") as f:
    f.write(smoke_test)
sftp.close()

run(client, f"cd {REMOTE} && timeout 15 python3 smoke_test.py", timeout=20, check=False)

# === Step 6: 跑 lab01 LED 闪烁 ===
print("\n" + "="*60)
print("=== Step 6: Run lab01_led_blink ===")
print("="*60)
run(client, f"cd {REMOTE} && timeout 5 python3 labs/lab01_led_blink.py 2>&1 || echo 'lab01 done'", timeout=10, check=False)

client.close()
print("\n=== ALL DONE ===")
