import http.server
import json
import logging
import socketserver
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

PORT = 7860
SCRIPT_DIR = Path(__file__).parent.resolve()
STATUS_FILE = SCRIPT_DIR.parent / "logs" / "status.json"
DASHBOARD_HTML = SCRIPT_DIR / "dashboard.html"

class DashboardHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/":
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            try:
                self.wfile.write(DASHBOARD_HTML.read_bytes())
            except Exception as e:
                self.wfile.write(f"Error loading dashboard: {e}".encode())
        
        elif self.path == "/api/status":
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            try:
                if STATUS_FILE.exists():
                    self.wfile.write(STATUS_FILE.read_bytes())
                else:
                    self.wfile.write(json.dumps({"state": "idle", "error": "Status file not found"}).encode())
            except Exception as e:
                 self.wfile.write(json.dumps({"error": str(e)}).encode())
        else:
            self.send_error(404)

    def log_message(self, format, *args):
        # 禁止打印请求日志到控制台，以免刷屏
        pass

class ThreadingServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

def start_server(port=PORT):
    """启动 Dashboard 服务器（阻塞式，需在线程中运行）。"""
    try:
        # 显式绑定到 0.0.0.0
        with ThreadingServer(("0.0.0.0", port), DashboardHandler) as httpd:
            # 实际绑定成功后打印日志
            sa = httpd.socket.getsockname()
            logger.info(f"📊 Dashboard running at http://{sa[0]}:{sa[1]}")
            httpd.serve_forever()
    except Exception as e:
        logger.error(f"❌ Dashboard Server Error: {e}", exc_info=True)

def run_dashboard_bg():
    """在后台线程启动 Dashboard 服务器。"""
    t = threading.Thread(target=start_server, daemon=True)
    t.start()
    return t

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    start_server()
