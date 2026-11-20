"""房间逻辑的测试（不经过网络）。"""

import os
import random
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server.rooms import Room, RoomError  # noqa: E402


def two_player_room(team_a, team_b, zei=True):
    room = Room("1234", rng=random.Random(1))
    room.join("甲")
    room.join("乙")
    room.handle("A", {"t": "config", "team_size": len(team_a), "zei": zei})
    room.handle("A", {"t": "team", "names": team_a})
    room.handle("B", {"t": "team", "names": team_b})
    return room


class RoomTests(unittest.TestCase):
    def test_battle_starts_when_both_teams_are_in_and_bench_is_hidden(self):
        room = two_player_room(["拳术宗师", "巫师"], ["饕餮", "牛顿"])
        self.assertEqual(room.phase, "battle")
        state = room.state_for("A")
        self.assertEqual(state["need"], "choose")
        self.assertTrue(any(a["id"] == "0" and a["legal"] for a in state["actions"]))
        foe_team = state["view"]["players"]["B"]["team"]
        self.assertEqual(foe_team[0]["name"], "饕餮")
        self.assertTrue(foe_team[1]["hidden"])            # 对手没上场的人物看不到
        self.assertEqual(state["view"]["players"]["A"]["team"][1]["name"], "巫师")
        self.assertNotIn("pending", state["view"])

    def test_opponent_choice_is_not_revealed_before_resolution(self):
        room = two_player_room(["拳术宗师"], ["饕餮"])
        room.state_for("B")
        room.handle("A", {"t": "choose", "action": "4"})
        state = room.state_for("B")
        self.assertEqual(state["view"]["chosen"], {"A": True, "B": False})
        self.assertEqual(state["events"], [])
        self.assertEqual(state["need"], "choose")

    def test_zei_round_trip(self):
        room = two_player_room(["拳术宗师"], ["饕餮"])
        room.handle("A", {"t": "choose", "action": "22"})   # 摄魂点穴手
        room.handle("B", {"t": "choose", "action": "3"})    # 点穴手（魔法）：两边互相都能封住对方，要贼先后手
        a, b = room.state_for("A"), room.state_for("B")
        self.assertEqual((a["need"], b["need"]), ("throw", "throw"))
        self.assertEqual(a["prompt"]["choices"]["B"]["name"], "点穴手")   # 贼之前双方的招已经亮出来
        room.handle("A", {"t": "throw", "hand": "石头"})
        self.assertEqual(room.state_for("A")["need"], "wait")
        self.assertEqual(room.state_for("B")["prompt"]["rounds"], [])      # 对手出了什么还看不到
        with self.assertRaises(RoomError):
            room.handle("A", {"t": "throw", "hand": "布"})
        room.handle("B", {"t": "throw", "hand": "石头"})    # 打平，重来
        self.assertEqual(room.state_for("B")["prompt"]["rounds"], [{"A": "石头", "B": "石头"}])
        room.handle("A", {"t": "throw", "hand": "布"})
        room.handle("B", {"t": "throw", "hand": "石头"})    # A 赢
        state = room.state_for("A")
        self.assertEqual(state["need"], "choose")
        self.assertEqual(state["last_zei"]["winner"], "A")
        self.assertEqual(state["view"]["round"], 2)
        self.assertEqual(state["view"]["players"]["A"]["team"][0]["hp"], 100000)   # 狮子吼被憋回去

    def test_events_are_sent_once_and_resent_after_reconnect(self):
        room = two_player_room(["拳术宗师"], ["饕餮"])
        first = room.state_for("A")
        self.assertGreater(len(first["events"]), 0)
        self.assertEqual(room.state_for("A")["events"], [])
        token = room.seats["A"].token
        room.leave("A")
        side, _ = room.join("甲", token)
        self.assertEqual(side, "A")
        self.assertEqual(room.state_for("A")["events"], first["events"])

    def test_room_is_full_and_only_host_configures(self):
        room = Room("1", rng=random.Random(1))
        room.join("甲")
        room.join("乙")
        self.assertTrue(room.join("丙")[0].startswith("w:"))      # 两个座位都有人：第三个人自动观战
        with self.assertRaises(RoomError):
            room.handle("B", {"t": "config", "team_size": 2})
        with self.assertRaises(RoomError):
            room.handle("A", {"t": "team", "names": ["拳术宗师"]})   # 人数不对

    def test_full_game_against_the_bot(self):
        for seed in range(20):
            rng = random.Random(seed)
            room = Room("9", rng=random.Random(seed))
            room.join("甲")
            room.handle("A", {"t": "bot"})
            room.handle("A", {"t": "config", "team_size": 2})
            room.handle("A", {"t": "auto", "on": True})
            room.handle("A", {"t": "team", "names": ["拳术宗师", "巫师"]})
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
                else:
                    self.fail(f"卡在 {state['need']}")
            self.assertEqual(room.phase, "over", f"seed {seed}")
            room.handle("A", {"t": "rematch"})
            self.assertEqual(room.phase, "lobby")


    def test_fan_swap_reaches_both_screens(self):
        room = two_player_room(["范仲淹"], ["拳术宗师"], zei=False)
        room.state_for("A")
        room.state_for("B")
        room.handle("A", {"t": "choose", "action": "t7"})
        room.handle("B", {"t": "choose", "action": "d2"})
        for side in ("A", "B"):
            state = room.state_for(side)
            self.assertEqual(state["view"]["players"]["A"]["team"][0]["name"], "拳术宗师")
            self.assertEqual(state["view"]["players"]["B"]["team"][0]["name"], "范仲淹")
            swap = [e for e in state["events"] if e["t"] == "swap_fighters"][0]
            self.assertEqual(swap["fighters"]["A"]["name"], "拳术宗师")
        actions = {a["id"] for a in room.state_for("B")["actions"]}
        self.assertIn("t7", actions)                       # 范仲淹到了乙这边，换人这个招也跟着过去


if __name__ == "__main__":
    unittest.main()
