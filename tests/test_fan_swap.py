"""范仲淹的换人：和对面场上的人物互换。"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from shai import Battle  # noqa: E402
from shai.model import Parasite  # noqa: E402
from test_battle import legal, play  # noqa: E402


class FanSwap(unittest.TestCase):
    def test_the_two_fighters_change_sides_with_everything_they_have(self):
        b = Battle(["范仲淹"], ["拳术宗师"], seed=1, true_body=False)
        b.fighter("B").hp = 60000
        b.fighter("B").learn_progress["幸运"] = 5                   # 对面的玩家学了幸运 1 级
        play(b, "t7", "d2")
        mine, theirs = b.fighter("A"), b.fighter("B")
        self.assertEqual((mine.name, mine.side, mine.hp), ("拳术宗师", "A", 60000))
        self.assertEqual(mine.inner["蛮力"], 3)                     # 内功跟着人物过来
        self.assertEqual(mine.inner_level("幸运"), 0)               # 学来的内功归玩家，不跟着人物过来
        self.assertEqual(theirs.inner_level("幸运"), 1)             # 换过去的范仲淹用上了那个玩家学的内功
        self.assertEqual((theirs.name, theirs.side, theirs.hp), ("范仲淹", "B", 100000))
        self.assertIn("t7", [a["id"] for a in b.legal_actions("B")])   # 对面现在可以用范仲淹的招
        self.assertNotIn("t7", [a["id"] for a in b.legal_actions("A")])

    def test_it_goes_before_everything_and_the_other_move_is_made_by_the_new_fighter(self):
        b = Battle(["范仲淹"], ["拳术宗师"], seed=1, true_body=False)
        play(b, "t7", "0", zei="A")
        # 对面选的普通攻击改由换过去的范仲淹来打，打在换过来的拳术宗师身上（铁布衫 3：只受一半）
        self.assertEqual(b.fighter("A").name, "拳术宗师")
        self.assertEqual(b.fighter("A").hp, 100000 - 5000)
        self.assertEqual(b.fighter("B").hp, 100000)

    def test_a_move_the_new_fighter_cannot_use_is_void(self):
        b = Battle(["范仲淹"], ["饕餮"], seed=1, true_body=False)
        play(b, "t7", "t1")                                        # 饕餮牙是饕餮的专属招
        self.assertEqual(b.fighter("A").name, "饕餮")
        self.assertEqual(b.fighter("A").hp, 150000)
        self.assertTrue(any("出不了" in line for line in b.log))

    def test_defense_one_blocks_it(self):
        b = Battle(["范仲淹"], ["拳术宗师"], seed=1, true_body=False)
        play(b, "t7", "d1")
        self.assertEqual(b.fighter("A").name, "范仲淹")
        self.assertEqual(b.fighter("B").name, "拳术宗师")

    def test_ordinary_switch_happens_after_it(self):
        b = Battle(["范仲淹"], ["武圣", "拳术宗师"], seed=1, true_body=False)
        play(b, "t7", "switch:1")
        self.assertEqual(b.fighter("A").name, "武圣")              # 换走的是对面当时在场上的人物
        self.assertEqual(b.fighter("B").name, "拳术宗师")
        self.assertEqual(b.players["B"].team[0].name, "范仲淹")    # 范仲淹到了对面，被换到场下

    def test_parasites_keep_pointing_at_the_right_fighter(self):
        b = Battle(["范仲淹"], ["武圣"], seed=1, true_body=False)
        b.fighter("B").parasites["蚂蟥"] = Parasite("蚂蟥", 1, "A")   # 范仲淹放在武圣身上的虫
        play(b, "t7", "d2")
        self.assertEqual(b.fighter("A").name, "武圣")
        self.assertEqual(b.fighter("A").parasites["蚂蟥"].source, "B")   # 还是算范仲淹的
        self.assertEqual(b.fighter("A").hp, 100000 - 20000)
        self.assertEqual(b.fighter("B").hp, 100000)                # 范仲淹满血，吸到的血加不上去

    def test_cannot_take_the_true_body(self):
        b = Battle(["范仲淹"], ["武圣"], seed=1)
        foe = b.fighter("B")
        foe.lives_remaining = 1
        foe.hp = 1
        play(b, "0", "d2")
        self.assertTrue(b.fighter("B").is_true_body)
        self.assertFalse(legal(b, "A")["t7"]["legal"])


if __name__ == "__main__":
    unittest.main()
