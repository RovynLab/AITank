# -*- coding: utf-8 -*-
"""开发机极简启动脚本：跳过所有硬件模块，只起 Flask 静态文件服务 + Mock 积木 API"""
import os, sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from petcar.api.flask_app import create_app

# ====== Mock block_service 和 pid_tracker ======
class MockBlockService:
    """最小实现让 register_block_api 可以注册路由"""
    def is_running(self): return False
    def run(self, program, **kw): return 0
    def stop(self, estop=False): pass
    def poll_status(self): return {"state": "idle", "logs": [], "elapsed": 0, "run_id": 0}
    def program_annotator_keys(self): return set()

class MockPidTracker:
    pid = None
    def is_alive(self): return False

mock_block_service = MockBlockService()
mock_pid_tracker = MockPidTracker()

app = create_app(block_service=mock_block_service, pid_tracker=mock_pid_tracker)

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    print(f"[Dev Flask] 启动在 http://localhost:{port}")
    print(f"[Dev Flask] 积木页面 http://localhost:{port}/static/blocks/index.html")
    print(f"[Dev Flask] Schema http://localhost:{port}/api/blocks/schema")
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False, threaded=True)
