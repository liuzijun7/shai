"""雨晨第一次试玩以后改的规则。"""

import os
import random
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from server.rooms import Room  # noqa: E402
from shai import Battle  # noqa: E402
from shai.model import Status  # noqa: E402
from test_battle import legal, play, settle  # noqa: E402


def fight(a, b, **more):
    return Battle([a] if isinstance(a, str) else a, [b] if isinstance(b, str) else b, seed=1, true_body=False, **more)


class ShenAlwaysHits(unittest.TestCase):
    def test_no_dodge_against_shen(self):
        b = fight("武圣", "陶渊明")                       # 陶渊明有虚空神术 3
        b.choose("A", "32")                               # 惊天混元掌
        b.choose("B", "d1")
        self.assertIsNone(b.pending)                      # 不用为闪避贼
        self.assertEqual(b.fighter("B").hp, 150000 - 50000)

    def test_the_xukong_debuff_does_not_stop_shen(self):
        b = fight("武圣", "欧阳修")
        b.fighter("A").statuses["虚空"] = Status("虚空", 3, "B")
        b.choose("A", "32")
        b.choose("B", "d1")
        self.assertIsNone(b.pending)
        self.assertEqual(b.fighter("B").hp, 300000 - 50000)

    def test_ordinary_moves_still_miss_and_the_log_says_why(self):
        b = fight("武圣", "欧阳修")
        b.fighter("A").statuses["虚空"] = Status("虚空", 3, "B")
        play(b, "0", "d2", zei="B")
        self.assertEqual(b.fighter("B").hp, 300000)
        self.assertTrue(any("身上有“虚空”，【普通攻击】打空了" in line for line in b.log))


class OneMoveOneThing(unittest.TestCase):
    def test_wizard_hits_five_times(self):
        b = fight("巫师", "欧阳修")
        self.assertEqual(b.fighter("A").inner_level("幻影"), 4)
        play(b, "0", "d2")
        self.assertEqual(b.fighter("B").hp, 300000 - 5 * 10000)

    def test_hits_stop_when_the_shield_breaks(self):
        b = fight("巫师", "库巴")                         # 库巴：盾牌 10 万，体力 10 万，3 条命
        settle(b)                                         # 回合开始先问扔不扔、跑不跑：都答“不”
        play(b, "32", "d1")                               # 5 下各 5 万：两下打碎盾牌，剩下三下落空
        foe = b.fighter("B")
        self.assertEqual((foe.shield, foe.hp, foe.lives_remaining), (0, 100000, 3))
        self.assertTrue(any("剩下的3下落空" in line for line in b.log))

    def test_hits_stop_when_a_life_is_lost(self):
        b = fight("巫师", "武圣")                         # 武圣 2 条命，没有盾牌
        play(b, "32", "d1")                               # 两下打掉第一条命，剩下三下不会打到第二条命
        foe = b.fighter("B")
        self.assertEqual((foe.lives_remaining, foe.hp), (1, 100000))


class KubaHelper(unittest.TestCase):
    """上面盾牌的测试依赖回合开始的提问顺序，这里单独确认一下。"""

    def test_turn_start_questions(self):
        b = fight("巫师", "库巴")
        self.assertEqual(b.pending["kind"], "choose")
        self.assertEqual(b.pending["askers"], ["A"])      # 先问巫师要不要扔
        b.answer("")
        self.assertEqual(b.pending["askers"], ["B"])      # 再问库巴要不要跑
        b.answer("")
        self.assertIsNone(b.pending)


