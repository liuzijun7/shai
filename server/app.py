"""WebSocket 服务器：把浏览器发来的消息交给房间，再把每个人该看到的局面发回去。

规则和房间逻辑都不在这里。这个文件只管连接。
"""

from __future__ import annotations

import os
import random
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

from shai.data import SCENES

from .rooms import SIDES, Room, RoomError, character_catalog

WEB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web")

app = FastAPI(title="晒")
rooms: dict[str, Room] = {}
sockets: dict[tuple[str, str], WebSocket] = {}      # (房间号, 哪一方) -> 连接


def _art_names() -> list[str]:
    """本机有图的人物。人物图不在仓库里，没有图的人物网页用圆圈加名字顶替。"""
    folder = os.path.join(WEB_DIR, "assets", "characters")
    if not os.path.isdir(folder):
        return []
    return sorted(name[:-4] for name in os.listdir(folder) if name.endswith(".png"))


def _new_code() -> str:
    while True:
        code = f"{random.randint(0, 9999):04d}"
        if code not in rooms:
            return code


async def _broadcast(room: Room) -> None:
    for side in SIDES:
        socket = sockets.get((room.code, side))
        if socket is None:
            continue
        try:
            await socket.send_json(room.state_for(side))
        except Exception:                            # 对方刚好断线：下次重连时会补发
            sockets.pop((room.code, side), None)
            room.leave(side)


@app.websocket("/ws")
async def websocket_endpoint(socket: WebSocket) -> None:
    await socket.accept()
    room: Room | None = None
    side: str | None = None
    try:
        while True:
            message: dict[str, Any] = await socket.receive_json()
            try:
                if message.get("t") == "join":
                    code = str(message.get("room") or "").strip() or _new_code()
                    target = rooms.setdefault(code, Room(code))
                    new_side, token = target.join(str(message.get("name") or ""), message.get("token"))
                    if room is not None and side is not None:
                        sockets.pop((room.code, side), None)
                        room.leave(side)
                    room, side = target, new_side
                    old = sockets.get((room.code, side))
                    if old is not None and old is not socket:       # 同一个人在别处又开了一个页面
                        await old.close()
                    sockets[(room.code, side)] = socket
                    await socket.send_json({"t": "joined", "room": room.code, "side": side, "token": token,
                                            "characters": character_catalog(), "scenes": [{"name": n, "height": SCENES[n]["height"]} for n in SCENES],
                                            "art": _art_names()})
                    room.drive()
                elif room is None or side is None:
                    raise RoomError("请先进入房间。")
                else:
                    room.handle(side, message)
            except RoomError as error:
                await socket.send_json({"t": "error", "message": str(error)})
            if room is not None:
                await _broadcast(room)
    except WebSocketDisconnect:
        pass
    finally:
        if room is not None and side is not None and sockets.get((room.code, side)) is socket:
            sockets.pop((room.code, side), None)
            room.leave(side)
            await _broadcast(room)


class FreshStatic(StaticFiles):
    """网页文件每次都向服务器确认是不是最新的，这样更新代码后不用清浏览器缓存。"""

    async def get_response(self, path: str, scope: Any):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache"
        return response


app.mount("/", FreshStatic(directory=WEB_DIR, html=True), name="web")
