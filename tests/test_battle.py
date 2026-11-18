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
    order = ("A", "B") if "A" in battle.waiting_for() else ("B", "A")     # 能透视的一方后选
    for side in order:
        battle.choose(side, a if side == "A" else b)
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
        self.assertFalse(legal(b, "A")["1"]["legal"])            # 流星是物理
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
        # 饕餮不能打全宇宙。对手在上面：普通的招够不着，能往上打的招够得着，神技不受限制。
        b = Battle(["饕餮"], ["武圣"], seed=1, true_body=False)
        b.fighter("B").scene = "电离层"                          # 比地面高 3 层
        self.assertFalse(legal(b, "A")["0"]["legal"])
        self.assertIn("够不着", legal(b, "A")["0"]["reason"])
        self.assertTrue(legal(b, "A")["6"]["legal"])             # 圣六式空凌能往上打
        self.assertTrue(legal(b, "A")["21"]["legal"])            # 雷神之怒也能
        self.assertFalse(legal(b, "A")["10"]["legal"])           # 寒潮不能往上打
        b.fighter("B").scene = "宇宙边缘"
        self.assertTrue(legal(b, "A")["6"]["legal"])             # 多高都打得到
        self.assertTrue(legal(b, "A")["32"]["legal"])            # 神技打得到
        # 在上面的人默认打得到下面的人。
        b = Battle(["陶渊明"], ["武圣"], seed=1, true_body=False)
        b.fighter("B").scene = "外地核"
        self.assertTrue(legal(b, "A")["30"]["legal"])            # 悬心拳
        b.fighter("B").scene = "对流层"
        self.assertFalse(legal(b, "A")["30"]["legal"])
        # 能打全宇宙的人物出什么招都打得到。
        b = Battle(["武圣"], ["饕餮"], seed=1, true_body=False)
        b.fighter("B").scene = "宇宙边缘"
        self.assertTrue(legal(b, "A")["0"]["legal"])

    def test_lost_life_resets_state(self):
        b = Battle(["拳术宗师"], ["武圣"], seed=2, true_body=False)    # 武圣有 2 条命
        target = b.fighter("B")
        target.hp = 1
        target.resources["星体能量"] = 7
        target.statuses["烧伤"] = Status("烧伤", 3, "A")
        play(b, "0", "d2")
        target = b.fighter("B")     # 结算会重建人物对象，要重新取
        self.assertEqual(target.lives_remaining, 1)
        self.assertEqual(target.hp, target.max_hp)
        self.assertEqual(target.resources["星体能量"], 0)
        self.assertNotIn("烧伤", target.statuses)

    def test_wu_sheng_has_two_lives(self):
        b = Battle(["武圣"], ["欧阳修"], seed=1, true_body=False)
        self.assertEqual(b.fighter("A").lives_total, 2)


