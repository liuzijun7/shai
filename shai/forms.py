"""进化和衰变。

雨晨的回答：
- 回合数只算这个人物在场上的回合；
- 进化以后体力按新形态回满；
- 衰变时向场上除自己以外的所有人放一次射线：β 射线扣 30% 体力并累计辐射 2 次，
  γ 射线一次累计辐射 15 次（等于秒杀，大难不死救不回来）；
- 衰变以后还可以再进化。

本子：
- 饕餮满 5 条命进化成肥饕餮；肥饕餮少于 5 条命时衰变（β）；
- 生化大师 10 回合进化成猪带小天王，再过 20 回合进化成蚂蟥大仙；
  蚂蟥大仙 10 回合后衰变（γ）回猪带小天王，再过 10 回合衰变（β）回生化大师。

占卜大师占中 3 次进化成魔法师在 ``turnstart.py`` 里；龙王和拳术宗师的进化在待办里。
"""

from __future__ import annotations

from .data import (BETA_RAY, DECAY_AFTER_TURNS, DECAY_BELOW_LIVES, EVOLVE_AFTER_TURNS, EVOLVE_AT_LIVES)
from .model import Fighter

SIDES = ("A", "B")


class Forms:
    def form_phase(self) -> None:
        """一回合结算完以后：场上的人物各多待了一回合，看要不要进化或衰变。"""
        for side in SIDES:
            fighter = self.fighter(side)
            if fighter.defeated:
                continue
            fighter.counters["form_turns"] = int(fighter.counters.get("form_turns", 0)) + 1
            self._check_form(fighter)

    def _check_form(self, fighter: Fighter) -> None:
        name, turns = fighter.name, int(fighter.counters.get("form_turns", 0))
        if name in EVOLVE_AT_LIVES:
            need, new = EVOLVE_AT_LIVES[name]
            if fighter.lives_remaining >= need:
                self.transform(fighter, new, "进化")
            return
        if name in DECAY_BELOW_LIVES:
            need, new, ray = DECAY_BELOW_LIVES[name]
            if fighter.lives_remaining < need:
                self._decay(fighter, new, ray)
            return
        # 猪带小天王两头都通：进化上来的继续往上进化，衰变下来的继续往下衰变。
        falling = bool(fighter.counters.get("decayed")) or name not in EVOLVE_AFTER_TURNS
        if name in DECAY_AFTER_TURNS and falling:
            need, new, ray = DECAY_AFTER_TURNS[name]
            if turns >= need:
                self._decay(fighter, new, ray)
        elif name in EVOLVE_AFTER_TURNS:
            need, new = EVOLVE_AFTER_TURNS[name]
            if turns >= need:
                self.transform(fighter, new, "进化")

    def _decay(self, fighter: Fighter, new_name: str, ray: str) -> None:
        self.transform(fighter, new_name, "衰变")
        foe = self.fighter(self.other(fighter.side))
        if foe.defeated:
            return
        self._emit("ray", side=foe.side, source=fighter.side, ray=ray)
        self._log(f"{self.label(fighter)}衰变时放出{ray}射线。")
        if ray == "γ":
            self.gamma_ray(fighter, foe, "衰变的γ射线")
        else:
            self.beta_ray(fighter, foe, "衰变的β射线")

    def beta_ray(self, source: Fighter, target: Fighter, reason: str = "β射线") -> None:
        """β 射线：扣 30% 体力，累计辐射 2 次。"""
        self.apply_nonbasic_damage(source, target, int(target.max_hp * BETA_RAY["hp_ratio"]), reason)
        if not target.defeated:
            self.add_radiation(target, BETA_RAY["radiation"], source.side, reason)

    def gamma_ray(self, source: Fighter, target: Fighter, reason: str = "伽马射线") -> None:
        """γ 射线：一次累计辐射 15 次。八分之一的可能是臭伽马，强制昏睡 10 回合。"""
        if target.has_status("无敌"):
            self._log(f"{self.label(target)}处于无敌，{reason}无效。")
            return
        self.add_radiation(target, 15, source.side, reason)
        if not target.defeated and self._chance(0.125, source.side, f"{self.label(source)}的伽马射线是不是臭伽马"):
            self.apply_status(target, "昏睡", 10, source.side, forced=True)
            self._log("臭伽马触发，强制昏睡。")
