"""启动联机服务器。

    python run_server.py              本机试玩：浏览器打开 http://localhost:8765
    python run_server.py --host 0.0.0.0 --port 8765      让同一个网络里的别人也能连

第一次用之前要装依赖：pip install -r requirements.txt
"""

from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)
sys.path.insert(0, ROOT)

try:
    import uvicorn
except ImportError:                                   # 这台电脑把库装在 D:\pylibs
    if os.path.isdir(r"D:\pylibs"):
        sys.path.append(r"D:\pylibs")
    import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(description="《晒》联机服务器")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    for stream in (sys.stdout, sys.stderr):           # 有些 Windows 终端不是 UTF-8，直接打印中文会报错
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    print(f"服务器已启动。浏览器打开 http://localhost:{args.port}")
    uvicorn.run("server.app:app", host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
