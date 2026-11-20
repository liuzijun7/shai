"""WebSocket 服务器：把浏览器发来的消息交给房间，再把每个人该看到的局面发回去。

规则和房间逻辑都不在这里。这个文件只管三件事：连接、每秒检查一次限时、把打完的对局存成文件。
"""

from __future__ import annotations

import asyncio
import json
import os
import random
import re
import time
import traceback
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from shai.data import SCENES
from shai.describe import codex

from .rooms import Room, RoomError, character_catalog, is_watcher

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB_DIR = os.path.join(ROOT, "web")
# 战报和回放文件放在哪里。里面有玩家的昵称，所以这个文件夹不进公开仓库（见 .gitignore）。
REPLAY_DIR = os.environ.get("SHAI_REPLAY_DIR") or os.path.join(ROOT, "replays")
REPLAY_ID = re.compile(r"^[0-9A-Za-z_-]{1,60}$")
REPLAY_LIST_MAX = 50
IDLE_ROOM_SECONDS = 3 * 3600        # 没有人连着的房间过这么久就清掉

rooms: dict[str, Room] = {}
sockets: dict[str, dict[str, WebSocket]] = {}       # 房间号 -> {身份 -> 连接}
last_active: dict[str, float] = {}


def _art_names() -> list[str]:
    """本机有图的人物。人物图不在仓库里，没有图的人物网页用圆圈加名字顶替。"""
    folder = os.path.join(WEB_DIR, "assets", "characters")
    if not os.path.isdir(folder):
        return []
    return sorted(name[:-4] for name in os.listdir(folder) if name.endswith(".png"))


def _defense_art() -> list[str]:
    """本机有的防御手绘图标（从本子照片里抠的，不在仓库里）。没有的时候网页只显示文字。"""
    folder = os.path.join(WEB_DIR, "assets", "defense")
    if not os.path.isdir(folder):
        return []
    return sorted(name[:-4] for name in os.listdir(folder) if name.endswith(".png"))


def _names(folder: str) -> list[str]:
    """web/assets/<folder>/ 里的图片名字（不带扩展名）。这些素材只在本机，不在仓库里。"""
    path = os.path.join(WEB_DIR, "assets", folder)
    if not os.path.isdir(path):
        return []
    return sorted(os.path.splitext(name)[0] for name in os.listdir(path)
                  if name.lower().endswith((".png", ".jpg", ".jpeg", ".webp")))


def _stamp() -> int:
    """网页文件最后一次改动的时间。页面发现自己比这个旧，就自己刷新一次，免得一直用着改到一半的旧页面。"""
    latest = 0.0
    for name in os.listdir(WEB_DIR):
        if name.endswith((".js", ".css", ".html")):
            latest = max(latest, os.path.getmtime(os.path.join(WEB_DIR, name)))
    return int(latest)


def _assets() -> dict[str, Any]:
    return {"art": _art_names(), "defense_art": _defense_art(), "backgrounds": _backgrounds(),
            "effects": _names("effects"), "ui": _names("ui"), "stamp": _stamp()}


def _backgrounds() -> list[str]:
    """本机放的对战背景图（web/assets/backgrounds/，不在仓库里）。没有的时候网页用画出来的擂台。"""
    folder = os.path.join(WEB_DIR, "assets", "backgrounds")
    if not os.path.isdir(folder):
        return []
    return sorted(name for name in os.listdir(folder) if name.lower().endswith((".png", ".jpg", ".jpeg", ".webp")))


def _scene_list() -> list[dict[str, Any]]:
    return [{"name": name, "height": SCENES[name]["height"]} for name in SCENES]


def _new_code() -> str:
    while True:
        code = f"{random.randint(0, 9999):04d}"
        if code not in rooms:
            return code


# ---------- 战报和回放文件 ----------

