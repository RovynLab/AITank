# -*- coding: utf-8 -*-
"""
api/flask_app.py — Flask Web API + 中控面板
============================================

面板页面:
  GET  / 或 /dashboard          → 中控面板 (静态页)

REST API:
  GET  /api/health              → 健康检查
  GET  /api/emotion?name=happy  → 设置表情
  GET  /api/emotions            → 可用表情列表
  GET  /api/chat?text=你好      → 大模型对话
  GET  /api/mood                → 查当前情感状态
  POST /api/base/move           → 底盘运动 {direction, duration}
  POST /api/base/speed          → 设置底盘速度 {speed: 0-255}
  POST /api/estop               → 急停 (底盘停 + 停止追踪)
  POST /api/ptz                 → 云台 {direction, delta}
  GET  /api/photo               → 拍照 (返回路径)
  GET  /api/photo/latest        → 最近一张照片 (图片)
  GET  /api/faces               → 查人脸
  GET  /api/video_feed          → MJPEG 实时视频流
  GET  /api/skills              → 技能列表 (name/desc/参数 schema)
  POST /api/skill/run           → 执行技能 {name, params}
  GET  /api/status              → 聚合状态 (心情/云台/底盘/系统/配置)
  GET  /api/logs?n=50           → 最近事件日志
  POST /api/tts                 → TTS 试听 {text}
  POST /api/asr/once            → 启动一次 ASR 识别 (后台)
  GET  /api/asr/result          → 查 ASR 结果
"""

from __future__ import annotations

import sys
import os
import json
import time
import threading
from collections import deque
from typing import Any

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

_START_TIME = time.time()


# ============================================================================
# 事件日志 (ring buffer)
# ============================================================================
class EventLog:
    """线程安全的最近事件记录，供面板日志控制台轮询"""

    def __init__(self, maxlen: int = 200):
        self._q: deque = deque(maxlen=maxlen)
        self._lock = threading.Lock()
        self._seq = 0

    def add(self, kind: str, msg: str):
        with self._lock:
            self._seq += 1
            self._q.append({
                "id": self._seq,
                "ts": time.strftime("%H:%M:%S"),
                "kind": kind,
                "msg": str(msg)[:200],
            })

    def recent(self, n: int = 50) -> list:
        with self._lock:
            return list(self._q)[-n:]


# ============================================================================
# 系统状态小工具 (树莓派友好, 全部容错)
# ============================================================================
def _cpu_temp():
    try:
        with open("/sys/class/thermal/thermal_zone0/temp") as f:
            return round(int(f.read().strip()) / 1000.0, 1)
    except Exception:
        return None


def _sys_stats() -> dict:
    stats = {"cpu_percent": None, "mem_percent": None, "temp_c": _cpu_temp()}
    try:
        import psutil
        stats["cpu_percent"] = round(psutil.cpu_percent(interval=None), 1)
        stats["mem_percent"] = round(psutil.virtual_memory().percent, 1)
    except Exception:
        pass
    return stats


