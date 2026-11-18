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

from .data import LOAN_TURNS, SCENES

DRAGONS = {"龙王", "肥龙王"}
DIVINERS = {"占卜大师", "魔法师"}
ATTRIBUTE_CHOICES = ("物理", "魔法", "特技", "地理", "化学", "生物", "神技", "物品", "无属性")


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
                winner = self._zei(
                    foe_side, side, "decisive", f"{self.label(foe)}要把{target.name}移到{forced}，{self.label(target)}自己要去{own}",
                    {foe_side: f"{target.name}被移到{forced}", side: f"{target.name}去{own}"})
                destination = forced if winner == foe_side else own
            else:
                destination = own or forced
            if destination:
                mover = foe.name if destination == forced and forced != own else target.name
                self.set_scene(target, destination, f"回合开始时{mover}选了场景")

    # ---------- 宋濂借内功 ----------
    # 雨晨：回合开始时弹出一个选择，列出对面场上人物现有的内功，宋濂选一种来借，不占出招。
    # 本子：“最多借 5 回合要换一个借（不耗回合）”。借满 5 回合再选一次，要换另一种。
    # 对面的人物下场或者死了，借来的就没有了（在 Battle._link_lenders 里清掉）。

    def loan_phase(self) -> None:
        for side in ("A", "B"):
            borrower = self.fighter(side)
            lender = borrower.lender
            if lender is None or lender.defeated or borrower.defeated:
                continue
            available = lender.own_inner()
            loan, turns = borrower.counters.get("loan"), int(borrower.counters.get("loan_turns", 0))
            if loan and loan in available and turns < LOAN_TURNS:
                borrower.counters["loan_turns"] = turns + 1        # 接着借
                continue
            if loan:                                               # 借满了，或者对面没有这种内功了
                borrower.counters["loan_last"] = loan
                borrower.counters.pop("loan", None)
                borrower.counters.pop("loan_turns", None)
                self._log(f"{self.label(borrower)}借的{loan}到期了。")
            last = borrower.counters.pop("loan_last", None)
            names = [name for name in sorted(available) if name != last]
            if not names:
                continue
            options = [{"id": "", "name": "不借"}] + [{"id": name, "name": f"{name}{available[name]}级"} for name in names]
            choice = self._decide(
                "choose", side=side, options=options,
                reason=f"{self.label(borrower)}借对面{lender.name}的哪一种内功？最多借{LOAN_TURNS}回合，到时候要换一种")["value"]
            if choice:
                borrower.counters["loan"], borrower.counters["loan_turns"] = choice, 1
                self._emit("loan", side=side, name=choice, level=available[choice], source=lender.name)
                self._log(f"{self.label(borrower)}借了{lender.name}的{choice}{available[choice]}级。")

    # ---------- 占卜 ----------
    # 雨晨的回答：每回合出招之前，占卜大师猜对手这回合用什么属性的招，双方都能看到他猜了什么。
    # 对手真的用了就算占中：体力和体力上限各加“占中的次数 × 1 万”。占中 3 次变成魔法师。

    def divination_phase(self) -> None:
        for side in ("A", "B"):
            diviner, foe = self.fighter(side), self.fighter(self.other(side))
            diviner.counters.pop("divination", None)
            if diviner.name not in DIVINERS or diviner.defeated or foe.defeated or side in self.skipping:
                continue
            options = [{"id": "", "name": "这回合不占卜"}] + [{"id": a, "name": a} for a in ATTRIBUTE_CHOICES]
            guess = self._decide("choose", side=side, options=options,
                                 reason=f"{self.label(diviner)}占卜：对手这回合用什么属性的招")["value"]
            if guess:
                diviner.counters["divination"] = guess
                self._emit("divine", side=side, attribute=guess)
                self._log(f"{self.label(diviner)}占卜：对手这回合会用【{guess}】的招。")

    def check_divination(self, specs: dict) -> None:
        for side in ("A", "B"):
            diviner = self.fighter(side)
            guess = diviner.counters.pop("divination", None)
            if not guess or diviner.defeated:
                continue
            spec = specs[self.other(side)]
            used = spec["action_kind"] not in {"defense", "skip", "switch"}
            hit = used and (guess in spec["attributes"] or (guess == "无属性" and not spec["attributes"]))
            if not hit:
                self._log(f"{self.label(diviner)}没有占中。")
                continue
            count = int(diviner.counters.get("divination_hits", 0)) + 1
            diviner.counters["divination_hits"] = count
            diviner.max_hp += count * 10000
            diviner.hp += count * 10000
            self._emit("divine_hit", side=side, count=count, **self.vitals(diviner))
            self._log(f"{self.label(diviner)}占中了（第{count}次），体力和体力上限各加{count * 10000}。")
            if count >= 3 and diviner.name == "占卜大师":
                self.transform(diviner, "魔法师", "进化")

    def _ask_scene(self, side: str, reason: str, none_label: str) -> str | None:
        options = [{"id": "", "name": none_label}] + [{"id": name, "name": name} for name in SCENES]
        value = self._decide("choose", side=side, options=options, reason=reason)["value"]
        return value or None

    def _kuba_phase(self, side: str) -> None:
        kuba, foe_side = self.fighter(side), self.other(side)
        if kuba.has_status("万能胶"):
            self._log(f"{self.label(kuba)}身上有万能胶，这回合不能扔也不能跑。")
            return
        k, thrower = self.label(kuba), self.label(self.fighter(foe_side))
        throw_to = self._ask_scene(foe_side, f"回合开始：要不要把{k}扔到别的场景？选了场景以后要贼，赢了才扔得动", "不扔")
        run_to = self._ask_scene(side, f"回合开始：{k}要不要跑到别的场景？选了场景以后要贼，赢了才跑得成", "不跑")
        steps = [name for name, wanted in (("throw", throw_to), ("run", run_to)) if wanted]
        if len(steps) == 2:
            # 第一次贼：定先扔还是先跑。后做的那一样决定库巴最后在哪，所以赢的人的那一样放在后面。
            winner = self._zei(
                foe_side, side, "decisive",
                f"{thrower}想把库巴扔到{throw_to}，{k}想跑到{run_to}。先定哪一样后做（后做的说了算）",
                {foe_side: "先贼“跑”，再贼“扔”", side: "先贼“扔”，再贼“跑”"})
            steps = ["run", "throw"] if winner == foe_side else ["throw", "run"]
        for step in steps:
            if step == "throw":
                if self._zei(foe_side, side, "decisive", f"{thrower}把{k}扔到{throw_to}",
                             {foe_side: f"库巴被扔到{throw_to}", side: "没扔动"}) == foe_side:
                    self.set_scene(kuba, throw_to, "被扔了出去")
                else:
                    self._log(f"{k}没被扔动。")
            elif self._zei(side, foe_side, "decisive", f"{k}跑到{run_to}",
                           {side: f"库巴跑到{run_to}", foe_side: "没跑成"}) == side:
                self.set_scene(kuba, run_to, "跑了")
            else:
                self._log(f"{k}没跑成。")
