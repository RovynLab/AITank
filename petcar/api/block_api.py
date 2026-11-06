# -*- coding: utf-8 -*-
"""petcar/api/block_api.py — 积木编程 Web API
==============================================
GET  /blocks                积木编辑器页面
GET  /api/blocks/schema     积木目录
POST /api/blocks/run        运行 {program}
POST /api/blocks/stop       正常停止
POST /api/blocks/estop      急停
GET  /api/blocks/status     运行状态 + 增量日志
"""

from __future__ import annotations

import os

from flask import jsonify, request, send_file

from ..blocks.catalog import get_schema
from ..blocks.compiler import CompileError
from ..blocks.service import BusyError


def register_block_api(app, service):
    """把积木相关路由注册到现有 Flask app"""

    @app.route("/blocks")
    @app.route("/blocks/")
    def blocks_page():
        return send_file(
            os.path.join(app.static_folder, "blocks", "index.html"))

    @app.route("/api/blocks/schema")
    def blocks_schema():
        return jsonify(get_schema())

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
