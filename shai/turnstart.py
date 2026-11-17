"""回合开始、出招之前发生的事：牛顿选场景、龙王移动对手、库巴的扔和跑。

规则来自雨晨的回答：
- 牛顿每回合开始可以自己选一个场景，不占出招。万能胶对他无效。
- 龙王每回合开始可以把对手移到任意一个场景，也可以不移。
- 两个效果撞了（龙王要移牛顿，牛顿要自己选）就贼，赢的人说了算。
- 库巴：对手可以“扔”（指定库巴去哪），库巴可以“跑”（自己选去哪）。两样都要的时候一共贼三次：
  先贼一次定先后，然后扔贼一次（对手赢才扔得成），跑贼一次（库巴赢才跑得成）。
  谁不想扔或不想跑，就不用贼那一次。库巴身上有万能胶时不能扔也不能跑。
"""

from __future__ import annotations

from .data import SCENES

DRAGONS = {"龙王", "肥龙王"}


class TurnStart:
    def scene_phase(self) -> None:
        for side in ("A", "B"):                 # side：这一方人物的场景可能要变
            target, foe_side = self.fighter(side), self.other(side)
            foe = self.fighter(foe_side)
            if target.defeated or foe.defeated:
                continue
            if target.name == "库巴":
                self._kuba_phase(side)
                continue
            forced = own = None
            if foe.name in DRAGONS:
                forced = self._ask_scene(foe_side, f"{self.label(foe)}要把{self.label(target)}移到哪个场景", "不移动")
            if target.name == "牛顿":
                own = self._ask_scene(side, f"{self.label(target)}这回合去哪个场景", "不动")
            if forced and own and forced != own:
                winner = self._zei(foe_side, side, "decisive", f"{foe.name}要移动{target.name}，{target.name}要自己选场景")
                destination = forced if winner == foe_side else own
            else:
                destination = own or forced
            if destination:
                self.set_scene(target, destination)

    def _ask_scene(self, side: str, reason: str, none_label: str) -> str | None:
        options = [{"id": "", "name": none_label}] + [{"id": name, "name": name} for name in SCENES]
        value = self._decide("choose", side=side, options=options, reason=reason)["value"]
        return value or None

    def _kuba_phase(self, side: str) -> None:
        kuba, foe_side = self.fighter(side), self.other(side)
        if kuba.has_status("万能胶"):
            self._log(f"{self.label(kuba)}身上有万能胶，这回合不能扔也不能跑。")
            return
        throw_to = self._ask_scene(foe_side, f"要不要把{self.label(kuba)}扔到别的场景", "不扔")
        run_to = self._ask_scene(side, f"{self.label(kuba)}要不要跑到别的场景", "不跑")
        steps = [name for name, wanted in (("throw", throw_to), ("run", run_to)) if wanted]
        if len(steps) == 2:
            # 第一次贼：定先扔还是先跑。后做的那一样决定库巴最后在哪，所以赢的人的那一样放在后面。
            winner = self._zei(foe_side, side, "decisive", "库巴的扔和跑，定先后")
            steps = ["run", "throw"] if winner == foe_side else ["throw", "run"]
        for step in steps:
            if step == "throw":
                if self._zei(foe_side, side, "decisive", f"扔{self.label(kuba)}") == foe_side:
                    self._log(f"{self.label(kuba)}被扔了出去。")
                    self.set_scene(kuba, throw_to)
                else:
                    self._log(f"{self.label(kuba)}没被扔动。")
            elif self._zei(side, foe_side, "decisive", f"{self.label(kuba)}要跑") == side:
                self._log(f"{self.label(kuba)}跑了。")
                self.set_scene(kuba, run_to)
            else:
                self._log(f"{self.label(kuba)}没跑成。")
