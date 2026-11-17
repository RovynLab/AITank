# -*- coding: utf-8 -*-
"""petcar/api/block_api.py — 积木编程 Web API
==============================================
GET  /blocks                积木编辑器页面
GET  /api/blocks/schema     积木目录
POST /api/blocks/run        运行 {program}
POST /api/blocks/stop       正常停止
POST /api/blocks/estop      急停
GET  /api/blocks/status     运行状态 + 增量日志

文件管理:
GET  /api/blocks/files                    列出所有积木文件（含示例）
POST /api/blocks/files/save               保存到用户目录 {name, program}
GET  /api/blocks/files/content?path=...   读取文件内容
POST /api/blocks/files/delete             删除用户文件 {path}
POST /api/blocks/files/rename             重命名/移动 {src, dst}
GET  /api/blocks/files/export?path=...    下载单个文件
"""

from __future__ import annotations

import json
import os
import shutil
import time

from flask import jsonify, request, send_file

from ..blocks.catalog import get_schema
from ..blocks.compiler import CompileError
from ..blocks.service import BusyError


# ============================================================================
# 文件存储布局（在 Pi 上 ~/.aitank/blocks/）
#   examples/   ← 板上固定示例，只读（随程序预装，升级时覆盖）
#   user/       ← 用户自己的积木
# ============================================================================
_BLOCKS_ROOT = os.environ.get(
    "PETCAR_BLOCKS_DIR",
    os.path.join(os.path.expanduser("~"), ".aitank", "blocks"),
)
EXAMPLES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "blocks", "examples")
USER_DIR = os.path.join(_BLOCKS_ROOT, "user")


def _ensure_dirs():
    os.makedirs(USER_DIR, exist_ok=True)


def _safe_join(base: str, rel: str) -> str | None:
    """安全拼接路径，防穿越"""
    if not rel:
        return None
    rel = rel.lstrip("/\\").replace("..", "_")
    full = os.path.realpath(os.path.join(base, rel))
    if not full.startswith(os.path.realpath(base)):
        return None
    return full


def _is_safe_name(name: str) -> bool:
    """文件名只允许中文/英文/数字/下划线/空格，不含扩展名"""
    if not name or len(name) > 80:
        return False
    base = os.path.splitext(name)[0]
    for ch in base:
        if not (ch.isalnum() or ch in " _-." or '\u4e00' <= ch <= '\u9fff'):
            return False
    return True


def _list_dir(base: str, prefix: str, readonly: bool) -> list:
    """列出目录下的 .json 文件，返回 [{path, name, size, mtime, readonly}]"""
    out = []
    try:
        for root, dirs, files in os.walk(base):
            rel_root = os.path.relpath(root, base)
            for fn in sorted(files):
                if not fn.lower().endswith(".json"):
                    continue
                full = os.path.join(root, fn)
                rel = os.path.join(rel_root, fn) if rel_root != "." else fn
                stat = os.stat(full)
                out.append({
                    "path": f"{prefix}/{rel.replace(os.sep, '/')}",
                    "name": os.path.splitext(fn)[0],
                    "size": stat.st_size,
                    "mtime": stat.st_mtime,
                    "mtime_text": time.strftime(
                        "%Y-%m-%d %H:%M", time.localtime(stat.st_mtime)),
                    "readonly": readonly,
                })
    except FileNotFoundError:
        pass
    return out


