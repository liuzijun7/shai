"""每个招打出去以后发生什么。从刘同学 ``engine.py`` 的 ``_resolve_action`` 逐条搬过来。

和原来不同的地方（都来自雨晨的回答）：
- 概率全部走 ``self._chance``：流星是否继续、死亡笔记秒杀、硫酸秒杀、臭伽马；
- 臭伽马的概率是八分之一，昏睡 10 回合是强制的，真空屏障过滤不掉；
- 新增纵目青铜怪的“换血”。
"""

from __future__ import annotations

from typing import Any

from .data import ACCELERATOR_BIG, SCENES, SELF_BUFFS, accelerator_level
from .model import Fighter, Status


class Actions:
    def resolve_action(self, actor: Fighter, target: Fighter, spec: dict[str, Any], destination: str | None) -> None:
        effect = spec["effect"]
        traits = self.traits(actor)
        base = self.character_damage(actor, spec)
        reps = self.effect_repetitions(actor)
        L = self.label

        # ----- 只和自己有关的动作 -----
        if effect == "learn":
            return self.learn(actor, spec["inner"])
        if effect == "collect_oxygen":
            return self.collect(actor, "氧气", reps, scene_multiplier=SCENES[actor.scene].get("oxygen_multiplier", 1))
        if effect == "collect_supernova":
            return self.collect(actor, "超新星", reps)
        if effect == "collect_star":
            return self.collect(actor, "星体能量", reps)
        if effect == "collect_wine":
            return self.collect(actor, "酒", reps, scene_multiplier=1)
        if effect == "collect_panacea":
            return self.collect(actor, "万灵丹", reps, scene_multiplier=1)
        if effect == "collect_glue":
            self.apply_status(actor, "万能胶", 5, actor.side, force_body=True)
            if actor.has_status("烧伤") or actor.has_status("点燃"):
                actor.statuses.pop("万能胶", None)
                self._log(f"{L(actor)}身上的火系状态使万能胶立即失效。")
            return
        if effect == "drink_wine":
            actor.resources["酒"] -= 1
            actor.statuses["无敌"] = Status("无敌", 1, actor.side, fresh=False)
            actor.counters["wine_invincible_until_next_turn"] = True
            self._emit("status", side=actor.side, name="无敌", turns=1, good=True)
            self._log(f"{L(actor)}喝下1个酒，本轮无敌。")
            return
        if effect == "choose_scene":
            return self.set_scene(actor, destination or "地面")
        if effect in {"build_yueyang", "build_pyramid"}:
            key = "岳阳楼" if effect == "build_yueyang" else "金字塔"
            actor.counters[key] = int(actor.counters.get(key, 0)) + reps
            self._log(f"{L(actor)}的{key}进度为{actor.counters[key]}/5。")
            while actor.counters[key] >= 5:
                actor.counters[key] -= 5
                self.upgrade_all_inner(actor)
            return
        if effect == "build_accelerator":
            built = min(ACCELERATOR_BIG["builds"], int(actor.devices.get("粒子加速器", 0)) + reps)
            actor.devices["粒子加速器"] = built
            self._emit("build", side=actor.side, name="粒子加速器", progress=built, of=ACCELERATOR_BIG["builds"])
            self._log(f"{L(actor)}造粒子加速器，造了{built}下。"
                      + ("已经可以打了。" if accelerator_level(built) else ""))
            return
        if effect == "panacea":
            actor.resources["万灵丹"] -= 1
            self.cleanse(actor)
            self._log(f"{L(actor)}清除了不良状态和寄生虫。")
            return
        if effect == "rebirth":
            self.cleanse(actor)
            actor.hp = int(actor.max_hp)
            # 本子：“清除自身所有坏东西并防一招”。无敌只管用的这一回合，回合结束就没有了。
            actor.statuses["无敌"] = Status("无敌", 1, actor.side, fresh=False)
            if actor.name == "巫师":
                actor.shield = 0
                actor.max_shield = 0
            self._emit("heal", side=actor.side, amount=0, reason="浴火重生", **self.vitals(actor))
            self._emit("status", side=actor.side, name="无敌", turns=1, good=True)
            self._log(f"{L(actor)}浴火重生，体力回满并获得无敌。")
            return
        if effect == "self_status":
            for name, turns in spec["statuses"]:
                self.apply_status(actor, name, turns, actor.side, force_body=True)
            return

        # ----- 下面都要有一个活着的对手 -----
        if target.defeated:
            self._log(f"对手已经倒下，【{spec['name']}】没有目标。")
            return

        if effect == "self_status_and_damage":
            if self.skill_hits(actor, target, spec) and not self.blocked_by_immunity(actor, target, spec):
                self.deal_skill_damage(actor, target, spec, base, reps, prechecked=True)
            else:
                self._log(f"【{spec['name']}】没有影响到{L(target)}。")
            for name, turns in spec["statuses"]:
                self.apply_status(actor, name, turns, actor.side, force_body=True)
            return self.after_special(actor, spec)
        if effect == "meteor":
            hits, series = 0, self.series_start(target)
            for _ in range(reps):
                while not self.series_over(target, series):
                    hits += 1
                    self.deal_skill_damage(actor, target, spec, base, 1)
                    if self.series_over(target, series) or not self._chance(
                            0.5, actor.side, f"{L(actor)}的流星还打不打下一拳", yes="再打一拳", no="流星到此为止"):
                        break
            self._log(f"流星共打出{hits}拳。")
            return

        if effect == "sound_wave" and SCENES[target.scene].get("vacuum"):
            self._log(f"{L(target)}处于真空，声波炮无效。")
            return self.after_special(actor, spec)
        if spec["target"] == "enemy":
            # 先看这个招对他有没有用。没用就不用为“躲不躲得开”贼了。
            if self.blocked_by_immunity(actor, target, spec):
                return self.after_special(actor, spec)
            if self.only_filtered_statuses(actor, target, spec):
                return self.after_special(actor, spec)
            if not self.skill_hits(actor, target, spec):
                return self.after_special(actor, spec)
        if effect == "sunspot":
            actor.resources["星体能量"] -= 3
        if effect == "planet":
            actor.resources["超新星"] -= 1
            actor.resources["星体能量"] -= 3
        if effect == "gamma" and actor.name != "达伽马":
            actor.resources["超新星"] -= 1
            actor.resources["星体能量"] -= 5

        if effect == "swap_hp":
            actor.hp, target.hp = target.hp, actor.hp
            actor.max_hp, target.max_hp = target.max_hp, actor.max_hp
            self._emit("swap_hp", side=actor.side, vitals={actor.side: self.vitals(actor), target.side: self.vitals(target)})
            self._log(f"{L(actor)}与{L(target)}互换体力和体力上限。")
            self.check_death(actor, target.side, "换血")
            self.check_death(target, actor.side, "换血")
            return
        if effect == "ultimate_drain":
            ratio = 1.0 if actor.name == "肥饕餮" else 0.8
            dealt = self.apply_nonbasic_damage(actor, target, int(target.max_hp * ratio), "究极吸取")
            if dealt:
                self.heal(actor, dealt, "究极吸取", over_cap=True)
            return self.after_special(actor, spec)
        if effect == "xray":
            if target.has_status("氪"):
                self._log(f"{L(target)}的氪屏障令X光无效。")
            else:
                self.add_radiation(target, 5 * reps, actor.side, "X光")
            return
        if effect == "gamma":
            if target.has_status("无敌"):
                self._log(f"{L(target)}处于无敌，伽马射线无效。")
                return
            self.gamma_ray(actor, target)
            return self.after_special(actor, spec)
        if effect == "sulfuric_acid" and actor.name in {"生化大师", "猪带小天王"}:
            if self._chance(0.5, actor.side, f"{L(actor)}的硫酸能不能秒杀", yes="直接打掉对手这条命", no="没有秒杀"):
                self.kill_current_life(target, actor.side, all_lives=False, reason="硫酸秒杀")
            else:
                self._log("硫酸的秒杀没有触发。")
            return self.after_special(actor, spec)
        if effect == "ether":
            if actor.name in {"生化大师", "猪带小天王"}:
                self.apply_status(target, "昏睡", self.duration(actor, spec, 5), actor.side)
            else:
                if target.has_status("烧伤") or target.has_status("点燃"):
                    self.apply_nonbasic_damage(actor, target, int(target.max_hp * 0.50), "乙醚联动")
                target.counters.setdefault("delayed_effects", []).append(
                    {"remaining": 2, "status": "昏睡", "turns": self.duration(actor, spec, 5), "source": actor.side})
                self._log(f"{L(target)}将在两个自己的回合后昏睡。")
            return self.after_special(actor, spec)      # 乙醚现在带特技：用完自己被封喉（自己的大招除外）
        if effect == "pork_tapeworm":
            return self.add_parasite(target, "猪带绦虫", reps, actor.side)
        if effect == "sleep_tapeworm":
            self.add_parasite(target, "昏睡绦虫", reps, actor.side)
            self.apply_status(target, "昏睡", 1, actor.side)
            return
        if effect == "leech":
            return self.add_parasite(target, "蚂蟥", reps, actor.side)
        if effect == "leech_wave":
            self.deal_skill_damage(actor, target, spec, base, reps, prechecked=True)
            self.add_parasite(target, "蚂蟥", 3 * reps, actor.side)
            return self.after_special(actor, spec)
        if effect == "taotie_fang":
            total, series = 0, self.series_start(target)
            for _ in range(2 * reps):
                if self.series_over(target, series):
                    break
                total += self.deal_skill_damage(actor, target, spec, base, 1, prechecked=True)
            actor.hp += total
            if actor.hp > actor.max_hp:
                actor.lives_total += 1
                actor.lives_remaining += 1
                actor.hp = int(actor.max_hp)
                self._log(f"{L(actor)}突破上限，增加一条命。")
            if total:
                self._emit("heal", side=actor.side, amount=total, reason="饕餮牙", **self.vitals(actor))
            return

        # ----- 大部分招共用的流程：伤害，状态，附加效果 -----
        lives = target.lives_remaining
        self.deal_skill_damage(actor, target, spec, base, reps, prechecked=True)
        if target.defeated or target.lives_remaining < lives:
            # 这一招已经打掉了对手一条命：剩下的特效不会落到他的下一条命上（雨晨）。
            return self.after_special(actor, spec)
        self.begin_status_batch()
        for name, turns in spec["statuses"]:
            who = actor if name in SELF_BUFFS else target
            fixed = actor.name == "灵力圣使" and "魔法" in spec["attributes"] and who is target
            self.apply_status(who, name, self.duration(actor, spec, turns), actor.side,
                              force_body=who is actor, unremovable=fixed)
        self.end_status_batch()
        if effect == "rise_self":
            self.move_vertical(actor, 2 if "圣六式覆盖" in traits else 1)
        elif effect == "lower_target":
            self.move_vertical(target, -4 if actor.name == "龙王" and spec["id"] == "9" else -1)
        elif effect == "antarctic":
            self.set_scene(target, "南极")
            if actor.name == "龙王":
                self.apply_status(target, "昏睡", self.duration(actor, spec, 3), actor.side)
        elif effect == "flood":
            self.water_level += 1
            self._emit("water", level=self.water_level)
            self._log(f"水面上升到高度{self.water_level}。")
        elif effect == "death_note":
            if self._chance(0.125, actor.side, f"{L(actor)}的死亡笔记能不能秒杀", yes="直接打掉对手这条命", no="没有秒杀"):
                self.kill_current_life(target, actor.side, all_lives=False, reason="死亡笔记秒杀")
        elif effect == "drop_ground":
            if target.scene_height > 0:
                self.set_scene(target, "地面")
        elif effect == "sunspot":
            if target.scene_height > 0:
                self.set_scene(target, "地面")
            for name in list(target.inner):
                target.inner[name] = max(0, target.inner[name] - 1)
            self._log(f"{L(target)}的全部内功下降一级。")
        elif effect == "accelerator":
            level = accelerator_level(int(actor.devices.get("粒子加速器", 0)))
            if level:
                self.add_radiation(target, int(level["radiation"]) * reps, actor.side, "粒子加速器")
        elif effect == "to_scene":
            self.set_scene(target, spec["scene"])
        elif effect == "foehn":
            if target.statuses.pop("万能胶", None):
                self._emit("status_end", side=target.side, name="万能胶")
                self._log(f"{L(target)}的万能胶被吹掉。")
            self.set_scene(target, "地面")
        elif effect == "planet":
            if target.scene_height > 0:
                self.set_scene(target, "地面")
            self.add_radiation(target, 1, actor.side, "行星撞地球")
        elif effect == "u92":
            if self._chance(0.5, actor.side, f"{L(actor)}的九十二三弑能不能让对手昏睡", yes="对手昏睡3回合", no="对手不昏睡"):
                self.apply_status(target, "昏睡", self.duration(actor, spec, 3), actor.side)
            if not target.defeated:
                self.add_radiation(target, 1, actor.side, "九十二三弑")
        elif effect == "melamine":
            if target.resources["万灵丹"]:
                target.resources["万灵丹"] = 0
                self._log(f"{L(target)}的万灵丹全部失效。")
        elif effect == "typhoon":
            for key in target.resources:
                if key != "氧气":
                    target.resources[key] = 0
            self._log(f"{L(target)}失去全部物品。")
        self.after_special(actor, spec)
