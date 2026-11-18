"""房间：进房、选人、选招、贼、电脑对手、限时、聊天、观战，以及“每个人能看到什么”。

这一层不碰网络，也不碰文件。每个方法改完状态就结束；外面的 WebSocket 层负责把
``state_for(身份)`` 的结果发给对应的人，并把打完的对局存成文件。这样房间逻辑可以直接测试。

“身份”是一个字符串：两位玩家是 ``"A"`` 和 ``"B"``，观战的人是 ``"w:"`` 加他的令牌。
"""

from __future__ import annotations

import random
import secrets
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from shai import Battle, RuleError
from shai.data import CHARACTERS, CHARACTER_NAME_TO_ID, SCENES, SELECTABLE_NAMES
from shai.zei import HANDS, ZeiGame

SIDES = ("A", "B")
MAX_TEAM = 6
MAX_WATCHERS = 20

# 限时（雨晨：按默认）。选招 60 秒，超时算普通攻击；贼 15 秒，超时由电脑随机出。
CHOOSE_SECONDS = 60
ZEI_SECONDS = 15
# 轮到一个人之前，他的网页要先把刚发生的事播成动画。每条事件多给一点时间，封顶 20 秒。
ANIMATION_SECONDS_PER_EVENT = 0.4
ANIMATION_GRACE_MAX = 20

CHAT_KEEP = 200          # 房间里最多留这么多条聊天
CHAT_SEND = 60           # 每次发给网页最近的这么多条
CHAT_MAX_LENGTH = 200    # 一条聊天最多这么多字
CHAT_GAP_SECONDS = 0.5   # 同一个人两条聊天至少隔这么久


class RoomError(Exception):
    """玩家的请求不能执行。文字会原样显示给他。"""


@dataclass
class Seat:
    name: str
    token: str
    is_bot: bool = False
    team: list[str] | None = None       # 选好的队伍；对手看不到
    auto_zei: bool = False              # 电脑替我随机出拳
    connected: bool = True
    events_sent: int = 0                # 已经发给这个人的事件条数


@dataclass
class Watcher:
    name: str
    token: str
    events_sent: int = 0


def is_watcher(key: str) -> bool:
    return key.startswith("w:")


