"""照着保存下来的记录，把一局对战原样重打一遍。

记录里有开局设置（双方的队伍、随机数种子、用不用贼）和双方每一步的输入（选的招、每次贼的结果、
每次选择）。规则引擎是确定的：同样的开局加同样的输入，结果一模一样。

网页上的回放不靠这个（它直接播记录里存的事件）。这个函数用来核对旧的记录、查问题。
"""

from __future__ import annotations

from typing import Any

from .battle import Battle


def rebuild(record: dict[str, Any]) -> Battle:
    battle = Battle(record["teams"]["A"], record["teams"]["B"], seed=record["seed"], zei=record["zei"])
    for step in record["history"]:
        if step["type"] == "choose":
            battle.choose(step["side"], step["action"], step.get("destination"))
        else:
            battle.answer(step["value"], step.get("detail"))
    return battle