class AnswersOf1118(unittest.TestCase):
    def test_radiation_takes_one_life_and_does_not_carry_over(self):
        b = fight("巫师", "武圣")                           # 巫师幻影 4：X 光 5 次乘 5，一共 25 次辐射
        play(b, "20", "d1")
        foe = b.fighter("B")
        self.assertEqual((foe.lives_remaining, foe.radiation, foe.hp), (1, 0, 100000))

    def test_a_move_that_took_a_life_does_not_touch_the_next_life(self):
        b = fight("拳术宗师", "武圣")
        b.fighter("B").hp = 5000
        play(b, "5", "d3", zei="B")                         # 吼：伤害加封喉 5 回合。这一下打掉了第一条命
        foe = b.fighter("B")
        self.assertEqual(foe.lives_remaining, 1)
        self.assertFalse(foe.has_status("封喉"))             # 封喉不会落到第二条命上

    def test_attributes_settled_by_the_user(self):
        from shai.data import SKILLS
        want = {"3": ("魔法",), "4": ("魔法",), "5": ("物理",), "9": ("物理", "地理"), "10": ("物理", "地理"),
                "12": ("特技",), "21": ("物理", "魔法", "特技"), "28": ("化学", "特技"), "29": ("化学", "特技")}
        for key, attributes in want.items():
            self.assertEqual(tuple(SKILLS[key]["attributes"]), attributes, SKILLS[key]["name"])
        b = fight("武圣", "宋濂")                           # 宋濂免疫魔法
        settle(b)
        self.assertIn("免疫魔法", legal(b, "A")["3"]["warning"])    # 点穴手是魔法
        self.assertEqual(legal(b, "A")["5"]["warning"], "")        # 吼是物理

    def test_your_own_signature_move_does_not_seal_you(self):
        b = fight("生化大师", "武圣")
        b.fighter("A").inner = {}
        play(b, "29", "d1")                                 # 乙醚是生化大师的大招（化学加特技）
        self.assertFalse(b.fighter("A").has_status("封喉"))
        self.assertTrue(legal(b, "A")["28"]["legal"])        # 下一回合还能接着用硫酸
        b = fight("武圣", "欧阳修")
        play(b, "29", "d1")                                 # 别人用乙醚，照常被封喉 3 回合
        self.assertTrue(b.fighter("A").has_status("封喉"))

    def test_fat_dragon_reaches_everywhere(self):
        b = fight("肥龙王", "武圣")
        settle(b)
        b.fighter("B").scene = "宇宙边缘"
        self.assertTrue(legal(b, "A")["0"]["legal"])


class AimAtYourself(unittest.TestCase):
    def test_any_move_can_be_used_on_yourself(self):
        b = fight("陶渊明", "武圣")
        b.fighter("B").scene = "宇宙"                       # 对手在天上，陶渊明够不着
        self.assertFalse(legal(b, "A")["0"]["legal"])
        self.assertTrue(legal(b, "A")["0"]["self_ok"])
        self.assertTrue(legal(b, "A")["6"]["self_ok"])
        self.assertNotIn("self_ok", legal(b, "A")["d1"])     # 防御没有“打自己”
        b.choose("A", "6", on_self=True)                    # 圣六式空凌打自己：挨一下，往上飞一层
        b.choose("B", "d3")                                 # 对手的防御 3 挡不了
        self.assertIsNone(b.pending)                        # 陶渊明有虚空神术，但打自己不用躲
        me = b.fighter("A")
        self.assertEqual(me.hp, 150000 - 20000)
        self.assertEqual(me.scene, "对流层")
        self.assertIn("A的陶渊明对自己使用【圣六式空凌】。", b.log)

    def test_you_can_kill_yourself_and_da_nan_bu_si_still_rolls(self):
        b = fight("饕餮", "武圣")                           # 饕餮有大难不死 3
        b.fighter("A").hp = 5000
        b.choose("A", "0", on_self=True)
        b.choose("B", "d1")
        self.assertEqual(b.pending["reason"], "A的饕餮的大难不死发不发动")
        b.answer("B")
        self.assertTrue(b.fighter("A").defeated)


class DeathEffects(unittest.TestCase):
    def test_everyone_sleeps_three_turns_when_lingli_dies(self):
        b = fight(["灵力圣使", "武圣"], "陶渊明")           # 陶渊明免疫不良特效，但这个昏睡是强制的
        b.fighter("A").hp = 1
        play(b, "d2", "0")
        self.assertEqual(b.fighter("A").name, "武圣")
        self.assertIn("A的灵力圣使倒下，全场强制昏睡3回合。", b.log)
        self.assertIn("B的陶渊明获得昏睡（3回合）。", b.log)
        self.assertTrue(b.fighter("B").has_status("昏睡"))


