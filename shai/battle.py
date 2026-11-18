"""一局对战的流程：队伍、换人、出手顺序、贼、回合推进。

对外只有几个入口：
- ``Battle(team_a, team_b)``：开一局；
- ``legal_actions(side)``：这一方现在能选什么；
- ``choose(side, action_id)``：这一方选招。双方都选完就自动结算；
- ``pending`` / ``answer(value)``：结算到一半需要玩家决定时（贼、选下一个上场的人物），
  ``pending`` 里是问题，用 ``answer`` 回答；
- ``view()``：当前局面；``events``：从开局到现在发生的每一件事，网页照着它播动画。

“算到一半停下来等人”的做法：每段结算开始前存一份局面。算到需要问玩家的地方，如果还没有
答案，就退回到存的那份局面，把问题交出去。玩家回答后从那份局面重新算，这次直接用答案。
所以一局对战可以完整地记成：开局设置、每回合双方的选择、每次决定的结果。
"""

from __future__ import annotations

import copy
import json
import random
from math import inf
from typing import Any

from .actions import Actions
from .data import ACCELERATOR_BIG, NO_SELF_EFFECTS, UP_REACH, accelerator_level
from .data import (
    CHARACTERS, CHARACTER_NAME_TO_ID, FIRST_STRIKE_IDS, LEARN_THRESHOLDS, SCENES, SEAL_BY_ATTRIBUTE,
    SELF_BUFFS, SKILLS,
    TIER_FAN_SWAP, TIER_FIRST, TIER_LINGBO4, TIER_NORMAL, TIER_SHEN, TIER_SWITCH, TRUE_BODY_ID,
    UNBLOCKABLE_CHARACTERS,
    character_skill_ids, is_signature,
)
from .model import Fighter, NeedDecision, Player, RuleError, Status
from .rules import Rules
from .forms import Forms
from .turnstart import TurnStart

SIDES = ("A", "B")
DEFENSE_CODE = {"d1": 1, "d2": 2, "d3": 3, "d4": 4}

_SKIP = {
    "id": "skip", "name": "跳过行动", "attributes": (), "damage": 0, "statuses": (), "defense": None,
    "distance": 0, "target": "self", "effect": "skip", "description": "因状态跳过行动。",
    "character": None, "action_kind": "skip",
}
_OXYGEN = {
    "id": "sys_collect_oxygen", "name": "收集氧气", "attributes": ("物品",), "damage": 0, "statuses": (),
    "defense": None, "distance": 0, "target": "self", "effect": "collect_oxygen",
    "description": "地面类场景收集氧气。", "character": None, "action_kind": "collect",
}


class _ProbeStop(Exception):
    """试算两种先后顺序时，算完这一回合就停。"""


# 判断“谁先出手有没有区别”时，最多试算这么多种情况。再多就不算了，保守地当作有区别。
# 两个超级真身对打时一回合里能有五六次概率，要试几十到一百多种情况。
PROBE_BUDGET = 400


