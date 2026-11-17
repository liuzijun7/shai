"""进化和衰变的测试。"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from shai import Battle  # noqa: E402
from test_battle import play  # noqa: E402


def quiet(fighter):
    """把内功清掉，免得放射性、昏沉大法这些搅进来。"""
    fighter.inner = {}
    fighter.initial_inner = {}


class TimedForms(unittest.TestCase):
    def test_biochemist_evolves_after_ten_turns_on_the_field(self):
        b = Battle(["生化大师"], ["欧阳修"], seed=1, true_body=False)
        quiet(b.fighter("A"))
        b.fighter("A").hp = 30000
        for _ in range(9):
            play(b, "d1", "d1")
        self.assertEqual(b.fighter("A").name, "生化大师")
        play(b, "d1", "d1")
        a = b.fighter("A")
        self.assertEqual(a.name, "猪带小天王")
        self.assertEqual(a.hp, 200000)                      # 进化以后体力按新形态回满
        self.assertEqual(a.inner["幸运"], 2)                # 内功换成新形态的
        self.assertIn("生化大师进化成猪带小天王", "".join(b.log))

    def test_turns_off_the_field_do_not_count(self):
        b = Battle(["生化大师", "武圣"], ["宋濂"], seed=1, true_body=False)
        quiet(b.fighter("A"))
        quiet(b.fighter("B"))
        play(b, "d1", "d1")
        play(b, "switch:1", "d1")
        for _ in range(12):
            play(b, "d1", "d1")
        waiting = b.players["A"].team[0]
        self.assertEqual(waiting.name, "生化大师")
        self.assertEqual(waiting.counters["form_turns"], 1)

    def test_second_evolution_after_twenty_more_turns(self):
        b = Battle(["猪带小天王"], ["欧阳修"], seed=1, true_body=False)
        quiet(b.fighter("A"))
        b.fighter("A").counters["form_turns"] = 19
        play(b, "d1", "d1")
        self.assertEqual(b.fighter("A").name, "蚂蟥大仙")
        self.assertEqual(b.fighter("A").inner["重贼"], 2)

    def test_first_decay_fires_a_gamma_ray(self):
        b = Battle(["蚂蟥大仙"], ["欧阳修"], seed=1, true_body=False)
        quiet(b.fighter("A"))
        b.fighter("A").counters["form_turns"] = 9
        play(b, "d1", "d1")
        self.assertEqual(b.fighter("A").name, "猪带小天王")
        self.assertTrue(b.fighter("B").defeated)            # γ 射线一次累计 15 次辐射
        self.assertEqual(b.winner, "A")

    def test_gamma_ray_does_not_hurt_the_radiation_immune(self):
        b = Battle(["蚂蟥大仙"], ["纵目青铜怪"], seed=1, true_body=False)
        quiet(b.fighter("A"))
        b.fighter("A").counters["form_turns"] = 9
        play(b, "d1", "d1", zei="B")                        # 臭伽马没出
        self.assertEqual(b.fighter("A").name, "猪带小天王")
        self.assertFalse(b.fighter("B").defeated)
        self.assertEqual(b.fighter("B").radiation, 0)

    def test_second_decay_fires_a_beta_ray_and_then_evolution_starts_over(self):
        b = Battle(["蚂蟥大仙"], ["纵目青铜怪", "武圣"], seed=1, true_body=False)
        quiet(b.fighter("A"))
        b.fighter("A").counters["form_turns"] = 9
        play(b, "d1", "d1", zei="B")
        quiet(b.fighter("A"))                                # 衰变以后内功换成了新形态自带的，再清一次
        play(b, "d1", "switch:1")
        a = b.fighter("A")
        a.hp = 150000
        for _ in range(8):
            play(b, "d1", "d1")
        self.assertEqual(b.fighter("A").name, "猪带小天王")   # 衰变下来的，不会再往上进化
        play(b, "d1", "d1")
        a, foe = b.fighter("A"), b.fighter("B")
        self.assertEqual(a.name, "生化大师")
        self.assertEqual(a.hp, 100000)                       # 衰变不回血，超过新上限的部分去掉
        self.assertEqual(foe.hp, 100000 - 30000)             # β 射线：扣 30%
        self.assertIn("B的武圣受到2点辐射，累计2/15。", b.log)   # 累计辐射 2 次
        quiet(b.fighter("A"))
        for _ in range(10):
            play(b, "d1", "d1")
        self.assertEqual(b.fighter("A").name, "猪带小天王")   # 衰变以后可以再进化
        self.assertFalse(b.fighter("A").counters["decayed"])


class GluttonForms(unittest.TestCase):
    def test_glutton_evolves_at_five_lives(self):
        b = Battle(["饕餮"], ["欧阳修"], seed=1, true_body=False)
        a = b.fighter("A")
        a.lives_total = a.lives_remaining = 4
        play(b, "d1", "d1")
        self.assertEqual(b.fighter("A").name, "饕餮")
        a = b.fighter("A")
        a.lives_total = a.lives_remaining = 5
        a.hp = 1000
        play(b, "d1", "d1")
        a = b.fighter("A")
        self.assertEqual((a.name, a.hp, a.lives_remaining), ("肥饕餮", 300000, 5))

    def test_fat_glutton_decays_below_five_lives(self):
        b = Battle(["肥饕餮"], ["欧阳修"], seed=1, true_body=False)
        a = b.fighter("A")
        a.inner = {}
        a.initial_inner = {}
        a.lives_total = a.lives_remaining = 5
        play(b, "d1", "d1")
        self.assertEqual(b.fighter("A").name, "肥饕餮")
        b.fighter("A").lives_remaining = 4
        play(b, "d1", "d1")
        a, foe = b.fighter("A"), b.fighter("B")
        self.assertEqual((a.name, a.hp, a.max_hp), ("饕餮", 150000, 150000))
        self.assertEqual(a.inner.get("大难不死"), 3)         # 内功退回饕餮自带的
        self.assertEqual(foe.hp, 300000 - 90000)
        self.assertEqual(foe.radiation, 2)


if __name__ == "__main__":
    unittest.main()