class BothMovesAlwaysComeOut(unittest.TestCase):
    def test_a_fighter_killed_first_still_gets_its_move_out(self):
        b = fight("陶渊明", ["饕餮", "武圣"])              # 陶渊明有凌波微步，先出手
        foe = b.fighter("B")
        foe.hp, foe.inner = 5000, {}
        play(b, "0", "x2", zei="B")                        # 陶渊明的虚空神术没躲开
        self.assertIn("B的饕餮虽然已经倒下，这回合选好的【芒星】照样打出来。", b.log)
        self.assertEqual(b.fighter("A").hp, 150000 - 10000)
        self.assertEqual(b.fighter("B").name, "武圣")      # 打完这一回合才换下一个人上场

    def test_a_fighter_that_lost_a_life_still_acts(self):
        b = fight("陶渊明", "武圣")
        b.fighter("B").hp = 5000
        play(b, "0", "x2", zei="B")
        self.assertIn("B的武圣虽然丢了一条命，这回合选好的【芒星】照样打出来。", b.log)
        self.assertEqual(b.fighter("A").hp, 150000 - 10000)


class BorrowedInner(unittest.TestCase):
    def test_song_lian_picks_one_inner_skill_of_the_fighter_on_the_field(self):
        b = fight("宋濂", ["陶渊明", "武圣"])                # 陶渊明：凌波微步 3、虚空神术 3
        self.assertEqual(b.pending["askers"], ["A"])          # 回合开始先问宋濂借哪一种
        self.assertEqual([o["id"] for o in b.pending["options"]], ["", "凌波微步", "虚空神术"])
        b.answer("凌波微步")
        song = b.fighter("A")
        self.assertEqual(song.lives_total, 1)
        self.assertEqual(song.inner_level("凌波微步"), 3)
        self.assertEqual(song.inner_level("虚空神术"), 0)     # 一次只借一种
        self.assertEqual(song.inner_level("铁布衫"), 3)       # 自己的铁布衫一直在
        self.assertEqual(b.view()["players"]["A"]["team"][0]["borrowed"], ["凌波微步"])
        play(b, "d1", "switch:1")
        song = b.fighter("A")
        self.assertEqual(song.inner_level("凌波微步"), 0)     # 陶渊明下场了，借来的就没有了
        self.assertIsNone(b.pending)                          # 武圣没有内功，没东西可借，不问

    def test_a_loan_lasts_five_turns_then_must_change(self):
        b = fight("宋濂", "陶渊明")
        b.answer("凌波微步")
        for _ in range(4):
            play(b, "d1", "d1")
            self.assertEqual(b.fighter("A").inner_level("凌波微步"), 3)
        b.choose("A", "d1")                                   # 第 5 回合打完，第 6 回合开始：借满 5 回合，要换一种
        b.choose("B", "d1")
        self.assertEqual([o["id"] for o in b.pending["options"]], ["", "虚空神术"])
        b.answer("虚空神术")
        self.assertEqual(b.fighter("A").inner_level("虚空神术"), 3)
        self.assertEqual(b.fighter("A").inner_level("凌波微步"), 0)

    def test_borrowed_inner_goes_when_the_lender_dies(self):
        b = fight("宋濂", ["巫师", "武圣"])
        b.answer("幻影")
        self.assertEqual(b.fighter("A").inner_level("幻影"), 4)
        foe = b.fighter("B")
        foe.shield, foe.hp = 0, 1
        play(b, "0", "d2")
        self.assertEqual(b.fighter("B").name, "武圣")
        self.assertEqual(b.fighter("A").inner_level("幻影"), 0)
        self.assertNotIn("幻影", b.view()["players"]["A"]["team"][0]["inner"])


class LearnedInnerBelongsToThePlayer(unittest.TestCase):
    def test_every_fighter_of_the_player_has_it(self):
        b = fight(["陶渊明", "武圣"], "欧阳修")
        play(b, "learn:幻影", "d1")
        play(b, "learn:幻影", "d1")                        # 陶渊明学一下算三下：6 下，幻影 1 级
        self.assertEqual(b.fighter("A").inner_level("幻影"), 1)
        play(b, "switch:1", "d1")
        wu = b.fighter("A")
        self.assertEqual(wu.name, "武圣")
        self.assertEqual(wu.inner_level("幻影"), 1)        # 换了人物，学来的内功还在
        self.assertEqual(wu.inner_level("凌波微步"), 0)    # 陶渊明自带的凌波微步不跟着走
        self.assertEqual(b.fighter("B").inner_level("幻影"), 0)
        play(b, "learn:幻影", "d1")
        self.assertEqual(b.fighter("A").learn_progress["幻影"], 7)   # 武圣接着学，进度是同一份


