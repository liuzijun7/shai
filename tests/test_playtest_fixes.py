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


class BorrowedInner(unittest.TestCase):
    def test_song_lian_borrows_only_from_the_fighter_on_the_field(self):
        b = fight("宋濂", ["巫师", "武圣"])
        song = b.fighter("A")
        self.assertEqual(song.lives_total, 1)
        self.assertEqual(song.inner_level("幻影"), 4)      # 对面是巫师：有巫师的幻影
        self.assertEqual(song.inner_level("铁布衫"), 3)    # 自己的铁布衫一直在
        play(b, "d1", "switch:1")
        song = b.fighter("A")
        self.assertEqual(song.inner_level("幻影"), 0)      # 巫师下场了，借来的幻影就没有了
        self.assertEqual(song.inner_level("铁布衫"), 3)

    def test_borrowed_inner_goes_when_the_lender_dies(self):
        b = fight("宋濂", ["巫师", "武圣"])
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
        self.assertEqual(sorted(b.waiting_for()), ["A", "B"])     # 上场的第 1 回合不透视
        play(b, "d1", "d1")
        self.assertEqual(b.waiting_for(), ["B"])                  # 第 2 回合透视：对手先选
        self.assertFalse(legal(b, "A")["0"]["legal"])
        self.assertIsNone(b.view()["peek"]["A"])
        b.choose("B", "5")
        self.assertEqual(b.waiting_for(), ["A"])
        self.assertEqual(b.view()["peek"]["A"]["name"], "狮子吼")
        self.assertIsNone(b.view()["peek"]["B"])
        b.choose("A", "d1")
        settle(b)
        self.assertEqual(b.round, 3)
        self.assertEqual(sorted(b.waiting_for()), ["A", "B"])     # 第 3 回合不透视，第 4 回合再透视
        play(b, "d1", "d1")
        self.assertEqual(b.waiting_for(), ["B"])

    def test_the_status_lets_the_other_side_see(self):
        b = fight("武圣", "饕餮")
        b.fighter("A").statuses["透视"] = Status("透视", 3, "B")
        self.assertEqual(b.waiting_for(), ["A"])
        self.assertTrue(b.view()["sees"]["B"])

    def test_two_seers_cancel_out(self):
        b = fight("纵目青铜怪", "纵目青铜怪")
        play(b, "d1", "d1")
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
        room.handle("A", {"t": "choose", "action": "d1"})       # 第 1 回合不透视
        room.handle("B", {"t": "choose", "action": "d1"})
        self.assertEqual(room.state_for("A")["need"], "wait")   # 第 2 回合：等对手先选
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
        room.handle("A", {"t": "choose", "action": "4"})    # 摄魂大法
        room.handle("B", {"t": "choose", "action": "5"})    # 狮子吼
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
        self.assertIn("免疫魔法", legal(b, "A")["12"]["warning"])     # 昏睡咒
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