class OrderAndZei(unittest.TestCase):
    def test_no_zei_when_order_does_not_matter(self):
        b = Battle(["武圣"], ["饕餮"], seed=1, true_body=False)
        b.choose("A", "0")
        b.choose("B", "0")
        self.assertIsNone(b.pending)
        self.assertEqual(b.fighter("B").hp, 150000 - 10000)
        self.assertEqual(b.fighter("A").hp, 100000 - 10000)

    def test_later_zei_does_not_force_an_order_zei(self):
        # 拳术宗师有暴击（要贼）。双方都是普通攻击，谁先谁后结果一样，所以不为先后手贼，只为暴击贼。
        b = Battle(["拳术宗师"], ["饕餮"], seed=1, true_body=False)
        b.choose("A", "0")
        b.choose("B", "0")
        self.assertEqual(b.pending["purpose"], "chance")
        self.assertIn("双方同一档出手，先后不影响结果。", b.log)
        b.answer("B")               # 暴击没出
        self.assertIsNone(b.pending)
        self.assertEqual(b.fighter("B").hp, 150000 - 15000)   # 蛮力 3：加 50%
        self.assertEqual(b.fighter("A").hp, 100000 - 5000)    # 铁布衫 3：只受一半

    def test_zei_decides_order_and_sealed_move_is_cancelled(self):
        b = Battle(["拳术宗师"], ["饕餮"], seed=1, true_body=False)
        b.choose("A", "4")          # 摄魂大法：封魔
        b.choose("B", "3")          # 点穴手：魔法，打中了封物
        self.assertEqual(b.pending["kind"], "zei")
        self.assertEqual(b.pending["purpose"], "order")
        self.assertEqual(sorted(b.pending["askers"]), ["A", "B"])
        b.answer("A")               # A 贼赢，A 先出手
        self.assertTrue(b.fighter("B").has_status("封魔"))
        self.assertFalse(b.fighter("A").has_status("封物"))   # 点穴手被憋回去，完全作废

    def test_zei_loser_seal_lands_after_the_attack(self):
        b = Battle(["拳术宗师"], ["饕餮"], seed=1, true_body=False)
        play(b, "4", "5", zei="B")
        self.assertEqual(b.fighter("A").hp, 100000 - 7500)
        self.assertTrue(b.fighter("B").has_status("封魔"))

    def test_shen_goes_before_normal_move_without_zei(self):
        b = Battle(["武圣"], ["饕餮"], seed=1, true_body=False)
        b.choose("A", "32")         # 惊天混元掌：神技
        b.choose("B", "0")
        self.assertIsNone(b.pending)
        self.assertIn("A先出手。", b.log)

    def test_unblockable_signature_is_not_cancelled(self):
        b = Battle(["拳术宗师"], ["牛顿"], seed=1, true_body=False)
        settle(b)                   # 牛顿回合开始先选场景，这里选“不动”
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
        b = Battle(["武圣"], ["饕餮"], seed=1, true_body=False)
        play(b, "32", "0")
        self.assertIn("32", b.fighter("A").used_shen)
        self.assertFalse(legal(b, "A")["32"]["legal"])
        self.assertTrue(legal(b, "A")["33"]["legal"])

    def test_wizard_shen_is_unlimited(self):
        b = Battle(["巫师"], ["欧阳修"], seed=1, true_body=False)   # 欧阳修血厚，挨得住幻影的四连击
        play(b, "33", "d1")
        b.choose("B", "d1")              # 灵气寒霜指打出了透视：对手先选，巫师看到以后再选
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
        b.choose("B", "3")
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


class TurnStartScenes(unittest.TestCase):
    def test_newton_picks_his_scene_for_free(self):
        b = Battle(["牛顿"], ["欧阳修"], seed=1, true_body=False)
        self.assertEqual(b.pending["kind"], "choose")
        self.assertEqual(b.pending["askers"], ["A"])
        b.answer("宇宙")
        self.assertEqual(b.fighter("A").scene, "宇宙")
        self.assertIsNone(b.pending)
        self.assertNotIn("c_newton_scene", legal(b, "A"))    # 不再是一个要占回合的招

    def test_dragon_moves_the_opponent(self):
        b = Battle(["龙王"], ["拳术宗师"], seed=1, true_body=False)
        self.assertEqual(b.pending["askers"], ["A"])
        b.answer("南极")
        self.assertEqual(b.fighter("B").scene, "南极")

    def test_dragon_against_newton_is_settled_by_zei(self):
        for zei_winner, expected in (("A", "南极"), ("B", "宇宙")):
            b = Battle(["龙王"], ["牛顿"], seed=1, true_body=False)
            b.answer("南极")         # 龙王要把牛顿移到南极
            b.answer("宇宙")         # 牛顿要自己去宇宙
            self.assertEqual(b.pending["kind"], "zei")
            b.answer(zei_winner)
            self.assertEqual(b.fighter("B").scene, expected)

    def test_kuba_throw_and_run_take_three_zei(self):
        b = Battle(["库巴"], ["拳术宗师"], seed=1, true_body=False)
        self.assertEqual(b.pending["askers"], ["B"])        # 先问对手要不要扔
        b.answer("南极")
        self.assertEqual(b.pending["askers"], ["A"])        # 再问库巴要不要跑
        b.answer("外太空")
        zeis = 0
        while b.pending and b.pending["kind"] == "zei":
            zeis += 1
            b.answer("A")           # 库巴三次都赢：没被扔动，跑成了
        self.assertEqual(zeis, 3)
        self.assertEqual(b.fighter("A").scene, "外太空")

    def test_kuba_nobody_wants_to_move_means_no_zei(self):
        b = Battle(["库巴"], ["拳术宗师"], seed=1, true_body=False)
        b.answer("")
        b.answer("")
        self.assertIsNone(b.pending)
        self.assertEqual(b.fighter("A").scene, "地面")