class Battle(Rules, Actions, TurnStart, Forms):
    VERSION = "1.0-dev"

    def __init__(self, team_a: list[str], team_b: list[str], seed: int | None = None,
                 zei: bool = True, true_body: bool = True, probe_order: bool = True):
        if not team_a or not team_b:
            raise RuleError("每一方至少要有一个人物。")
        self.seed = seed
        self._main_rng = random.Random(seed)
        self.rng = self._main_rng
        self.zei_enabled = zei            # False：这一局所有的贼都改成电脑掷概率
        self.probe_order = probe_order    # True：先后手不影响结果时不贼
        self.players = {
            side: Player(side, [self._make_fighter(side, name) for name in team]
                         + ([self._make_fighter(side, "超级真身", true_body=True)] if true_body else []))
            for side, team in zip(SIDES, (team_a, team_b))
        }
        self.round = 1
        self.water_level = -1
        self.done = False
        self.winner: str | None = None
        self.log: list[str] = []
        self.events: list[dict[str, Any]] = []
        self.choices: dict[str, dict[str, Any]] = {}
        self.skipping: set[str] = set()
        self.pending: dict[str, Any] | None = None
        self._decisions: list[dict[str, Any]] = []
        self._cursor = 0
        self._forced_first: str | None = None
        self._unit: str | None = None
        self._snap: dict[str, Any] | None = None
        # 这一段里已经定下来、可以给玩家看的事件条数。停下来等人之前发生的事不会再变，所以照常显示。
        self._kept = 0
        self._count = 0
        self._mute = False                    # 试算先后顺序时不产生事件
        self._want_start = False              # 这一回合结算完了，下一回合的“回合开始”单独算一段
        self._probe_assign: dict[str, Any] | None = None   # 试算时，后面那些贼假设的结果
        self._probe_seen: dict[str, int] = {}
        self.history: list[dict[str, Any]] = []   # 每一步输入，用来回放

        names = {side: self.fighter(side).name for side in SIDES}
        self._log(f"对战开始：A的{names['A']} 对 B的{names['B']}。")
        self._begin("open")

    # ================= 对外入口 =================

    def fighter(self, side: str) -> Fighter:
        return self.players[side].fighter

    @staticmethod
    def other(side: str) -> str:
        return "B" if side == "A" else "A"

    def waiting_for(self) -> list[str]:
        """现在在等谁：有待决定的问题时是要回答的人，否则是还没选招的人。"""
        if self.done:
            return []
        if self.pending:
            return list(self.pending["askers"])
        return [side for side in SIDES if side not in self.choices and not self._must_wait(side)]

    # ---------- 透视 ----------

    def _sees_through(self, side: str) -> bool:
        """这一方这回合能不能透视对手：对手先选招，他看到以后再选。

        纵目青铜怪自带透视。规则文档：“登场后下一回合透视对手技能，之后每隔一回合透视一次”。
        雨晨：人死了以后他顶上来不算一回合，所以他上场以后第一个能出招的回合就透视，之后隔一回合一次。
        换人上场的那一回合他不出招，下一回合是他第一个能出招的回合，也是透视。
        身上有“透视”状态（灵气寒霜指打出来的）的人物每回合都被对手透视。
        两边互相都能透视就抵消，照常同时选。
        """
        me, foe = self.fighter(side), self.fighter(self.other(side))
        if me.defeated or foe.defeated:
            return False

        def can(seer: Fighter, seen: Fighter) -> bool:
            turn = int(seer.counters.get("field_turns", 0))
            return ("透视" in self.traits(seer) and turn % 2 == 1) or seen.has_status("透视")

        return can(me, foe) and not can(foe, me)

    def _must_wait(self, side: str) -> bool:
        """能透视的一方要等对手先选。"""
        return self._sees_through(side) and self.other(side) not in self.choices

    def _peek(self, side: str) -> dict[str, Any] | None:
        """这一方透视到的东西：对手这回合已经选好的招。看不到就是 None。"""
        other = self.other(side)
        if side in self.choices or other not in self.choices or other in self.skipping or not self._sees_through(side):
            return None
        spec = self.choices[other]["spec"]
        return {"id": spec["id"], "name": spec["name"], "destination": self.choices[other]["destination"],
                "on_self": bool(self.choices[other].get("on_self"))}

    def legal_actions(self, side: str) -> list[dict[str, Any]]:
        actor, target = self.fighter(side), self.fighter(self.other(side))
        ids = list(character_skill_ids(self.char(actor)))
        if actor.scene_height == 0:
            ids.append("sys_collect_oxygen")
        blocked_all = None
        if self.done:
            blocked_all = "对战已结束"
        elif self.pending:
            blocked_all = "正在等待一个决定"
        elif side in self.choices:
            blocked_all = "这回合不能出招" if side in self.skipping else "本回合已经选过"
        elif self._must_wait(side):
            blocked_all = "你能透视对手：等对手先选"
        result = []
        for action_id in ids:
            spec = _OXYGEN if action_id == "sys_collect_oxygen" else SKILLS[action_id]
            reason = blocked_all or self._illegal_reason(actor, target, spec)
            entry = {**spec, "tier": self._tier(actor, spec), "legal": reason is None, "reason": reason or "",
                     "warning": self._warning(target, spec)}
            if spec["target"] == "enemy" and spec["action_kind"] == "skill" and spec["effect"] not in NO_SELF_EFFECTS:
                # 打自己：不看够不够得着，别的限制（被封、东西不够）照旧
                self_reason = blocked_all or self._illegal_reason(actor, actor, spec)
                entry["self_ok"], entry["self_reason"] = self_reason is None, self_reason or ""
            if spec["effect"] in {"build_accelerator", "accelerator"}:
                built = int(actor.devices.get("粒子加速器", 0))
                entry["damage"] = self.character_damage(actor, spec)
                entry["description"] = (f"已经造了 {built} 下。造满 10 下可以打：一下 3 万，加 3 次辐射。"
                                        "造满 20 下：一下 5 万，加 5 次辐射，不管对手在哪个场景都打得到。")
            result.append(entry)
        for name, needs in LEARN_THRESHOLDS.items():          # 学内功：占这个回合的出招
            reason = blocked_all or self.learn_reason(actor, name)
            progress = actor.learn_progress.get(name, 0)
            result.append({
                "id": f"learn:{name}", "name": f"学{name}", "attributes": (), "damage": 0, "statuses": (),
                "defense": None, "distance": 0, "target": "self", "effect": "learn", "inner": name,
                "description": "学一次内功占用这个回合的出招。", "character": None, "action_kind": "learn",
                "tier": TIER_NORMAL, "legal": reason is None, "reason": reason or "",
                "progress": progress, "next": next((n for n in needs if n > progress), None),
                "level": actor.own_level(name),
            })
        for index in self.players[side].bench():
            other = self.players[side].team[index]
            result.append({
                "id": f"switch:{index}", "name": f"换上{other.name}", "attributes": (), "damage": 0,
                "statuses": (), "defense": None, "distance": 0, "target": "self", "effect": "switch",
                "description": "换人占用这个回合的出招，比所有的招都先生效。", "character": None,
                "action_kind": "switch", "switch_to": index, "tier": TIER_SWITCH,
                "legal": blocked_all is None, "reason": blocked_all or "",
            })
        return result

    def choose(self, side: str, action_id: str, destination: str | None = None, on_self: bool = False) -> None:
        """选这回合的招。on_self：把一个本来打对手的招改成打自己。"""
        if side not in SIDES:
            raise RuleError("未知的一方。")
        actions = {a["id"]: a for a in self.legal_actions(side)}
        if action_id not in actions:
            raise RuleError(f"未知动作：{action_id}")
        action = actions[action_id]
        if on_self:
            if "self_ok" not in action:
                raise RuleError("这个动作不能对自己用。")
            if not action["self_ok"]:
                raise RuleError(action["self_reason"] or "现在不能执行这个动作。")
        elif not action["legal"]:
            raise RuleError(action["reason"] or "现在不能执行这个动作。")
        if action["effect"] == "choose_scene" and destination not in SCENES:
            raise RuleError("这个动作需要选一个场景。")
        self.choices[side] = {"spec": action, "destination": destination, "on_self": bool(on_self),
                              "lives": self.fighter(side).lives_remaining}
        step = {"type": "choose", "side": side, "action": action_id, "destination": destination}
        if on_self:
            step["on_self"] = True
        self.history.append(step)
        if len(self.choices) == 2:
            self._begin("round")

    def answer(self, value: Any, detail: Any = None) -> None:
        """回答 ``pending`` 里的问题。贼：赢的一方（单次贼打平传 None）。选择：选项的 id。

        detail：贼的时候双方每一轮出的拳。只是记下来给人看，不影响结果。
        """
        request = self.pending
        if request is None:
            raise RuleError("现在没有等待决定的问题。")
        if request["kind"] == "choose":
            if value not in [o["id"] for o in request["options"]]:
                raise RuleError("这个选项不存在。")
        elif value not in request["sides"] and not (value is None and request["mode"] == "single"):
            raise RuleError("贼的结果无效。")
        entry = {"kind": request["_kind"], "value": value}
        if detail:
            entry["detail"] = detail
        self._decisions.append(entry)
        self.history.append({"type": "answer", **entry})
        self._run()

    def view(self) -> dict[str, Any]:
        return {
            "version": self.VERSION, "round": self.round, "water_level": self.water_level,
            "done": self.done, "winner": self.winner, "zei_enabled": self.zei_enabled,
            "pending": self.pending, "waiting_for": self.waiting_for(),
            "chosen": {side: side in self.choices for side in SIDES},
            "sees": {side: self._sees_through(side) for side in SIDES},     # 谁能透视对手（双方都看得到）
            "peek": {side: self._peek(side) for side in SIDES},             # 透视到的招（只能给本人看）
            "players": {
                side: {"active": p.active, "team": [self._fighter_view(f) for f in p.team]}
                for side, p in self.players.items()
            },
        }

    # ================= 存档、重算、试算 =================

    def _begin(self, unit: str) -> None:
        self._unit = unit
        self._snap = self._snapshot()
        self._decisions = []
        self._kept = 0
        self._run()

    def _run(self) -> None:
        status, request, _ = self._attempt()
        guard = 0
        while status == "need" and request["kind"] == "order" and self.probe_order and guard < 8:
            guard += 1
            prints = []
            self._mute = True
            same = self._order_irrelevant(request, {}, [PROBE_BUDGET])
            self._forced_first, self._mute, self._probe_assign = None, False, None
            self._restore(self._snap)
            if not same:
                break                           # 先后有区别：要贼
            self._decisions.insert(request["index"], {"kind": "order", "value": request["sides"][0], "auto": True})
            status, request, _ = self._attempt()
        if status == "done":
            self.pending, self._decisions, self._snap, self._unit = None, [], None, None
            if self._want_start and not self.done:
                # 回合的结果先定下来，再开始下一回合。这样下一回合开始时的提问（占卜、龙王移场景）
                # 不会让上一回合的结果悬着。
                self._want_start = False
                self._begin("start")
        else:
            self.pending = self._public_request(request)

    def _order_irrelevant(self, request: dict[str, Any], assumed: dict[str, Any], budget: list[int]) -> bool:
        """两种先后顺序的结果是不是一样。

        试算中途如果还要贼（比如闪避、暴击），就把那次贼的每一种结果都假设一遍。
        只有在每一种假设下两种顺序的结果都一样，才算“先后无所谓”。
        """
        if budget[0] <= 0:
            return False                        # 情况太多，不再细算，保守地当作有区别
        budget[0] -= 1
        prints = []
        for first in request["sides"]:
            self._forced_first, self._probe_assign = first, assumed
            status, need, fingerprint = self._attempt()
            if status == "need":
                # 每次贼只有“成”和“不成”两种结果，各试一遍就够了。
                # （只出一次的那种贼，打平总是和其中一方赢的效果一样，不用单独试。）
                return all(self._order_irrelevant(request, {**assumed, need["label"]: v}, budget) for v in need["sides"])
            prints.append(fingerprint)
        return prints[0] == prints[1]

    def _attempt(self) -> tuple[str, dict[str, Any] | None, str | None]:
        """从存的局面把这一段完整算一次。返回 (状态, 问题, 局面指纹)。"""
        self._restore(self._snap)
        self._cursor = 0
        self._count = 0
        self._status_batch = None
        self._probe_seen = {}
        try:
            if self._unit == "open":
                self._open()
            elif self._unit == "start":
                self._start_phase()
            else:
                self._resolve_round()
            return "done", None, None
        except _ProbeStop:
            return "probe", None, self._fingerprint()
        except NeedDecision as need:
            if not self._mute:
                self._kept = max(self._kept, self._count)   # 停下来之前发生的事保留下来，照常显示
            self._restore(self._snap)
            need.request["so_far"] = [e["text"] for e in self.events[self._snap["events"]:] if e["t"] == "log"][-6:]
            return "need", need.request, None
        finally:
            self.rng = self._main_rng

    def _snapshot(self) -> dict[str, Any]:
        return {
            "players": copy.deepcopy(self.players), "choices": copy.deepcopy(self.choices),
            "skipping": set(self.skipping),
            "scalars": (self.round, self.water_level, self.done, self.winner),
            "log": len(self.log), "events": len(self.events), "rng": self._main_rng.getstate(),
        }

    def _restore(self, snap: dict[str, Any]) -> None:
        self.players = copy.deepcopy(snap["players"])
        self.choices = copy.deepcopy(snap["choices"])
        self.skipping = set(snap["skipping"])
        self.round, self.water_level, self.done, self.winner = snap["scalars"]
        self._want_start = False
        keep = snap["events"] + (self._kept if snap is self._snap else 0)
        kept_logs = sum(1 for e in self.events[snap["events"]:keep] if e["t"] == "log")
        del self.events[keep:]
        del self.log[snap["log"] + kept_logs:]
        self._main_rng.setstate(snap["rng"])
        self.rng = self._main_rng

    def _fingerprint(self) -> str:
        """这一回合算完以后的局面，用来比较“谁先出手”有没有区别。

        有一方已经全灭的话，这一局就结束了，只比“谁全灭了”：别的细节（比如赢的人最后有没有被打昏睡）不算区别。
        """
        lost = [side for side in SIDES if not self.players[side].alive_any()]
        if lost:
            return "over:" + ",".join(lost)
        state = {"players": {s: [self._fighter_view(f) for f in p.team] + [p.active] for s, p in self.players.items()},
                 "water": self.water_level}
        return json.dumps(state, ensure_ascii=False, sort_keys=True, default=str)

    def _public_request(self, request: dict[str, Any]) -> dict[str, Any]:
        public = {k: v for k, v in request.items() if k != "index"}
        public["_kind"] = request["kind"]       # 引擎内部用：是定先后手的贼、定概率的贼，还是选择
        if request["kind"] == "choose":
            public["askers"] = [request["side"]]
        else:
            public["kind"] = "zei"              # 对外不区分“定先后手的贼”和“定概率的贼”
            public["purpose"] = "order" if request["kind"] == "order" else "chance"
            public["askers"] = list(request["sides"])
        return public

    # ================= 决定：贼、选择 =================

    def _decide(self, kind: str, **request: Any) -> dict[str, Any]:
        if self._cursor < len(self._decisions):
            decision = self._decisions[self._cursor]
            if decision["kind"] != kind:
                raise RuntimeError("决定的记录和结算的顺序对不上。")
            self._cursor += 1
            return decision
        if self._forced_first is not None and kind == "zei":
            # 试算：这次贼还没有真的发生，按假设的结果往下算；没有假设过就报告出来，让外面逐种结果去试
            reason = request.get("reason", "")
            seen = self._probe_seen.get(reason, 0)
            self._probe_seen[reason] = seen + 1
            label = f"{reason}#{seen}"
            if self._probe_assign is not None and label in self._probe_assign:
                return {"kind": kind, "value": self._probe_assign[label]}
            raise NeedDecision({"kind": kind, "index": self._cursor, "label": label, **request})
        raise NeedDecision({"kind": kind, "index": self._cursor, **request})

    def _rezei(self, a: str, b: str) -> dict[str, int]:
        return {side: self.fighter(side).inner_level("重贼") for side in (a, b)}

    def _zei(self, a: str, b: str, mode: str, reason: str, stakes: dict[Any, str] | None = None,
             series: dict[str, int] | None = None) -> str | None:
        """a 和 b 贼一次。decisive：贼到分出胜负，返回赢的一方。single：只贼一次，平局返回 None。

        stakes：谁赢了会怎样（键是 a、b，打平用 None），写给玩家看。
        series：这是“要连赢几把”里的第几把，比如 {"need": 2, "index": 1}。
        """
        if not self.zei_enabled:
            if mode == "decisive":
                return a if self.rng.random() < 0.5 else b
            roll = self.rng.random()
            return a if roll < 1 / 3 else (None if roll < 2 / 3 else b)
        stakes = stakes or {}
        shown = {a: stakes.get(a, ""), b: stakes.get(b, ""), "tie": stakes.get(None, "")}
        decision = self._decide("zei", mode=mode, sides=[a, b], reason=reason, rezei=self._rezei(a, b),
                                stakes=shown, series=series)
        winner = decision["value"]
        outcome = stakes.get(winner, "")
        self._emit("zei", mode=mode, sides=[a, b], winner=winner, reason=reason, purpose="chance",
                   rounds=decision.get("detail") or [], outcome=outcome, series=series)
        self._log(f"贼（{reason}）：{self._hands_text(decision)}{'打平' if winner is None else winner + '赢'}"
                  + (f"，{outcome}。" if outcome else "。"))
        return winner

    @staticmethod
    def _hands_text(decision: dict[str, Any]) -> str:
        """战报里写双方最后一把出了什么；之前打平过几把也写上。"""
        rounds = decision.get("detail") or []
        if not rounds:
            return ""
        last = rounds[-1]
        ties = f"先打平{len(rounds) - 1}把，然后" if len(rounds) > 1 else ""
        return ties + "，".join(f"{side}出{hand}" for side, hand in sorted(last.items())) + "，"

    def _chance(self, probability: float, side: str, reason: str, yes: str = "成", no: str = "不成") -> bool:
        """一次概率判定。``side`` 是想让它生效的那一方，要他贼赢才算。

        三分之一：贼一次赢了才算。三分之二：贼一次不输就算。二分之一：贼到分出胜负。
        四分之一：连赢两次。八分之一：连赢三次。别的概率由电脑掷随机数。
        yes、no：成了会怎样、不成会怎样，写给玩家看。
        """
        if probability <= 0:
            return False
        if probability >= 1:
            return True
        other = self.other(side)

        def near(x: float) -> bool:
            return abs(probability - x) < 0.02

        if near(1 / 3):
            return self._zei(side, other, "single", reason, {side: yes, other: no, None: no}) == side
        if near(2 / 3):
            return self._zei(side, other, "single", reason, {side: yes, other: no, None: yes}) != other
        for wins, p in ((1, 1 / 2), (2, 1 / 4), (3, 1 / 8)):
            if near(p):
                for k in range(1, wins + 1):
                    stakes = {side: yes if k == wins else f"还要再赢{wins - k}把才算数", other: no}
                    series = {"need": wins, "index": k} if wins > 1 else None
                    if self._zei(side, other, "decisive", reason, stakes, series) != side:
                        return False
                return True
        return self.rng.random() < probability

    def _decide_order(self, a: str, b: str, reason: str, chosen: dict[str, Any]) -> str:
        if self._forced_first is not None:
            return self._forced_first
        if not self.zei_enabled:
            return a if self.rng.random() < 0.5 else b
        first = {side: f"{self.label(self.fighter(side))}先出手" for side in (a, b)}
        decision = self._decide("order", mode="decisive", sides=[a, b], reason=reason,
                                choices=chosen, rezei=self._rezei(a, b),
                                stakes={a: first[a], b: first[b], "tie": ""}, series=None)
        winner = decision["value"]
        if decision.get("auto"):
            self._log("双方同一档出手，先后不影响结果。")
        else:
            self._emit("zei", mode="decisive", sides=[a, b], winner=winner, reason=reason, purpose="order",
                       rounds=decision.get("detail") or [], outcome=first[winner], series=None)
            self._log(f"贼（{reason}）：{self._hands_text(decision)}{winner}赢，{winner}先出手。")
        return winner

    # ================= 回合流程 =================

    def _open(self) -> None:
        self._link_lenders()
        for side in SIDES:
            self._on_enter(self.fighter(side))
        self._start_phase()

    def _link_lenders(self) -> None:
        """借内功的人物（宋濂）只向对面场上的人物借：那个人物下场或者死了，借来的内功就没有了。"""
        for side in SIDES:
            fighter, foe = self.fighter(side), self.fighter(self.other(side))
            lender = foe if "借内功" in self.traits(fighter) else None
            if fighter.lender is not lender:            # 对面换了人：原来借的那一种作废，下回合开始重新选
                fighter.counters.pop("loan", None)
                fighter.counters.pop("loan_turns", None)
                fighter.counters.pop("loan_last", None)
            fighter.lender = lender

    def _start_phase(self) -> None:
        self.choices, self.skipping = {}, set()
        self._link_lenders()
        for side in SIDES:
            actor, target = self.fighter(side), self.fighter(self.other(side))
            if actor.defeated:
                continue
            if self.start_of_turn(actor, None if target.defeated else target):
                self.skipping.add(side)
                self.choices[side] = {"spec": dict(_SKIP), "destination": None, "lives": actor.lives_remaining}
        self._replace_fallen()
        if self._check_end():
            return
        for side in list(self.skipping):        # 换上来的新人物不继承上一个人物的“跳过”
            if self.fighter(side).counters.get("personal_turns", 0) == 0:
                self.skipping.discard(side)
                self.choices.pop(side, None)
        self.scene_phase()                      # 牛顿选场景、龙王移动对手、库巴的扔和跑
        self.loan_phase()                       # 宋濂选借对面的哪一种内功
        self.divination_phase()                 # 占卜大师猜对手这回合用什么属性的招
        if len(self.choices) == 2:              # 双方都不能出招：直接结算这一回合
            self._resolve_round()

    def _resolve_round(self) -> None:
        entries = {side: self.choices[side] for side in SIDES}
        specs = {side: entries[side]["spec"] for side in SIDES}
        chosen = {side: {"id": specs[side]["id"], "name": specs[side]["name"]} for side in SIDES}
        self._emit("round", n=self.round, choices=chosen)
        self._log(f"第{self.round}回合：A的{self.fighter('A').name}选择【{specs['A']['name']}】，"
                  f"B的{self.fighter('B').name}选择【{specs['B']['name']}】。")
        self.check_divination(specs)
        # A、B 各用一条独立的随机数流：谁先出手不会改变另一方的随机结果。
        streams = {side: random.Random(self._main_rng.getrandbits(64)) for side in SIDES}

        # 1. 范仲淹的换人最先生效，然后是普通换人
        void: dict[str, str] = {}               # 人物被换走以后，原来选的招出不了的一方
        for side in SIDES:
            if specs[side]["effect"] == "swap_character" and side not in void:
                self._fan_swap(side, specs, entries, void)
        for side in SIDES:
            if specs[side]["action_kind"] == "switch":
                self._switch(side, specs[side]["switch_to"], voluntary=True)

        # 2. 憋神技：场上所有神技作废，出神技的人被封神 3 回合；被憋不算用掉
        cancelled: set[str] = set()
        if any(specs[side]["effect"] == "block_divine" for side in SIDES):
            for side in SIDES:
                if "神技" in specs[side]["attributes"]:
                    cancelled.add(side)
                    self._emit("stifle", side=side, by=self.other(side), skill=specs[side]["name"])
                    self._log(f"{self.label(self.fighter(side))}的【{specs[side]['name']}】被憋神技憋回去，没有效果。")
                    self.apply_status(self.fighter(side), "封神", 3, self.other(side), force_body=True)

        # 3. 防御和平面镜，不分先后手
        blocked: dict[str, str] = {}
        reflected: set[str] = set()
        for defender, attacker in (("A", "B"), ("B", "A")):
            d_spec, a_spec = specs[defender], specs[attacker]
            if a_spec["target"] != "enemy" or attacker in cancelled or entries[attacker].get("on_self"):
                continue
            code = DEFENSE_CODE.get(d_spec["id"])
            if code is not None and a_spec["defense"] == code:
                blocked[attacker] = d_spec["name"]
            elif d_spec["effect"] == "mirror" and a_spec["defense"] == "j":
                reflected.add(attacker)

        # 4. 出手顺序：档位高的先；同一档先后有区别就贼
        acting = [side for side in SIDES
                  if specs[side]["action_kind"] not in {"defense", "skip", "switch"} and side not in cancelled
                  and specs[side]["effect"] != "swap_character"]
        order = acting
        if len(acting) == 2:
            tiers = [self._tier(self.fighter(side), specs[side]) for side in acting]
            if tiers[0] == tiers[1]:
                first = self._decide_order(acting[0], acting[1], "两边的招同一档，谁先出手结果不一样", chosen)
                order = acting if first == acting[0] else acting[::-1]
            else:
                order = acting if tiers[0] > tiers[1] else acting[::-1]
                self._log(f"{order[0]}先出手。")

        # 5. 依次出招
        for side in order:
            self.rng = streams[side]
            actor, target, spec = self.fighter(side), self.fighter(self.other(side)), specs[side]
            # 雨晨：一回合里两边选好的招都会打出来。就算先被对面打死了、或者丢了一条命，这一招照样出。
            # （只有被先手封住的招会憋回去。）
            if actor.defeated:
                self._log(f"{self.label(actor)}虽然已经倒下，这回合选好的【{spec['name']}】照样打出来。")
            elif actor.lives_remaining < entries[side]["lives"]:
                self._log(f"{self.label(actor)}虽然丢了一条命，这回合选好的【{spec['name']}】照样打出来。")
            if side in void:
                self._emit("cancel", side=side, skill=spec["name"], why="人物被换走")
                self._log(f"{side}场上的人物被换成了{actor.name}，原来选的【{spec['name']}】出不了：{void[side]}。")
                continue
            if self._is_sealed(actor, spec) and not self._unblockable(actor, spec):
                self._emit("sealed", side=side, skill=spec["name"])
                self._log(f"{self.label(actor)}的【{spec['name']}】被先手封住，憋回去了，这回合没有出招。")
                continue
            if "神技" in spec["attributes"] and actor.name != "巫师":
                actor.used_shen.add(spec["id"])
            if entries[side].get("on_self"):            # 打自己：不用躲，对手也挡不了；伤害照算
                self._emit("move", **self._move_data(actor, actor, spec), on_self=True)
                self._log(f"{self.label(actor)}对自己使用【{spec['name']}】。")
                self.resolve_action(actor, actor, spec, entries[side]["destination"])
                continue
            if side in blocked:
                self._emit("move", **self._move_data(actor, target, spec), blocked=True)
                self._emit("block", side=target.side, attacker=side, by=blocked[side], skill=spec["name"])
                self._log(f"{self.label(target)}使用【{blocked[side]}】，防住了{self.label(actor)}的【{spec['name']}】。")
                continue
            if side in reflected:
                self._emit("move", **self._move_data(actor, target, spec), blocked=True)
                self._emit("reflect", side=target.side, attacker=side, skill=spec["name"])
                self._log(f"{self.label(target)}使用【平面镜】，把{self.label(actor)}的【{spec['name']}】反弹回去。")
                target = actor
            else:
                self._emit("move", **self._move_data(actor, target, spec))
            self._log(f"{self.label(actor)}使用【{spec['name']}】。")
            self.resolve_action(actor, target, spec, entries[side]["destination"])
            for key, amount in actor.resources.items():          # 丢了一条命以后东西清零了，照样出的招不能把数量扣成负的
                actor.resources[key] = max(0, amount)
        self.rng = self._main_rng
        for side in SIDES:
            if specs[side]["action_kind"] == "defense" and specs[side]["effect"] != "block_divine":
                attacker = self.other(side)
                if attacker not in blocked and attacker not in reflected:
                    self._emit("defend_miss", side=side, by=specs[side]["name"])
                    self._log(f"{self.label(self.fighter(side))}的【{specs[side]['name']}】没有防住对应的招。")

        # 6. 回合结束
        self._emit("phase", name="end")
        for side in order + [s for s in SIDES if s not in order]:
            self.rng = streams[side]
            self.end_of_turn(self.fighter(side))
        self.rng = self._main_rng
        if self._forced_first is not None:
            raise _ProbeStop()

        # 7. 进化和衰变；倒下的人物换下一个；判断胜负；进入下一回合
        self.form_phase()
        self._replace_fallen()
        if self._check_end():
            return
        self.round += 1
        self._want_start = True

    # ================= 换人和胜负 =================

    def _switch(self, side: str, index: int, voluntary: bool) -> None:
        player = self.players[side]
        old, new = player.fighter, player.team[index]
        for name in [n for n in old.statuses if n not in SELF_BUFFS and n != "无敌"]:
            old.statuses.pop(name, None)       # 下场时不良特效和虫子消失
        old.parasites.clear()
        old.lender = None
        player.active = index
        new.counters["field_turns"] = 0        # 重新上场：从头数“上场以后的第几回合”
        new.scene = old.scene                  # 新上场的人物站在上一个人物的场景
        self._link_lenders()
        # 把上场的人物整个放进事件里：他这时候才亮出来，网页手里的局面可能还是他上场之前的
        self._emit("switch", side=side, index=index, name=new.name, voluntary=voluntary,
                   scene=new.scene, height=new.scene_height, fighter=self._fighter_view(new), **self.vitals(new))
        self._log(f"{side}换上{new.name}。" if voluntary else f"{side}的{old.name}倒下，{new.name}上场。")
        self._on_enter(new)

    def _fan_swap(self, side: str, specs: dict[str, Any], entries: dict[str, Any], void: dict[str, str]) -> None:
        """范仲淹的换人：他和对面场上的人物互换，两个人物带着自己的一切（内功、体力、状态、场景）换边。

        对面这回合原来选的招，改由换过去的范仲淹来出；范仲淹出不了的（比如那个人物的专属招）就作废。
        """
        other = self.other(side)
        mine, theirs, spec = self.fighter(side), self.fighter(other), specs[side]
        self._emit("move", **self._move_data(mine, theirs, spec))
        if DEFENSE_CODE.get(specs[other]["id"]) == spec["defense"]:
            self._emit("block", side=other, attacker=side, by=specs[other]["name"], skill=spec["name"])
            self._log(f"{self.label(theirs)}使用【{specs[other]['name']}】，防住了{self.label(mine)}的【换人】。")
            return
        if theirs.is_true_body or theirs.defeated:
            self._log(f"{self.label(mine)}的【换人】没有可以换的对象。")
            return
        a, b = self.players[side], self.players[other]
        a.team[a.active], b.team[b.active] = theirs, mine
        mine.learn_progress, theirs.learn_progress = b.learn_progress, a.learn_progress   # 学来的内功归玩家，不跟着人物走
        for fighter in (mine, theirs):
            fighter.side = self.other(fighter.side)
            for status in fighter.statuses.values():        # 状态和虫子是谁加的，也跟着换边
                if status.source in SIDES:
                    status.source = self.other(status.source)
            for parasite in fighter.parasites.values():
                parasite.source = self.other(parasite.source)
            for item in fighter.counters.get("delayed_effects", []):
                if item.get("source") in SIDES:
                    item["source"] = self.other(item["source"])
        self._link_lenders()
        self._emit("swap_fighters", side=side, fighters={s: self._fighter_view(self.fighter(s)) for s in SIDES})
        self._log(f"{side}的{mine.name}使用【换人】：{theirs.name}归{side}，{mine.name}归{other}。")
        for s in SIDES:
            entries[s]["lives"] = self.fighter(s).lives_remaining
        if specs[other]["action_kind"] not in {"defense", "skip", "switch"}:
            reason = self._illegal_reason(self.fighter(other), self.fighter(side), specs[other])
            if reason:
                void[other] = reason

    def _on_enter(self, fighter: Fighter) -> None:
        if fighter.entered:
            return
        fighter.entered = True
        traits, foe = self.traits(fighter), self.fighter(self.other(fighter.side))
        if "初登场无敌3" in traits:
            fighter.statuses["无敌"] = Status("无敌", 3, fighter.side, fresh=False)
        if "首次X光" in traits and not foe.defeated:
            self.add_radiation(foe, 5, fighter.side, "首次出场X光")

    def _replace_fallen(self) -> None:
        # 新上场的人物可能一登场就打死对面（比如首次出场的 X 光），所以要反复检查到没人倒下为止。
        for _ in range(2 * max(len(p.team) for p in self.players.values()) + 2):
            if not any(p.fighter.defeated and p.alive_any() for p in self.players.values()):
                return
            self._replace_fallen_once()

    def _replace_fallen_once(self) -> None:
        for side in SIDES:
            player = self.players[side]
            if not player.fighter.defeated:
                continue
            bench = player.bench()
            if len(bench) > 1:
                options = [{"id": str(i), "name": player.team[i].name} for i in bench]
                decision = self._decide("choose", side=side, options=options, reason=f"{side}选择下一个上场的人物")
                index = int(decision["value"])
            elif bench:
                index = bench[0]
            else:
                body = [i for i, f in enumerate(player.team) if f.is_true_body and not f.defeated]
                if not body:
                    continue                    # 没有人了，由 _check_end 判负
                index = body[0]
                self._log(f"{side}的人物全部倒下，超级真身上场。")
            self._switch(side, index, voluntary=False)

    def _check_end(self) -> bool:
        lost = [side for side in SIDES if not self.players[side].alive_any()]
        if not lost:
            return False
        self.done = True
        self.winner = None if len(lost) == 2 else self.other(lost[0])
        self._emit("end", winner=self.winner)
        self._log(f"对战结束，{self.winner}获胜。" if self.winner else "对战结束，双方同时倒下。")
        return True

    # ================= 能不能出这个招 =================

    def _tier(self, fighter: Fighter, spec: dict[str, Any]) -> int:
        if spec["effect"] == "swap_character":
            return TIER_FAN_SWAP
        if spec["action_kind"] == "switch":
            return TIER_SWITCH
        if spec["action_kind"] in {"defense", "skip"}:
            return TIER_NORMAL
        tier = TIER_NORMAL
        if "神技" in spec["attributes"]:
            tier = TIER_SHEN
        elif spec["id"] in FIRST_STRIKE_IDS:
            tier = TIER_FIRST
        level = fighter.inner_level("凌波微步")
        if level >= 4:
            tier = max(tier, TIER_LINGBO4)
        elif level == 3:
            tier = max(tier, TIER_SHEN)
        elif level >= 1:
            tier = max(tier, TIER_FIRST)
        return tier

    @staticmethod
    def _is_sealed(actor: Fighter, spec: dict[str, Any]) -> bool:
        return any(SEAL_BY_ATTRIBUTE.get(a) and actor.has_status(SEAL_BY_ATTRIBUTE[a]) for a in spec["attributes"])

    @staticmethod
    def _unblockable(actor: Fighter, spec: dict[str, Any]) -> bool:
        """大招憋不回去的人物：他的大招不会被先手封住。"""
        return actor.name in UNBLOCKABLE_CHARACTERS and is_signature(actor.name, spec)

    def _illegal_reason(self, actor: Fighter, target: Fighter, spec: dict[str, Any]) -> str | None:
        if actor.defeated:
            return "人物已经倒下"
        if spec["id"] == "25":
            return "臭伽马只能由伽马射线触发"
        if spec.get("character") and spec["id"] not in self.char(actor)["skills"]:
            return "不是这个人物的专属招"
        if spec["effect"] == "swap_character" and target.is_true_body:
            return "不能和超级真身互换"
        if actor.name == "武圣":
            first_life = actor.lives_remaining == actor.lives_total
            if spec["id"] in {"t2", "t3"} and first_life:
                return "第一条命不能用第二条命的招"
            if spec["id"] in {"t4", "t5"} and not first_life:
                return "只有第一条命可以用"
        for attribute in spec["attributes"]:
            seal = SEAL_BY_ATTRIBUTE.get(attribute)
            if seal and actor.has_status(seal):
                return f"处于{seal}，{attribute}类的招被封"
        if "神技" in spec["attributes"] and actor.name != "巫师" and spec["id"] in actor.used_shen:
            return "这条命里已经用过这个神技"
        effect = spec["effect"]
        if effect == "aurora" and actor.scene != "南极":
            return "极光只能在南极使用"
        if effect == "gamma" and actor.name != "达伽马" and (actor.resources["超新星"] < 1 or actor.resources["星体能量"] < 5):
            return "需要1超新星和5星体能量"
        if effect == "sunspot" and actor.resources["星体能量"] < 3:
            return "需要3星体能量"
        if effect == "build_accelerator" and actor.devices.get("粒子加速器", 0) >= ACCELERATOR_BIG["builds"]:
            return "粒子加速器已经造到头了"
        if effect == "accelerator" and accelerator_level(int(actor.devices.get("粒子加速器", 0))) is None:
            return "粒子加速器还没造好（要造 10 下）"
        if effect == "planet" and (actor.resources["超新星"] < 1 or actor.resources["星体能量"] < 3):
            return "需要1超新星和3星体能量"
        if effect == "panacea" and actor.resources["万灵丹"] < 1:
            return "没有万灵丹"
        if effect == "collect_supernova" and not SCENES[actor.scene].get("collect_supernova"):
            return "当前场景不能收集超新星"
        if effect == "collect_star" and not SCENES[actor.scene].get("collect_star"):
            return "当前场景不能收集星体能量"
        if effect == "collect_oxygen" and actor.scene_height != 0:
            return "氧气只能在地面高度收集"
        if effect == "drink_wine" and actor.resources["酒"] < 1:
            return "没有酒"
        if effect in {"rise_self", "choose_scene"} and actor.has_status("万能胶"):
            return "万能胶使场景无法移动"
        any_scene = effect == "accelerator" and actor.devices.get("粒子加速器", 0) >= ACCELERATOR_BIG["builds"]
        # 够不够得着（雨晨）：在上面的人默认打得到下面的人；在下面的人默认打不到上面的人，
        # 除非这个招本身能往上打；神技不受限制；能打全宇宙的人物出什么招都打得到。
        any_scene = any_scene or "神技" in spec["attributes"]
        # 哪些招能往上打、最高打到哪一层，是雨晨逐个定的（见 data.py 的 UP_REACH）。
        # 引擎原来的“人物距离”和“招的距离”这两个数不用了。
        if spec["target"] == "enemy" and actor.distance != inf and not any_scene \
                and target.scene_height > actor.scene_height:
            top = UP_REACH.get(spec["id"])
            if top is None:
                return "够不着：对手在你上面，这个招不能往上打"
            if target.scene_height > top:
                limit = "大气层之内（最高到电离层）" if top <= 3 else "外太空"
                return f"够不着：对手在{target.scene}，这个招往上最高只能打到{limit}"
        return None

    def _warning(self, target: Fighter, spec: dict[str, Any]) -> str:
        """这个招现在出了也没用的原因（对手免疫，或者对手正无敌）。只是提醒，不拦着出。"""
        hits_foe = spec["target"] == "enemy" or spec["effect"] == "self_status_and_damage"
        if not hits_foe or spec["action_kind"] != "skill" or target.defeated:
            return ""
        why = self.immunity_reason(target, spec)
        if why is None and spec["effect"] is None and int(spec["damage"]) <= 0 and spec["statuses"]                 and "免疫不良" in self.traits(target) and all(name not in SELF_BUFFS for name, _ in spec["statuses"]):
            why = "免疫不良特效"
        return f"对手{why}，这个招现在打他无效" if why else ""

    # ================= 杂项 =================

    def _make_fighter(self, side: str, name: str, true_body: bool = False) -> Fighter:
        char_id = TRUE_BODY_ID if true_body else CHARACTER_NAME_TO_ID.get(name, str(name))
        if char_id not in CHARACTERS:
            raise RuleError(f"未知人物：{name}")
        data = CHARACTERS[char_id]
        return Fighter(
            side=side, character_id=char_id, name=data["name"], max_hp=data["hp"], hp=data["hp"],
            distance=data["distance"], inner=dict(data["inner"]), initial_inner=dict(data["inner"]),
            max_shield=data["shield"], shield=data["shield"], lives_total=data["lives"],
            lives_remaining=data["lives"], is_true_body=true_body,
        )

    def _fighter_view(self, f: Fighter) -> dict[str, Any]:
        return {
            "side": f.side, "character_id": f.character_id, "name": f.name, "hp": f.hp, "max_hp": f.max_hp,
            "shield": f.shield, "max_shield": f.max_shield, "lives_remaining": f.lives_remaining,
            "lives_total": f.lives_total, "distance": "无穷" if f.distance == inf else f.distance,
            "scene": f.scene, "height": f.scene_height, "inner": f.all_inner(),
            "borrowed": sorted(n for n, level in f.all_inner().items() if level > f.own_level(n)),      # 借来的
            "learned": sorted(n for n in f.learn_progress if f.learned_level(n) > int(f.inner.get(n, 0))),  # 玩家学来的
            "traits": sorted(self.traits(f)),
            "statuses": {n: {"turns": s.turns, "layer": s.layer} for n, s in f.statuses.items()},
            "parasites": {n: {"count": p.count, "layer": p.layer} for n, p in f.parasites.items()},
            "resources": dict(f.resources), "radiation": f.radiation, "defeated": f.defeated,
            "used_shen": sorted(f.used_shen), "is_true_body": f.is_true_body, "entered": f.entered,
            "learn_progress": dict(f.learn_progress), "devices": dict(f.devices),
        }

    def _move_data(self, actor: Fighter, target: Fighter, spec: dict[str, Any]) -> dict[str, Any]:
        return {
            "side": actor.side, "target": actor.side if spec["target"] == "self" else target.side,
            "id": spec["id"], "name": spec["name"], "attributes": list(spec["attributes"]),
            "action_kind": spec["action_kind"], "effect": spec["effect"],
        }

    def _log(self, message: str) -> None:
        if self._skip_event():
            return
        self.log.append(message)
        self.events.append({"t": "log", "text": message})

    def _emit(self, kind: str, **data: Any) -> None:
        if self._skip_event():
            return
        self.events.append({"t": kind, **data})

    def _skip_event(self) -> bool:
        """重算时，上一次已经显示过的事件不再重复；试算时什么都不产生。"""
        self._count += 1
        return self._mute or self._count <= self._kept
