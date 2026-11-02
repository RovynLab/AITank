import paramiko

HOST, USER, PASS = "192.168.0.100", "pi", "raspberry"

c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=USER, password=PASS, timeout=10)

tests = [
    # loop 类
    ("labs/lab04_pwm_servo.py",   "sudo timeout 6 python3 labs/lab04_pwm_servo.py 2>&1"),
    ("labs/lab06_mecanum_class.py", "sudo timeout 6 python3 labs/lab06_mecanum_class.py 2>&1"),
    ("labs/lab07_mecanum_global.py", "sudo timeout 6 python3 labs/lab07_mecanum_global.py 2>&1"),
    ("labs/lab09_joystick.py",    "sudo timeout 6 python3 labs/lab09_joystick.py 2>&1"),
    ("labs/lab10_ptz_control.py", "sudo timeout 6 python3 labs/lab10_ptz_control.py 2>&1"),
    # demos
    ("demos/flask_web_control/app.py", "sudo timeout 5 python3 demos/flask_web_control/app.py 2>&1"),
    ("demos/flask_web_control/MecanumChasis.py", "sudo timeout 5 python3 -c \"import sys; sys.path.insert(0,'deps'); import demos.flask_web_control.MecanumChasis as M; print('import OK')\" 2>&1"),
    ("demos/object_tracking/ball_track.py --help", "sudo timeout 5 python3 demos/object_tracking/ball_track.py --help 2>&1"),
    ("demos/traffic_sign/main.py --help", "sudo timeout 5 python3 demos/traffic_sign/main.py --help 2>&1"),
    # ai
    ("ai/ball_track_simple.py", "sudo timeout 5 python3 -c \"import sys; sys.path.insert(0,'deps'); import ai.ball_track_simple; print('OK')\" 2>&1"),
    ("ai/finger.py", "sudo timeout 5 python3 -c \"import sys; sys.path.insert(0,'deps'); import ai.finger; print('OK')\" 2>&1"),
]

for label, cmd in tests:
    full_cmd = f"cd /home/pi/AITank && echo '{PASS}' | {cmd}"
    print(f"\n{'='*60}\n❌  {label}\n{'='*60}")
    stdin, stdout, stderr = c.exec_command(full_cmd, timeout=15)
    if "sudo" in cmd: stdin.write(PASS + "\n"); stdin.flush()
    out = stdout.read().decode(errors="replace")
    err = stderr.read().decode(errors="replace")
    print("--- STDOUT ---")
    print(out.strip()[:500] or "(empty)")
    print("--- STDERR ---")
    print(err.strip()[:1000] or "(empty)")
    print(f"--- exit={stdout.channel.recv_exit_status()} ---")

c.close()
