"""网页客户端的冒烟测试：开一局真的对局，把服务器发给玩家的局面交给网页的代码，看每张招式卡和每个描述框都拼得出来。

网页的代码在 Node 里跑（见 ``tests/client_check.js``），页面是假的。电脑上没有 Node 的话这个测试跳过。
"""

import json
import os
import shutil
import subprocess
import tempfile
import unittest

from server.rooms import Room
from shai.describe import codex

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NODE = shutil.which("node") or (r"C:\Program Files\nodejs\node.exe" if os.path.exists(r"C:\Program Files\nodejs\node.exe") else None)


@unittest.skipUnless(NODE, "没有 Node，跳过网页客户端的测试")
class ClientSmokeTests(unittest.TestCase):
    def test_every_card_and_tooltip_builds(self):
        room = Room("1")
        key, _ = room.join("甲", None)
        room.handle(key, {"t": "bot"})
        room.handle(key, {"t": "config", "team_size": 3, "timers": False})
        room.handle(key, {"t": "team", "names": ["武圣", "巫师", "埃及法老"]})
        room.drive()
        state = room.state_for(key)
        self.assertEqual(state["need"], "choose")
        payload = {"state": state, "codex": codex(), "art": {"characters": ["武圣"], "defense": ["d1", "d2", "d3", "d4", "dhands", "dinf"]}}
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "state.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False)
            done = subprocess.run([NODE, os.path.join(ROOT, "tests", "client_check.js"), path],
                                  capture_output=True, text=True, encoding="utf-8", timeout=60)
        self.assertEqual(done.returncode, 0, done.stderr)
        result = json.loads(done.stdout.strip().splitlines()[-1])
        self.assertEqual(result["problems"], [])
        self.assertGreater(result["cards"], 80)


if __name__ == "__main__":
    unittest.main()
