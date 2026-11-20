"""没打完的对局存盘：记下来、照着搭回来、接着打；以及存盘文件的读写。"""

import json
import os
import random
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import fastapi  # noqa: F401
except ImportError:                                   # 这台电脑把库装在 D:\pylibs
    if os.path.isdir(r"D:\pylibs"):
        sys.path.append(r"D:\pylibs")
    try:
        import fastapi  # noqa: F401
    except ImportError:
        fastapi = None

from server.rooms import CHOOSE_SECONDS, Room  # noqa: E402
from test_step5 import Clock, room_with  # noqa: E402


def played_a_bit():
    """两个真人打了两回合，第三回合甲已经选了、乙还没选。"""
    room, clock = room_with(["武圣", "巫师"], ["宋濂", "饕餮"], zei=False)
    for _ in range(2):
        room.handle("A", {"t": "choose", "action": "0"})
        room.handle("B", {"t": "choose", "action": "0"})
    room.handle("A", {"t": "choose", "action": "0"})
    room.handle("A", {"t": "chat", "text": "等我一下"})
    return room, clock


class SavedGames(unittest.TestCase):
    def test_nothing_to_save_outside_a_battle(self):
        room = Room("1234", rng=random.Random(1))
        room.join("甲")
        self.assertIsNone(room.snapshot())

    def test_a_restored_room_is_where_the_game_stopped(self):
        room, _ = played_a_bit()
        data = json.loads(json.dumps(room.snapshot(), ensure_ascii=False))     # 和写进文件再读回来一样
        back = Room.restore(data, rng=random.Random(2), clock=Clock())
        self.assertEqual(back.phase, "battle")
        self.assertEqual(back.battle.round, 3)
        self.assertEqual(back._plain_view(), room._plain_view())
        self.assertEqual(back.battle.events, room.battle.events)
        self.assertEqual(back._start_view, room._start_view)
        self.assertEqual((back.team_size, back.zei_enabled, back.timers_enabled), (2, False, True))
        self.assertIn("等我一下", [c["text"] for c in back.chat])
        for side in ("A", "B"):                                    # 凭原来的令牌坐回原位
            self.assertEqual(back.join("回来的人", room.seats[side].token)[0], side)
        a, b = back.state_for("A"), back.state_for("B")
        self.assertEqual((a["need"], b["need"]), ("wait", "choose"))          # 甲选过的那一招还在
        self.assertEqual(a["events_from"], 0)                                 # 回来的人从头拿到全部事件
        back.handle("B", {"t": "choose", "action": "0"})
        self.assertEqual(back.battle.round, 4)

    def test_clocks_wait_until_every_human_is_back(self):
        room, _ = played_a_bit()
        clock = Clock()
        back = Room.restore(room.snapshot(), rng=random.Random(2), clock=clock)
        clock.now += 10 * CHOOSE_SECONDS
        self.assertFalse(back.tick())
        back.join("甲", room.seats["A"].token)
        back.drive()
        self.assertEqual(back.state_for("A")["timers"], {"A": None, "B": None})
        clock.now += 10 * CHOOSE_SECONDS
        self.assertFalse(back.tick())
        back.join("乙", room.seats["B"].token)
        back.drive()
        left = back.state_for("B")["timers"]["B"]                  # 从头算，再加上给网页播动画的一点时间
        self.assertTrue(CHOOSE_SECONDS <= left <= CHOOSE_SECONDS + 20, left)
        self.assertEqual(back.battle.round, 3)

    def test_a_save_that_no_longer_matches_the_rules_is_refused(self):
        room, _ = played_a_bit()
        for change in ({"engine_version": "别的版本"}, {"events": 1}, {"tail": {"t": "log", "text": "不是这一句"}},
                       {"history": [{"type": "choose", "side": "A", "action": "没有这个招"}]}):
            with self.assertRaises(ValueError):
                Room.restore(dict(room.snapshot(), **change))

    def test_a_game_against_the_computer_comes_back_too(self):
        clock = Clock()
        room = Room("1234", rng=random.Random(3), clock=clock)
        room.join("甲")
        room.handle("A", {"t": "config", "team_size": 1})
        room.handle("A", {"t": "bot"})
        room.handle("A", {"t": "team", "names": ["武圣"]})
        room.handle("A", {"t": "auto", "on": True})
        room.handle("A", {"t": "choose", "action": "0"})
        back = Room.restore(room.snapshot(), rng=random.Random(4), clock=Clock())
        self.assertTrue(back.seats["B"].is_bot)
        self.assertTrue(back.seats["A"].auto_zei)
        self.assertEqual(back.battle.events, room.battle.events)
        back.join("甲", room.seats["A"].token)
        back.drive()
        self.assertFalse(back._away)                               # 真人只有一个，他回来就接着计时


@unittest.skipIf(fastapi is None, "没有装 fastapi")
class SaveFiles(unittest.TestCase):
    def setUp(self):
        import server.app as app_module
        self.app = app_module
        self.folder = tempfile.TemporaryDirectory()
        self.old, app_module.SAVE_DIR = app_module.SAVE_DIR, self.folder.name
        app_module.rooms.clear()
        app_module.saved_marks.clear()

    def tearDown(self):
        self.app.SAVE_DIR = self.old
        self.app.rooms.clear()
        self.app.saved_marks.clear()
        self.folder.cleanup()

    def test_store_load_and_remove(self):
        room, _ = played_a_bit()
        room.code = "房间一"                                        # 房间号可以是中文
        self.app._store_room(room)
        path = self.app._save_path("房间一")
        self.assertTrue(os.path.isfile(path))
        stamp = os.path.getmtime(path)
        self.app._store_room(room)                                 # 没有变化：不重写
        self.assertEqual(os.path.getmtime(path), stamp)
        back = self.app._open_room("房间一")                         # 内存里没有这个房间：从文件读回来
        self.assertEqual(back.battle.round, 3)
        self.assertIs(self.app._open_room("房间一"), back)
        self.assertEqual(self.app._open_room("别的房间").phase, "lobby")
        back.handle("B", {"t": "choose", "action": "0"})           # 又走了一步：存盘跟着更新
        self.app._store_room(back)
        with open(path, encoding="utf-8") as f:
            self.assertEqual(len(json.load(f)["history"]), len(back.battle.history))
        back.battle = None                                         # 不在对战中了（打完了，或者回到选人物）：存盘删掉
        self.app._store_room(back)
        self.assertFalse(os.path.isfile(path))

    def test_a_broken_save_is_set_aside_and_a_new_game_starts(self):
        room, _ = played_a_bit()
        data = dict(room.snapshot(), events=1)
        os.makedirs(self.folder.name, exist_ok=True)
        with open(self.app._save_path("1234"), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        fresh = self.app._open_room("1234")
        self.assertEqual(fresh.phase, "lobby")
        self.assertTrue(any("旧规则" in c["text"] for c in fresh.chat))
        self.assertTrue(os.path.isfile(self.app._save_path("1234") + ".bad"))


if __name__ == "__main__":
    unittest.main()
