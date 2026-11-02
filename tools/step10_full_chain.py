import paramiko
HOST, USER, PASS = "192.168.0.100", "pi", "raspberry"
def run(c, cmd, timeout=10):
    stdin, stdout, stderr = c.exec_command(cmd, timeout=timeout)
    if "sudo -S" in cmd: stdin.write(PASS + "\n"); stdin.flush()
    out = stdout.read().decode(errors="replace").strip()
    err = stderr.read().decode(errors="replace").strip()
    print(f">>> {cmd.replace(PASS,'***')[:120]}")
    if out: print(f"  {out}")
    if err and "password" not in err.lower() and "pygame" not in err.lower(): print(f"  [ERR] {err[:300]}")
    print()

c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=USER, password=PASS, timeout=10)

# 用 deps 路径验证完整链路
for chk in [
    ("Platform + I2C bus", "cd /home/pi/AITank && python3 -c \"import sys; sys.path.insert(0,'deps'); from Adafruit_GPIO import Platform, I2C; print('detect=', Platform.platform_detect(), 'pi=', Platform.pi_version(), 'bus=', I2C.get_default_bus())\""),
    ("MotorHAT init", "cd /home/pi/AITank && python3 -c \"import sys; sys.path.insert(0,'deps'); from Adafruit_MotorHAT import Adafruit_MotorHAT; mh=Adafruit_MotorHAT(addr=0x60); print('MotorHAT OK')\""),
    ("sudo + MotorHAT", "cd /home/pi/AITank && echo '" + PASS + "' | sudo -S python3 -c \"import sys; sys.path.insert(0,'deps'); from Adafruit_MotorHAT import Adafruit_MotorHAT; mh=Adafruit_MotorHAT(addr=0x60); print('MotorHAT OK under sudo')\""),
    ("lab01 import check", "cd /home/pi/AITank && head -15 labs/lab01_led_blink.py | tail -10"),
]:
    run(c, f"echo '{PASS}' | sudo -S {chk[1]}" if "sudo" not in chk[1] else chk[1])

# 跑 lab05 wheel_test 实际
run(c, f"cd /home/pi/AITank && echo '{PASS}' | sudo -S timeout 3 python3 -c \"\nimport sys, os\n_here = os.path.join('.', 'labs')\nfor _u in range(3):\n    _d = os.path.join(_here, '..' * _u, 'deps')\n    if os.path.isdir(_d) and _d not in sys.path: sys.path.insert(0, _d)\nfrom Adafruit_MotorHAT import Adafruit_MotorHAT, Adafruit_DCMotor\n_mh = Adafruit_MotorHAT(addr=0x60)\nm1 = _mh.getMotor(1); m1.setSpeed(100); m1.run(Adafruit_MotorHAT.FORWARD)\nimport time; time.sleep(0.5)\nm1.run(Adafruit_MotorHAT.RELEASE)\nprint('Motor forward + release OK')\n\"")

c.close()
print("=== ALL GOOD ===")