# ============================================================================
def create_app(chat=None, emotion=None, mecanum=None, ptz=None, camera=None,
               mood_engine=None, tts=None, asr=None, skill_manager=None):
    """创建 Flask app。所有参数可选, 传了就用, 不传就 Mock/降级"""
    try:
        from flask import Flask, request, jsonify, Response, send_file
    except ImportError:
        print("[Flask] Flask 未安装, API 不可用")
        return None

    from petcar import config

    app = Flask(__name__, static_folder=os.path.join(_HERE, "static"))
    log = EventLog()
    log.add("sys", "Flask 已启动")

    # ASR 一次性识别任务状态
    asr_job = {"running": False, "result": None, "done": False}

    # 检测标注注册表: 每个检测器独立开关 (复选), 视频流只画已开启的框。
    # detect 返回 [(x, y, w, h, score), ...] 原图坐标
    annotators = {}
    try:
        from ..drivers.detectors import (get_detector, detect_tennis_ball,
                                         detect_motion, detect_color)
        _motion_state = {}
        # 颜色识别 HSV 配置 (P1 面板可调, P2 颜色追踪复用)
        color_cfg = {"h_min": 25, "h_max": 45, "s_min": 90,
                     "s_max": 255, "v_min": 90, "v_max": 255}
        # 检测器共享一次推理结果并按帧限频复用缓存框 (TFLite ~150ms, 每 2 帧一次)
        _dnn_cache = {"m": "uninit", "raw": [], "frame_id": -1, "count": 0}

        def _dnn_all(frame):
            c = _dnn_cache
            if c["m"] == "uninit":
                try:
                    c["m"] = get_detector(log=lambda msg: log.add("sys", msg))
                except Exception as e:
                    c["m"] = None
                    log.add("sys", f"检测器不可用: {e}")
            if c["m"] is None:
                return []
            fid = id(frame)          # 同一帧多个标注只推理一次
            if fid == c.get("fid"):
                return c["raw"]
            c["fid"] = fid
            c["count"] += 1
            if c["count"] - c["frame_id"] >= 2:   # 每 2 帧真跑一次, 其余复用
                c["frame_id"] = c["count"]
                try:
                    c["raw"] = c["m"].detect(frame)
                except Exception:
                    c["raw"] = []
            return c["raw"]

        def _dnn(classes):
            def fn(frame):
                return [(x, y, w, h, s) for x, y, w, h, s, cid in
                        _dnn_all(frame) if cid in classes]
            return fn

        annotators.update({
            # COCO: 0=person 14=bird 15=cat 16=dog 32=sports ball 39=bottle 41=cup 62=tv
            "person": {"label": "人", "tag": "person", "color": (0, 200, 255),
                       "enabled": False, "detect": _dnn({0})},
            "pet":    {"label": "宠物", "tag": "pet", "color": (255, 120, 0),
                       "enabled": False, "detect": _dnn({14, 15, 16})},
            "cup":    {"label": "水杯", "tag": "cup", "color": (0, 120, 255),
                       "enabled": False, "detect": _dnn({39, 41})},
            "ball":   {"label": "网球", "tag": "ball", "color": (0, 255, 255),
                       "enabled": False, "detect": _dnn({32})},
            "tv":     {"label": "屏幕", "tag": "tv", "color": (200, 0, 255),
                       "enabled": False, "detect": _dnn({62})},
            # 传统视觉 (无模型, 秒开)
            "tennis": {"label": "网球·色", "tag": "tennis", "color": (60, 220, 60),
                       "enabled": False, "detect": lambda f: [(x, y, w, h, s) for x, y, w, h, s, _ in detect_tennis_ball(f)]},
            "motion": {"label": "运动", "tag": "motion", "color": (255, 255, 0),
                       "enabled": False, "detect": lambda f: [(x, y, w, h, s) for x, y, w, h, s, _ in detect_motion(f, _motion_state)]},
            # P1 颜色识别 (HSV 可调), 也是 P2 颜色追踪的目标源
            "color": {"label": "颜色", "tag": "color", "color": (0, 220, 220),
                      "enabled": False,
                      "detect": lambda f: [(x, y, w, h, s) for x, y, w, h, s, _ in detect_color(f, color_cfg)]},
        })
    except Exception as e:
        log.add("sys", f"检测器注册失败: {e}")

    # P2 PID 追踪器 (人脸 / 颜色积木)
    pid_tracker = None
    if camera and ptz:
        try:
            from ..core.pid_tracker import PIDTracker
            pid_tracker = PIDTracker(
                camera, ptz, get_color_cfg=lambda: color_cfg,
                log=lambda msg: log.add("sys", msg))
        except Exception as e:
            log.add("sys", f"PID 追踪器初始化失败: {e}")

    # ========== /api/track (PID 追踪) ==========
    @app.route("/api/track", methods=["GET", "POST"])
    def track_api():
        if pid_tracker is None:
            return jsonify({"ok": False, "note": "追踪器不可用"}), 503
        if request.method == "POST":
            d = request.get_json(silent=True) or {}
            action = d.get("action")
            if action == "start":
                pid_tracker.set_params(kp=d.get("kp"), ki=d.get("ki"),
                                       kd=d.get("kd"), target=d.get("target"))
                pid_tracker.start()
            elif action == "stop":
                pid_tracker.stop()
            elif action == "params":
                pid_tracker.set_params(kp=d.get("kp"), ki=d.get("ki"),
                                       kd=d.get("kd"), target=d.get("target"))
        return jsonify({"ok": True, **pid_tracker.status()})

    # ========== /api/color_cfg (P1 颜色识别 HSV) ==========
    @app.route("/api/color_cfg", methods=["GET", "POST"])
    def color_cfg_api():
        if request.method == "POST":
            d = request.get_json(silent=True) or {}
            for k in ("h_min", "h_max", "s_min", "s_max", "v_min", "v_max"):
                if k in d:
                    hi = 180 if k.startswith("h") else 255
                    color_cfg[k] = max(0, min(hi, int(d[k])))
            log.add("sys", "颜色识别参数已更新")
        return jsonify(color_cfg)
    if camera:
        annotators["face"] = {
            "label": "人脸",
            "tag": "face",
            "color": (0, 255, 140),
            "enabled": False,
            "detect": lambda frame: [
                (int(cx - w / 2), int(cy - h / 2), int(w), int(h), float(score))
                for cx, cy, w, h, score in camera.detect_faces(frame)
            ],
        }

    # ========== /api/detect ==========
    @app.route("/api/detect", methods=["GET", "POST"])
    def detect_api():
        if request.method == "POST":
            data = request.get_json(silent=True) or {}
            name = data.get("name", "")
            if name in annotators:
                a = annotators[name]
                enabled = data.get("enabled")
                a["enabled"] = (not a["enabled"]) if enabled is None else bool(enabled)
                log.add("sys", f"标注[{a['label']}] {'开' if a['enabled'] else '关'}")
        def css(c):
            b, g, r = c
            return f"#{r:02x}{g:02x}{b:02x}"
        return jsonify({"detectors": [
            {"name": k, "label": v["label"], "enabled": v["enabled"],
             "color": css(v["color"])}
            for k, v in annotators.items()
        ]})

    # ========== /api/health ==========
    @app.route("/api/health")
    def health():
        return jsonify({"ok": True, "time": time.time()})

    # ========== /api/emotion ==========
    @app.route("/api/emotion", methods=["GET", "POST"])
    def set_emotion():
        if request.method == "POST":
            data = request.get_json(silent=True) or {}
            name = data.get("name", "neutral")
            duration = float(data.get("duration", 0))
        else:
            name = request.args.get("name", "neutral")
            duration = float(request.args.get("duration", 0))
        if emotion:
            emotion.set_emotion(name, duration=duration)
        log.add("emotion", f"设置表情 {name}")
        return jsonify({"emotion": name, "duration": duration})

    # ========== /api/emotions ==========
    @app.route("/api/emotions")
    def list_emotions():
        try:
            from petcar.drivers.oled import ALL_EMOTIONS
            return jsonify({"emotions": ALL_EMOTIONS})
        except Exception:
            return jsonify({"emotions": ["neutral", "happy", "sad", "angry",
                                         "surprised", "sleepy", "thinking"]})

    # ========== /api/chat ==========
    @app.route("/api/chat")
    def chat_api():
        text = request.args.get("text", "").strip()
        speak_flag = request.args.get("speak", "1") in ("1", "true", "yes")
        if not text:
            return jsonify({"error": "text 必填"}), 400
        if chat:
            resp = chat.chat(text)
            # 同步表情 + 异步 TTS 出声
            if emotion and resp.emotion:
                emotion.set_emotion(resp.emotion)
                if resp.reply and speak_flag:
                    emotion.start_speak(duration=max(2, len(resp.reply) * 0.15))
            if tts and resp.reply and speak_flag:
                threading.Thread(
                    target=tts.speak,
                    args=(resp.reply, resp.emotion),
                    daemon=True,
                ).start()
            log.add("chat", f"Q: {text[:30]} → {resp.reply[:30]}")
            return jsonify({
                "reply": resp.reply,
                "emotion": resp.emotion,
                "tools_called": resp.tools_called,
                "spoke": bool(tts and speak_flag),
            })
        return jsonify({
            "reply": f"(ChatAgent 未配置) {text}",
            "emotion": "neutral",
            "tools_called": [],
            "spoke": False,
        })

    # ========== /api/mood ==========
    @app.route("/api/mood")
    def mood_api():
        if mood_engine:
            s = mood_engine.get_state()
            return jsonify({
                "valence": round(s.valence, 3),
                "arousal": round(s.arousal, 3),
                "intensity": round(s.intensity, 3),
                "emotion": s.to_emotion(),
            })
        return jsonify({"emotion": "neutral", "note": "mood_engine 未连接"})

    # ========== /api/base/move ==========
    @app.route("/api/base/move", methods=["POST", "GET"])
    def base_move():
        if request.method == "GET":
            direction = request.args.get("direction", "forward")
            duration = float(request.args.get("duration", 2))
        else:
            data = request.get_json(silent=True) or {}
            direction = data.get("direction", "forward")
            duration = float(data.get("duration", 2))

        if mecanum:
            mecanum.move_for_duration(direction, duration)
        log.add("move", f"{direction} {duration}s")
        return jsonify({"direction": direction, "duration": duration})

    # ========== /api/base/speed ==========
    @app.route("/api/base/speed", methods=["POST"])
    def base_speed():
        data = request.get_json(silent=True) or {}
        speed = int(data.get("speed", config.MOTOR_NORMAL_SPEED))
        if mecanum:
            mecanum.set_speed(speed)
            speed = mecanum.normal_speed
        log.add("move", f"速度设为 {speed}")
        return jsonify({"speed": speed})

    # ========== /api/estop ==========
    @app.route("/api/estop", methods=["POST", "GET"])
    def estop():
        if mecanum:
            mecanum.stop()
        if camera:
            try:
                camera.stop_face_tracking()
            except Exception:
                pass
        log.add("sys", "急停!")
        return jsonify({"ok": True, "stopped": True})

    # ========== /api/ptz ==========
    @app.route("/api/ptz", methods=["POST", "GET"])
    def ptz_api():
        if request.method == "GET":
            direction = request.args.get("direction", "center")
            delta = float(request.args.get("delta", 10))
        else:
            data = request.get_json(silent=True) or {}
            direction = data.get("direction", "center")
            delta = float(data.get("delta", 10))

        if ptz:
            if direction == "up": ptz.look_up(delta)
            elif direction == "down": ptz.look_down(delta)
            elif direction == "left": ptz.look_left(delta)
            elif direction == "right": ptz.look_right(delta)
            else: ptz.look_center()
            log.add("ptz", f"{direction} Δ{delta} → H{ptz.h_cur:.0f} V{ptz.v_cur:.0f}")
            return jsonify({"direction": direction, "delta": delta,
                            "h": ptz.h_cur, "v": ptz.v_cur})
        return jsonify({"direction": direction, "delta": delta})

    # ========== /api/photo ==========
    @app.route("/api/photo")
    def photo_api():
        if camera:
            path = camera.take_photo()
            log.add("photo", f"拍照 → {os.path.basename(path) if path else '失败'}")
            return jsonify({"path": path})
        return jsonify({"path": None, "note": "camera 未连接"})

    # ========== /api/photo/latest ==========
    @app.route("/api/photo/latest")
    def photo_latest():
        try:
            files = [os.path.join(config.PHOTO_DIR, f)
                     for f in os.listdir(config.PHOTO_DIR)
                     if f.lower().endswith((".jpg", ".jpeg", ".png"))]
            if not files:
                return jsonify({"error": "还没有照片"}), 404
            return send_file(max(files, key=os.path.getmtime))
        except Exception as e:
            return jsonify({"error": str(e)}), 404

    # ========== /api/faces ==========
    @app.route("/api/faces")
    def faces_api():
        if camera:
            faces = camera.detect_faces()
            simple = [{"cx": f[0], "cy": f[1], "w": f[2], "h": f[3], "score": round(f[4], 2)} for f in faces]
            return jsonify({"count": len(faces), "faces": simple})
        return jsonify({"count": 0})

    # ========== /api/video_feed (MJPEG) ==========
    @app.route("/api/video_feed")
    def video_feed():
        if camera is None:
            return jsonify({"error": "camera 未连接"}), 503

        def gen():
            import cv2
            # 摄像头是懒打开的: 视频流请求时确保已打开
            if not getattr(camera, "is_open", camera.cap is not None):
                try:
                    camera.open()
                except Exception as e:
                    log.add("sys", f"摄像头打开失败: {e}")
            last_frame_at = time.time()
            while True:
                frame = camera.latest_frame() if hasattr(camera, "latest_frame") else None
                if frame is None:
                    # 长时间无帧 (摄像头被关/采集线程异常): 断开让前端重连
                    if time.time() - last_frame_at > 15:
                        log.add("sys", "视频流无帧超时, 断开等待前端重连")
                        return
                    time.sleep(0.2)
                    continue
                last_frame_at = time.time()
                # 画框: 已开启的检测标注 + PID 追踪目标 (需画就先拷贝, 不污染共享帧)
                try:
                    track_box = (pid_tracker.last_box if pid_tracker
                                 and pid_tracker.running else None)
                    active = [a for a in annotators.values() if a["enabled"]]
                    if active or track_box:
                        frame = frame.copy()
                        for a in active:
                            for (x, y, w, h, score) in a["detect"](frame):
                                cv2.rectangle(frame, (x, y), (x + w, y + h), a["color"], 2)
                                cv2.putText(frame, f"{a['tag']} {score:.2f}",
                                            (x, max(12, y - 6)),
                                            cv2.FONT_HERSHEY_SIMPLEX, 0.45, a["color"], 1)
                        if track_box:
                            x, y, w, h = track_box
                            c_red = (60, 60, 255)
                            cv2.rectangle(frame, (x - 3, y - 3), (x + w + 3, y + h + 3), c_red, 3)
                            cv2.circle(frame, (x + w // 2, y + h // 2), 5, c_red, -1)
                            cv2.putText(frame, "TRACK", (x, max(14, y - 10)),
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, c_red, 2)
                except Exception:
                    pass
                try:
                    ok, jpg = cv2.imencode(".jpg", frame,
                                           [cv2.IMWRITE_JPEG_QUALITY, 70])
                except Exception:
                    continue
                if not ok:
                    continue
                yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
                       + jpg.tobytes() + b"\r\n")
                time.sleep(1.0 / 15)   # 上限 15fps, 省 CPU

        return Response(gen(),
                        mimetype="multipart/x-mixed-replace; boundary=frame")

    # ========== /api/camera/open /close ==========
    @app.route("/api/camera/open", methods=["POST"])
    def camera_open():
        if camera is None:
            return jsonify({"ok": False, "open": False, "note": "camera 未连接"}), 503
        if not camera.is_open:
            ok = camera.open()
            log.add("sys", "摄像头打开" if ok else "摄像头打开失败")
        return jsonify({"ok": camera.is_open, "open": camera.is_open})

    @app.route("/api/camera/close", methods=["POST"])
    def camera_close():
        if camera is None:
            return jsonify({"ok": True, "open": False})
        camera.close()
        log.add("sys", "摄像头已关闭")
        return jsonify({"ok": True, "open": False})

    # ========== /api/skills ==========
    @app.route("/api/skills")
    def skills_list():
        if not skill_manager:
            return jsonify({"skills": []})
        skills = []
        for spec in skill_manager.list_tool_specs():
            fn = spec.get("function", {})
            skills.append({
                "name": fn.get("name"),
                "description": fn.get("description", ""),
                "parameters": fn.get("parameters", {}),
            })
        return jsonify({"skills": skills})

    # ========== /api/skill/run ==========
    @app.route("/api/skill/run", methods=["POST"])
    def skill_run():
        if not skill_manager:
            return jsonify({"ok": False, "result": "SkillManager 未连接"}), 503
        data = request.get_json(silent=True) or {}
        name = data.get("name", "")
        params = data.get("params", {}) or {}
        if not isinstance(params, dict):
            return jsonify({"ok": False, "result": "params 必须是对象"}), 400

        t0 = time.time()
        try:
            result = skill_manager.execute(name, **params)
            ok = not str(result).startswith(("执行出错", "参数不对", "抱歉"))
        except Exception as e:
            result, ok = f"执行异常: {e}", False
        dt = round((time.time() - t0) * 1000)
        log.add("skill", f"{name}{params} → {str(result)[:40]} ({dt}ms)")
        return jsonify({"ok": ok, "result": str(result), "ms": dt})

    # ========== /api/status ==========
    @app.route("/api/status")
    def status():
        out: dict[str, Any] = {
            "ok": True,
            "uptime_s": round(time.time() - _START_TIME),
            "system": _sys_stats(),
        }
        # 心情
        if mood_engine:
            s = mood_engine.get_state()
            out["mood"] = {
                "valence": round(s.valence, 3),
                "arousal": round(s.arousal, 3),
                "intensity": round(s.intensity, 3),
                "emotion": s.to_emotion(),
            }
        # 表情 (实际显示中的)
        if emotion:
            try:
                out["emotion_display"] = emotion.get_emotion()
            except Exception:
                pass
        # 云台
        if ptz:
            out["ptz"] = {"h": round(ptz.h_cur, 1), "v": round(ptz.v_cur, 1)}
        # 底盘
        if mecanum:
            out["base"] = {
                "speed": mecanum.normal_speed,
                "command": getattr(mecanum, "current_command", None),
            }
        # 摄像头
        if camera:
            out["camera"] = {
                "open": bool(getattr(camera, "is_open", camera.cap is not None)),
                "tracking": bool(getattr(camera, "tracking", False)),
                "width": camera.width, "height": camera.height,
            }
        # 配置
        out["config"] = {
            "llm_backend": config.LLM_BACKEND,
            "llm_model": getattr(config, "OLLAMA_MODEL", ""),
            "asr_mode": config.ASR_MODE,
            "tts_mode": config.TTS_MODE,
            "pet_name": config.PET_NAME,
        }
        return jsonify(out)

    # ========== /api/logs ==========
    @app.route("/api/logs")
    def logs_api():
        n = int(request.args.get("n", 50))
        return jsonify({"logs": log.recent(n)})

    # ========== /api/tts ==========
    @app.route("/api/tts", methods=["POST"])
    def tts_api():
        data = request.get_json(silent=True) or {}
        text = (data.get("text") or "").strip()
        if not text:
            return jsonify({"ok": False, "note": "text 必填"}), 400
        if tts:
            tts.speak_async(text)
            log.add("tts", f"朗读: {text[:30]}")
            return jsonify({"ok": True})
        return jsonify({"ok": False, "note": "tts 未连接"}), 503

    # ========== /api/asr/once ==========
    @app.route("/api/asr/once", methods=["POST"])
    def asr_once():
        if asr is None:
            return jsonify({"ok": False, "note": "asr 未连接"}), 503
        if asr_job["running"]:
            return jsonify({"ok": False, "note": "上一次识别还没结束"}), 409

        def work():
            asr_job["running"] = True
            asr_job["done"] = False
            asr_job["result"] = None
            try:
                log.add("asr", "开始识别 (whisper 模式需在小车终端按 Enter)")
                asr_job["result"] = asr.listen(timeout=6)
                log.add("asr", f"识别结果: {asr_job['result'] or '(没听清)'}")
            except Exception as e:
                asr_job["result"] = f"识别异常: {e}"
            finally:
                asr_job["running"] = False
                asr_job["done"] = True

        threading.Thread(target=work, daemon=True).start()
        return jsonify({"ok": True, "running": True})

    @app.route("/api/asr/result")
    def asr_result():
        return jsonify(asr_job)

    # ========== 中控面板 ==========
    @app.route("/")
    @app.route("/dashboard")
    def index():
        return send_file(os.path.join(app.static_folder, "dashboard.html"))

    return app
