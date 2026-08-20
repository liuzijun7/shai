"""《晒》双角色先选招、后统一结算的规则引擎。

这个模块不依赖 Tkinter。GUI、自动测试和后续强化学习环境都调用同一个
``GameEngine``，避免出现“界面一套规则、训练又一套规则”。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from math import floor, inf
import random
from typing import Any

from game_data import (
    ALL_INNER_NAMES,
    CHARACTERS,
    CHARACTER_NAME_TO_ID,
    CONTROL_STATUSES,
    DAMAGE_STATUSES,
    INNER_VALUES,
    SCENES,
    SEAL_BY_ATTRIBUTE,
    SELF_BUFFS,
    SKILLS,
    VERTICAL_SCENES,
    character_skill_ids,
)


@dataclass
class Status:
    name: str
    turns: int
    source: str | None = None
    layer: str = "body"
    unremovable: bool = False
    fresh: bool = True


@dataclass
class Parasite:
    name: str
    count: int
    source: str
    age: int = 0
    layer: str = "body"


@dataclass
class Fighter:
    side: str
    character_id: str
    name: str
    max_hp: int
    hp: int
    distance: float
    inner: dict[str, int]
    initial_inner: dict[str, int]
    max_shield: int = 0
    shield: int = 0
    lives_total: int = 1
    lives_remaining: int = 1
    scene: str = "地面"
    statuses: dict[str, Status] = field(default_factory=dict)
    parasites: dict[str, Parasite] = field(default_factory=dict)
    resources: dict[str, int] = field(default_factory=lambda: {
        "氧气": 10, "星体能量": 0, "超新星": 0, "万灵丹": 0,
        "海洋之心": 0, "酒": 0, "万能胶": 0,
    })
    radiation: int = 0
    counters: dict[str, Any] = field(default_factory=dict)
    defeated: bool = False

    @property
    def scene_height(self) -> int:
        return int(SCENES[self.scene]["height"])

    def has_status(self, name: str) -> bool:
        return name in self.statuses and self.statuses[name].turns > 0

    def inner_level(self, name: str) -> int:
        if self.has_status("封内"):
            return 0
        return int(self.inner.get(name, 0))


class RuleError(ValueError):
    pass


class GameEngine:
    """A/B 双角色先选招、再统一结算的规则测试引擎。

    公开接口专门保持简单、可序列化：
    - ``reset``：重开对战；
    - ``legal_actions``：得到动作及灰显原因；
    - ``step``：执行一个动作；
    - ``observation``：得到当前完整状态。
    """

    VERSION = "0.2.0"

    def __init__(self, character_a: str = "陶渊明", character_b: str = "武圣", seed: int | None = None):
        self.random = random.Random(seed)
        self.seed = seed
        self.fighters: dict[str, Fighter] = {}
        self.current_side = "A"
        self.round_number = 1
        self.half_turn = 0
        self.water_level = -1
        self.done = False
        self.winner: str | None = None
        self.log: list[str] = []
        self.pending_actions: dict[str, dict[str, Any]] = {}
        self._round_prepared = False
        self.reset(character_a, character_b, seed)

    # ---------- public API ----------

    def reset(self, character_a: str = "陶渊明", character_b: str = "武圣", seed: int | None = None) -> dict[str, Any]:
        if seed is not None:
            self.seed = seed
            self.random.seed(seed)
        self.fighters = {
            "A": self._make_fighter("A", character_a),
            "B": self._make_fighter("B", character_b),
        }
        self.current_side = "A"
        self.round_number = 1
        self.half_turn = 0
        self.water_level = -1
        self.done = False
        self.winner = None
        self.pending_actions = {}
        self.log = [f"对战开始：A的{self.fighters['A'].name} 对 B的{self.fighters['B'].name}。"]

        # 宋濂复制对手内功，再额外获得铁布衫3。
        for side, other_side in (("A", "B"), ("B", "A")):
            if self.fighters[side].name == "宋濂":
                self.fighters[side].inner = dict(self.fighters[other_side].inner)
                self.fighters[side].inner["铁布衫"] = 3
                self.fighters[side].initial_inner = dict(self.fighters[side].inner)

        # 首次登场被动。
        for side in ("A", "B"):
            fighter = self.fighters[side]
            if "初登场无敌3" in self.character_data(fighter)["traits"]:
                fighter.statuses["无敌"] = Status("无敌", 3, side, fresh=False)
            if "首次X光" in self.character_data(fighter)["traits"]:
                self._add_radiation(self.fighters[self.other_side(side)], 5, side, "首次出场X光")

        self._round_prepared = False
        self._prepare_round()
        return self.observation()

    def legal_actions(self, side: str | None = None) -> list[dict[str, Any]]:
        side = side or self.current_side
        actor = self.fighters[side]
        target = self.fighters[self.other_side(side)]
        action_ids = list(character_skill_ids(self.character_data(actor)))
        if actor.scene_height == 0:
            action_ids.append("sys_collect_oxygen")
        result = []
        for action_id in action_ids:
            if action_id == "sys_collect_oxygen":
                spec = {
                    "id": action_id, "name": "收集氧气", "attributes": ("物品",),
                    "damage": 0, "statuses": (), "defense": None, "distance": 0,
                    "target": "self", "effect": "collect_oxygen", "description": "地面类场景收集氧气。",
                    "character": None, "action_kind": "collect",
                }
            else:
                spec = SKILLS[action_id]
            reason = self._illegal_reason(actor, target, spec)
            already_selected = side in self.pending_actions
            result.append({
                **spec,
                "attributes_text": "+".join(spec["attributes"]) or "无属性",
                "special_effect": self._special_effect_text(actor, spec),
                "initiative": self._initiative(actor, spec) if spec["action_kind"] != "defense" else 0,
                "legal": reason is None and side == self.current_side and not self.done and not already_selected,
                "reason": reason or ("本回合已经选招" if already_selected else ("还没轮到该角色选招" if side != self.current_side else "")),
            })
        return result

    def step(self, action_id: str, destination: str | None = None) -> dict[str, Any]:
        if self.done:
            raise RuleError("对战已经结束。")
        if not self._round_prepared:
            self._prepare_round()
        actor = self.fighters[self.current_side]
        actions = {item["id"]: item for item in self.legal_actions()}
        if action_id not in actions:
            raise RuleError(f"未知动作：{action_id}")
        if not actions[action_id]["legal"]:
            raise RuleError(actions[action_id]["reason"] or "当前不能执行该动作。")
        spec = actions[action_id]
        if spec["effect"] == "choose_scene" and destination not in SCENES:
            raise RuleError("该操作需要选择有效场景。")

        start_log = len(self.log)
        selecting_side = self.current_side
        self.pending_actions[selecting_side] = {
            "spec": spec,
            "destination": destination,
            "lives_remaining": actor.lives_remaining,
        }
        round_resolved = False
        next_side = next((side for side in ("A", "B") if side not in self.pending_actions and not self.fighters[side].defeated), None)
        if next_side is not None:
            self.current_side = next_side
        else:
            self._resolve_pending_round()
            round_resolved = True
        return {
            "observation": self.observation(),
            "events": self.log[start_log:],
            "done": self.done,
            "winner": self.winner,
            "round_resolved": round_resolved,
            "selected_side": selecting_side,
        }

    def observation(self) -> dict[str, Any]:
        return {
            "version": self.VERSION,
            "round": self.round_number,
            "current_side": self.current_side,
            "pending_actions": {
                side: {"action_id": item["spec"]["id"], "name": item["spec"]["name"]}
                for side, item in self.pending_actions.items()
            },
            "water_level": self.water_level,
            "done": self.done,
            "winner": self.winner,
            "fighters": {side: self._fighter_observation(f) for side, f in self.fighters.items()},
            "legal_action_ids": [a["id"] for a in self.legal_actions() if a["legal"]] if not self.done else [],
            "log": list(self.log),
        }

    # ---------- creation / serialization ----------

    def _make_fighter(self, side: str, character: str) -> Fighter:
        char_id = CHARACTER_NAME_TO_ID.get(character, str(character))
        if char_id not in CHARACTERS:
            raise RuleError(f"未知人物：{character}")
        data = CHARACTERS[char_id]
        return Fighter(
            side=side,
            character_id=char_id,
            name=data["name"],
            max_hp=data["hp"],
            hp=data["hp"],
            distance=data["distance"],
            inner=dict(data["inner"]),
            initial_inner=dict(data["inner"]),
            max_shield=data["shield"],
            shield=data["shield"],
            lives_total=data["lives"],
            lives_remaining=data["lives"],
        )

    @staticmethod
    def character_data(fighter: Fighter) -> dict[str, Any]:
        return CHARACTERS[fighter.character_id]

    def _fighter_observation(self, fighter: Fighter) -> dict[str, Any]:
        distance = "无穷" if fighter.distance == inf else fighter.distance
        return {
            "side": fighter.side,
            "character_id": fighter.character_id,
            "name": fighter.name,
            "hp": fighter.hp,
            "max_hp": fighter.max_hp,
            "shield": fighter.shield,
            "max_shield": fighter.max_shield,
            "lives_remaining": fighter.lives_remaining,
            "lives_total": fighter.lives_total,
            "distance": distance,
            "scene": fighter.scene,
            "height": fighter.scene_height,
            "inner": dict(fighter.inner),
            "statuses": {name: asdict(value) for name, value in fighter.statuses.items()},
            "parasites": {name: asdict(value) for name, value in fighter.parasites.items()},
            "resources": dict(fighter.resources),
            "radiation": fighter.radiation,
            "counters": dict(fighter.counters),
            "defeated": fighter.defeated,
        }

    # ---------- turn flow ----------

    def _prepare_round(self) -> None:
        """同时处理A/B的开始阶段，并把不能行动者登记为跳过。"""
        if self.done:
            return
        self.pending_actions = {}
        self._round_prepared = True
        for side in ("A", "B"):
            actor = self.fighters[side]
            target = self.fighters[self.other_side(side)]
            if actor.defeated or self._start_turn(actor, target):
                self.pending_actions[side] = {
                    "spec": self._skip_spec(),
                    "destination": None,
                    "lives_remaining": actor.lives_remaining,
                }
        self._check_battle_end()
        if self.done:
            return
        next_side = next((side for side in ("A", "B") if side not in self.pending_actions), None)
        if next_side is None:
            self._resolve_pending_round()
        else:
            self.current_side = next_side

    def _start_turn(self, actor: Fighter, target: Fighter) -> bool:
        actor.counters["personal_turns"] = int(actor.counters.get("personal_turns", 0)) + 1
        # 喝酒的无敌维持到下次自己的行动开始；下一次行动获得伤害/特效倍率。
        if actor.counters.pop("wine_invincible_until_next_turn", False):
            actor.statuses.pop("无敌", None)
            actor.counters["wine_boost_active"] = True
        else:
            actor.counters["wine_boost_active"] = False

        self._process_delayed_effects(actor)
        self._trigger_lucky(actor)
        self._trigger_periodic_inner(actor, target)

        if actor.scene == "南极" and actor.counters["personal_turns"] % 3 == 0:
            self._apply_status(target=actor, name="昏睡", turns=1, source=None, force_body=True)
            self._log(f"{self._label(actor)}受到南极寒冷影响，本回合昏睡。")

        if actor.has_status("昏睡"):
            self._log(f"{self._label(actor)}处于昏睡，跳过行动。")
            return True
        if actor.has_status("封印"):
            self._log(f"{self._label(actor)}处于封印，跳过行动。")
            return True
        return False

    def _end_turn(self, actor: Fighter, target: Fighter) -> None:
        if actor.defeated:
            return
        self._resolve_damage_statuses(actor)
        self._resolve_parasites(actor)
        self._resolve_scene(actor)
        self._trigger_end_inner(actor)

        if not actor.defeated and "回合末换血" in self.character_data(actor)["traits"] and not target.defeated:
            actor.hp, target.hp = min(target.hp, actor.max_hp), min(actor.hp, target.max_hp)
            self._log(f"{self._label(actor)}与{self._label(target)}交换体力。")

        self._decrement_statuses(actor)
        actor.counters["wine_boost_active"] = False
        self._check_death(actor, source=None, reason="回合结束结算")

    def _resolve_pending_round(self) -> None:
        """防御先于先制判断；随后按先制执行两边动作并统一结束阶段。"""
        if self.done:
            return
        entries = {side: self.pending_actions[side] for side in ("A", "B")}
        specs = {side: entries[side]["spec"] for side in ("A", "B")}
        self._log(
            f"第{self.round_number}回合：A的{self.fighters['A'].name}选择【{specs['A']['name']}】，"
            f"B的{self.fighters['B'].name}选择【{specs['B']['name']}】。"
        )

        # 憋神技无视先后：只要有人选择，场上神技全部变成普通攻击并附加封神3。
        if any(specs[side]["effect"] == "block_divine" for side in ("A", "B")):
            for side in ("A", "B"):
                if "神技" in specs[side]["attributes"]:
                    self._log(f"{self._label(self.fighters[side])}的【{specs[side]['name']}】被憋神技，改为普通攻击。")
                    self._apply_status(self.fighters[side], "封神", 3, self.other_side(side), force_body=True)
                    specs[side] = SKILLS["0"]

        blocked: dict[str, str] = {}
        reflected: set[str] = set()
        defense_code = {"d1": 1, "d2": 2, "d3": 3, "d4": 4}
        for defender_side, attacker_side in (("A", "B"), ("B", "A")):
            defense_spec = specs[defender_side]
            attack_spec = specs[attacker_side]
            if attack_spec["target"] != "enemy":
                continue
            expected = defense_code.get(defense_spec["id"])
            if expected is not None and attack_spec["defense"] == expected:
                blocked[attacker_side] = defense_spec["name"]
            elif defense_spec["effect"] == "mirror" and attack_spec["defense"] == "j":
                reflected.add(attacker_side)

        actionable = [side for side in ("A", "B") if specs[side]["action_kind"] != "defense" and specs[side]["effect"] != "skip"]
        if len(actionable) == 2:
            ia = self._initiative(self.fighters[actionable[0]], specs[actionable[0]])
            ib = self._initiative(self.fighters[actionable[1]], specs[actionable[1]])
            if ia == ib:
                order = actionable if self.random.random() < 0.5 else list(reversed(actionable))
                self._log(f"双方先制均为{ia}，随机由{order[0]}先手。")
            else:
                order = actionable if ia > ib else list(reversed(actionable))
                self._log(f"{order[0]}先手。")
        else:
            order = actionable

        starting_lives = {side: entries[side]["lives_remaining"] for side in ("A", "B")}
        for side in order:
            actor = self.fighters[side]
            target = self.fighters[self.other_side(side)]
            spec = specs[side]
            if actor.defeated:
                self._log(f"{self._label(actor)}已经失去全部生命，行动取消。")
                continue
            if actor.lives_remaining < starting_lives[side]:
                self._log(f"{self._label(actor)}已经失去选招时的当前命，原行动取消。")
                continue
            if side in blocked:
                self._log(f"{self._label(target)}使用【{blocked[side]}】，成功防御{self._label(actor)}的【{spec['name']}】。")
                continue
            if side in reflected:
                self._log(f"{self._label(target)}使用【平面镜】，将{self._label(actor)}的【{spec['name']}】反弹。")
                target = actor
            if self._is_now_sealed(actor, spec):
                self._log(f"{self._label(actor)}的【{spec['name']}】被先手封禁，自动改为普通攻击。")
                spec = SKILLS["0"]
            self._log(f"{self._label(actor)}使用【{spec['name']}】。")
            self._resolve_action(actor, target, spec, entries[side]["destination"])

        # 防御动作不分先后；未匹配时只是不产生额外效果。
        for side in ("A", "B"):
            if specs[side]["action_kind"] == "defense" and specs[side]["effect"] != "block_divine":
                if self.other_side(side) not in blocked and self.other_side(side) not in reflected:
                    self._log(f"{self._label(self.fighters[side])}的【{specs[side]['name']}】没有防住对应技能。")

        for side in order + [side for side in ("A", "B") if side not in order]:
            self._end_turn(self.fighters[side], self.fighters[self.other_side(side)])
        self._check_battle_end()
        self.pending_actions = {}
        self._round_prepared = False
        if not self.done:
            self.round_number += 1
            self.current_side = "A"
            self._prepare_round()

    # ---------- legal action checks ----------

    def _illegal_reason(self, actor: Fighter, target: Fighter, spec: dict[str, Any]) -> str | None:
        if self.done:
            return "对战已结束"
        if actor.defeated:
            return "人物已经死亡"
        if spec["id"] == "25":
            return "臭伽马只能由伽马射线触发"
        if spec.get("character") and spec["character"] != actor.name:
            return "不是该人物的专属技能"
        if actor.name == "武圣":
            first_life = actor.lives_remaining == actor.lives_total
            if spec["id"] in {"t2", "t3"} and first_life:
                return "第一条命不能使用第二命技能"
            if spec["id"] in {"t4", "t5"} and not first_life:
                return "只有第一条命可以使用"
        for attribute in spec["attributes"]:
            seal = SEAL_BY_ATTRIBUTE.get(attribute)
            if seal and actor.has_status(seal):
                return f"处于{seal}，{attribute}技能被封"
        if spec["effect"] == "aurora" and actor.scene != "南极":
            return "极光只能在南极使用"
        if spec["effect"] == "gamma" and actor.name != "达伽马":
            if actor.resources["超新星"] < 1 or actor.resources["星体能量"] < 5:
                return "需要1超新星和5星体能量"
        if spec["effect"] == "sunspot" and actor.resources["星体能量"] < 3:
            return "需要3星体能量"
        if spec["effect"] == "panacea" and actor.resources["万灵丹"] < 1:
            return "没有万灵丹"
        if spec["effect"] == "collect_supernova" and not SCENES[actor.scene].get("collect_supernova"):
            return "当前场景不能收集超新星"
        if spec["effect"] == "collect_star" and not SCENES[actor.scene].get("collect_star"):
            return "当前场景不能收集星体能量"
        if spec["effect"] == "collect_oxygen" and actor.scene_height != 0:
            return "氧气只能在地面高度收集"
        if spec["effect"] == "drink_wine" and actor.resources["酒"] < 1:
            return "没有酒"
        if spec["effect"] in {"swap_character", "divination"}:
            return "该技能还需要候选队列或占卜输入，当前测试版暂不执行"
        if spec["effect"] in {"rise_self", "choose_scene"} and actor.has_status("万能胶"):
            return "万能胶使场景无法移动"
        if spec["target"] == "enemy" and actor.distance != inf:
            reach = float(actor.distance) + float(spec["distance"])
            height_gap = abs(actor.scene_height - target.scene_height)
            if height_gap > reach:
                return f"距离不足：高度差{height_gap}，人物+技能距离{int(reach)}"
        return None

    # ---------- action resolution ----------

    def _resolve_action(self, actor: Fighter, target: Fighter, spec: dict[str, Any], destination: str | None) -> None:
        effect = spec["effect"]
        traits = self.character_data(actor)["traits"]
        base_damage = self._character_damage_override(actor, spec)
        repetitions = self._effect_repetitions(actor)

        if effect == "collect_oxygen":
            self._collect(actor, "氧气", repetitions, scene_multiplier=SCENES[actor.scene].get("oxygen_multiplier", 1))
            return
        if effect == "collect_supernova":
            self._collect(actor, "超新星", repetitions)
            return
        if effect == "collect_star":
            self._collect(actor, "星体能量", repetitions)
            return
        if effect == "collect_wine":
            self._collect(actor, "酒", repetitions, scene_multiplier=1)
            return
        if effect == "collect_panacea":
            self._collect(actor, "万灵丹", repetitions, scene_multiplier=1)
            return
        if effect == "collect_glue":
            # 万能胶是收集即用，不进入库存；火系状态会立即消除它。
            self._apply_status(actor, "万能胶", 5, actor.side, force_body=True)
            if actor.has_status("烧伤") or actor.has_status("点燃"):
                actor.statuses.pop("万能胶", None)
                self._log(f"{self._label(actor)}身上的火系状态使万能胶立即失效。")
            return
        if effect == "drink_wine":
            actor.resources["酒"] -= 1
            actor.statuses["无敌"] = Status("无敌", 1, actor.side, fresh=False)
            actor.counters["wine_invincible_until_next_turn"] = True
            self._log(f"{self._label(actor)}喝下1个酒，本轮无敌。")
            return
        if effect == "choose_scene":
            self._set_scene(actor, destination or "地面")
            return
        if effect in {"build_yueyang", "build_pyramid"}:
            key = "岳阳楼" if effect == "build_yueyang" else "金字塔"
            actor.counters[key] = int(actor.counters.get(key, 0)) + repetitions
            self._log(f"{self._label(actor)}的{key}进度为{actor.counters[key]}/5。")
            while actor.counters[key] >= 5:
                actor.counters[key] -= 5
                self._upgrade_all_inner(actor)
            return
        if effect == "panacea":
            actor.resources["万灵丹"] -= 1
            self._cleanse(actor, include_radiation=False)
            self._log(f"{self._label(actor)}清除了不良状态和寄生虫。")
            return
        if effect == "rebirth":
            self._cleanse(actor, include_radiation=False)
            actor.hp = actor.max_hp
            actor.statuses["无敌"] = Status("无敌", 1, actor.side)
            if actor.name == "巫师":
                actor.shield = 0
                actor.max_shield = 0
            self._log(f"{self._label(actor)}浴火重生，体力回满并获得无敌。")
            return
        if effect == "self_status":
            for name, turns in spec["statuses"]:
                self._apply_status(actor, name, turns, actor.side, force_body=True)
            return
        if effect == "self_status_and_damage":
            if self._skill_hits(actor, target, spec) and not self._blocked_by_immunity(actor, target, spec):
                self._deal_skill_damage(actor, target, spec, base_damage, repetitions, prechecked=True)
            else:
                self._log(f"【{spec['name']}】没有影响到{self._label(target)}。")
            for name, turns in spec["statuses"]:
                self._apply_status(actor, name, turns, actor.side, force_body=True)
            if spec["id"] == "35":
                # 道威在状态施加后才影响后续技能，本次不倒推回血。
                pass
            self._after_special(actor, spec)
            return
        if effect == "meteor":
            total_hits = 0
            for _ in range(repetitions):
                while True:
                    total_hits += 1
                    self._deal_skill_damage(actor, target, spec, base_damage, 1)
                    if target.defeated or self.random.random() >= 0.50:
                        break
            self._log(f"流星共命中{total_hits}拳。")
            return

        # 其余对敌动作统一做一次命中和免疫判定；未命中时伤害、特效和位移均失败。
        if effect == "sound_wave" and SCENES[target.scene].get("vacuum"):
            self._log(f"{self._label(target)}处于真空，声波炮无效。")
            self._after_special(actor, spec)
            return
        if spec["target"] == "enemy":
            if not self._skill_hits(actor, target, spec):
                self._log(f"{self._label(target)}闪避了【{spec['name']}】。")
                self._after_special(actor, spec)
                return
            if self._blocked_by_immunity(actor, target, spec):
                self._after_special(actor, spec)
                return
        if effect == "sunspot":
            actor.resources["星体能量"] -= 3
        if effect == "gamma" and actor.name != "达伽马":
            actor.resources["超新星"] -= 1
            actor.resources["星体能量"] -= 5

        if effect == "ultimate_drain":
            ratio = 1.0 if actor.name == "肥饕餮" else 0.8
            amount = int(target.max_hp * ratio)
            dealt = self._apply_nonbasic_damage(actor, target, amount, "究极吸取")
            if dealt:
                actor.hp += dealt
                self._log(f"{self._label(actor)}吸取并恢复{dealt}体力。")
            self._after_special(actor, spec)
            return
        if effect == "xray":
            if target.has_status("氪"):
                self._log(f"{self._label(target)}的氪屏障令X光无效。")
            else:
                self._add_radiation(target, 5 * repetitions, actor.side, "X光")
            return
        if effect == "gamma":
            if target.has_status("无敌"):
                self._log(f"{self._label(target)}处于无敌，伽马射线无效。")
                return
            self._add_radiation(target, 15, actor.side, "伽马射线")
            if self.random.random() < 1 / 3 and not target.defeated:
                self._apply_status(target, "昏睡", self._duration(actor, spec, 10), actor.side)
                self._log("臭伽马触发。")
            self._after_special(actor, spec)
            return
        if effect == "sulfuric_acid" and actor.name in {"生化大师", "猪带小天王"}:
            if self.random.random() < 0.5:
                self._kill_current_life(target, actor.side, all_lives=False, reason="硫酸秒杀")
            else:
                self._log("硫酸的50%秒杀没有触发。")
            return
        if effect == "ether":
            if actor.name in {"生化大师", "猪带小天王"}:
                self._apply_status(target, "昏睡", self._duration(actor, spec, 5), actor.side)
            else:
                if target.has_status("烧伤") or target.has_status("点燃"):
                    self._apply_nonbasic_damage(actor, target, int(target.max_hp * 0.50), "乙醚联动")
                target.counters.setdefault("delayed_effects", []).append({
                    "remaining": 2, "status": "昏睡", "turns": self._duration(actor, spec, 5), "source": actor.side,
                })
                self._log(f"{self._label(target)}将在两个自己的回合后昏睡。")
            return
        if effect == "pork_tapeworm":
            self._add_parasite(target, "猪带绦虫", repetitions, actor.side)
            return
        if effect == "sleep_tapeworm":
            self._add_parasite(target, "昏睡绦虫", repetitions, actor.side)
            self._apply_status(target, "昏睡", 1, actor.side)
            return
        if effect == "leech":
            self._add_parasite(target, "蚂蟥", repetitions, actor.side)
            return
        if effect == "leech_wave":
            self._deal_skill_damage(actor, target, spec, base_damage, repetitions, prechecked=True)
            self._add_parasite(target, "蚂蟥", 3 * repetitions, actor.side)
            self._after_special(actor, spec)
            return
        if effect == "taotie_fang":
            total = 0
            for _ in range(2 * repetitions):
                total += self._deal_skill_damage(actor, target, spec, base_damage, 1, prechecked=True)
            actor.hp += total
            if actor.hp > actor.max_hp:
                actor.lives_total += 1
                actor.lives_remaining += 1
                actor.hp = actor.max_hp
                self._log(f"{self._label(actor)}突破上限，增加一条命。")
            return

        # 大部分技能共用的“伤害→特效→位移/附加效果”流程。
        self._deal_skill_damage(actor, target, spec, base_damage, repetitions, prechecked=True)
        if target.defeated:
            self._after_special(actor, spec)
            return
        for name, turns in spec["statuses"]:
            status_target = actor if name in SELF_BUFFS else target
            unremovable = actor.name == "灵力圣使" and "魔法" in spec["attributes"] and status_target is target
            self._apply_status(status_target, name, self._duration(actor, spec, turns), actor.side,
                               force_body=status_target is actor, unremovable=unremovable)

        if effect == "rise_self":
            steps = 2 if "圣六式覆盖" in traits else 1
            self._move_vertical(actor, steps)
        elif effect == "lower_target":
            steps = -4 if actor.name == "龙王" and spec["id"] == "9" else -1
            self._move_vertical(target, steps)
        elif effect == "antarctic":
            self._set_scene(target, "南极")
            if actor.name == "龙王":
                self._apply_status(target, "昏睡", self._duration(actor, spec, 3), actor.side)
        elif effect == "flood":
            self.water_level += 1
            self._log(f"水面上升到高度{self.water_level}。")
        elif effect == "death_note":
            if self.random.random() < 0.125:
                self._kill_current_life(target, actor.side, all_lives=False, reason="死亡笔记秒杀")
        elif effect == "drop_ground":
            if target.scene_height > 0:
                self._set_scene(target, "地面")
        elif effect == "sunspot":
            if target.scene_height > 0:
                self._set_scene(target, "地面")
            for name in list(target.inner):
                target.inner[name] = max(0, target.inner[name] - 1)
            self._log(f"{self._label(target)}的全部内功下降一级。")
        elif effect == "typhoon":
            for key in target.resources:
                if key != "氧气":
                    target.resources[key] = 0
            self._log(f"{self._label(target)}失去全部物品。")

        self._after_special(actor, spec)

    # ---------- combat helpers ----------

    def _character_damage_override(self, actor: Fighter, spec: dict[str, Any]) -> int:
        name = spec["name"]
        if actor.name == "灵力圣使" and name == "圣六式空凌":
            return 90000
        if actor.name == "范仲淹" and name == "洪水":
            return 80000
        if actor.name == "牛顿" and name == "麒麟芒星":
            return 90000
        if actor.name == "龙王" and name in {"寒潮", "地震", "台风"}:
            return 50000
        if actor.name == "肥龙王" and spec["id"] in {"8", "9", "10", "11"}:
            return 80000
        return int(spec["damage"])

    def _deal_skill_damage(self, actor: Fighter, target: Fighter, spec: dict[str, Any], base: int,
                           repetitions: int, prechecked: bool = False) -> int:
        if base <= 0:
            return 0
        total = 0
        for _ in range(repetitions):
            if target.defeated:
                break
            if not prechecked and not self._skill_hits(actor, target, spec):
                self._log(f"{self._label(target)}闪避了【{spec['name']}】。")
                continue
            if not prechecked and self._blocked_by_immunity(actor, target, spec):
                continue
            multiplier = 1.0
            level = actor.inner_level("蛮力")
            if level:
                multiplier *= 1 + INNER_VALUES["蛮力"][level]
            if actor.has_status("狂龙"):
                multiplier *= 3
            if actor.counters.get("wine_boost_active"):
                multiplier *= 2
            if "魔法" in spec["attributes"] and "魔法2" in self.character_data(actor)["traits"]:
                multiplier *= 2
            amount = int(round(base * multiplier))
            iron = target.inner_level("铁布衫")
            if iron:
                amount = int(round(amount * INNER_VALUES["铁布衫"][iron]))
            if "丝袜" in self.character_data(target)["traits"]:
                amount = min(amount, 30000)
            dealt_to_body = self._apply_basic_damage(actor, target, amount, spec["name"])
            total += dealt_to_body
            if dealt_to_body > 0 and actor.has_status("道威"):
                self._heal(actor, dealt_to_body, "道威")
            elastic = target.inner_level("弹性形变")
            if dealt_to_body > 0 and elastic and not actor.defeated:
                reflected = int(round(dealt_to_body * INNER_VALUES["弹性形变"][elastic]))
                self._apply_nonbasic_damage(target, actor, reflected, "弹性形变反弹")
        return total

    def _skill_hits(self, actor: Fighter, target: Fighter, spec: dict[str, Any]) -> bool:
        if "必中" in self.character_data(actor)["traits"]:
            return True
        hit = 0.25 if actor.has_status("虚空") else 1.0
        dodge = 0.0
        level = target.inner_level("虚空神术")
        if level:
            dodge += INNER_VALUES["虚空神术"][level]
        dodge += float(SCENES[target.scene].get("dodge", 0.0))
        dodge = min(1.0, dodge)
        return self.random.random() < max(0.0, hit - dodge)

    def _blocked_by_immunity(self, actor: Fighter, target: Fighter, spec: dict[str, Any]) -> bool:
        traits = self.character_data(target)["traits"]
        attrs = set(spec["attributes"])
        if target.has_status("无敌"):
            self._log(f"{self._label(target)}处于无敌，【{spec['name']}】无效。")
            return True
        if "免疫物理" in traits and "物理" in attrs:
            self._log(f"{self._label(target)}免疫物理技能。")
            return True
        if "免疫魔法" in traits and "魔法" in attrs:
            self._log(f"{self._label(target)}免疫魔法技能。")
            return True
        if "免疫火系" in traits and spec["name"] in {"火山爆发", "百步烈烧", "千步烈烧"}:
            self._log(f"{self._label(target)}免疫火系技能。")
            return True
        if "免疫冰系" in traits and spec["name"] in {"寒潮", "极光", "灵气寒霜指"}:
            self._log(f"{self._label(target)}免疫冰系技能。")
            return True
        return False

    def _apply_basic_damage(self, actor: Fighter, target: Fighter, amount: int, reason: str) -> int:
        if amount <= 0 or target.defeated:
            return 0
        if target.shield > 0:
            old = target.shield
            target.shield = max(0, target.shield - amount)
            self._log(f"{self._label(target)}的盾牌承受{min(old, amount)}伤害，剩余{target.shield}。")
            if target.shield == 0:
                self._remove_shield_effects(target)
            return 0
        old_hp = target.hp
        target.hp = max(0, target.hp - amount)
        actual = old_hp - target.hp
        self._log(f"{self._label(target)}受到{actual}伤害，体力{target.hp}/{target.max_hp}。")
        if actual > 0 and target.has_status("昏睡"):
            target.statuses.pop("昏睡", None)
            self._log(f"{self._label(target)}因受到基础伤害而苏醒。")
        self._check_death(target, actor.side, reason)
        return actual

    def _apply_nonbasic_damage(self, actor: Fighter | None, target: Fighter, amount: int, reason: str,
                               bypass_shield: bool = False) -> int:
        if amount <= 0 or target.defeated:
            return 0
        if target.has_status("无敌"):
            self._log(f"{self._label(target)}处于无敌，免疫{reason}。")
            return 0
        if target.shield > 0 and not bypass_shield:
            old = target.shield
            target.shield = max(0, target.shield - amount)
            self._log(f"{self._label(target)}的盾牌受到{min(old, amount)}点{reason}，剩余{target.shield}。")
            if target.shield == 0:
                self._remove_shield_effects(target)
            return min(old, amount)
        old = target.hp
        target.hp = max(0, target.hp - amount)
        actual = old - target.hp
        self._log(f"{self._label(target)}因{reason}损失{actual}体力，剩余{target.hp}。")
        self._check_death(target, actor.side if actor else None, reason)
        return actual

    def _apply_status(self, target: Fighter, name: str, turns: int, source: str | None,
                      force_body: bool = False, unremovable: bool = False) -> bool:
        if turns <= 0 or target.defeated:
            return False
        harmful = name not in SELF_BUFFS and name != "无敌"
        if harmful and target.has_status("无敌"):
            self._log(f"{self._label(target)}处于无敌，免疫{name}。")
            return False
        if harmful and "免疫不良" in self.character_data(target)["traits"]:
            self._log(f"{self._label(target)}自动过滤{name}。")
            return False
        if harmful and target.has_status("真空"):
            turns = floor(turns / 2)
            if turns <= 0:
                self._log(f"{self._label(target)}的真空屏障使{name}时长归零。")
                return False
        layer = "body"
        if harmful and target.shield > 0 and not force_body:
            if name in CONTROL_STATUSES:
                self._log(f"{self._label(target)}有盾牌，控制状态{name}无效。")
                return False
            if name in DAMAGE_STATUSES:
                layer = "shield"
        if name == "昏睡" and name in target.statuses:
            self._log(f"{self._label(target)}已经昏睡，新的昏睡不刷新。")
            return False
        existing = target.statuses.get(name)
        if existing and existing.turns >= turns:
            self._log(f"{self._label(target)}的{name}保持{existing.turns}回合。")
            return False
        target.statuses[name] = Status(name, turns, source, layer, unremovable, fresh=True)
        self._log(f"{self._label(target)}获得{name}（{turns}回合）。")
        if name in {"烧伤", "点燃"} and target.has_status("万能胶"):
            target.statuses.pop("万能胶", None)
            self._log(f"{self._label(target)}的万能胶被{name}消除。")
        return True

    def _add_parasite(self, target: Fighter, name: str, count: int, source: str) -> None:
        if count <= 0:
            return
        if target.has_status("无敌") or "免疫不良" in self.character_data(target)["traits"]:
            self._log(f"{self._label(target)}免疫{name}。")
            return
        layer = "shield" if target.shield > 0 else "body"
        current = target.parasites.get(name)
        if current and current.source == source and current.layer == layer:
            current.count += count
        else:
            target.parasites[name] = Parasite(name, count, source, 0, layer)
        self._log(f"{self._label(target)}被附加{count}条{name}。")

    # ---------- periodic effects ----------

    def _trigger_lucky(self, actor: Fighter) -> None:
        level = actor.inner_level("幸运")
        if level and self.random.random() < INNER_VALUES["幸运"][level]:
            removed = [name for name, status in actor.statuses.items() if name not in SELF_BUFFS and not status.unremovable]
            for name in removed:
                actor.statuses.pop(name, None)
            actor.parasites.clear()
            if removed:
                self._log(f"{self._label(actor)}发动幸运，解除不良状态和寄生虫。")

    def _trigger_periodic_inner(self, actor: Fighter, target: Fighter) -> None:
        turns = int(actor.counters.get("personal_turns", 1))
        level = actor.inner_level("轻于鸿毛")
        if level and turns % int(INNER_VALUES["轻于鸿毛"][level]) == 0:
            self._move_vertical(actor, 1)
        level = actor.inner_level("重于泰山")
        if level and turns % int(INNER_VALUES["重于泰山"][level]) == 0:
            self._move_vertical(actor, -1)
        level = actor.inner_level("昏沉大法")
        if level and turns % int(INNER_VALUES["昏沉大法"][level]) == 0:
            self._apply_status(actor, "昏睡", 1, actor.side, force_body=True)
            self._apply_status(target, "昏睡", 1, actor.side)
            self._log("昏沉大法令全场昏睡。")
        level = actor.inner_level("放射性")
        if level:
            self._add_radiation(target, int(INNER_VALUES["放射性"][level]), actor.side, "放射性")

    def _trigger_end_inner(self, actor: Fighter) -> None:
        level = actor.inner_level("生机勃勃")
        if level:
            self._heal(actor, int(actor.max_hp * INNER_VALUES["生机勃勃"][level]), "生机勃勃")

    def _resolve_damage_statuses(self, actor: Fighter) -> None:
        for name, status in list(actor.statuses.items()):
            if name == "烧伤":
                self._damage_status_layer(actor, status, int(actor.max_hp * 0.10), "烧伤")
            elif name == "点燃":
                base = actor.shield if status.layer == "shield" and actor.shield > 0 else actor.hp
                self._damage_status_layer(actor, status, int(base / 3), "点燃")
            elif name == "超燃":
                self._damage_status_layer(actor, status, int(actor.max_hp * 2 / 3), "超燃")

    def _damage_status_layer(self, actor: Fighter, status: Status, amount: int, reason: str) -> None:
        if status.layer == "shield" and actor.shield > 0:
            old = actor.shield
            actor.shield = max(0, actor.shield - amount)
            self._log(f"{self._label(actor)}的盾牌因{reason}损失{min(old, amount)}，剩余{actor.shield}。")
            if actor.shield == 0:
                self._remove_shield_effects(actor)
        else:
            self._apply_nonbasic_damage(None, actor, amount, reason, bypass_shield=True)

    def _resolve_parasites(self, actor: Fighter) -> None:
        for parasite in list(actor.parasites.values()):
            parasite.age += 1
            if parasite.name == "猪带绦虫":
                ratio = 0.10
                if self.fighters[parasite.source].name in {"生化大师", "猪带小天王"}:
                    ratio += 0.10 * max(0, parasite.age - 1)
                amount = int(actor.max_hp * ratio * parasite.count)
                if parasite.age % 5 == 0:
                    parasite.count *= 2
                    self._log(f"{self._label(actor)}的猪带绦虫繁殖为{parasite.count}条。")
            elif parasite.name == "蚂蟥":
                amount = int(actor.max_hp * 0.20 * parasite.count)
            elif parasite.name == "昏睡绦虫":
                amount = 0
                if parasite.age % 3 == 0:
                    self._apply_status(actor, "昏睡", 1, parasite.source)
            else:
                amount = 0
            if amount:
                source = self.fighters.get(parasite.source)
                dealt = self._apply_nonbasic_damage(source, actor, amount, parasite.name)
                # “吸取”按转移血量实现，但不允许普通寄生虫突破上限。
                if source and dealt:
                    self._heal(source, dealt, parasite.name)

    def _resolve_scene(self, actor: Fighter) -> None:
        scene = SCENES[actor.scene]
        if scene.get("heal"):
            self._heal(actor, int(actor.max_hp * scene["heal"]), actor.scene)
        if scene.get("hp_loss"):
            self._apply_nonbasic_damage(None, actor, int(actor.max_hp * scene["hp_loss"]), actor.scene, bypass_shield=True)
        if scene.get("vacuum"):
            if actor.resources["氧气"] > 0:
                actor.resources["氧气"] -= 1
                self._log(f"{self._label(actor)}消耗1氧气，剩余{actor.resources['氧气']}。")
            else:
                self._apply_nonbasic_damage(None, actor, int(actor.max_hp * 0.10), "缺氧", bypass_shield=True)
        if scene.get("random_radiation"):
            radiation = self.random.choice((1, 2, 5))
            self._add_radiation(actor, radiation, None, "宇宙边缘射线")
        if actor.scene_height < self.water_level and "免疫水压" not in self.character_data(actor)["traits"]:
            layers = self.water_level - actor.scene_height
            self._apply_nonbasic_damage(None, actor, int(actor.max_hp * 0.10 * layers), "水压", bypass_shield=True)
            actor.counters["underwater_turns"] = int(actor.counters.get("underwater_turns", 0)) + 1
            if actor.counters["underwater_turns"] % 3 == 0:
                self._move_vertical(actor, 1)
        else:
            actor.counters["underwater_turns"] = 0

    def _process_delayed_effects(self, actor: Fighter) -> None:
        effects = actor.counters.get("delayed_effects", [])
        remaining = []
        for item in effects:
            item["remaining"] -= 1
            if item["remaining"] <= 0:
                self._apply_status(actor, item["status"], item["turns"], item.get("source"))
            else:
                remaining.append(item)
        actor.counters["delayed_effects"] = remaining

    def _decrement_statuses(self, actor: Fighter) -> None:
        for name, status in list(actor.statuses.items()):
            if name == "无敌" and actor.counters.get("wine_invincible_until_next_turn"):
                continue
            if status.fresh:
                status.fresh = False
                continue
            status.turns -= 1
            if status.turns <= 0:
                actor.statuses.pop(name, None)
                self._log(f"{self._label(actor)}的{name}结束。")

    # ---------- death / life / movement ----------

    def _check_death(self, fighter: Fighter, source: str | None, reason: str) -> None:
        if fighter.defeated or fighter.hp > 0:
            return
        level = fighter.inner_level("大难不死")
        if level:
            probability = INNER_VALUES["大难不死"][level]
            if self.random.random() < probability:
                fighter.hp = max(1, int(fighter.max_hp * probability))
                self._log(f"{self._label(fighter)}发动大难不死，恢复至{fighter.hp}体力。")
                return
        self._kill_current_life(fighter, source, all_lives=False, reason=reason)

    def _kill_current_life(self, fighter: Fighter, source: str | None, all_lives: bool, reason: str) -> None:
        if fighter.defeated:
            return
        if all_lives:
            fighter.lives_remaining = 0
        else:
            fighter.lives_remaining -= 1
        if fighter.lives_remaining <= 0:
            fighter.hp = 0
            fighter.defeated = True
            self._log(f"{self._label(fighter)}因{reason}失去全部生命。")
            return
        self._log(f"{self._label(fighter)}因{reason}失去一条命，剩余{fighter.lives_remaining}条。")
        self._reset_life(fighter)

    def _reset_life(self, fighter: Fighter) -> None:
        fighter.hp = fighter.max_hp
        fighter.shield = fighter.max_shield
        fighter.scene = "地面"
        fighter.statuses.clear()
        fighter.parasites.clear()
        fighter.resources = {"氧气": 10, "星体能量": 0, "超新星": 0, "万灵丹": 0, "海洋之心": 0, "酒": 0, "万能胶": 0}
        fighter.radiation = 0
        fighter.counters.clear()
        fighter.inner = dict(fighter.initial_inner)
        if fighter.name == "武圣" and fighter.lives_remaining < fighter.lives_total:
            fighter.inner.update({"幸运": 3, "大难不死": 2})
        self._log(f"{self._label(fighter)}进入下一条命，体力、盾牌、状态、内功、场景、辐射和物品已重置。")

    def _add_radiation(self, target: Fighter, amount: int, source: str | None, reason: str) -> None:
        if "免疫辐射" in self.character_data(target)["traits"]:
            self._log(f"{self._label(target)}免疫{reason}。")
            return
        target.radiation += int(amount)
        self._log(f"{self._label(target)}受到{amount}点辐射，累计{target.radiation}/15。")
        if target.radiation >= 15:
            self._kill_current_life(target, source, all_lives=True, reason="辐射达到15点")

    def _move_vertical(self, fighter: Fighter, steps: int) -> None:
        if fighter.has_status("万能胶"):
            self._log(f"{self._label(fighter)}受万能胶影响，场景不能移动。")
            return
        current_height = fighter.scene_height
        heights = [SCENES[name]["height"] for name in VERTICAL_SCENES]
        index = min(range(len(heights)), key=lambda i: abs(heights[i] - current_height))
        new_index = max(0, min(len(VERTICAL_SCENES) - 1, index + steps))
        self._set_scene(fighter, VERTICAL_SCENES[new_index])

    def _set_scene(self, fighter: Fighter, scene: str) -> None:
        if scene not in SCENES:
            raise RuleError(f"未知场景：{scene}")
        if fighter.has_status("万能胶") and fighter.name != "牛顿":
            self._log(f"{self._label(fighter)}受万能胶影响，场景不能移动。")
            return
        fighter.scene = scene
        self._log(f"{self._label(fighter)}移动到{scene}（高度{fighter.scene_height}）。")

    # ---------- utilities ----------

    @staticmethod
    def _skip_spec() -> dict[str, Any]:
        return {
            "id": "skip", "name": "跳过行动", "attributes": (), "damage": 0,
            "statuses": (), "defense": None, "distance": 0, "target": "self",
            "effect": "skip", "description": "因状态跳过行动。", "character": None,
            "action_kind": "skip",
        }

    def _initiative(self, fighter: Fighter, spec: dict[str, Any]) -> int:
        if spec["id"] == "t7":
            return 10
        value = 3 if "神技" in spec["attributes"] else 0
        level = fighter.inner_level("凌波微步")
        if level:
            value += int(INNER_VALUES["凌波微步"][level])
        return value

    @staticmethod
    def _is_now_sealed(actor: Fighter, spec: dict[str, Any]) -> bool:
        return any(SEAL_BY_ATTRIBUTE.get(attribute) and actor.has_status(SEAL_BY_ATTRIBUTE[attribute])
                   for attribute in spec["attributes"])

    def _special_effect_text(self, actor: Fighter, spec: dict[str, Any]) -> str:
        notes: list[str] = []
        overridden = self._character_damage_override(actor, spec)
        if overridden != int(spec["damage"]):
            notes.append(f"{actor.name}使用时基础伤害改为{overridden:,}")
        traits = self.character_data(actor)["traits"]
        if "必中" in traits and spec["target"] == "enemy":
            notes.append("角色特效：必中")
        if "特效时长2" in traits and spec["statuses"]:
            notes.append("角色特效：状态时长×2")
        if "魔法2" in traits and "魔法" in spec["attributes"]:
            notes.append("角色特效：魔法伤害和状态时长×2")
        if actor.name == "生化大师" and spec["id"] == "28":
            notes.append("角色覆盖：50%概率秒杀")
        if actor.name == "生化大师" and spec["id"] == "29":
            notes.append("角色覆盖：立即昏睡5回合，不延迟")
        if actor.name == "肥饕餮" and spec["id"] == "19":
            notes.append("角色覆盖：吸取体力上限100%")
        repetitions = self._effect_repetitions(actor)
        if repetitions > 1 and spec["action_kind"] != "defense":
            notes.append(f"本回合幻影触发：效果×{repetitions}（状态时长不叠加）")
        return "；".join(notes)

    def _effect_repetitions(self, actor: Fighter) -> int:
        level = actor.inner_level("幻影")
        if not level:
            return 1
        x = int(INNER_VALUES["幻影"][level])
        interval = 5 - x
        return x if int(actor.counters.get("personal_turns", 1)) % interval == 0 else 1

    def _duration(self, actor: Fighter, spec: dict[str, Any], turns: int) -> int:
        multiplier = 1
        traits = self.character_data(actor)["traits"]
        if "特效时长2" in traits:
            multiplier *= 2
        if "魔法" in spec["attributes"] and "魔法2" in traits:
            multiplier *= 2
        if actor.counters.get("wine_boost_active"):
            multiplier *= 2
        return int(turns * multiplier)

    def _collect(self, actor: Fighter, resource: str, repetitions: int, scene_multiplier: int | None = None) -> None:
        if scene_multiplier is None:
            scene_multiplier = int(SCENES[actor.scene].get("collect_multiplier", 1))
        character_multiplier = 5 if "收集5" in self.character_data(actor)["traits"] else 1
        quantity = int(repetitions * scene_multiplier * character_multiplier)
        actor.resources[resource] += quantity
        self._log(f"{self._label(actor)}收集{quantity}个{resource}，现有{actor.resources[resource]}。")

    def _heal(self, fighter: Fighter, amount: int, reason: str) -> int:
        if amount <= 0 or fighter.defeated:
            return 0
        old = fighter.hp
        fighter.hp = min(fighter.max_hp, fighter.hp + amount)
        actual = fighter.hp - old
        if actual:
            self._log(f"{self._label(fighter)}因{reason}恢复{actual}体力。")
        return actual

    def _cleanse(self, fighter: Fighter, include_radiation: bool = False) -> None:
        for name, status in list(fighter.statuses.items()):
            if name in SELF_BUFFS or name == "无敌" or status.unremovable:
                continue
            fighter.statuses.pop(name, None)
        fighter.parasites.clear()
        if include_radiation:
            fighter.radiation = 0

    def _remove_shield_effects(self, fighter: Fighter) -> None:
        for name, status in list(fighter.statuses.items()):
            if status.layer == "shield":
                fighter.statuses.pop(name, None)
        for name, parasite in list(fighter.parasites.items()):
            if parasite.layer == "shield":
                fighter.parasites.pop(name, None)
        self._log(f"{self._label(fighter)}的盾牌破碎，盾牌上的效果消失。")

    def _upgrade_all_inner(self, fighter: Fighter) -> None:
        for name in ALL_INNER_NAMES:
            fighter.inner[name] = min(3, int(fighter.inner.get(name, 0)) + 1)
        self._log(f"{self._label(fighter)}的全部内功升一级。")

    def _after_special(self, actor: Fighter, spec: dict[str, Any]) -> None:
        if "特技" in spec["attributes"]:
            self._apply_status(actor, "封喉", 3, actor.side, force_body=True)

    def _check_battle_end(self) -> None:
        defeated = [side for side, fighter in self.fighters.items() if fighter.defeated]
        if not defeated:
            return
        self.done = True
        alive = [side for side in ("A", "B") if side not in defeated]
        self.winner = alive[0] if len(alive) == 1 else None
        if self.winner:
            self._log(f"对战结束，{self.winner}获胜。")
        else:
            self._log("对战结束，双方同时失去全部生命。")

    @staticmethod
    def other_side(side: str) -> str:
        return "B" if side == "A" else "A"

    @staticmethod
    def _label(fighter: Fighter) -> str:
        return f"{fighter.side}的{fighter.name}"

    def _log(self, message: str) -> None:
        self.log.append(message)
