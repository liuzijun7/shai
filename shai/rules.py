"""底层规则：伤害、状态、寄生虫、场景、死亡。

这些规则从刘同学的 ``engine.py`` 逐条搬过来。改动的地方：
- 所有概率都走 ``self._chance``，由它决定是贼还是掷随机数；
- 每个变化都额外发一条结构化事件，供网页播放动画；
- 回合结束时先算回血，最后算扣血和虫子（雨晨的回答，也是本子基本规则第 ⑧ 条）；
- 水压按本子基本规则第 ⑪ 条：地幔及以下没有水压；洪水后地面算在水下（雨晨的回答）。
"""

from __future__ import annotations

from math import floor
from typing import Any

from .data import (
    ALL_INNER_NAMES, CHARACTERS, CONTROL_STATUSES, DAMAGE_STATUSES, FIRE_SKILL_NAMES, ICE_SKILL_NAMES,
    INNER_VALUES, LEARN_MULTIPLIER,
    LEARN_THRESHOLDS, MAX_INNER_LEVEL, MAX_LEARNED_INNER, SCENES, SELF_BUFFS, SURE_HIT_IDS, VERTICAL_SCENES,
    accelerator_level,
)
from .model import Fighter, Parasite, RuleError, Status


class Rules:
    # 由 Battle 提供：self.rng、self.water_level、self._chance、self._log、self._emit、
    # self.fighter(side)、self.other(side)

    # ---------- 小工具 ----------

    @staticmethod
    def char(fighter: Fighter) -> dict[str, Any]:
        return CHARACTERS[fighter.character_id]

    @staticmethod
    def label(fighter: Fighter) -> str:
        return f"{fighter.side}的{fighter.name}"

    @staticmethod
    def vitals(fighter: Fighter) -> dict[str, Any]:
        return {
            "hp": fighter.hp, "max_hp": fighter.max_hp, "shield": fighter.shield,
            "max_shield": fighter.max_shield, "lives": fighter.lives_remaining,
            "lives_total": fighter.lives_total,
        }

    def traits(self, fighter: Fighter) -> set[str]:
        return self.char(fighter)["traits"]

    # ---------- 命中和免疫 ----------

    def skill_hits(self, actor: Fighter, target: Fighter, spec: dict[str, Any]) -> bool:
        """这一招打不打得中。没打中的话在这里把原因写进战报。神技必中（雨晨）。"""
        if "必中" in self.traits(actor) or spec["id"] in SURE_HIT_IDS or "神技" in spec["attributes"]:
            return True
        name, a, t = spec["name"], self.label(actor), self.label(target)
        why = None
        if actor.has_status("虚空") and not self._chance(
                0.25, actor.side, f"{a}身上有“虚空”（命中只剩四分之一），【{name}】打不打得中",
                yes="这一招打中", no="这一招打空"):
            why = f"{a}身上有“虚空”，【{name}】打空了。"
        if why is None:
            level = target.inner_level("虚空神术")
            if level and self._chance(INNER_VALUES["虚空神术"][level], target.side,
                                      f"{t}用虚空神术躲【{name}】", yes="躲开这一招", no="没躲开"):
                why = f"{t}用虚空神术躲开了【{name}】。"
        if why is None:
            dodge = float(SCENES[target.scene].get("dodge", 0.0))
            if dodge and self._chance(dodge, target.side, f"{t}在{target.scene}里躲【{name}】",
                                      yes="躲开这一招", no="没躲开"):
                why = f"{t}在{target.scene}里躲开了【{name}】。"
        if why is None:
            return True
        self._emit("miss", side=target.side, skill=name)
        self._log(why)
        return False

    def immunity_reason(self, target: Fighter, spec: dict[str, Any]) -> str | None:
        """这个招对这个人物无效的原因；有效就返回 None。"""
        traits, attrs = self.traits(target), set(spec["attributes"])
        if target.has_status("无敌"):
            return "处于无敌"
        if "免疫物理" in traits and "物理" in attrs:
            return "免疫物理的招"
        if "免疫魔法" in traits and "魔法" in attrs:
            return "免疫魔法的招"
        if "免疫火系" in traits and spec["name"] in FIRE_SKILL_NAMES:
            return "免疫火系的招"
        if "免疫冰系" in traits and spec["name"] in ICE_SKILL_NAMES:
            return "免疫冰系的招"
        return None

    def only_filtered_statuses(self, actor: Fighter, target: Fighter, spec: dict[str, Any]) -> bool:
        """这个招没有伤害、没有别的效果，只会给对手加不良状态，而对手免疫不良特效：整个招对他没用。"""
        harmful = [name for name, _ in spec["statuses"] if name not in SELF_BUFFS]
        plain = spec["effect"] is None and self.character_damage(actor, spec) <= 0
        if not (plain and harmful and len(harmful) == len(spec["statuses"]) and "免疫不良" in self.traits(target)):
            return False
        self._emit("immune", side=target.side, skill=spec["name"])
        self._log(f"{self.label(target)}免疫不良特效，【{spec['name']}】对他没有用。")
        return True

    def blocked_by_immunity(self, actor: Fighter, target: Fighter, spec: dict[str, Any]) -> bool:
        why = self.immunity_reason(target, spec)
        if why is None:
            return False
        self._emit("immune", side=target.side, skill=spec["name"])
        self._log(f"{self.label(target)}{why}，【{spec['name']}】无效。")
        return True

    # ---------- 伤害 ----------

    def character_damage(self, actor: Fighter, spec: dict[str, Any]) -> int:
        name = spec["name"]
        if spec["effect"] == "accelerator":
            level = accelerator_level(int(actor.devices.get("粒子加速器", 0)))
            return int(level["damage"]) if level else 0
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

    def deal_skill_damage(self, actor: Fighter, target: Fighter, spec: dict[str, Any], base: int,
                          repetitions: int, prechecked: bool = False) -> int:
        if base <= 0:
            return 0
        total = 0
        series = self.series_start(target)
        for done in range(repetitions):
            if self.series_over(target, series):
                if repetitions - done > 0 and not target.defeated:
                    self._log(f"【{spec['name']}】剩下的{repetitions - done}下落空：一个招只能打掉一个盾牌或一条命。")
                break
            if not prechecked and self.blocked_by_immunity(actor, target, spec):
                continue
            if not prechecked and not self.skill_hits(actor, target, spec):
                continue
            multiplier = 1.0
            level = actor.inner_level("蛮力")
            if level:
                multiplier *= 1 + INNER_VALUES["蛮力"][level]
            if actor.has_status("狂龙"):
                multiplier *= 3
            if actor.counters.get("wine_boost_active"):
                multiplier *= 2
            if "魔法" in spec["attributes"] and "魔法2" in self.traits(actor):
                multiplier *= 2
            crit = actor.inner_level("暴击")
            if crit and self._chance(INNER_VALUES["暴击"][crit], actor.side, f"{self.label(actor)}的【{spec['name']}】出不出暴击",
                                     yes="这一下伤害翻倍", no="没有暴击"):
                multiplier *= 2
                self._emit("crit", side=actor.side)
                self._log(f"{self.label(actor)}打出暴击，伤害翻倍。")
            amount = int(round(base * multiplier))
            iron = target.inner_level("铁布衫")
            if iron:
                amount = int(round(amount * INNER_VALUES["铁布衫"][iron]))
            if "丝袜" in self.traits(target):
                amount = min(amount, 30000)
            dealt = self.apply_basic_damage(actor, target, amount, spec["name"])
            total += dealt
            if dealt > 0 and actor.has_status("道威"):
                self.heal(actor, dealt, "道威")
            elastic = target.inner_level("弹性形变")
            if dealt > 0 and elastic and not actor.defeated:
                self.apply_nonbasic_damage(target, actor, int(round(dealt * INNER_VALUES["弹性形变"][elastic])), "弹性形变反弹")
        return total

    @staticmethod
    def series_start(target: Fighter) -> tuple[int, bool]:
        """一个招开始打之前记下：对手还有几条命、有没有盾牌。"""
        return target.lives_remaining, target.shield > 0

    @staticmethod
    def series_over(target: Fighter, start: tuple[int, bool]) -> bool:
        """一个招只能打一样东西（雨晨）：打的是盾牌，盾牌碎了就停；打的是体力，这条命没了就停。"""
        lives, shielded = start
        return target.defeated or target.lives_remaining < lives or (shielded and target.shield <= 0)

    def apply_basic_damage(self, actor: Fighter, target: Fighter, amount: int, reason: str) -> int:
        """基础伤害：有盾牌先打盾牌，盾牌不溢出。返回打到体力上的数值。"""
        if amount <= 0 or target.defeated:
            return 0
        if target.shield > 0:
            old = target.shield
            target.shield = max(0, target.shield - amount)
            self._emit("damage", side=target.side, amount=min(old, amount), layer="shield", reason=reason, **self.vitals(target))
            self._log(f"{self.label(target)}的盾牌承受{min(old, amount)}伤害，剩余{target.shield}。")
            if target.shield == 0:
                self.remove_shield_effects(target)
            return 0
        old_hp = target.hp
        target.hp = max(0, target.hp - amount)
        actual = old_hp - target.hp
        self._emit("damage", side=target.side, amount=actual, layer="hp", reason=reason, **self.vitals(target))
        self._log(f"{self.label(target)}受到{actual}伤害，体力{target.hp}。")
        if actual > 0 and target.has_status("昏睡"):
            target.statuses.pop("昏睡", None)
            self._emit("status_end", side=target.side, name="昏睡")
            self._log(f"{self.label(target)}因受到基础伤害而苏醒。")
        self.check_death(target, actor.side, reason)
        return actual

    def apply_nonbasic_damage(self, actor: Fighter | None, target: Fighter, amount: int, reason: str,
                              bypass_shield: bool = False) -> int:
        if amount <= 0 or target.defeated:
            return 0
        if target.has_status("无敌"):
            self._log(f"{self.label(target)}处于无敌，免疫{reason}。")
            return 0
        if target.shield > 0 and not bypass_shield:
            old = target.shield
            target.shield = max(0, target.shield - amount)
            self._emit("damage", side=target.side, amount=min(old, amount), layer="shield", reason=reason, **self.vitals(target))
            self._log(f"{self.label(target)}的盾牌受到{min(old, amount)}点{reason}，剩余{target.shield}。")
            if target.shield == 0:
                self.remove_shield_effects(target)
            return min(old, amount)
        old = target.hp
        target.hp = max(0, target.hp - amount)
        actual = old - target.hp
        self._emit("damage", side=target.side, amount=actual, layer="hp", reason=reason, **self.vitals(target))
        self._log(f"{self.label(target)}因{reason}损失{actual}体力，剩余{target.hp}。")
        self.check_death(target, actor.side if actor else None, reason)
        return actual

    def heal(self, fighter: Fighter, amount: int, reason: str, over_cap: bool = False) -> int:
        if amount <= 0 or fighter.defeated:
            return 0
        old = fighter.hp
        capped = not (over_cap or "体力无上限" in self.traits(fighter))
        fighter.hp = min(int(fighter.max_hp), fighter.hp + amount) if capped else fighter.hp + amount
        actual = fighter.hp - old
        if actual:
            self._emit("heal", side=fighter.side, amount=actual, reason=reason, **self.vitals(fighter))
            self._log(f"{self.label(fighter)}因{reason}恢复{actual}体力。")
        return actual

    # ---------- 状态和寄生虫 ----------

    def apply_status(self, target: Fighter, name: str, turns: int, source: str | None,
                     force_body: bool = False, unremovable: bool = False, forced: bool = False) -> bool:
        """加状态。``forced`` 为真时无视无敌、免疫和真空屏障（例如臭伽马的强制昏睡）。"""
        if turns <= 0 or target.defeated:
            return False
        harmful = name not in SELF_BUFFS and name != "无敌"
        if harmful and not forced:
            if target.has_status("无敌"):
                self._not_applied(target, name, "处于无敌")
                return False
            if "免疫不良" in self.traits(target):
                self._not_applied(target, name, "免疫不良特效")
                return False
            if target.has_status("真空"):
                turns = floor(turns / 2)
                if turns <= 0:
                    self._log(f"{self.label(target)}的真空屏障使{name}时长归零。")
                    return False
        layer = "body"
        if harmful and target.shield > 0 and not force_body and not forced:
            if name in CONTROL_STATUSES:
                self._log(f"{self.label(target)}有盾牌，控制状态{name}无效。")
                return False
            if name in DAMAGE_STATUSES:
                layer = "shield"
        if name == "昏睡" and name in target.statuses:
            self._log(f"{self.label(target)}已经昏睡，新的昏睡不刷新。")
            return False
        existing = target.statuses.get(name)
        if existing and existing.turns >= turns:
            self._log(f"{self.label(target)}的{name}保持{existing.turns}回合。")
            return False
        target.statuses[name] = Status(name, turns, source, layer, unremovable or forced, fresh=True)
        self._emit("status", side=target.side, name=name, turns=turns, good=not harmful)
        self._log(f"{self.label(target)}获得{name}（{turns}回合）。")
        if name in {"烧伤", "点燃"} and target.has_status("万能胶"):
            target.statuses.pop("万能胶", None)
            self._log(f"{self.label(target)}的万能胶被{name}消除。")
        return True

    def _not_applied(self, target: Fighter, name: str, why: str) -> None:
        """一个状态没加上。一个招带好几个状态时先攒着，最后合成一行写进战报。"""
        batch = getattr(self, "_status_batch", None)
        if batch is not None:
            batch.append((target.side, self.label(target), why, name))
        else:
            self._log(f"{self.label(target)}{why}，{name}没有加上。")

    def begin_status_batch(self) -> None:
        self._status_batch = []

    def end_status_batch(self) -> None:
        batch, self._status_batch = getattr(self, "_status_batch", None) or [], None
        groups: dict[tuple[str, str, str], list[str]] = {}
        for side, label, why, name in batch:
            groups.setdefault((side, label, why), []).append(name)
        for (_, label, why), names in groups.items():
            self._log(f"{label}{why}，{'、'.join(names)}没有加上。")

    def add_parasite(self, target: Fighter, name: str, count: int, source: str) -> None:
        if count <= 0:
            return
        if target.has_status("无敌") or "免疫不良" in self.traits(target):
            self._log(f"{self.label(target)}免疫{name}。")
            return
        layer = "shield" if target.shield > 0 else "body"
        current = target.parasites.get(name)
        if current and current.source == source and current.layer == layer:
            current.count += count
        else:
            target.parasites[name] = Parasite(name, count, source, 0, layer)
        self._emit("parasite", side=target.side, name=name, count=count)
        self._log(f"{self.label(target)}被附加{count}条{name}。")

    def cleanse(self, fighter: Fighter, include_radiation: bool = False) -> None:
        for name, status in list(fighter.statuses.items()):
            if name in SELF_BUFFS or name == "无敌" or status.unremovable:
                continue
            fighter.statuses.pop(name, None)
        fighter.parasites.clear()
        if include_radiation:
            fighter.radiation = 0

    def remove_shield_effects(self, fighter: Fighter) -> None:
        for name, status in list(fighter.statuses.items()):
            if status.layer == "shield":
                fighter.statuses.pop(name, None)
        for name, parasite in list(fighter.parasites.items()):
            if parasite.layer == "shield":
                fighter.parasites.pop(name, None)
        self._log(f"{self.label(fighter)}的盾牌破碎，盾牌上的效果消失。")

    def duration(self, actor: Fighter, spec: dict[str, Any], turns: int) -> int:
        multiplier, traits = 1, self.traits(actor)
        if "特效时长2" in traits:
            multiplier *= 2
        if "魔法" in spec["attributes"] and "魔法2" in traits:
            multiplier *= 2
        if actor.counters.get("wine_boost_active"):
            multiplier *= 2
        return int(turns * multiplier)

    def effect_repetitions(self, actor: Fighter) -> int:
        """幻影：每隔几个回合，这回合的招效果重复几次。"""
        level = actor.inner_level("幻影")
        if not level:
            return 1
        x = int(INNER_VALUES["幻影"][level])
        interval = max(1, 5 - x)
        return x if int(actor.counters.get("personal_turns", 1)) % interval == 0 else 1

    def upgrade_all_inner(self, fighter: Fighter) -> None:
        for name in ALL_INNER_NAMES:
            fighter.inner[name] = min(MAX_INNER_LEVEL, int(fighter.inner.get(name, 0)) + 1)
        self._log(f"{self.label(fighter)}的全部内功升一级。")

    def collect(self, actor: Fighter, resource: str, repetitions: int, scene_multiplier: int | None = None) -> None:
        if scene_multiplier is None:
            scene_multiplier = int(SCENES[actor.scene].get("collect_multiplier", 1))
        character_multiplier = 5 if "收集5" in self.traits(actor) else 1
        quantity = int(repetitions * scene_multiplier * character_multiplier)
        actor.resources[resource] += quantity
        self._emit("collect", side=actor.side, resource=resource, quantity=quantity, total=actor.resources[resource])
        self._log(f"{self.label(actor)}收集{quantity}个{resource}，现有{actor.resources[resource]}。")

    def after_special(self, actor: Fighter, spec: dict[str, Any]) -> None:
        """特技用完，自己被封喉 3 回合。"""
        if "特技" in spec["attributes"]:
            self.apply_status(actor, "封喉", 3, actor.side, force_body=True)

    # ---------- 辐射、场景移动 ----------

    def add_radiation(self, target: Fighter, amount: int, source: str | None, reason: str) -> None:
        if "免疫辐射" in self.traits(target):
            self._log(f"{self.label(target)}免疫{reason}。")
            return
        target.radiation += int(amount)
        self._emit("radiation", side=target.side, amount=int(amount), total=target.radiation, reason=reason)
        self._log(f"{self.label(target)}受到{amount}点辐射，累计{target.radiation}/15。")
        if target.radiation >= 15:
            self.kill_current_life(target, source, all_lives=True, reason="辐射达到15点")

    def move_vertical(self, fighter: Fighter, steps: int, why: str = "") -> None:
        if fighter.has_status("万能胶"):
            self._log(f"{self.label(fighter)}受万能胶影响，场景不能移动。")
            return
        heights = [SCENES[name]["height"] for name in VERTICAL_SCENES]
        index = min(range(len(heights)), key=lambda i: abs(heights[i] - fighter.scene_height))
        self.set_scene(fighter, VERTICAL_SCENES[max(0, min(len(VERTICAL_SCENES) - 1, index + steps))], why)

    def set_scene(self, fighter: Fighter, scene: str, why: str = "") -> None:
        if scene not in SCENES:
            raise RuleError(f"未知场景：{scene}")
        if fighter.has_status("万能胶") and fighter.name != "牛顿":
            self._log(f"{self.label(fighter)}受万能胶影响，场景不能移动。")
            return
        if fighter.scene == scene:
            return
        fighter.scene = scene
        self._emit("scene", side=fighter.side, scene=scene, height=fighter.scene_height)
        self._log(f"{self.label(fighter)}{why + '，' if why else ''}移动到{scene}（高度{fighter.scene_height}）。")

    # ---------- 回合开始 ----------

    def start_of_turn(self, actor: Fighter, target: Fighter | None) -> bool:
        """处理一个人物的回合开始。返回 True 表示他这回合不能出招。"""
        actor.counters["personal_turns"] = int(actor.counters.get("personal_turns", 0)) + 1
        actor.counters["field_turns"] = int(actor.counters.get("field_turns", 0)) + 1    # 这次上场以后的第几回合
        if actor.counters.pop("wine_invincible_until_next_turn", False):
            actor.statuses.pop("无敌", None)
            actor.counters["wine_boost_active"] = True
        else:
            actor.counters["wine_boost_active"] = False

        remaining = []
        for item in actor.counters.get("delayed_effects", []):
            item["remaining"] -= 1
            if item["remaining"] <= 0:
                self.apply_status(actor, item["status"], item["turns"], item.get("source"))
            else:
                remaining.append(item)
        actor.counters["delayed_effects"] = remaining

        level = actor.inner_level("幸运")
        bad = [n for n, s in actor.statuses.items() if n not in SELF_BUFFS and n != "无敌" and not s.unremovable]
        if level and (bad or actor.parasites) and self._chance(
                INNER_VALUES["幸运"][level], actor.side, f"{self.label(actor)}的幸运发不发动",
                yes="解除身上的不良状态和虫子", no="没有解除"):
            for name in bad:
                actor.statuses.pop(name, None)
                self._emit("status_end", side=actor.side, name=name)
            actor.parasites.clear()
            self._log(f"{self.label(actor)}发动幸运，解除不良状态和寄生虫。")

        turns = int(actor.counters["personal_turns"])
        level = actor.inner_level("轻于鸿毛")
        if level and turns % int(INNER_VALUES["轻于鸿毛"][level]) == 0:
            self.move_vertical(actor, 1, f"有内功轻于鸿毛{level}级，自己往上飘一层")
        level = actor.inner_level("重于泰山")
        if level and turns % int(INNER_VALUES["重于泰山"][level]) == 0:
            self.move_vertical(actor, -1, f"有内功重于泰山{level}级，自己往下沉一层")
        level = actor.inner_level("昏沉大法")
        if level and turns % int(INNER_VALUES["昏沉大法"][level]) == 0:
            self.apply_status(actor, "昏睡", 1, actor.side, force_body=True)
            if target is not None:
                self.apply_status(target, "昏睡", 1, actor.side)
            self._log("昏沉大法令全场昏睡。")
        level = actor.inner_level("放射性")
        if level and target is not None:
            self.add_radiation(target, int(INNER_VALUES["放射性"][level]), actor.side, "放射性")

        if actor.scene == "南极" and turns % 3 == 0:
            self.apply_status(actor, "昏睡", 1, None, force_body=True)
            self._log(f"{self.label(actor)}受到南极寒冷影响，本回合昏睡。")
        for why in ("昏睡", "封印"):
            if actor.has_status(why):
                self._emit("skip", side=actor.side, why=why)
                self._log(f"{self.label(actor)}处于{why}，跳过行动。")
                return True
        return False

    # ---------- 回合结束 ----------

    def end_of_turn(self, actor: Fighter) -> None:
        """先算回血，最后算扣血和虫子。"""
        if actor.defeated:
            return
        scene = SCENES[actor.scene]
        if scene.get("heal"):
            self.heal(actor, int(actor.max_hp * scene["heal"]), actor.scene)
        level = actor.inner_level("生机勃勃")
        if level:
            self.heal(actor, int(actor.max_hp * INNER_VALUES["生机勃勃"][level]), "生机勃勃")

        for name, status in list(actor.statuses.items()):
            if name == "烧伤":
                self._burn(actor, status, int(actor.max_hp * 0.10), "烧伤")
            elif name == "点燃":
                base = actor.shield if status.layer == "shield" and actor.shield > 0 else actor.hp
                self._burn(actor, status, int(base / 3), "点燃")
            elif name == "超燃":
                self._burn(actor, status, int(actor.max_hp * 2 / 3), "超燃")
        self._parasites(actor)

        if scene.get("hp_loss"):
            self.apply_nonbasic_damage(None, actor, int(actor.max_hp * scene["hp_loss"]), actor.scene, bypass_shield=True)
        if scene.get("vacuum"):
            if actor.resources["氧气"] > 0:
                actor.resources["氧气"] -= 1
                self._log(f"{self.label(actor)}消耗1氧气，剩余{actor.resources['氧气']}。")
            else:
                self.apply_nonbasic_damage(None, actor, int(actor.max_hp * 0.10), "缺氧", bypass_shield=True)
        if scene.get("random_radiation"):
            self.add_radiation(actor, self.rng.choice((1, 2, 5)), None, "宇宙边缘射线")
        self._water(actor)

        if "真身" in self.traits(actor) and 0 < actor.hp < 20000:
            actor.hp = int(actor.max_hp)
            self._emit("heal", side=actor.side, amount=0, reason="真身回满", **self.vitals(actor))
            self._log(f"{self.label(actor)}体力低于2万，自动回满。")

        for name, status in list(actor.statuses.items()):
            if name == "无敌" and actor.counters.get("wine_invincible_until_next_turn"):
                continue
            if status.fresh:
                status.fresh = False
                continue
            status.turns -= 1
            if status.turns <= 0:
                actor.statuses.pop(name, None)
                self._emit("status_end", side=actor.side, name=name)
                self._log(f"{self.label(actor)}的{name}结束。")
        actor.counters["wine_boost_active"] = False
        self.check_death(actor, None, "回合结束结算")

    def _burn(self, actor: Fighter, status: Status, amount: int, reason: str) -> None:
        if status.layer == "shield" and actor.shield > 0:
            old = actor.shield
            actor.shield = max(0, actor.shield - amount)
            self._emit("damage", side=actor.side, amount=min(old, amount), layer="shield", reason=reason, **self.vitals(actor))
            self._log(f"{self.label(actor)}的盾牌因{reason}损失{min(old, amount)}，剩余{actor.shield}。")
            if actor.shield == 0:
                self.remove_shield_effects(actor)
        else:
            self.apply_nonbasic_damage(None, actor, amount, reason, bypass_shield=True)

    def _parasites(self, actor: Fighter) -> None:
        for parasite in list(actor.parasites.values()):
            parasite.age += 1
            amount = 0
            source = self.fighter(parasite.source)
            if parasite.name == "猪带绦虫":
                ratio = 0.10
                if source is not None and source.name in {"生化大师", "猪带小天王"}:
                    ratio += 0.10 * max(0, parasite.age - 1)
                amount = int(actor.max_hp * ratio * parasite.count)
                if parasite.age % 5 == 0:
                    parasite.count *= 2
                    self._log(f"{self.label(actor)}的猪带绦虫繁殖为{parasite.count}条。")
            elif parasite.name == "蚂蟥":
                amount = int(actor.max_hp * 0.20 * parasite.count)
            elif parasite.name == "昏睡绦虫" and parasite.age % 3 == 0:
                self.apply_status(actor, "昏睡", 1, parasite.source)
            if amount:
                dealt = self.apply_nonbasic_damage(source, actor, amount, parasite.name)
                if source is not None and dealt and not source.defeated:
                    self.heal(source, dealt, parasite.name)

    def _water(self, actor: Fighter) -> None:
        """水压：在水面下第 n 层每回合扣 10n%。地幔及以下没有水压。"""
        height = actor.scene_height
        under = height >= 0 and height <= self.water_level and "免疫水压" not in self.traits(actor)
        if not under:
            actor.counters["underwater_turns"] = 0
            return
        layers = self.water_level - height + 1
        self.apply_nonbasic_damage(None, actor, int(actor.max_hp * 0.10 * layers), "水压", bypass_shield=True)
        actor.counters["underwater_turns"] = int(actor.counters.get("underwater_turns", 0)) + 1
        if actor.counters["underwater_turns"] % 3 == 0:
            self.move_vertical(actor, 1, "在水里待满3回合，浮上来一层")

    # ---------- 学内功 ----------

    def learned_level(self, name: str, progress: int) -> int:
        return min(MAX_INNER_LEVEL, sum(1 for need in LEARN_THRESHOLDS[name] if progress >= need))

    def learn_slots(self, fighter: Fighter) -> int:
        """除了开局自带的以外，还能学几种内功。"""
        return MAX_LEARNED_INNER + int(INNER_VALUES["内功栏"].get(fighter.own_level("内功栏"), 0))

    def learn_reason(self, fighter: Fighter, name: str) -> str | None:
        if fighter.own_level(name) >= min(MAX_INNER_LEVEL, len(LEARN_THRESHOLDS[name])):
            return "这种内功已经学满了"
        innate = self.char(fighter)["inner"]
        extra = [n for n in fighter.learn_progress if n not in innate]
        if name not in innate and name not in extra and len(extra) >= self.learn_slots(fighter):
            return f"除了自带的，最多再学 {self.learn_slots(fighter)} 种内功"
        return None

    def learn(self, fighter: Fighter, name: str) -> None:
        gain = LEARN_MULTIPLIER.get(fighter.name, 1) * int(SCENES[fighter.scene].get("learn_multiplier", 1))
        before = fighter.own_level(name)
        progress = fighter.learn_progress.get(name, 0) + gain
        fighter.learn_progress[name] = progress          # 这一份进度是这个玩家所有人物共用的
        level = fighter.own_level(name)
        leveled = level > before
        need = next((n for n in LEARN_THRESHOLDS[name] if n > progress), None)
        self._emit("learn", side=fighter.side, name=name, progress=progress, level=level, leveled=leveled)
        self._log(f"{self.label(fighter)}学{name}，学了{progress}下"
                  + (f"，升到{level}级。" if leveled else (f"，到{need}下升级。" if need else "。")))

    # ---------- 进化和衰变 ----------

    def transform(self, fighter: Fighter, new_name: str, why: str) -> None:
        """把人物变成另一个形态。

        进化：体力按新形态回满，内功取新旧两边较高的等级。
        衰变：内功退回新形态自带的（自己学来的保留）；体力不回，超过新上限的部分去掉。
        """
        from .data import CHARACTER_NAME_TO_ID
        old_name, data = fighter.name, CHARACTERS[CHARACTER_NAME_TO_ID[new_name]]
        decay = why == "衰变"
        fighter.character_id, fighter.name = data["id"], data["name"]
        fighter.max_hp, fighter.distance = data["hp"], data["distance"]
        if decay:
            fighter.hp = min(int(fighter.hp), int(data["hp"]))
            fighter.inner = dict(data["inner"])
        else:
            fighter.hp = int(data["hp"])
            for name, level in data["inner"].items():
                fighter.inner[name] = max(int(fighter.inner.get(name, 0)), level)
        fighter.initial_inner = dict(data["inner"])
        fighter.counters["form_turns"] = 0
        fighter.counters["decayed"] = decay
        self._emit("evolve", side=fighter.side, old=old_name, new=new_name, why=why, **self.vitals(fighter))
        self._log(f"{fighter.side}的{old_name}{why}成{new_name}" + ("。" if decay else "，体力回满。"))

    # ---------- 死亡和多条命 ----------

    def check_death(self, fighter: Fighter, source: str | None, reason: str) -> None:
        if fighter.defeated or fighter.hp > 0:
            return
        level = fighter.inner_level("大难不死")
        if level:
            probability = INNER_VALUES["大难不死"][level]
            if self._chance(probability, fighter.side, f"{self.label(fighter)}的大难不死发不发动",
                            yes="这条命保住，恢复一部分体力", no="这条命没了"):
                full = "真身" in self.traits(fighter)
                fighter.hp = int(fighter.max_hp) if full else max(1, int(fighter.max_hp * probability))
                self._emit("revive", side=fighter.side, **self.vitals(fighter))
                self._log(f"{self.label(fighter)}发动大难不死，恢复至{fighter.hp}体力。")
                return
        self.kill_current_life(fighter, source, all_lives=False, reason=reason)

    def kill_current_life(self, fighter: Fighter, source: str | None, all_lives: bool, reason: str) -> None:
        if fighter.defeated:
            return
        fighter.lives_remaining = 0 if all_lives else fighter.lives_remaining - 1
        if fighter.lives_remaining <= 0:
            fighter.hp = 0
            fighter.defeated = True
            self._emit("life_lost", side=fighter.side, defeated=True, **self.vitals(fighter))
            self._log(f"{self.label(fighter)}因{reason}失去全部生命。")
            return
        self._emit("life_lost", side=fighter.side, defeated=False, **self.vitals(fighter))
        self._log(f"{self.label(fighter)}因{reason}失去一条命，剩余{fighter.lives_remaining}条。")
        self.reset_life(fighter)

    def reset_life(self, fighter: Fighter) -> None:
        fighter.hp = int(fighter.max_hp)
        fighter.shield = fighter.max_shield
        fighter.scene = "地面"
        fighter.statuses.clear()
        fighter.parasites.clear()
        fighter.reset_resources()
        fighter.radiation = 0
        fighter.counters.clear()
        fighter.used_shen.clear()
        fighter.inner = dict(fighter.initial_inner)
        if fighter.name == "武圣" and fighter.lives_remaining < fighter.lives_total:
            fighter.inner.update({"幸运": 3, "大难不死": 2})
        self._emit("respawn", side=fighter.side, scene=fighter.scene, height=fighter.scene_height, **self.vitals(fighter))
        self._log(f"{self.label(fighter)}进入下一条命，体力、盾牌、状态、内功、场景、辐射和物品已重置。")