class Rebirth(unittest.TestCase):
    def test_invincible_only_for_the_round_it_is_used(self):
        b = fight("武圣", ["欧阳修", "宋濂"])
        play(b, "0", "36")                                # 欧阳修用浴火重生
        self.assertEqual(b.fighter("B").hp, 300000)
        self.assertFalse(b.fighter("B").has_status("无敌"))   # 回合结束就没有了，不会带到后面的回合


class SeeThrough(unittest.TestCase):
    def test_bronze_monster_picks_after_seeing_the_other_pick(self):
        b = fight("纵目青铜怪", "饕餮")
        self.assertEqual(b.waiting_for(), ["B"])                  # 上场以后第一个能出招的回合就透视：对手先选
        self.assertFalse(legal(b, "A")["0"]["legal"])
        self.assertIsNone(b.view()["peek"]["A"])
        b.choose("B", "5")
        self.assertEqual(b.waiting_for(), ["A"])
        self.assertEqual(b.view()["peek"]["A"]["name"], "狮子吼")
        self.assertIsNone(b.view()["peek"]["B"])
        b.choose("A", "d1")
        settle(b)
        self.assertEqual(b.round, 2)
        self.assertEqual(sorted(b.waiting_for()), ["A", "B"])     # 下一回合不透视
        play(b, "d1", "d1")
        self.assertEqual(b.waiting_for(), ["B"])                  # 隔一回合又透视

    def test_coming_in_after_a_death_sees_through_at_once(self):
        b = fight(["武圣", "纵目青铜怪"], "饕餮")
        first = b.fighter("A")
        first.lives_remaining, first.hp = 1, 1
        play(b, "d2", "0")                                        # 武圣倒下，纵目青铜怪顶上来（不算一回合）
        self.assertEqual(b.fighter("A").name, "纵目青铜怪")
        self.assertEqual(b.waiting_for(), ["B"])                  # 他出招的第一个回合，对手就被透视

    def test_switching_in_sees_through_on_the_next_turn(self):
        b = fight(["武圣", "纵目青铜怪"], "饕餮")
        play(b, "switch:1", "d1")                                 # 换人占这一回合
        self.assertEqual(b.waiting_for(), ["B"])                  # 下一回合透视

    def test_the_status_lets_the_other_side_see(self):
        b = fight("武圣", "饕餮")
        b.fighter("A").statuses["透视"] = Status("透视", 3, "B")
        self.assertEqual(b.waiting_for(), ["A"])
        self.assertTrue(b.view()["sees"]["B"])

    def test_two_seers_cancel_out(self):
        b = fight("纵目青铜怪", "纵目青铜怪")
        self.assertTrue(b.view()["sees"] == {"A": False, "B": False})
        self.assertEqual(sorted(b.waiting_for()), ["A", "B"])

    def test_only_the_seer_gets_the_peek_over_the_network(self):
        room = Room("1", rng=random.Random(1))
        room.join("甲")
        room.join("乙")
        room.handle("A", {"t": "config", "team_size": 1, "zei": False})
        room.handle("A", {"t": "team", "names": ["纵目青铜怪"]})
        room.handle("B", {"t": "team", "names": ["饕餮"]})
        watcher, _ = room.join("丙")
        self.assertEqual(room.state_for("A")["need"], "wait")   # 第 1 回合就透视：等对手先选
        room.handle("B", {"t": "choose", "action": "5"})
        self.assertEqual(room.state_for("A")["view"]["peek"]["name"], "狮子吼")
        self.assertEqual(room.state_for("A")["need"], "choose")
        self.assertIsNone(room.state_for("B")["view"]["peek"])
        self.assertIsNone(room.state_for(watcher)["view"]["peek"])


