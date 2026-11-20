"""第五步：限时、聊天、观战、战报和回放（都不经过网络）。"""

import json
import os
import random
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from server.rooms import CHOOSE_SECONDS, ZEI_SECONDS, Room, RoomError  # noqa: E402
from shai.replay import rebuild  # noqa: E402


class Clock:
    """假的钟：测试里自己拨时间。"""

    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def room_with(team_a, team_b, zei=True, timers=True):
    clock = Clock()
    room = Room("1234", rng=random.Random(1), clock=clock)
    room.join("甲")
    room.join("乙")
    room.handle("A", {"t": "config", "team_size": len(team_a), "zei": zei, "timers": timers})
    room.handle("A", {"t": "team", "names": team_a})
    room.handle("B", {"t": "team", "names": team_b})
    return room, clock


class Watching(unittest.TestCase):
    def test_third_person_watches_and_sees_only_what_is_on_the_field(self):
        room, _ = room_with(["拳术宗师", "巫师"], ["饕餮", "牛顿"])
        key, token = room.join("丙")
        self.assertTrue(key.startswith("w:"))
        state = room.state_for(key)
        self.assertEqual((state["role"], state["need"], state["you"]), ("watch", "watch", None))
        self.assertEqual(state["watchers"], ["丙"])
        for side, name in (("A", "拳术宗师"), ("B", "饕餮")):
            team = state["view"]["players"][side]["team"]
            self.assertEqual(team[0]["name"], name)
            self.assertTrue(team[1]["hidden"])                    # 两边没上场的人物都看不到
        self.assertNotIn("actions", state)
        room.handle("A", {"t": "choose", "action": "4"})
        state = room.state_for(key)
        self.assertEqual(state["view"]["chosen"], {"A": True, "B": False})   # 只知道谁选好了，不知道选了什么
        self.assertEqual(state["events"], [])
        with self.assertRaises(RoomError):
            room.handle(key, {"t": "choose", "action": "0"})
        self.assertEqual(room.join("丙", token)[0], key)          # 刷新页面还是同一个观战的人

    def test_watcher_sees_the_zei_but_not_the_hands_in_flight(self):
        room, _ = room_with(["拳术宗师"], ["饕餮"])
        key, _ = room.join("丙")
        room.handle("A", {"t": "choose", "action": "22"})         # 摄魂点穴手
        room.handle("B", {"t": "choose", "action": "3"})          # 点穴手：两边互相都能封住对方，要贼先后手
        room.handle("A", {"t": "throw", "hand": "石头"})
        state = room.state_for(key)
        self.assertEqual(state["need"], "watch")
        self.assertEqual(state["prompt"]["thrown"], {"A": True, "B": False})
        self.assertEqual(state["prompt"]["rounds"], [])

    def test_you_can_ask_to_watch_and_leaving_frees_the_spot(self):
        room = Room("7", rng=random.Random(1))
        key, _ = room.join("丙", watch=True)
        self.assertTrue(key.startswith("w:"))
        self.assertIsNone(room.seats["A"])
        self.assertEqual(room.state_for(key)["phase"], "lobby")
        room.leave(key)
        self.assertEqual(room.watchers, {})


class Chat(unittest.TestCase):
    def test_players_and_watchers_can_chat(self):
        room, clock = room_with(["拳术宗师"], ["饕餮"])
        key, _ = room.join("丙")
        room.handle("A", {"t": "chat", "text": "  你好  呀 "})
        clock.now += 1
        room.handle(key, {"t": "chat", "text": "加油"})
        chat = room.state_for("B")["chat"]
        self.assertEqual([(c["who"], c["name"], c["text"]) for c in chat], [("A", "甲", "你好 呀"), ("w", "丙", "加油")])
        room.handle("A", {"t": "chat", "text": "   "})            # 空的不发
        self.assertEqual(len(room.chat), 2)

    def test_long_messages_are_cut_and_fast_ones_refused(self):
        room, clock = room_with(["拳术宗师"], ["饕餮"])
        room.handle("A", {"t": "chat", "text": "啊" * 500})
        self.assertEqual(len(room.chat[-1]["text"]), 200)
        with self.assertRaises(RoomError):
            room.handle("A", {"t": "chat", "text": "再来"})
        clock.now += 1
        room.handle("A", {"t": "chat", "text": "再来"})
        self.assertEqual(room.chat[-1]["text"], "再来")