def save_replay(record: dict[str, Any]) -> str:
    """把一局的记录存成三样：完整记录（回放用）、文字战报、目录里的一行摘要。返回回放编号。"""
    os.makedirs(REPLAY_DIR, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(record["ended_at"]))
    code = re.sub(r"[^0-9A-Za-z_-]", "", str(record["room"]))[:8] or "room"
    replay_id, n = f"{stamp}-{code}", 1
    while os.path.exists(os.path.join(REPLAY_DIR, replay_id + ".json")):
        n += 1
        replay_id = f"{stamp}-{code}-{n}"
    record = dict(record, id=replay_id)
    with open(os.path.join(REPLAY_DIR, replay_id + ".json"), "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False)
    names, teams, winner = record["names"], record["teams"], record["winner"]
    result = "平局" if winner is None else f"{winner}（{names[winner]}）获胜"
    lines = [
        "《晒》对战战报",
        "时间：" + time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(record["ended_at"])),
        f"房间：{record['room']}",
        f"A：{names['A']}（{'、'.join(teams['A'])}）",
        f"B：{names['B']}（{'、'.join(teams['B'])}）",
        f"结果：{result}，共 {record['rounds']} 回合",
        "",
    ] + [event["text"] for event in record["events"] if event["t"] == "log"]
    with open(os.path.join(REPLAY_DIR, replay_id + ".txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    summary = {key: record[key] for key in ("id", "ended_at", "room", "names", "bots", "teams", "winner", "rounds")}
    with open(os.path.join(REPLAY_DIR, "index.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(summary, ensure_ascii=False) + "\n")
    return replay_id


def _save_if_finished(room: Room) -> None:
    if room.finished is None or room.replay_id is not None:
        return
    try:
        room.replay_id = save_replay(room.finished)
    except Exception:                                # 存不了（比如磁盘满了）不能影响对战
        traceback.print_exc()
        room.replay_id = ""


def _replay_path(replay_id: str, extension: str) -> str:
    if not REPLAY_ID.match(replay_id):
        raise HTTPException(status_code=404, detail="没有这个回放")
    path = os.path.join(REPLAY_DIR, replay_id + extension)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="没有这个回放")
    return path


# ---------- 把局面发给每个人 ----------

async def _broadcast(room: Room) -> None:
    _save_if_finished(room)
    for key, socket in list(sockets.get(room.code, {}).items()):
        try:
            await socket.send_json(room.state_for(key))
        except Exception:                            # 对方刚好断线：下次重连时会补发
            _drop(room, key, socket)


def _drop(room: Room, key: str, socket: WebSocket) -> None:
    held = sockets.get(room.code, {})
    if held.get(key) is socket:
        held.pop(key, None)
        room.leave(key)


async def _ticker() -> None:
    """每秒看一次有没有人超时；顺手清掉很久没人的房间。"""
    count = 0
    while True:
        await asyncio.sleep(1)
        count += 1
        for room in list(rooms.values()):
            try:
                if room.tick():
                    await _broadcast(room)
            except Exception:
                traceback.print_exc()
        if count % 60 == 0:
            now = time.monotonic()
            for code in list(rooms):
                if sockets.get(code):
                    last_active[code] = now
                elif now - last_active.get(code, now) > IDLE_ROOM_SECONDS:
                    rooms.pop(code, None)
                    sockets.pop(code, None)
                    last_active.pop(code, None)


@asynccontextmanager
async def lifespan(_: FastAPI):
    task = asyncio.create_task(_ticker())
    yield
    task.cancel()


app = FastAPI(title="晒", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)


@app.get("/api/info")
def info() -> dict[str, Any]:
    """看回放的时候没有进房间，网页从这里拿场景表和有图的人物。"""
    return {"scenes": _scene_list(), **_assets()}


@app.get("/api/codex")
def get_codex() -> dict[str, Any]:
    """图鉴：每个招、每个人物、每种内功和状态的说明文字。悬浮描述框也用这一份。"""
    return codex()


@app.get("/api/replays")
def list_replays() -> list[dict[str, Any]]:
    path = os.path.join(REPLAY_DIR, "index.jsonl")
    if not os.path.isfile(path):
        return []
    with open(path, encoding="utf-8") as f:
        lines = f.readlines()[-REPLAY_LIST_MAX:]
    result = []
    for line in reversed(lines):
        try:
            result.append(json.loads(line))
        except ValueError:
            continue
    return result


@app.get("/api/replays/{replay_id}")
def get_replay(replay_id: str) -> FileResponse:
    return FileResponse(_replay_path(replay_id, ".json"), media_type="application/json")


@app.get("/api/replays/{replay_id}/log")
def get_replay_log(replay_id: str) -> FileResponse:
    return FileResponse(_replay_path(replay_id, ".txt"), media_type="text/plain; charset=utf-8",
                        filename=f"shai-{replay_id}.txt")


@app.websocket("/ws")
async def websocket_endpoint(socket: WebSocket) -> None:
    await socket.accept()
    room: Room | None = None
    key: str | None = None
    try:
        while True:
            message: dict[str, Any] = await socket.receive_json()
            try:
                if message.get("t") == "join":
                    code = str(message.get("room") or "").strip()[:8] or _new_code()
                    target = rooms.setdefault(code, Room(code))
                    new_key, token = target.join(str(message.get("name") or ""), message.get("token"),
                                                 watch=bool(message.get("watch")))
                    if room is not None and key is not None:
                        _drop(room, key, socket)
                    room, key = target, new_key
                    held = sockets.setdefault(room.code, {})
                    old = held.get(key)
                    if old is not None and old is not socket:       # 同一个人在别处又开了一个页面
                        await old.close()
                    held[key] = socket
                    last_active[room.code] = time.monotonic()
                    await socket.send_json({
                        "t": "joined", "room": room.code, "token": token,
                        "side": None if is_watcher(key) else key, "role": "watch" if is_watcher(key) else "play",
                        "characters": character_catalog(), "scenes": _scene_list(), **_assets(),
                    })
                    room.drive()
                elif room is None or key is None:
                    raise RoomError("请先进入房间。")
                else:
                    room.handle(key, message)
            except RoomError as error:
                await socket.send_json({"t": "error", "message": str(error)})
            if room is not None:
                await _broadcast(room)
    except WebSocketDisconnect:
        pass
    finally:
        if room is not None and key is not None and sockets.get(room.code, {}).get(key) is socket:
            _drop(room, key, socket)
            await _broadcast(room)


class FreshStatic(StaticFiles):
    """网页文件每次都向服务器确认是不是最新的，这样更新代码后不用清浏览器缓存。"""

    async def get_response(self, path: str, scope: Any):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache"
        return response


app.mount("/", FreshStatic(directory=WEB_DIR, html=True), name="web")
