"""新引擎的测试。在仓库根目录运行：python -m unittest discover -s tests -v"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shai import Battle, RuleError  # noqa: E402
from shai.model import Status  # noqa: E402


def settle(battle, zei="A", pick=0):
    """把所有待决定的问题答掉：贼一律让 ``zei`` 赢，选择一律选第 ``pick`` 个。"""
    while battle.pending:
        if battle.pending["kind"] == "zei":
            battle.answer(zei)
        else:
            battle.answer(battle.pending["options"][pick]["id"])


def play(battle, a, b, zei="A"):
    battle.choose("A", a)
    battle.choose("B", b)
    settle(battle, zei)


def legal(battle, side):
    return {x["id"]: x for x in battle.legal_actions(side)}


class BasicRules(unittest.TestCase):
    """刘同学原来的测试对应的规则，搬到新引擎上再核对一遍。"""

    def test_normal_attack_resolves_after_both_choose(self):
        b = Battle(["欧阳修"], ["武圣"], seed=1, true_body=False)
        b.choose("A", "0")
        self.assertEqual(b.fighter("B").hp, 100000)     # 双方都选完才结算
        b.choose("B", "d2")
        self.assertEqual(b.fighter("B").hp, 90000)

    def test_shield_takes_damage_without_overflow(self):
        b = Battle(["欧阳修"], ["巫师"], seed=1, true_body=False)
        b.fighter("B").shield = 5000
        play(b, "0", "d2")
        self.assertEqual(b.fighter("B").shield, 0)
        self.assertEqual(b.fighter("B").hp, 50000)

    def test_sealed_attribute_is_illegal_but_normal_attack_remains(self):
        b = Battle(["欧阳修"], ["武圣"], seed=1, true_body=False)
        b.fighter("A").statuses["封物"] = Status("封物", 3, "B", fresh=False)
        self.assertFalse(legal(b, "A")["3"]["legal"])
        self.assertTrue(legal(b, "A")["0"]["legal"])

    def test_iron_shirt_halves_damage(self):
        b = Battle(["欧阳修"], ["拳术宗师"], seed=1, true_body=False)
        play(b, "0", "d2")
        self.assertEqual(b.fighter("B").hp, 95000)

    def test_sleep_does_not_refresh_but_other_status_takes_longest(self):
        b = Battle(["欧阳修"], ["武圣"], seed=1, true_body=False)
        target = b.fighter("B")
        b.apply_status(target, "昏睡", 1, "A", force_body=True)
        b.apply_status(target, "昏睡", 5, "A", force_body=True)
        self.assertEqual(target.statuses["昏睡"].turns, 1)
        b.apply_status(target, "烧伤", 2, "A", force_body=True)
        b.apply_status(target, "烧伤", 5, "A", force_body=True)
        self.assertEqual(target.statuses["烧伤"].turns, 5)

    def test_radiation_kills_all_lives(self):
        b = Battle(["欧阳修"], ["宋濂"], seed=1, true_body=False)
        b.add_radiation(b.fighter("B"), 15, "A", "测试辐射")
        self.assertTrue(b.fighter("B").defeated)
        self.assertEqual(b.fighter("B").lives_remaining, 0)

    def test_radiation_immunity(self):
        b = Battle(["欧阳修"], ["纵目青铜怪"], seed=1, true_body=False)
        b.add_radiation(b.fighter("B"), 15, "A", "测试辐射")
        self.assertEqual(b.fighter("B").radiation, 0)
        self.assertFalse(b.fighter("B").defeated)

    def test_range_uses_height_gap(self):
        b = Battle(["拳术宗师"], ["武圣"], seed=1, true_body=False)
        b.fighter("B").scene = "宇宙"
        self.assertFalse(legal(b, "A")["0"]["legal"])
        self.assertTrue(legal(b, "A")["6"]["legal"])

    def test_lost_life_resets_state(self):
        b = Battle(["拳术宗师"], ["宋濂"], seed=2, true_body=False)
        target = b.fighter("B")
        target.hp = 1
        target.resources["星体能量"] = 7
        target.statuses["烧伤"] = Status("烧伤", 3, "A")
        play(b, "0", "d2")
        target = b.fighter("B")     # 结算会重建人物对象，要重新取
        self.assertEqual(target.lives_remaining, 2)
        self.assertEqual(target.hp, target.max_hp)
        self.assertEqual(target.resources["星体能量"], 0)
        self.assertNotIn("烧伤", target.statuses)

    def test_wu_sheng_has_two_lives(self):
        b = Battle(["武圣"], ["欧阳修"], seed=1, true_body=False)
        self.assertEqual(b.fighter("A").lives_total, 2)


class OrderAndZei(unittest.TestCase):
    def test_no_zei_when_order_does_not_matter(self):
        b = Battle(["拳术宗师"], ["饕餮"], seed=1, true_body=False)
        b.choose("A", "0")
        b.choose("B", "0")
        self.assertIsNone(b.pending)
        self.assertEqual(b.fighter("B").hp, 150000 - 15000)   # 蛮力 3：加 50%
        self.assertEqual(b.fighter("A").hp, 100000 - 5000)    # 铁布衫 3：只受一半

    def test_zei_decides_order_and_sealed_move_is_cancelled(self):
        b = Battle(["拳术宗师"], ["饕餮"], seed=1, true_body=False)
        b.choose("A", "4")          # 摄魂大法：封魔
        b.choose("B", "5")          # 狮子吼：魔法
        self.assertEqual(b.pending["kind"], "zei")
        self.assertEqual(b.pending["purpose"], "order")
        self.assertEqual(sorted(b.pending["askers"]), ["A", "B"])
        b.answer("A")               # A 贼赢，A 先出手
        self.assertTrue(b.fighter("B").has_status("封魔"))
        self.assertEqual(b.fighter("A").hp, 100000)           # 狮子吼被憋回去，完全作废

    def test_zei_loser_seal_lands_after_the_attack(self):
        b = Battle(["拳术宗师"], ["饕餮"], seed=1, true_body=False)
        play(b, "4", "5", zei="B")
        self.assertEqual(b.fighter("A").hp, 100000 - 7500)
        self.assertTrue(b.fighter("B").has_status("封魔"))

    def test_shen_goes_before_normal_move_without_zei(self):
        b = Battle(["欧阳修"], ["饕餮"], seed=1, true_body=False)
        b.choose("A", "32")         # 惊天混元掌：神技
        b.choose("B", "0")
        self.assertIsNone(b.pending)
        self.assertIn("A先出手。", b.log)

    def test_unblockable_signature_is_not_cancelled(self):
        b = Battle(["拳术宗师"], ["牛顿"], seed=1, true_body=False)
        b.fighter("B").shield = 0
        play(b, "3", "2", zei="A")  # 点穴手封物理；牛顿的麒麟芒星是物理，但牛顿的大招憋不回去
        self.assertLess(b.fighter("A").hp, 100000)

    def test_chance_mapping(self):
        b = Battle(["欧阳修"], ["饕餮"], seed=1, true_body=False)

        def chance(p, answers):
            b._decisions = [{"kind": "zei", "value": v} for v in answers]
            b._cursor = 0
            return b._chance(p, "A", "测试")

        self.assertTrue(chance(1 / 3, ["A"]))
        self.assertFalse(chance(1 / 3, [None]))
        self.assertTrue(chance(2 / 3, [None]))
        self.assertFalse(chance(2 / 3, ["B"]))
        self.assertTrue(chance(0.5, ["A"]))
        self.assertTrue(chance(0.25, ["A", "A"]))
        self.assertFalse(chance(0.25, ["A", "B"]))
        self.assertTrue(chance(0.125, ["A", "A", "A"]))
        self.assertFalse(chance(0.125, ["B"]))
        b._decisions, b._cursor = [], 0

    def test_dodge_is_decided_by_zei(self):
        b = Battle(["欧阳修"], ["陶渊明"], seed=1, true_body=False)
        b.choose("A", "0")
        b.choose("B", "d2")
        self.assertEqual(b.pending["purpose"], "chance")
        b.answer("B")               # 陶渊明贼赢：闪避成功
        self.assertEqual(b.fighter("B").hp, 150000)

    def test_zei_can_be_switched_off(self):
        b = Battle(["拳术宗师"], ["陶渊明"], seed=3, zei=False, true_body=False)
        for _ in range(5):
            if b.done:
                break
            b.choose("A", "0")
            b.choose("B", "0")
            self.assertIsNone(b.pending)

    def test_same_inputs_give_same_battle(self):
        def run():
            b = Battle(["拳术宗师", "欧阳修"], ["饕餮", "巫师"], seed=7)
            play(b, "4", "5", zei="B")
            play(b, "0", "1", zei="A")
            play(b, "switch:1", "0", zei="A")
            return b.log
        self.assertEqual(run(), run())


class ShenRules(unittest.TestCase):
    def test_stifled_shen_does_nothing_and_is_not_used_up(self):
        b = Battle(["欧阳修"], ["饕餮"], seed=1, true_body=False)
        play(b, "32", "ds")
        self.assertEqual(b.fighter("B").hp, 150000)
        self.assertTrue(b.fighter("A").has_status("封神"))
        self.assertNotIn("32", b.fighter("A").used_shen)

    def test_shen_once_per_life(self):
        b = Battle(["欧阳修"], ["饕餮"], seed=1, true_body=False)
        play(b, "32", "0")
        self.assertIn("32", b.fighter("A").used_shen)
        self.assertFalse(legal(b, "A")["32"]["legal"])
        self.assertTrue(legal(b, "A")["33"]["legal"])

    def test_wizard_shen_is_unlimited(self):
        b = Battle(["巫师"], ["欧阳修"], seed=1, true_body=False)   # 欧阳修血厚，挨得住幻影的四连击
        play(b, "33", "d1")
        self.assertTrue(legal(b, "A")["33"]["legal"])


class Teams(unittest.TestCase):
    def test_switch_takes_the_turn_and_goes_first(self):
        b = Battle(["拳术宗师", "饕餮"], ["欧阳修"], seed=1, true_body=False)
        play(b, "switch:1", "0")
        self.assertEqual(b.fighter("A").name, "饕餮")
        self.assertEqual(b.fighter("A").hp, 150000 - 10000)   # 对手的招打在新上场的人物身上
        self.assertEqual(b.players["A"].team[0].hp, 100000)

    def test_bad_statuses_vanish_when_leaving_and_scene_is_inherited(self):
        b = Battle(["拳术宗师", "饕餮"], ["欧阳修"], seed=1, true_body=False)
        old = b.fighter("A")
        old.statuses["封物"] = Status("封物", 4, "B", fresh=False)
        old.scene = "南极"
        play(b, "switch:1", "d1")
        old = b.players["A"].team[0]
        self.assertNotIn("封物", old.statuses)
        self.assertEqual(b.fighter("A").scene, "南极")

    def test_fallen_fighter_is_replaced_by_player_choice(self):
        b = Battle(["拳术宗师", "饕餮", "巫师"], ["欧阳修"], seed=1, true_body=False)
        b.fighter("A").hp = 1
        b.choose("A", "d1")
        b.choose("B", "0")
        self.assertEqual(b.pending["kind"], "choose")
        self.assertEqual(b.pending["askers"], ["A"])
        self.assertEqual([o["name"] for o in b.pending["options"]], ["饕餮", "巫师"])
        b.answer("2")
        self.assertEqual(b.fighter("A").name, "巫师")
        self.assertFalse(b.done)

    def test_single_replacement_needs_no_question(self):
        b = Battle(["拳术宗师", "饕餮"], ["欧阳修"], seed=1, true_body=False)
        b.fighter("A").hp = 1
        play(b, "d1", "0")
        self.assertEqual(b.fighter("A").name, "饕餮")

    def test_true_body_enters_last_and_battle_ends_after_it(self):
        b = Battle(["拳术宗师"], ["饕餮"], seed=1)
        b.fighter("A").hp = 1
        play(b, "d1", "0")
        self.assertEqual(b.fighter("A").name, "超级真身")
        self.assertFalse(b.done)
        body = b.fighter("A")
        body.hp = 1
        body.inner = {}             # 去掉闪避和大难不死，让这一下一定打死
        play(b, "d1", "0")
        self.assertTrue(b.done)
        self.assertEqual(b.winner, "B")

    def test_cannot_choose_twice_or_while_waiting(self):
        b = Battle(["拳术宗师"], ["饕餮"], seed=1, true_body=False)
        b.choose("A", "4")
        with self.assertRaises(RuleError):
            b.choose("A", "0")
        b.choose("B", "5")
        self.assertIsNotNone(b.pending)
        with self.assertRaises(RuleError):
            b.choose("A", "0")


class Scenes(unittest.TestCase):
    def test_ground_is_under_water_after_first_flood(self):
        b = Battle(["范仲淹"], ["拳术宗师"], seed=1, true_body=False)
        play(b, "8", "d1")          # 范仲淹的洪水 8 万；拳术宗师铁布衫 3 只受一半
        self.assertEqual(b.water_level, 0)
        self.assertEqual(b.fighter("B").hp, 100000 - 40000 - 10000)   # 再扣 10% 水压

    def test_heal_before_burn_at_end_of_turn(self):
        b = Battle(["欧阳修"], ["饕餮"], seed=1, true_body=False)
        f = b.fighter("B")
        f.hp = 5000
        f.inner["生机勃勃"] = 2      # 回 20%
        f.statuses["烧伤"] = Status("烧伤", 3, "A", fresh=False)   # 扣 10%
        play(b, "d1", "d1")
        f = b.fighter("B")
        self.assertFalse(f.defeated)
        self.assertEqual(f.hp, 5000 + 30000 - 15000)


if __name__ == "__main__":
    unittest.main()


class ZeiMiniGame(unittest.TestCase):
    def test_decisive_draw_repeats_then_winner(self):
        from shai.zei import ZeiGame
        game = ZeiGame({"sides": ["A", "B"], "mode": "decisive", "rezei": {"A": 0, "B": 0}})
        self.assertEqual(game.throw({"A": "石头", "B": "石头"}), "again")
        self.assertEqual(game.throw({"A": "石头", "B": "剪刀"}), "done")
        self.assertEqual(game.winner, "A")

    def test_single_draw_ends_with_no_winner(self):
        from shai.zei import ZeiGame
        game = ZeiGame({"sides": ["A", "B"], "mode": "single", "rezei": {}})
        self.assertEqual(game.throw({"A": "布", "B": "布"}), "done")
        self.assertIsNone(game.winner)

    def test_loser_with_rezei_may_throw_again(self):
        from shai.zei import ZeiGame
        game = ZeiGame({"sides": ["A", "B"], "mode": "decisive", "rezei": {"A": 0, "B": 1}})
        self.assertEqual(game.throw({"A": "石头", "B": "剪刀"}), "redo?")
        self.assertEqual(game.redo_side, "B")
        self.assertTrue(game.redo(True))
        self.assertEqual(game.throw({"A": "石头", "B": "布"}), "done")   # A 没有重贼，输了就是输了
        self.assertEqual(game.winner, "B")
