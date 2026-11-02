import paramiko

HOST, USER, PASS = "192.168.0.100", "pi", "raspberry"
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=USER, password=PASS, timeout=10)

cmd = f"""echo '{PASS}' | sudo -S python3 -c "
import sys
sys.path.insert(0, '/home/pi/v4_test')
import Adafruit_MotorHAT.Adafruit_MotorHAT_Motors as m
print('MotorHAT_Motors.py 加载自:', m.__file__)
import Adafruit_MotorHAT
print('Adafruit_MotorHAT 包路径:', Adafruit_MotorHAT.__file__)
# 打印 M1 num=0 的 IN 引脚, 确认是 v4 原版的 in2=9,in1=8
print()
print('M1 num=0 IN2/in1:', m.Adafruit_DCMotor.__init__.__doc__)
print()
import inspect
src = inspect.getsource(m.Adafruit_DCMotor.__init__)
# 找 num == 0 那段
for line in src.split(chr(10)):
    if 'num == 0' in line or 'in2' in line or 'in1' in line or 'pwm' in line:
        print('  ', line.strip())
" 2>&1"""

stdin, stdout, stderr = c.exec_command(cmd, timeout=15)
stdin.write(PASS + "\n"); stdin.flush()
print(stdout.read().decode())
err = stderr.read().decode()
if err: print("STDERR:", err[:300])
c.close()
