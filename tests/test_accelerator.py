"""粒子加速器（本子 ⑩）：造 10 下可以打，再造 10 下更强。"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from shai import Battle  # noqa: E402
from test_battle import legal, play  # noqa: E402

BUILD, FIRE = "sys_build_accelerator", "sys_fire_accelerator"


class Accelerator(unittest.TestCase):
    def test_ten_builds_then_it_fires(self):
        b = Battle(["范仲淹"], ["武圣"], seed=1, true_body=False)
        for _ in range(9):
            play(b, BUILD, "d1")
        self.assertFalse(legal(b, "A")[FIRE]["legal"])
        play(b, BUILD, "d1")
        self.assertEqual(b.fighter("A").devices["粒子加速器"], 10)
        self.assertTrue(legal(b, "A")[FIRE]["legal"])
        self.assertEqual(legal(b, "A")[FIRE]["damage"], 30000)
        play(b, FIRE, "d1")
        self.assertEqual(b.fighter("B").hp, 100000 - 30000)
        self.assertEqual(b.fighter("B").radiation, 3)

    def test_twenty_builds_hit_harder_and_reach_any_scene(self):
        b = Battle(["范仲淹"], ["武圣"], seed=1, true_body=False)
        b.fighter("A").devices["粒子加速器"] = 10
        b.fighter("B").scene = "外太空"
        self.assertFalse(legal(b, "A")[FIRE]["legal"])              # 小的打不到那么远
        b.fighter("A").devices["粒子加速器"] = 19
        play(b, BUILD, "d1")
        self.assertFalse(legal(b, "A")[BUILD]["legal"])             # 造到头了
        play(b, FIRE, "d1")
        self.assertEqual(b.fighter("B").hp, 100000 - 50000)
        self.assertEqual(b.fighter("B").radiation, 5)

    def test_it_stays_with_the_fighter_after_losing_a_life(self):
        b = Battle(["武圣"], ["欧阳修"], seed=1, true_body=False)
        a = b.fighter("A")
        a.devices["粒子加速器"] = 10
        a.hp = 1
        play(b, "d2", "0")
        a = b.fighter("A")
        self.assertEqual(a.lives_remaining, 1)
        self.assertEqual(a.devices["粒子加速器"], 10)


if __name__ == "__main__":
    unittest.main()