class Timers(unittest.TestCase):
    def test_choosing_too_slowly_counts_as_a_normal_attack(self):
        room, clock = room_with(["武圣"], ["宋濂"], zei=False)
        self.assertEqual(room.state_for("A")["timers"], {"A": 60.0, "B": 60.0})
        room.handle("A", {"t": "choose", "action": "d1"})
        clock.now += CHOOSE_SECONDS - 1
        self.assertFalse(room.tick())
        self.assertEqual(room.state_for("B")["timers"], {"A": None, "B": 1.0})
        clock.now += 2
        self.assertTrue(room.tick())
        self.assertEqual(room.battle.round, 2)
        self.assertIn("乙选招超时，按【普通攻击】算。", [c["text"] for c in room.chat])
        self.assertTrue(any("B的宋濂使用【普通攻击】" in line for line in room.battle.log))

    def test_a_new_round_gets_a_fresh_clock_plus_time_for_the_animation(self):
        room, clock = room_with(["武圣"], ["宋濂"], zei=False)
        room.handle("A", {"t": "choose", "action": "0"})
        clock.now += 50
        room.handle("B", {"t": "choose", "action": "0"})
        left = room.state_for("A")["timers"]["A"]
        self.assertGreater(left, CHOOSE_SECONDS)                  # 重新算，而且多给了播动画的时间
        self.assertLessEqual(left, CHOOSE_SECONDS + 20)

    def test_throwing_too_slowly_lets_the_computer_throw(self):
        room, clock = room_with(["拳术宗师"], ["饕餮"])
        room.handle("A", {"t": "choose", "action": "22"})
        room.handle("B", {"t": "choose", "action": "3"})
        self.assertEqual(room.state_for("A")["need"], "throw")
        room.handle("A", {"t": "throw", "hand": "石头"})
        clock.now += ZEI_SECONDS + 21
        self.assertTrue(room.tick())
        self.assertIn("乙出拳超时，电脑替他出。", [c["text"] for c in room.chat])
        self.assertFalse(room.throws.get("B"))                    # 这一轮已经结算

    def test_no_timeouts_when_the_host_turns_timers_off(self):
        room, clock = room_with(["武圣"], ["宋濂"], zei=False, timers=False)
        clock.now += 10000
        self.assertFalse(room.tick())
        self.assertEqual(room.state_for("A")["timers"], {"A": None, "B": None})
        self.assertEqual(room.battle.round, 1)

    def test_a_player_who_left_still_times_out_so_the_game_does_not_hang(self):
        room, clock = room_with(["武圣"], ["宋濂"], zei=False)
        room.leave("B")
        room.handle("A", {"t": "choose", "action": "0"})
        clock.now += CHOOSE_SECONDS + 1
        self.assertTrue(room.tick())
        self.assertEqual(room.battle.round, 2)


class TimersWhenNobodyIsThere(unittest.TestCase):
    def test_the_game_waits_when_every_human_has_left(self):
        room, clock = room_with(["武圣"], ["宋濂"], zei=False)
        token = room.seats["A"].token
        room.leave("A")
        room.leave("B")
        clock.now += 10 * CHOOSE_SECONDS
        self.assertFalse(room.tick())
        self.assertEqual(room.battle.round, 1)
        room.join("甲", token)                                    # 回来的人重新计时，不会一回来就被判超时
        room.drive()
        self.assertEqual(room.state_for("A")["timers"]["A"], float(CHOOSE_SECONDS))
        self.assertTrue(room.tick())                              # 乙还没回来，他的时间早就到了
        self.assertIn("乙选招超时，按【普通攻击】算。", [c["text"] for c in room.chat])
        self.assertEqual(room.battle.round, 1)                    # 甲还没选，这一回合还没结算


def bot_game(seed):
    rng = random.Random(seed)
    room = Room("9", rng=random.Random(seed), wall=lambda: 1763400000.0)
    room.join("甲")
    room.handle("A", {"t": "bot"})
    room.handle("A", {"t": "config", "team_size": 2})
    room.handle("A", {"t": "auto", "on": True})
    room.handle("A", {"t": "team", "names": ["拳术宗师", "范仲淹"]})
    for _ in range(3000):
        state = room.state_for("A")
        if state["phase"] == "over":
            break
        if state["need"] == "choose":
            action = rng.choice([a for a in state["actions"] if a["legal"]])
            message = {"t": "choose", "action": action["id"]}
            if action["effect"] == "choose_scene":
                message["destination"] = "地面"
            room.handle("A", message)
        elif state["need"] == "pick":
            room.handle("A", {"t": "pick", "option": state["prompt"]["options"][0]["id"]})
    return room


class Replays(unittest.TestCase):
    def test_a_finished_game_leaves_a_complete_record(self):
        room = bot_game(3)
        record = room.finished
        self.assertEqual(room.phase, "over")
        self.assertEqual(record["names"], {"A": "甲", "B": "电脑"})
        self.assertEqual(record["teams"]["A"], ["拳术宗师", "范仲淹"])
        self.assertEqual(record["winner"], room.battle.winner)
        self.assertEqual(record["events"][-2]["t"], "end")
        self.assertEqual(record["start_view"]["round"], 1)
        json.dumps(record, ensure_ascii=False, allow_nan=False)   # 能原样存成文件
        room.handle("A", {"t": "rematch"})
        self.assertIsNone(room.finished)

    def test_replaying_the_inputs_gives_the_same_game(self):
        for seed in range(6):
            room = bot_game(seed)
            again = rebuild(room.finished)
            self.assertEqual(again.log, room.battle.log, f"seed {seed}")
            self.assertEqual(again.winner, room.battle.winner)

    def test_the_record_replays_the_same_in_another_python_process(self):
        # 另开一个 Python，换一个字符串散列的种子：结果不能依赖集合的遍历顺序。
        room = bot_game(4)
        record = json.loads(json.dumps(room.finished, ensure_ascii=False))
        code = ("import json, sys; sys.path.insert(0, sys.argv[1]); from shai.replay import rebuild; "
                "b = rebuild(json.load(sys.stdin)); print(json.dumps([b.winner, len(b.log), b.log[-3:]]))")
        env = dict(os.environ, PYTHONHASHSEED="12345", PYTHONIOENCODING="utf-8")
        out = subprocess.run([sys.executable, "-c", code, ROOT], input=json.dumps(record), env=env,
                             capture_output=True, text=True, encoding="utf-8", check=True).stdout
        self.assertEqual(json.loads(out), [room.battle.winner, len(room.battle.log), room.battle.log[-3:]])


if __name__ == "__main__":
    unittest.main()