class ClearerInformation(unittest.TestCase):
    def test_zei_keeps_the_hands_and_says_what_was_at_stake(self):
        room = Room("1", rng=random.Random(1))
        room.join("甲")
        room.join("乙")
        room.handle("A", {"t": "config", "team_size": 1})
        room.handle("A", {"t": "team", "names": ["拳术宗师"]})
        room.handle("B", {"t": "team", "names": ["饕餮"]})
        room.handle("A", {"t": "choose", "action": "22"})   # 摄魂点穴手
        room.handle("B", {"t": "choose", "action": "3"})    # 点穴手：两边互相都能封住对方，要贼先后手
        state = room.state_for("A")
        self.assertEqual(state["need"], "throw")
        self.assertEqual(state["prompt"]["stakes"], {"A": "A的拳术宗师先出手", "B": "B的饕餮先出手", "tie": ""})
        room.handle("A", {"t": "throw", "hand": "石头"})
        room.handle("B", {"t": "throw", "hand": "石头"})    # 打平
        room.handle("A", {"t": "throw", "hand": "石头"})
        room.handle("B", {"t": "throw", "hand": "剪刀"})    # A 赢
        events = room.battle.events
        zei = [e for e in events if e["t"] == "zei"][0]
        self.assertEqual(zei["rounds"], [{"A": "石头", "B": "石头"}, {"A": "石头", "B": "剪刀"}])
        self.assertEqual((zei["winner"], zei["outcome"], zei["purpose"]), ("A", "A的拳术宗师先出手", "order"))
        self.assertTrue(any("先打平1把，然后A出石头，B出剪刀，A赢，A先出手" in line for line in room.battle.log))

    def test_chance_zei_says_how_many_wins_are_needed(self):
        b = fight("武圣", "欧阳修")
        b.fighter("A").statuses["虚空"] = Status("虚空", 3, "B")
        b.choose("A", "0")
        b.choose("B", "d2")
        self.assertEqual(b.pending["series"], {"need": 2, "index": 1})
        self.assertEqual(b.pending["stakes"]["A"], "还要再赢1把才算数")
        self.assertEqual(b.pending["stakes"]["B"], "这一招打空")
        b.answer("A")
        self.assertEqual(b.pending["series"], {"need": 2, "index": 2})
        self.assertEqual(b.pending["stakes"]["A"], "这一招打中")

    def test_moves_that_will_do_nothing_carry_a_warning(self):
        b = fight("武圣", "宋濂")                          # 宋濂免疫魔法
        self.assertIn("免疫魔法", legal(b, "A")["4"]["warning"])      # 摄魂大法是魔法
        self.assertEqual(legal(b, "A")["12"]["warning"], "")         # 昏睡咒是特技，宋濂不免疫
        self.assertEqual(legal(b, "A")["0"]["warning"], "")
        self.assertIn("免疫魔法", b.view()["players"]["B"]["team"][0]["traits"])

    def test_switch_event_carries_the_new_fighter(self):
        b = fight(["武圣", "巫师"], "欧阳修")
        play(b, "switch:1", "d1")
        switch = [e for e in b.events if e["t"] == "switch"][0]
        self.assertEqual(switch["fighter"]["name"], "巫师")

    def test_filtered_statuses_are_reported_in_one_line(self):
        b = fight("武圣", "陶渊明")                        # 陶渊明免疫不良特效
        play(b, "x7", "d1")                                # 一零二仙折：除了神技全封
        lines = [line for line in b.log if "没有加上" in line]
        self.assertEqual(lines, ["B的陶渊明免疫不良特效，封物、封魔、封喉、封品、封土、封化、封生没有加上。"])

    def test_no_zei_for_a_move_that_cannot_do_anything(self):
        b = fight("武圣", "陶渊明")                        # 陶渊明：虚空神术 3，免疫不良特效
        self.assertIn("免疫不良特效", legal(b, "A")["12"]["warning"])
        b.choose("A", "12")                                # 昏睡咒只会加昏睡，对他没用
        b.choose("B", "d2")
        self.assertIsNone(b.pending)                       # 不用为“躲不躲得开”贼
        self.assertIn("B的陶渊明免疫不良特效，【昏睡咒】对他没有用。", b.log)

    def test_no_order_zei_when_either_order_ends_the_game_the_same_way(self):
        # 甲先出手会把乙打死，乙的招就出不来；乙先出手，甲先被打昏睡再把乙打死。两种顺序都是乙全灭，不用贼先后。
        b = fight("武圣", "武圣")
        foe = b.fighter("B")
        foe.lives_remaining, foe.hp = 1, 5000
        b.choose("A", "30")                                # 悬心拳
        b.choose("B", "12")                                # 昏睡咒
        self.assertTrue(b.done)
        self.assertEqual(b.winner, "A")
        self.assertFalse(any("谁先出手" in line for line in b.log))

    def test_floating_up_says_why(self):
        b = fight("武圣", "欧阳修")
        self.assertTrue(any("有内功轻于鸿毛3级，自己往上飘一层，移动到对流层" in line for line in b.log))


if __name__ == "__main__":
    unittest.main()
