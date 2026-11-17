"""战报和回放文件：存下来、列出来、取回来。需要装了 fastapi 才跑。"""

import json
import os
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

from test_step5 import bot_game  # noqa: E402


@unittest.skipIf(fastapi is None, "没有装 fastapi")
class ReplayFiles(unittest.TestCase):
    def setUp(self):
        import server.app as app_module
        self.app = app_module
        self.folder = tempfile.TemporaryDirectory()
        self.old, app_module.REPLAY_DIR = app_module.REPLAY_DIR, self.folder.name

    def tearDown(self):
        self.app.REPLAY_DIR = self.old
        self.folder.cleanup()

    def test_save_list_and_fetch(self):
        room = bot_game(3)
        replay_id = self.app.save_replay(room.finished)
        second = self.app.save_replay(room.finished)              # 同一秒同一个房间：编号不能撞
        self.assertNotEqual(replay_id, second)
        with open(os.path.join(self.folder.name, replay_id + ".json"), encoding="utf-8") as f:
            record = json.load(f)
        self.assertEqual(record["id"], replay_id)
        self.assertEqual(record["events"][-2]["t"], "end")
        with open(os.path.join(self.folder.name, replay_id + ".txt"), encoding="utf-8") as f:
            text = f.read()
        self.assertIn("《晒》对战战报", text)
        self.assertIn("A：甲（拳术宗师、范仲淹）", text)
        self.assertIn("对战结束", text)
        listed = self.app.list_replays()
        self.assertEqual([item["id"] for item in listed], [second, replay_id])   # 新的在前
        self.assertNotIn("events", listed[0])                    # 目录里只有摘要
        self.assertTrue(self.app.get_replay(replay_id).path.endswith(replay_id + ".json"))
        self.assertTrue(self.app.get_replay_log(replay_id).path.endswith(replay_id + ".txt"))

    def test_bad_ids_are_refused(self):
        from fastapi import HTTPException
        for bad in ("../secrets", "a/b", "", "不存在", "x" * 80, "20260101-000000-0000"):
            with self.assertRaises(HTTPException):
                self.app.get_replay(bad)

    def test_room_gets_its_replay_id_once(self):
        room = bot_game(5)
        self.app._save_if_finished(room)
        first = room.replay_id
        self.assertTrue(first)
        self.app._save_if_finished(room)
        self.assertEqual(room.replay_id, first)
        self.assertEqual(len(self.app.list_replays()), 1)
        self.assertEqual(room.state_for("A")["replay_id"], first)


if __name__ == "__main__":
    unittest.main()
