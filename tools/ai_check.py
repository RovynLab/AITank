import paramiko

HOST, USER, PASS = "192.168.0.100", "pi", "raspberry"
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=USER, password=PASS, timeout=10)

files = ["ball_track_simple.py", "face_recognition.py", "finger.py", "finger_v2.py"]

for f in files:
    print(f"\n{'='*60}")
    print(f"ai/{f}")
    print("=" * 60)
    # 语法检查 + import 测试
    cmd = f"cd /home/pi/AITank && python3 -c \"import sys; sys.path.insert(0,'.'); exec(open('ai/{f}').read().split('if __name__')[0]); print('  import OK')\" 2>&1"
    stdin, stdout, stderr = c.exec_command(cmd, timeout=15)
    out = stdout.read().decode(errors="replace")
    err = stderr.read().decode(errors="replace")
    if "import OK" in out and not err.strip():
        print("  ✅ 语法+导入链通过")
    else:
        print(f"  ❌ 报错:\n  {out.strip()}\n  {err.strip()}")

c.close()
