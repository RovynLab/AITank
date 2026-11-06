import paramiko, time

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.0.100", username="pi", password="raspberrypi", timeout=15)

def run(cmd, t=60, ignore_timeout=False):
    _, so, se = c.exec_command(cmd, timeout=t)
    try:
        out = so.read().decode(errors="replace").strip()
        err = se.read().decode(errors="replace").strip()
    except Exception:
        if ignore_timeout:
            print("(channel 挂起属预期)")
            return ""
        raise
    print(f"$ {cmd[:90]}")
    print((out + "\n" + err).strip()[:900])
    print()
    return out

# 1) 下载 NanoDet 模型 (~15MB)
run("wget -q -O ~/.opencv/models/object_detection_nanodet_2022nov.onnx "
    "https://github.com/opencv/opencv_zoo/raw/main/models/object_detection_nanodet/object_detection_nanodet_2022nov.onnx "
    "&& ls -la ~/.opencv/models/", t=300)

# 2) 模型加载 + 对实拍帧推理, 验证解码 (用 petcar 的 detectors 模块)
run("cd /home/pi/AITank && python3 -c \""
    "import cv2, time; "
    "from petcar.drivers.detectors import NanoDet; "
    "cap = cv2.VideoCapture(0); cap.set(3, 640); cap.set(4, 480); "
    "[cap.read() for _ in range(8)]; "
    "ok, f = cap.read(); cap.release(); "
    "print('frame', f.shape if ok else None); "
    "m = NanoDet(); "
    "t0 = time.time(); dets = m.detect(f); dt = time.time() - t0; "
    "print(f'infer {dt:.2f}s, {len(dets)} dets'); "
    "[print('  ', d) for d in dets[:5]]\"", t=180)

# 3) 重启 petcar
run("pkill -f 'petcar.main'; sleep 1; echo killed")
run("cd /home/pi/AITank && setsid env PETCAR_ASR_MODE=mock PETCAR_TTS_MODE=mock "
    "python3 -m petcar.main --flask --port 5000 "
    "> petcar/logs/petcar.log 2>&1 < /dev/null & echo started",
    t=8, ignore_timeout=True)
time.sleep(12)
run("curl -s http://localhost:5000/api/detect")
run("curl -s http://localhost:5000/api/health")
c.close()
