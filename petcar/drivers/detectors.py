"""petcar 目标检测器

NanoDet 通用物体检测 (COCO 80 类) + 传统视觉检测器, 全部输出
(x, y, w, h, score, cls_id) 统一接口, 供视频流画框使用。
模型路径与环境变量 PETCAR_MODEL_DIR 一致 (默认 ~/.opencv/models)。
"""
import os

import cv2
import numpy as np

MODEL_DIR = os.environ.get(
    "PETCAR_MODEL_DIR",
    os.path.join(os.path.expanduser("~"), ".opencv", "models"),
)

COCO_CLASSES = [
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train",
    "truck", "boat", "traffic light", "fire hydrant", "stop sign",
    "parking meter", "bench", "bird", "cat", "dog", "horse", "sheep",
    "cow", "elephant", "bear", "zebra", "giraffe", "backpack", "umbrella",
    "handbag", "tie", "suitcase", "frisbee", "skis", "snowboard",
    "sports ball", "kite", "baseball bat", "baseball glove", "skateboard",
    "surfboard", "tennis racket", "bottle", "wine glass", "cup", "fork",
    "knife", "spoon", "bowl", "banana", "apple", "sandwich", "orange",
    "broccoli", "carrot", "hot dog", "pizza", "donut", "cake", "chair",
    "couch", "potted plant", "bed", "dining table", "toilet", "tv",
    "laptop", "mouse", "remote", "keyboard", "cell phone", "microwave",
    "oven", "toaster", "sink", "refrigerator", "book", "clock", "vase",
    "scissors", "teddy bear", "hair drier", "toothbrush",
]


class TFLiteSSD:
    """v4 的 TensorFlow Lite SSD MobileNet (量化, COCO 80 类)。
    输入 300x300, 输出 boxes/classes/scores 归一化坐标。Pi 上约 100~200ms/帧。"""

    def __init__(self, conf=0.5):
        path = os.path.join(MODEL_DIR, "detect.tflite")
        label_path = os.path.join(MODEL_DIR, "labelmap.txt")
        if not os.path.exists(path):
            raise RuntimeError(f"模型缺失: {path}")
        self.conf = conf
        try:
            from tflite_runtime.interpreter import Interpreter
        except ImportError:
            try:
                from ai_edge_litert.interpreter import Interpreter
            except ImportError:
                from tensorflow.lite.python.interpreter import Interpreter
        self.labels = [l.strip() for l in open(label_path)] if os.path.exists(label_path) else COCO_CLASSES
        # SSD uses sparse COCO-90 indices; the API and NanoDet use COCO-80.
        # Some label maps include a leading background label, which is not
        # emitted by this SSD model's zero-based class output.
        if os.path.exists(label_path):
            labels = list(self.labels)
            if labels and labels[0].lower() in ("???", "background", "__background__"):
                labels = labels[1:]
        else:
            missing = {11, 25, 28, 29, 44, 65, 67, 68, 70, 82}
            names = iter(COCO_CLASSES)
            labels = ["???" if i in missing else next(names) for i in range(90)]
        self.class_ids = {i: COCO_CLASSES.index(name) for i, name in enumerate(labels)
                          if name in COCO_CLASSES}
        self.itp = Interpreter(model_path=path)
        self.itp.allocate_tensors()
        ind = self.itp.get_input_details()
        self.out = self.itp.get_output_details()
        self.h, self.w = ind[0]["shape"][1], ind[0]["shape"][2]
        self.in_idx = ind[0]["index"]
        self.float_input = ind[0]["dtype"] == np.float32

    def detect(self, frame, classes=None):
        h0, w0 = frame.shape[:2]
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        x = cv2.resize(rgb, (self.w, self.h))
        x = np.expand_dims(x, 0)
        if self.float_input:
            x = (np.float32(x) - 127.5) / 127.5
        self.itp.set_tensor(self.in_idx, x)
        self.itp.invoke()
        boxes = self.itp.get_tensor(self.out[0]["index"])[0]
        clss = self.itp.get_tensor(self.out[1]["index"])[0]
        scores = self.itp.get_tensor(self.out[2]["index"])[0]
        out = []
        for i in range(len(scores)):
            s = float(scores[i])
            if s <= self.conf or s > 1.0:
                continue
            cid = self.class_ids.get(int(clss[i]))
            if cid is None:
                continue
            if classes is not None and cid not in classes:
                continue
            ymin = max(0.0, min(1.0, float(boxes[i][0])))
            xmin = max(0.0, min(1.0, float(boxes[i][1])))
            ymax = max(0.0, min(1.0, float(boxes[i][2])))
            xmax = max(0.0, min(1.0, float(boxes[i][3])))
            x1, y1 = int(xmin * w0), int(ymin * h0)
            out.append((x1, y1, int((xmax - xmin) * w0), int((ymax - ymin) * h0), s, cid))
        return out


