"""房间：进房、选人、选招、贼、电脑对手，以及“每个人能看到什么”。

这一层不碰网络。每个方法改完状态就结束；外面的 WebSocket 层负责把
``state_for(side)`` 的结果发给对应的人。这样房间逻辑可以直接测试。
"""

from __future__ import annotations

import random
import secrets
from dataclasses import dataclass, field
from typing import Any

from shai import Battle, RuleError
from shai.data import CHARACTERS, CHARACTER_NAME_TO_ID, SCENES, SELECTABLE_NAMES
from shai.zei import HANDS, ZeiGame

SIDES = ("A", "B")
MAX_TEAM = 6


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
class Room:
    code: str
    rng: random.Random = field(default_factory=random.Random)
    seats: dict[str, Seat | None] = field(default_factory=lambda: {"A": None, "B": None})
    team_size: int = 3
    zei_enabled: bool = True
    battle: Battle | None = None
    zei: ZeiGame | None = None
    throws: dict[str, str] = field(default_factory=dict)
    last_zei: dict[str, Any] | None = None

    # ---------- 进房 ----------

    def join(self, name: str, token: str | None = None) -> tuple[str, str]:
        name = (name or "").strip()[:12] or "无名"
        for side in SIDES:                              # 断线重连：凭令牌坐回原位
            seat = self.seats[side]
            if seat and token and seat.token == token:
                seat.connected, seat.events_sent = True, 0
                return side, seat.token
        for side in SIDES:
            if self.seats[side] is None:
                self.seats[side] = Seat(name=name, token=secrets.token_hex(8))
                return side, self.seats[side].token
        raise RoomError("房间已经满了。")

    def leave(self, side: str) -> None:
        seat = self.seats.get(side)
        if seat:
            seat.connected = False

    @property
    def phase(self) -> str:
        if self.battle is None:
            return "lobby"
        return "over" if self.battle.done else "battle"

    # ---------- 处理玩家发来的消息 ----------

    def handle(self, side: str, message: dict[str, Any]) -> None:
        kind = message.get("t")
        handler = getattr(self, f"_on_{kind}", None)
        if handler is None:
            raise RoomError("不认识的请求。")
        try:
            handler(side, message)
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
        for seat in self.seats.values():
            if seat:
                seat.team, seat.events_sent = None, 0
        self._refresh_bot_team()

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
                self.battle = Battle(a.team, b.team, seed=self.rng.getrandbits(48), zei=self.zei_enabled)
                self.zei, self.throws, self.last_zei = None, {}, None
        for _ in range(10000):
            if self.phase != "battle" or not self._step():
                return

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
                battle.answer(self.rng.choice(request["options"])["id"])
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
        self.battle.answer(game.winner)

    # ---------- 每个人能看到什么 ----------

    def state_for(self, side: str) -> dict[str, Any]:
        seat = self.seats[side]
        state: dict[str, Any] = {
            "t": "state", "room": self.code, "you": side, "phase": self.phase,
            "settings": {"team_size": self.team_size, "zei": self.zei_enabled, "max_team": MAX_TEAM},
            "seats": {s: None if x is None else {
                "name": x.name, "bot": x.is_bot, "connected": x.connected or x.is_bot,
                "ready": x.team is not None, "auto_zei": x.auto_zei,
            } for s, x in self.seats.items()},
        }
        if self.phase == "lobby":
            state["my_team"] = seat.team
            return state
        battle = self.battle
        view = battle.view()
        foe = "B" if side == "A" else "A"
        view["players"][foe]["team"] = [               # 对手还没上过场的人物看不到
            f if f["entered"] else {"hidden": True, "defeated": False}
            for f in view["players"][foe]["team"]
            if f["entered"] or not f["is_true_body"]    # 没上场的真身不占位置（它排在最后，不影响下标）
        ]
        request = view.pop("pending")
        view.pop("waiting_for")
        state["view"] = view
        state["events_from"] = seat.events_sent
        state["events"] = battle.events[seat.events_sent:]
        seat.events_sent = len(battle.events)
        state["last_zei"] = self.last_zei
        state["paused"] = request is not None        # 结算停在半路：view 还是这一段开始前的局面
        state["need"], state["prompt"] = self._need(side, request)
        if state["need"] == "choose":
            state["actions"] = [self._action_view(a) for a in battle.legal_actions(side)]
        return state

    def _need(self, side: str, request: dict[str, Any] | None) -> tuple[str, dict[str, Any] | None]:
        if self.battle.done:
            return "over", {"winner": self.battle.winner}
        if request and request["kind"] == "zei":
            game = self.zei
            prompt = {
                "reason": request["reason"], "mode": request["mode"], "purpose": request["purpose"],
                "choices": request.get("choices"), "so_far": request.get("so_far", []),
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
                "effect", "description", "character", "action_kind", "tier", "legal", "reason")
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