class Divination(unittest.TestCase):
    @staticmethod
    def round_with_guess(b, guess, a_move, b_move):
        """回合开始先回答占卜，再双方选招；中途的贼都让 A 赢，但不替占卜大师回答下一回合的占卜。"""
        b.answer(guess)
        b.choose("A", a_move)
        b.choose("B", b_move)
        while b.pending and b.pending["kind"] == "zei":
            b.answer("A")

    def test_hit_adds_hp_and_three_hits_evolve(self):
        b = Battle(["占卜大师"], ["饕餮"], seed=1, true_body=False)
        self.assertIn("占卜", b.pending["reason"])
        for hits in (1, 2):
            before = b.fighter("A").max_hp
            self.round_with_guess(b, "无属性", "d1", "0")     # 猜对手用无属性的招（普通攻击）
            self.assertEqual(b.fighter("A").max_hp, before + hits * 10000)
        self.round_with_guess(b, "无属性", "d1", "0")
        self.assertEqual(b.fighter("A").name, "魔法师")        # 占中 3 次进化
        self.assertEqual(b.fighter("A").hp, b.fighter("A").max_hp)

    def test_miss_changes_nothing_and_guess_is_public(self):
        b = Battle(["占卜大师"], ["饕餮"], seed=1, true_body=False)
        before = b.fighter("A").max_hp
        self.round_with_guess(b, "魔法", "d1", "0")
        self.assertIn("A的占卜大师占卜：对手这回合会用【魔法】的招。", b.log)   # 双方都看得到
        self.assertIn("A的占卜大师没有占中。", b.log)
        self.assertEqual(b.fighter("A").max_hp, before)


class LearningInner(unittest.TestCase):
    def test_learning_takes_the_turn_and_levels_up_at_thresholds(self):
        b = Battle(["武圣"], ["饕餮"], seed=1, true_body=False)
        for _ in range(4):
            play(b, "learn:幸运", "d1")
        self.assertEqual(b.fighter("A").learn_progress["幸运"], 4)
        self.assertEqual(b.fighter("A").inner_level("幸运"), 0)
        play(b, "learn:幸运", "d1")
        self.assertEqual(b.fighter("A").inner_level("幸运"), 1)       # 学满 5 下升到 1 级

    def test_some_characters_learn_faster(self):
        b = Battle(["陶渊明"], ["饕餮"], seed=1, true_body=False)
        play(b, "learn:蛮力", "d1")
        play(b, "learn:蛮力", "d1")
        self.assertEqual(b.fighter("A").learn_progress["蛮力"], 6)     # 陶渊明学一下算三下
        self.assertEqual(b.fighter("A").inner_level("蛮力"), 1)

    def test_only_three_extra_kinds(self):
        b = Battle(["武圣"], ["饕餮"], seed=1, true_body=False)
        for name in ("幸运", "蛮力", "铁布衫"):
            play(b, f"learn:{name}", "d1")
        self.assertFalse(legal(b, "A")["learn:幻影"]["legal"])
        self.assertTrue(legal(b, "A")["learn:幸运"]["legal"])           # 已经在学的可以接着学

    def test_crit_doubles_damage(self):
        b = Battle(["拳术宗师"], ["欧阳修"], seed=1, true_body=False)   # 拳术宗师：蛮力 3、暴击 3
        play(b, "0", "d2", zei="A")
        self.assertEqual(b.fighter("B").hp, 300000 - 10000 * 1.5 * 2)