def register_block_api(app, service, pid_tracker=None):
    """把积木相关路由注册到现有 Flask app"""

    @app.route("/blocks")
    @app.route("/blocks/")
    def blocks_page():
        return send_file(
            os.path.join(app.static_folder, "blocks", "index.html"))

    @app.route("/api/blocks/schema")
    def blocks_schema():
        return jsonify(get_schema())

    # ========================================================================
    # 文件管理 API
    # ========================================================================

    @app.route("/api/blocks/files")
    def files_list():
        _ensure_dirs()
        examples = _list_dir(EXAMPLES_DIR, "examples", readonly=True)
        user = _list_dir(USER_DIR, "user", readonly=False)
        return jsonify({
            "root": _BLOCKS_ROOT,
            "examples_dir": EXAMPLES_DIR,
            "user_dir": USER_DIR,
            "examples": examples,
            "user": user,
        })

    @app.route("/api/blocks/files/content")
    def files_content():
        path = request.args.get("path", "").strip()
        if not path:
            return jsonify({"ok": False, "error": "path 必填"}), 400
        parts = path.split("/", 1)
        if len(parts) != 2:
            return jsonify({"ok": False, "error": "path 格式错误"}), 400
        prefix, rel = parts
        if prefix == "examples":
            base = EXAMPLES_DIR
            readonly = True
        elif prefix == "user":
            base = USER_DIR
            readonly = False
        else:
            return jsonify({"ok": False, "error": "未知目录"}), 400
        full = _safe_join(base, rel)
        if full is None or not os.path.isfile(full):
            return jsonify({"ok": False, "error": "文件不存在"}), 404
        try:
            with open(full, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            return jsonify({"ok": False, "error": f"读取失败: {e}"}), 500
        return jsonify({"ok": True, "program": data, "readonly": readonly})

    @app.route("/api/blocks/files/save", methods=["POST"])
    def files_save():
        """保存到用户目录。body: {name, program, path?}"""
        _ensure_dirs()
        d = request.get_json(silent=True) or {}
        program = d.get("program")
        if not isinstance(program, dict):
            return jsonify({"ok": False, "error": "program 必填"}), 400
        # 校验 JSON 可序列化
        try:
            text = json.dumps(program, ensure_ascii=False, indent=2)
        except Exception as e:
            return jsonify({"ok": False, "error": f"program 不是合法 JSON: {e}"}), 400

        # 确定目标文件
        if d.get("path"):
            # 已有路径（覆盖）
            parts = d["path"].split("/", 1)
            if len(parts) != 2 or parts[0] != "user":
                return jsonify({"ok": False, "error": "只能保存到 user 目录"}), 400
            full = _safe_join(USER_DIR, parts[1])
            if full is None:
                return jsonify({"ok": False, "error": "路径不合法"}), 400
        else:
            # 新建：用 name
            name = (d.get("name") or "").strip()
            if not _is_safe_name(name):
                return jsonify({"ok": False, "error": "文件名不合法（1-80字，只能是中英文数字下划线）"}), 400
            full = os.path.join(USER_DIR, name + ".json")
        try:
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "w", encoding="utf-8") as f:
                f.write(text)
            stat = os.stat(full)
            rel = os.path.relpath(full, USER_DIR).replace(os.sep, "/")
        except Exception as e:
            return jsonify({"ok": False, "error": f"保存失败: {e}"}), 500
        return jsonify({
            "ok": True,
            "path": f"user/{rel}",
            "name": os.path.splitext(os.path.basename(full))[0],
            "size": stat.st_size,
            "mtime": stat.st_mtime,
        })

    @app.route("/api/blocks/files/delete", methods=["POST"])
    def files_delete():
        d = request.get_json(silent=True) or {}
        path = d.get("path", "")
        parts = path.split("/", 1) if path else []
        if len(parts) != 2 or parts[0] != "user":
            return jsonify({"ok": False, "error": "只能删除 user 目录下的文件"}), 400
        full = _safe_join(USER_DIR, parts[1])
        if full is None or not os.path.exists(full):
            return jsonify({"ok": False, "error": "文件不存在"}), 404
        try:
            os.remove(full)
        except Exception as e:
            return jsonify({"ok": False, "error": f"删除失败: {e}"}), 500
        return jsonify({"ok": True})

    @app.route("/api/blocks/files/rename", methods=["POST"])
    def files_rename():
        """重命名或移动（均在 user 目录内）。body: {src, dst}"""
        d = request.get_json(silent=True) or {}
        src = d.get("src", "")
        dst = d.get("dst", "")
        if not src or not dst:
            return jsonify({"ok": False, "error": "src 和 dst 必填"}), 400
        for label, p in (("src", src), ("dst", dst)):
            parts = p.split("/", 1)
            if len(parts) != 2 or parts[0] != "user":
                return jsonify({"ok": False, "error": f"{label} 必须在 user 目录"}), 400
        src_full = _safe_join(USER_DIR, src.split("/", 1)[1])
        dst_full = _safe_join(USER_DIR, dst.split("/", 1)[1])
        if src_full is None or dst_full is None:
            return jsonify({"ok": False, "error": "路径不合法"}), 400
        if not os.path.exists(src_full):
            return jsonify({"ok": False, "error": "源文件不存在"}), 404
        if os.path.exists(dst_full):
            return jsonify({"ok": False, "error": "目标已存在"}), 400
        try:
            os.makedirs(os.path.dirname(dst_full), exist_ok=True)
            os.rename(src_full, dst_full)
        except Exception as e:
            return jsonify({"ok": False, "error": f"重命名失败: {e}"}), 500
        return jsonify({"ok": True})

    @app.route("/api/blocks/files/export")
    def files_export():
        path = request.args.get("path", "").strip()
        parts = path.split("/", 1) if path else []
        if len(parts) != 2:
            return jsonify({"ok": False, "error": "path 必填"}), 400
        if parts[0] == "examples":
            base = EXAMPLES_DIR
        elif parts[0] == "user":
            base = USER_DIR
        else:
            return jsonify({"ok": False, "error": "未知目录"}), 400
        full = _safe_join(base, parts[1])
        if full is None or not os.path.isfile(full):
            return jsonify({"ok": False, "error": "文件不存在"}), 404
        name = os.path.basename(full)
        return send_file(full, as_attachment=True, download_name=name,
                         mimetype="application/json")

    # ========================================================================
    # 运行控制（不变）
    # ========================================================================
    @app.route("/api/blocks/run", methods=["POST"])
    def blocks_run():
        data = request.get_json(silent=True) or {}
        program = data.get("program")
        if not isinstance(program, dict):
            return jsonify({
                "ok": False,
                "errors": [{"blockId": None, "message": "缺少程序内容"}],
            }), 400

        try:
            result = service.run(program)
        except BusyError:
            return jsonify({
                "ok": False,
                "error": "already_running",
                "message": "已有程序在运行，请先停止",
            }), 409
        except CompileError as e:
            return jsonify({"ok": False, "errors": e.errors}), 400
        except Exception as e:
            return jsonify({
                "ok": False,
                "errors": [{"blockId": None, "message": f"启动失败: {e}"}],
            }), 500

        return jsonify({"ok": True, **result})

    @app.route("/api/blocks/stop", methods=["POST"])
    def blocks_stop():
        service.stop(estop=False)
        return jsonify({"ok": True})

    @app.route("/api/blocks/estop", methods=["POST"])
    def blocks_estop():
        service.stop(estop=True)
        return jsonify({"ok": True})

    @app.route("/api/blocks/status")
    def blocks_status():
        try:
            since = int(request.args.get("since", 0))
        except (TypeError, ValueError):
            since = 0
        return jsonify(service.status(since=since))
