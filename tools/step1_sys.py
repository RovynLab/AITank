"""快速测试: 扫两个 I2C 总线 + 确认 PCA9685 + 开 I2C + 装 apt 依赖"""
import paramiko, time

HOST, USER, PASS = "192.168.0.100", "pi", "raspberry"

def run(client, cmd, timeout=120, check=True):
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    if "sudo -S" in cmd:
        stdin.write(PASS + "\n")
        stdin.flush()
    out = stdout.read().decode(errors="replace")
    err = stderr.read().decode(errors="replace")
    code = stdout.channel.recv_exit_status()
    short = cmd.replace(PASS, "***").strip()
    print(f"\n>>> {short[:100]}")
    if out.strip(): print(out.strip())
    if err.strip() and "password" not in err.lower(): print(f"[ERR] {err.strip()}")
    if check and code != 0: print(f"    [WARN] exit={code}")
    else: print(f"    (exit={code})")
    return code, out, err

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, username=USER, password=PASS, timeout=10)
print("=== CONNECTED ===\n")

# 1. 开 I2C
print("--- Step 1: Enable I2C via raspi-config ---")
run(client, f"echo '{PASS}' | sudo -S raspi-config nonint do_i2c 0", check=False)

# 2. 扫两个总线
print("\n--- Step 2: Scan I2C bus 1 ---")
run(client, f"echo '{PASS}' | sudo -S i2cdetect -y 1", check=False)
print("\n--- Step 3: Scan I2C bus 2 ---")
run(client, f"echo '{PASS}' | sudo -S i2cdetect -y 2", check=False)

# 3. apt update
print("\n--- Step 4: apt update ---")
run(client, f"echo '{PASS}' | sudo -S apt-get update -y", timeout=180)

# 4. 装系统依赖
print("\n--- Step 5: install system deps ---")
pkgs = "i2c-tools python3-smbus python3-pip python3-numpy python3-venv libatlas-base-dev libhdf5-dev libjpeg-dev libpng-dev python3-psutil"
run(client, f"echo '{PASS}' | sudo -S apt-get install -y {pkgs}", timeout=300)

# 5. 确认 I2C 状态
print("\n--- Step 6: Confirm I2C status ---")
run(client, f"echo '{PASS}' | sudo -S raspi-config nonint get_i2c")
run(client, f"echo '{PASS}' | sudo -S ls -la /dev/i2c*")

client.close()
print("\n=== DONE ===")
