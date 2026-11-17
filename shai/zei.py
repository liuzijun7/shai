"""贼（石头剪刀布）这个小游戏本身。

规则引擎只说“这里需要 A 和 B 贼一次”，并等一个结果。真正让两个人出拳、打平重来、
用内功“重贼”再来一次，都在这里。服务器和命令行都用它。

用法：
    game = ZeiGame(battle.pending)
    while True:
        state = game.throw({"A": "石头", "B": "布"})
        if state == "again": continue            # 打平，重出
        if state == "redo?":                     # 输的一方有重贼，可以选择再来
            if game.redo(想不想重来): continue
        break
    battle.answer(game.winner)
"""

from __future__ import annotations

from typing import Any

HANDS = ("石头", "剪刀", "布")
_BEATS = {"石头": "剪刀", "剪刀": "布", "布": "石头"}


def judge(first: str, second: str) -> int:
    """1：第一个人赢。-1：第二个人赢。0：打平。"""
    if first == second:
        return 0
    return 1 if _BEATS[first] == second else -1


class ZeiGame:
    def __init__(self, request: dict[str, Any]):
        self.sides: list[str] = list(request["sides"])
        self.mode: str = request["mode"]            # decisive：贼到分出胜负；single：只贼一次
        self.redo_left = {side: int(request.get("rezei", {}).get(side, 0)) for side in self.sides}
        self.rounds: list[dict[str, str]] = []      # 每一轮双方出的拳
        self.winner: str | None = None
        self.done = False
        self.redo_side: str | None = None           # 正在等谁决定要不要重贼

    def throw(self, hands: dict[str, str]) -> str:
        """双方各出一拳。返回 "again"（打平重出）、"redo?"（等输的一方决定重不重贼）或 "done"。"""
        if self.done or self.redo_side:
            raise ValueError("现在不能出拳。")
        a, b = self.sides
        if hands.get(a) not in HANDS or hands.get(b) not in HANDS:
            raise ValueError("出拳只能是石头、剪刀、布。")
        self.rounds.append({a: hands[a], b: hands[b]})
        result = judge(hands[a], hands[b])
        if result == 0:
            if self.mode == "decisive":
                return "again"
            self.winner, self.done = None, True
            return "done"
        self.winner = a if result == 1 else b
        loser = b if result == 1 else a
        if self.redo_left[loser] > 0:
            self.redo_side = loser
            return "redo?"
        self.done = True
        return "done"

    def redo(self, yes: bool) -> bool:
        """输的一方决定要不要用一次重贼。返回 True 表示要重新出拳。"""
        if not self.redo_side:
            raise ValueError("现在没有人可以重贼。")
        side, self.redo_side = self.redo_side, None
        if not yes:
            self.done = True
            return False
        self.redo_left[side] -= 1
        self.winner = None
        return True