def get_detector(log=None):
    """优先 v4 的 TFLite SSD (稳定), 缺失则回退 NanoDet。"""
    try:
        d = TFLiteSSD()
        if log:
            log("TFLite SSD 加载成功 (v4)")
        return d
    except Exception as e:
        if log:
            log(f"TFLite 不可用({e}), 回退 NanoDet")
        return NanoDet()


class NanoDet:
    """NanoDet-Plus-m 320x320 (cv2.dnn)。模型 ~15MB, Pi 4 上约 1~2fps, 已限频。"""

    INPUT = 320
    STRIDES = (8, 16, 32)
    REG_MAX = 7

    def __init__(self, conf=0.35, nms=0.6):
        path = os.path.join(MODEL_DIR, "object_detection_nanodet_2022nov.onnx")
        if not os.path.exists(path):
            raise RuntimeError(f"模型缺失: {path}")
        self.net = cv2.dnn.readNet(path)
        self.layer_names = self.net.getUnconnectedOutLayersNames()
        self.conf = conf
        self.nms = nms
        self._proj = np.arange(self.REG_MAX, dtype=np.float32)

    def detect(self, frame, classes=None):
        """返回 [(x, y, w, h, score, cls_id), ...], 坐标在原图系"""
        h0, w0 = frame.shape[:2]
        blob = cv2.dnn.blobFromImage(
            frame, scalefactor=1.0 / 255.0, size=(self.INPUT, self.INPUT),
            mean=(0, 0, 0), swapRB=True, crop=False)
        self.net.setInput(blob)
        outs = self.net.forward(self.layer_names)
        boxes, scores, labels = self._decode(outs)
        if len(boxes) == 0:
            return []
        keep = scores > self.conf
        boxes, scores, labels = boxes[keep], scores[keep], labels[keep]
        if classes is not None:
            m = np.isin(labels, list(classes))
            boxes, scores, labels = boxes[m], scores[m], labels[m]
        if len(boxes) == 0:
            return []
        sx, sy = w0 / self.INPUT, h0 / self.INPUT
        boxes *= np.array([sx, sy, sx, sy], dtype=np.float32)
        idxs = cv2.dnn.NMSBoxes(boxes.tolist(), scores.tolist(),
                                self.conf, self.nms, top_k=100)
        if len(idxs) == 0:
            return []
        idxs = np.asarray(idxs).flatten()
        return [(int(boxes[i][0]), int(boxes[i][1]), int(boxes[i][2]),
                 int(boxes[i][3]), float(scores[i]), int(labels[i]))
                for i in idxs]

    def _decode(self, outs):
        all_b, all_s, all_l = [], [], []
        for i, stride in enumerate(self.STRIDES):
            cls_out = np.squeeze(outs[i * 2])       # (80, H, W)
            reg_out = np.squeeze(outs[i * 2 + 1])   # (28, H, W)
            _, H, W = cls_out.shape

            cls_s = 1.0 / (1.0 + np.exp(-cls_out))          # sigmoid
            cls_s = np.transpose(cls_s, (1, 2, 0)).reshape(-1, 80)
            max_s = cls_s.max(axis=1)
            lab = cls_s.argmax(axis=1)

            reg = np.transpose(reg_out, (1, 2, 0)).reshape(-1, 4, self.REG_MAX)
            reg = np.exp(reg - reg.max(axis=2, keepdims=True))
            reg /= reg.sum(axis=2, keepdims=True)
            dist = (reg * self._proj).sum(axis=2) * stride  # (N,4) l,t,r,b

            yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
            xx = (xx.reshape(-1) + 0.5) * stride
            yy = (yy.reshape(-1) + 0.5) * stride
            x1 = xx - dist[:, 0]; y1 = yy - dist[:, 1]
            x2 = xx + dist[:, 2]; y2 = yy + dist[:, 3]
            b = np.stack([x1, y1, x2 - x1, y2 - y1], axis=1)
            all_b.append(b); all_s.append(max_s); all_l.append(lab)
        return (np.concatenate(all_b), np.concatenate(all_s),
                np.concatenate(all_l))


