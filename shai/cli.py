"""在命令行里打一局，用来试规则。在仓库根目录运行：

    python -m shai.cli --a 陶渊明,武圣 --b 牛顿,饕餮
    python -m shai.cli --a 拳术宗师 --b 饕餮 --bot B          B 由电脑随机出招
    python -m shai.cli --bot AB --seed 3                      两边都是电脑，看一局自动对战

选招时输入编号，或者输入招式名字的一部分来搜索。
"""

from __future__ import annotations

import argparse
import random
import sys

from .battle import SIDES, Battle
from .data import SCENES, SELECTABLE_NAMES
from .model import RuleError
from .zei import HANDS, ZeiGame


def show(battle: Battle) -> None:
    view = battle.view()
    print(f"\n===== 第{view['round']}回合   水面高度 {view['water_level']} =====")
    for side in SIDES:
        player = view["players"][side]
        for index, f in enumerate(player["team"]):
            mark = "▶" if index == player["active"] else " "
            if f["defeated"]:
                print(f" {mark} {side} {f['name']}（已倒下）")
                continue
            if f["is_true_body"] and index != player["active"]:
                continue
            extra = []
            if f["shield"]:
                extra.append(f"盾{f['shield']}")
            if f["lives_total"] > 1:
                extra.append(f"命{f['lives_remaining']}/{f['lives_total']}")
            if f["radiation"]:
                extra.append(f"辐射{f['radiation']}/15")
            extra += [f"{n}{s['turns']}" for n, s in f["statuses"].items()]
            extra += [f"{n}×{p['count']}" for n, p in f["parasites"].items()]
            print(f" {mark} {side} {f['name']}  体力{f['hp']}  {f['scene']}  {' '.join(extra)}")


def ask_action(battle: Battle, side: str) -> tuple[str, str | None]:
    actions = [a for a in battle.legal_actions(side) if a["legal"]]
    while True:
        text = input(f"[{side}] 选招（编号 / 名字 / ? 列出全部）：").strip()
        if text == "?" or not text:
            for i, a in enumerate(actions):
                attrs = "+".join(a["attributes"]) or "无属性"
                print(f"  {i:>2} {a['name']}  [{attrs}] 伤害{a['damage']} 防{a['defense'] or '-'}")
            continue
        found = [actions[int(text)]] if text.isdigit() and int(text) < len(actions) else [a for a in actions if text in a["name"]]
        if len(found) != 1:
            print("  找到：" + "、".join(a["name"] for a in found[:12]) if found else "  没有这个招。")
            continue
        action = found[0]
        destination = None
        if action["effect"] == "choose_scene":
            destination = input("  去哪个场景：").strip()
            if destination not in SCENES:
                print("  没有这个场景。")
                continue
        return action["id"], destination


def bot_action(battle: Battle, side: str, rng: random.Random) -> tuple[str, str | None]:
    action = rng.choice([a for a in battle.legal_actions(side) if a["legal"]])
    return action["id"], rng.choice(list(SCENES)) if action["effect"] == "choose_scene" else None


def run_zei(battle: Battle, bots: str, rng: random.Random) -> None:
    request = battle.pending
    print(f"\n-- 贼：{request['reason']} --")
    game = ZeiGame(request)
    while True:
        hands = {}
        for side in game.sides:
            if side in bots:
                hands[side] = rng.choice(HANDS)
            else:
                hand = ""
                while hand not in HANDS:
                    hand = input(f"[{side}] 出拳（石头 / 剪刀 / 布）：").strip()
                hands[side] = hand
        state = game.throw(hands)
        print("   " + "  ".join(f"{s}出{h}" for s, h in hands.items()))
        if state == "again":
            print("   打平，重来。")
            continue
        if state == "redo?":
            side = game.redo_side
            again = True if side in bots else input(f"[{side}] 输了。用一次重贼吗？(y/n)：").strip().lower() == "y"
            if game.redo(again):
                continue
        break
    print("   结果：" + ("打平" if game.winner is None else f"{game.winner}赢"))
    battle.answer(game.winner)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="《晒》命令行对战")
    parser.add_argument("--a", default="", help="A 的队伍，逗号分隔")
    parser.add_argument("--b", default="", help="B 的队伍，逗号分隔")
    parser.add_argument("--bot", default="", help="由电脑控制的一方：A、B 或 AB")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--no-zei", action="store_true", help="这一局所有的贼都改成电脑掷概率")
    parser.add_argument("--max-rounds", type=int, default=300)
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    rng = random.Random(args.seed)
    team_a = [n for n in args.a.split(",") if n] or rng.sample(SELECTABLE_NAMES, 3)
    team_b = [n for n in args.b.split(",") if n] or rng.sample(SELECTABLE_NAMES, 3)
    battle = Battle(team_a, team_b, seed=args.seed, zei=not args.no_zei)
    printed = 0
    while not battle.done and battle.round <= args.max_rounds:
        for line in battle.log[printed:]:
            print("  " + line)
        printed = len(battle.log)
        if battle.pending:
            request = battle.pending
            if request["kind"] == "zei":
                run_zei(battle, args.bot, rng)
            else:
                side = request["askers"][0]
                names = [o["name"] for o in request["options"]]
                if side in args.bot:
                    pick = rng.randrange(len(names))
                else:
                    pick = -1
                    while not 0 <= pick < len(names):
                        text = input(f"[{side}] {request['reason']}（" + "、".join(f"{i}:{n}" for i, n in enumerate(names)) + "）：").strip()
                        pick = int(text) if text.isdigit() else -1
                battle.answer(request["options"][pick]["id"])
            continue
        show(battle)
        for side in battle.waiting_for():
            try:
                battle.choose(side, *(bot_action(battle, side, rng) if side in args.bot else ask_action(battle, side)))
            except RuleError as error:
                print(f"  不行：{error}")
                break
            if battle.pending or battle.done:
                break
    for line in battle.log[printed:]:
        print("  " + line)
    print("\n" + ("对战结束。" if battle.done else f"到第 {args.max_rounds} 回合还没打完，停止。"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