@dataclass
class Room:
    code: str
    rng: random.Random = field(default_factory=random.Random)
    clock: Callable[[], float] = time.monotonic     # 算限时用；测试里换成假的钟
    wall: Callable[[], float] = time.time           # 记“这一局是什么时候打完的”
    seats: dict[str, Seat | None] = field(default_factory=lambda: {"A": None, "B": None})
    watchers: dict[str, Watcher] = field(default_factory=dict)      # 令牌 -> 观战的人
    team_size: int = 3
    zei_enabled: bool = True
    timers_enabled: bool = True
    battle: Battle | None = None
    zei: ZeiGame | None = None
    throws: dict[str, str] = field(default_factory=dict)
    last_zei: dict[str, Any] | None = None
    chat: list[dict[str, Any]] = field(default_factory=list)
    chat_count: int = 0
    deadlines: dict[str, dict[str, Any]] = field(default_factory=dict)   # 哪一方 -> 这一次要在什么时候之前做完
    finished: dict[str, Any] | None = None          # 刚打完的这一局的完整记录，等外面存成文件
    replay_id: str | None = None                    # 存好以后的回放编号
    _seed: int = 0
    _start_view: dict[str, Any] | None = None
    _events_seen: dict[str, int] = field(default_factory=dict)
    _chat_at: dict[str, float] = field(default_factory=dict)

    # ---------- 进房 ----------

    def join(self, name: str, token: str | None = None, watch: bool = False) -> tuple[str, str]:
        """返回（身份，令牌）。两个座位都有人、或者对战已经开始时，新来的人自动成为观战。"""
        name = (name or "").strip()[:12] or "无名"
        for side in SIDES:                              # 断线重连：凭令牌坐回原位
            seat = self.seats[side]
            if seat and token and seat.token == token:
                seat.connected, seat.events_sent = True, 0
                self.deadlines.pop(side, None)          # 回来的人重新计时
                return side, seat.token
        if token and token in self.watchers:
            self.watchers[token].events_sent = 0
            return "w:" + token, token
        if not watch and self.phase == "lobby":
            for side in SIDES:
                if self.seats[side] is None:
                    self.seats[side] = Seat(name=name, token=secrets.token_hex(8))
                    return side, self.seats[side].token
        if len(self.watchers) >= MAX_WATCHERS:
            raise RoomError("观战的人太多了。")
        token = secrets.token_hex(8)
        self.watchers[token] = Watcher(name=name, token=token)
        return "w:" + token, token

    def leave(self, key: str) -> None:
        if is_watcher(key):
            self.watchers.pop(key[2:], None)
            return
        seat = self.seats.get(key)
        if seat:
            seat.connected = False

    @property
    def phase(self) -> str:
        if self.battle is None:
            return "lobby"
        return "over" if self.battle.done else "battle"

    def _name(self, key: str) -> str:
        if is_watcher(key):
            watcher = self.watchers.get(key[2:])
            return watcher.name if watcher else "观战"
        seat = self.seats.get(key)
        return seat.name if seat else key

    # ---------- 处理玩家发来的消息 ----------

    def handle(self, key: str, message: dict[str, Any]) -> None:
        kind = message.get("t")
        handler = getattr(self, f"_on_{kind}", None)
        if handler is None:
            raise RoomError("不认识的请求。")
        if is_watcher(key) and kind != "chat":
            raise RoomError("你在观战，不能操作。")
        try:
            handler(key, message)
        except RuleError as error:
            raise RoomError(str(error)) from None
        self.drive()

    def _on_config(self, side: str, m: dict[str, Any]) -> None:
        self._lobby_only()
        if side != "A":
            raise RoomError("只有房主可以改设置。")
        if "team_size" in m:
            size = int(m["team_size"])
            if not 1 <= size <= MAX_TEAM:
                raise RoomError(f"每人带 1 到 {MAX_TEAM} 个人物。")
            if size != self.team_size:
                self.team_size = size
                for seat in self.seats.values():        # 人数变了，已选的队伍作废
                    if seat and not seat.is_bot:
                        seat.team = None
        if "zei" in m:
            self.zei_enabled = bool(m["zei"])
        if "timers" in m:
            self.timers_enabled = bool(m["timers"])
        self._refresh_bot_team()

    def _on_bot(self, side: str, m: dict[str, Any]) -> None:
        self._lobby_only()
        if side != "A":
            raise RoomError("只有房主可以加电脑对手。")
        if self.seats["B"] is not None:
            raise RoomError("对面已经有人了。")
        self.seats["B"] = Seat(name="电脑", token=secrets.token_hex(8), is_bot=True)
        self._refresh_bot_team()

    def _on_team(self, side: str, m: dict[str, Any]) -> None:
        self._lobby_only()
        names = list(m.get("names") or [])
        if len(names) != self.team_size:
            raise RoomError(f"要选 {self.team_size} 个人物。")
        if len(set(names)) != len(names):
            raise RoomError("同一个人物不能选两次。")
        for name in names:
            if name not in SELECTABLE_NAMES:
                raise RoomError(f"不能选 {name}。")
        self.seats[side].team = names

    def _on_unready(self, side: str, m: dict[str, Any]) -> None:
        self._lobby_only()
        self.seats[side].team = None

    def _on_choose(self, side: str, m: dict[str, Any]) -> None:
        self._battle_only()
        self.battle.choose(side, str(m.get("action")), m.get("destination"))

    def _on_throw(self, side: str, m: dict[str, Any]) -> None:
        self._battle_only()
        if self.zei is None or side not in self.zei.sides:
            raise RoomError("现在不用贼。")
        if self.zei.redo_side:
            raise RoomError("正在等对方决定要不要重贼。")
        if m.get("hand") not in HANDS:
            raise RoomError("只能出石头、剪刀、布。")
        if side in self.throws:
            raise RoomError("这一轮你已经出过了。")
        self.throws[side] = m["hand"]
        self._settle_throws()

    def _on_redo(self, side: str, m: dict[str, Any]) -> None:
        self._battle_only()
        if self.zei is None or self.zei.redo_side != side:
            raise RoomError("现在轮不到你决定重贼。")
        if not self.zei.redo(bool(m.get("yes"))):
            self._finish_zei()

    def _on_pick(self, side: str, m: dict[str, Any]) -> None:
        self._battle_only()
        request = self.battle.pending
        if not request or request["kind"] != "choose" or request["askers"] != [side]:
            raise RoomError("现在不用你选。")
        self.battle.answer(str(m.get("option")))

    def _on_auto(self, side: str, m: dict[str, Any]) -> None:
        self.seats[side].auto_zei = bool(m.get("on"))

    def _on_rematch(self, side: str, m: dict[str, Any]) -> None:
        if self.phase != "over":
            raise RoomError("这一局还没打完。")
        self.battle, self.zei, self.throws, self.last_zei = None, None, {}, None
        self.finished, self.replay_id, self.deadlines, self._events_seen = None, None, {}, {}
        for seat in self.seats.values():
            if seat:
                seat.team, seat.events_sent = None, 0
        for watcher in self.watchers.values():
            watcher.events_sent = 0
        self._refresh_bot_team()

    def _on_chat(self, key: str, m: dict[str, Any]) -> None:
        text = " ".join(str(m.get("text") or "").split())[:CHAT_MAX_LENGTH]
        if not text:
            return
        now = self.clock()
        if now - self._chat_at.get(key, -1e9) < CHAT_GAP_SECONDS:
            raise RoomError("发得太快了，等一下再发。")
        self._chat_at[key] = now
        self._say("w" if is_watcher(key) else key, self._name(key), text)

    def _say(self, who: str, name: str, text: str) -> None:
        """往聊天里加一条。who 是 "A"、"B"、"w"（观战的人）或 "sys"（系统提示）。"""
        self.chat.append({"n": self.chat_count, "who": who, "name": name, "text": text})
        self.chat_count += 1
        del self.chat[:-CHAT_KEEP]

    def _lobby_only(self) -> None:
        if self.phase != "lobby":
            raise RoomError("对战已经开始了。")

    def _battle_only(self) -> None:
        if self.phase != "battle":
            raise RoomError("现在不在对战中。")

    def _refresh_bot_team(self) -> None:
        bot = self.seats["B"]
        if bot and bot.is_bot and self.phase == "lobby":
            bot.team = self.rng.sample(SELECTABLE_NAMES, self.team_size)

    # ---------- 推进：开局、电脑对手、自动出拳 ----------

    def drive(self) -> None:
        if self.phase == "lobby":
            a, b = self.seats["A"], self.seats["B"]
            if a and b and a.team and b.team:
                self._seed = self.rng.getrandbits(48)
                self.battle = Battle(a.team, b.team, seed=self._seed, zei=self.zei_enabled)
                self.zei, self.throws, self.last_zei = None, {}, None
                self.finished, self.replay_id, self.deadlines, self._events_seen = None, None, {}, {}
                self._start_view = self._plain_view()
        for _ in range(10000):
            if self.phase != "battle" or not self._step():
                break
        self._refresh_deadlines()
        if self.phase == "over" and self.finished is None:
            self.finished = self.replay_record()

    def _step(self) -> bool:
        """让电脑做一件事。返回 False 表示现在在等真人。"""
        battle, request = self.battle, self.battle.pending
        if request and request["kind"] == "zei":
            if self.zei is None:
                self.zei, self.throws = ZeiGame(request), {}
            if self.zei.redo_side:
                if self._automatic(self.zei.redo_side):
                    if not self.zei.redo(True):
                        self._finish_zei()
                    return True
                return False
            moved = False
            for side in self.zei.sides:
                if side not in self.throws and self._automatic(side):
                    self.throws[side] = self.rng.choice(HANDS)
                    moved = True
            if moved:
                self._settle_throws()
            return moved
        if request and request["kind"] == "choose":
            side = request["askers"][0]
            if self.seats[side].is_bot:
                options = request["options"]
                # 第一项是“不做”的选择（不扔、不跑、不占卜）：电脑一半的时候选它，免得每回合都要贼
                idle = options[0]["id"] == "" and self.rng.random() < 0.5
                battle.answer((options[0] if idle else self.rng.choice(options))["id"])
                return True
            return False
        for side in battle.waiting_for():
            if self.seats[side].is_bot:
                action = self.rng.choice([a for a in battle.legal_actions(side) if a["legal"]])
                destination = self.rng.choice(list(SCENES)) if action["effect"] == "choose_scene" else None
                battle.choose(side, action["id"], destination)
                return True
        return False

    def _automatic(self, side: str) -> bool:
        seat = self.seats[side]
        return seat.is_bot or seat.auto_zei

    def _settle_throws(self) -> None:
        if self.zei is None or len(self.throws) < 2:
            return
        state = self.zei.throw(self.throws)
        self.throws = {}
        if state == "done":
            self._finish_zei()

    def _finish_zei(self) -> None:
        game, self.zei, self.throws = self.zei, None, {}
        self.last_zei = {"reason": self.battle.pending["reason"], "rounds": game.rounds, "winner": game.winner}
        self.battle.answer(game.winner, detail=game.rounds)

    # ---------- 限时 ----------

    def _prompt_key(self, side: str) -> tuple[str, str] | None:
        """这个人现在要做什么。返回（哪一类，区分“这一次”的记号）；不用他做事就返回 None。"""
        seat = self.seats[side]
        if self.phase != "battle" or seat is None or seat.is_bot:
            return None
        battle = self.battle
        need, _ = self._need(side, battle.pending)
        step, rounds = len(battle.history), len(self.zei.rounds) if self.zei else 0
        if need == "choose":
            return "choose", f"{battle.round}"
        if need == "pick":
            return "pick", f"{step}"
        if need == "throw":
            return "throw", f"{step}-{rounds}"
        if need == "redo":
            return "redo", f"{step}-{rounds}"
        return None

    def _refresh_deadlines(self) -> None:
        """有人新轮到要做事，就给他开始计时；已经在计时的不重新算。"""
        if self.phase != "battle" or not self.timers_enabled:
            self.deadlines = {}
            return
        now, events = self.clock(), self.battle.events
        for side in SIDES:
            key = self._prompt_key(side)
            if key is None:
                self.deadlines.pop(side, None)
                continue
            current = self.deadlines.get(side)
            if current and current["key"] == key:
                continue
            limit = CHOOSE_SECONDS if key[0] in {"choose", "pick"} else ZEI_SECONDS
            fresh = sum(1 for event in events[self._events_seen.get(side, 0):] if event["t"] != "log")
            self._events_seen[side] = len(events)
            grace = min(ANIMATION_GRACE_MAX, ANIMATION_SECONDS_PER_EVENT * fresh)
            self.deadlines[side] = {"key": key, "at": now + limit + grace, "limit": limit}

    def tick(self) -> bool:
        """外面每秒叫一次。有人超时就替他做默认的事。局面有变化返回 True。"""
        if self.phase != "battle" or not self.timers_enabled:
            return False
        if not any(seat and not seat.is_bot and seat.connected for seat in self.seats.values()):
            return False                                # 真人都不在：不替人出招，等有人回来
        now, changed = self.clock(), False
        for side in SIDES:
            entry = self.deadlines.get(side)
            if entry is None or now < entry["at"] or self._prompt_key(side) != entry["key"]:
                continue
            self._time_out(side, entry["key"][0])
            self.deadlines.pop(side, None)
            changed = True
        if changed:
            self.drive()
        return changed

    def _time_out(self, side: str, kind: str) -> None:
        name, battle = self.seats[side].name, self.battle
        if kind == "choose":            # 选招超时算普通攻击；普通攻击也出不了（比如够不着）就算防御 1
            legal = {a["id"]: a for a in battle.legal_actions(side) if a["legal"] and a["effect"] != "choose_scene"}
            action = legal.get("0") or legal.get("d1") or next(iter(legal.values()))
            battle.choose(side, action["id"])
            self._say("sys", "", f"{name}选招超时，按【{action['name']}】算。")
        elif kind == "pick":
            option = battle.pending["options"][0]
            battle.answer(option["id"])
            self._say("sys", "", f"{name}超时，按“{option['name']}”算。")
        elif kind == "throw":
            self.throws[side] = self.rng.choice(HANDS)
            self._say("sys", "", f"{name}出拳超时，电脑替他出。")
            self._settle_throws()
        elif kind == "redo":
            self._say("sys", "", f"{name}超时，不重贼。")
            if not self.zei.redo(False):
                self._finish_zei()

    def _timers_view(self) -> dict[str, float | None]:
        now = self.clock()
        return {side: round(max(0.0, self.deadlines[side]["at"] - now), 1) if side in self.deadlines else None
                for side in SIDES}

    # ---------- 战报和回放 ----------

    def _plain_view(self) -> dict[str, Any]:
        view = self.battle.view()
        view.pop("pending")
        view.pop("waiting_for")
        view["peek"] = None
        return view

    def replay_record(self) -> dict[str, Any]:
        """这一局的完整记录：开局设置、每一步输入、发生的全部事件。保存、回放都用它。"""
        battle = self.battle
        return {
            "format": 1, "engine_version": battle.VERSION, "room": self.code, "ended_at": self.wall(),
            "names": {side: self.seats[side].name for side in SIDES},
            "bots": {side: self.seats[side].is_bot for side in SIDES},
            "teams": {side: list(self.seats[side].team or []) for side in SIDES},
            "seed": self._seed, "zei": self.zei_enabled,
            "history": list(battle.history),            # 双方每一步的选择和每次贼的结果：照着重打一遍，结果一模一样
            "events": list(battle.events),              # 发生的全部事件：网页照着播就是回放
            "start_view": self._start_view, "final_view": self._plain_view(),
            "winner": battle.winner, "rounds": battle.round,
        }

    # ---------- 每个人能看到什么 ----------

    def state_for(self, key: str) -> dict[str, Any]:
        watcher = self.watchers.get(key[2:]) if is_watcher(key) else None
        seat = None if watcher else self.seats[key]
        state: dict[str, Any] = {
            "t": "state", "room": self.code, "you": None if watcher else key,
            "role": "watch" if watcher else "play", "phase": self.phase,
            "settings": {"team_size": self.team_size, "zei": self.zei_enabled, "max_team": MAX_TEAM,
                         "timers": self.timers_enabled, "choose_seconds": CHOOSE_SECONDS, "zei_seconds": ZEI_SECONDS},
            "seats": {s: None if x is None else {
                "name": x.name, "bot": x.is_bot, "connected": x.connected or x.is_bot,
                "ready": x.team is not None, "auto_zei": x.auto_zei,
            } for s, x in self.seats.items()},
            "watchers": [w.name for w in self.watchers.values()],
            "chat": self.chat[-CHAT_SEND:],
        }
        if self.phase == "lobby":
            state["my_team"] = seat.team if seat else None
            return state
        battle = self.battle
        view = battle.view()
        hidden = SIDES if watcher else ("B" if key == "A" else "A",)
        for side in hidden:                             # 还没上过场的人物：对手看不到，观战的人两边都看不到
            view["players"][side]["team"] = [
                f if f["entered"] else {"hidden": True, "defeated": False}
                for f in view["players"][side]["team"]
                if f["entered"] or not f["is_true_body"]    # 没上场的真身不占位置（它排在最后，不影响下标）
            ]
        request = view.pop("pending")
        view.pop("waiting_for")
        peeks = view.pop("peek")
        view["peek"] = None if watcher else peeks[key]      # 透视到的招只给本人看
        reader = watcher or seat
        state["view"] = view
        state["events_from"] = reader.events_sent
        state["events"] = battle.events[reader.events_sent:]
        reader.events_sent = len(battle.events)
        state["last_zei"] = self.last_zei
        state["paused"] = request is not None        # 结算停在半路：view 还是这一段开始前的局面
        state["need"], state["prompt"] = self._need("" if watcher else key, request)
        if watcher and state["need"] != "over":
            state["need"] = "watch"
        state["timers"] = self._timers_view()
        state["replay_id"] = self.replay_id
        if state["need"] == "choose":
            state["actions"] = [self._action_view(a) for a in battle.legal_actions(key)]
        return state

    def _need(self, side: str, request: dict[str, Any] | None) -> tuple[str, dict[str, Any] | None]:
        """这个人现在要做什么。side 传空字符串表示旁观的人。"""
        if self.battle.done:
            return "over", {"winner": self.battle.winner}
        if request and request["kind"] == "zei":
            game = self.zei
            prompt = {
                "reason": request["reason"], "mode": request["mode"], "purpose": request["purpose"],
                "choices": request.get("choices"), "so_far": request.get("so_far", []),
                "stakes": request.get("stakes"), "series": request.get("series"), "sides": request["sides"],
                "rounds": game.rounds if game else [],
                "thrown": {s: s in self.throws for s in request["sides"]},
                "redo_side": game.redo_side if game else None,
                "redo_left": game.redo_left if game else {},
            }
            if side not in request["sides"]:
                return "wait", prompt
            if game and game.redo_side:
                return ("redo" if game.redo_side == side else "wait"), prompt
            return ("wait" if side in self.throws else "throw"), prompt
        if request and request["kind"] == "choose":
            if request["askers"] == [side]:
                return "pick", {"reason": request["reason"], "options": request["options"],
                                "so_far": request.get("so_far", [])}
            return "wait", {"reason": request["reason"]}
        return ("choose" if side in self.battle.waiting_for() else "wait"), None

    @staticmethod
    def _action_view(action: dict[str, Any]) -> dict[str, Any]:
        keys = ("id", "name", "attributes", "damage", "statuses", "defense", "distance", "target",
                "effect", "description", "character", "action_kind", "tier", "legal", "reason", "warning",
                "inner", "progress", "next", "level")
        return {k: action.get(k) for k in keys}


def character_catalog() -> list[dict[str, Any]]:
    """选人界面用的人物列表。"""
    result = []
    for name in SELECTABLE_NAMES:
        c = CHARACTERS[CHARACTER_NAME_TO_ID[name]]
        result.append({
            "name": name, "hp": c["hp"], "shield": c["shield"], "lives": c["lives"],
            "distance": "无穷" if c["distance"] == float("inf") else c["distance"],
            "inner": c["inner"], "traits": sorted(c["traits"]),
        })
    return result