def detect_color(frame, cfg):
    """按 HSV 范围检测颜色块。cfg: {h_min,h_max,s_min,s_max,v_min,v_max}
    返回 [(x, y, w, h, score, cls_id=-1), ...], 面积越大概率越高。"""
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    h_min, h_max = cfg.get("h_min", 0), cfg.get("h_max", 180)
    lo = (h_min, cfg.get("s_min", 90), cfg.get("v_min", 90))
    hi = (h_max, cfg.get("s_max", 255), cfg.get("v_max", 255))
    if h_min <= h_max:
        mask = cv2.inRange(hsv, lo, hi)
    else:  # 红色跨界: h>170 或 h<10
        mask = cv2.bitwise_or(
            cv2.inRange(hsv, (0, lo[1], lo[2]), (h_max, hi[1], hi[2])),
            cv2.inRange(hsv, (h_min, lo[1], lo[2]), (180, hi[1], hi[2])))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    mask = cv2.medianBlur(mask, 5)
    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    out = []
    for c in cnts:
        area = cv2.contourArea(c)
        if area < 300:
            continue
        x, y, w, h = cv2.boundingRect(c)
        out.append((x, y, w, h, min(0.99, area / 20000.0), -1))
    out.sort(key=lambda b: b[2] * b[3], reverse=True)
    return out


def detect_tennis_ball(frame):
    """网球 (荧光黄绿色小球): HSV 分割 + 形态学 + 形状三重门限, 无模型。

    四道门限过滤误报:
    1. 长宽比: 球是圆的, 外接框 w/h ≈ 1 (0.65~1.55)
    2. 圆形度: 轮廓面积/最小外接圆面积 ≥ 0.62 (圆=1.0)
    3. 填充率: 轮廓面积/外接框面积 ≥ 0.55 (正圆=π/4≈0.785)
    4. 面积: 350~80000 px², 太小是噪点, 太大贴脸了

    返回 [(x, y, w, h, score, cls_id=-1), ...], score 由圆形度+填充率+面积
    加权而成, 按框面积从大到小排序。
    """
    out = []
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    # 荧光黄绿: H 30~50 (纯黄=30, 纯绿=60); S≥70 排除灰白, V≥60 容忍阴影
    mask = cv2.inRange(hsv, (30, 70, 60), (50, 255, 255))
    k_open = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    k_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, k_open)    # 去孤立噪点
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k_close)  # 缝合高光碎块
    mask = cv2.medianBlur(mask, 5)                           # 平滑边缘
    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for c in cnts:
        area = cv2.contourArea(c)
        if area < 350 or area > 80000:
            continue
        x, y, w, h = cv2.boundingRect(c)
        if w < 16 or h < 16:
            continue
        ar = w / float(h)
        if ar < 0.65 or ar > 1.55:
            continue
        (_, _), r = cv2.minEnclosingCircle(c)
        circ = area / (3.1416 * r * r + 1e-6)
        if circ < 0.62:
            continue
        fill = area / (w * h + 1e-6)
        if fill < 0.55:
            continue
        score = min(0.99, 0.5 * circ + 0.3 * fill + 0.2 * min(1.0, area / 5000.0))
        out.append((x, y, w, h, score, -1))
    out.sort(key=lambda b: b[2] * b[3], reverse=True)
    return out


def detect_motion(frame, state):
    """运动区域 (帧差)。state 跨帧保存上一灰度帧。"""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (5, 5), 0)
    prev = state.get("prev")
    state["prev"] = gray
    if prev is None:
        return []
    diff = cv2.absdiff(gray, prev)
    _, th = cv2.threshold(diff, 25, 255, cv2.THRESH_BINARY)
    th = cv2.dilate(th, np.ones((5, 5), np.uint8))
    cnts, _ = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    out = []
    for c in cnts:
        if cv2.contourArea(c) < 1500:
            continue
        x, y, w, h = cv2.boundingRect(c)
        out.append((x, y, w, h, 0.8, -1))
    return out
