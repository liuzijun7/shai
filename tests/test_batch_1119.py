"""雨晨 2026-11-19 逐个定的招、虫子和场景。"""

import os
import random
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from server.rooms import Room  # noqa: E402
from shai import Battle  # noqa: E402
from shai.data import SCENES, SKILLS  # noqa: E402
from shai.model import Parasite, Status  # noqa: E402
from test_battle import legal, play, settle  # noqa: E402


def fight(a="范仲淹", b="范仲淹"):
    """范仲淹：10 万体力，没有内功，没有免疫，站在地面不乱动。"""
    return Battle([a] if isinstance(a, str) else a, [b] if isinstance(b, str) else b, seed=1, true_body=False)


def ids(battle, side):
    return [a["id"] for a in battle.legal_actions(side)]


class NewMoves(unittest.TestCase):
    def test_true_fire_burns_an_eighth_for_three_turns(self):
        b = fight()
        play(b, "x15", "d2")
        self.assertEqual(b.fighter("B").hp, 100000 - 10000 - 12500)       # 1 万，再烧掉上限的八分之一
        play(b, "d1", "d1")
        play(b, "d1", "d1")
        self.assertEqual(b.fighter("B").hp, 100000 - 10000 - 3 * 12500)
        self.assertFalse(b.fighter("B").has_status("真火"))               # 烧满 3 回合
        b = fight(b="武圣")                                               # 武圣免疫火系
        play(b, "x15", "d2")
        self.assertEqual(b.fighter("B").hp, 100000)

    def test_nine_mile_fire_drives_the_target_out_of_antarctica(self):
        b = fight()
        b.fighter("B").scene = "南极"
        play(b, "x16", "d1")
        foe = b.fighter("B")
        self.assertEqual(foe.scene, "地面")
        self.assertEqual(foe.hp, 100000 - 30000 - 12500)
        self.assertEqual(foe.statuses["真火"].turns, 9)                     # 一共烧 10 回合，已经烧了 1 回合

    def test_laser_lets_you_pick_three_seals_and_zei_for_each(self):
        b = fight(a="巫师", b="欧阳修")                                    # 巫师有幻影 4，但幻影对激光不起作用
        b.choose("A", "x17")
        b.choose("B", "d1")
        for attribute in ("物理", "魔法", "特技"):
            self.assertEqual(b.pending["kind"], "choose")
            self.assertEqual(b.pending["askers"], ["A"])
            b.answer(attribute)
        for winner in ("A", "B", "A"):
            self.assertEqual(b.pending["kind"], "zei")
            b.answer(winner)
        foe = b.fighter("B")
        self.assertEqual(foe.hp, 300000 - 10000)                          # 只打一下
        self.assertEqual(foe.radiation, 1)
        self.assertEqual(foe.statuses["封物"].turns, 3)
        self.assertTrue(foe.has_status("封喉"))
        self.assertFalse(foe.has_status("封魔"))                          # 这一把贼输了

    def test_moving_light_wave_exists_but_is_not_offered(self):
        self.assertEqual(SKILLS["x18"]["name"], "动感光波")
        self.assertNotIn("x18", ids(fight(), "A"))

    def test_dispel_removes_one_effect_of_your_choice(self):
        b = fight()
        b.fighter("A").statuses["封喉"] = Status("封喉", 3, "B")
        b.fighter("B").statuses["无敌"] = Status("无敌", 3, "B")           # 对手无敌也挡不住通灵之手
        b.choose("A", "x19")
        b.choose("B", "d2")
        self.assertEqual([o["id"] for o in b.pending["options"]], ["me:s:封喉", "foe:s:无敌"])
        b.answer("foe:s:无敌")
        self.assertFalse(b.fighter("B").has_status("无敌"))
        self.assertTrue(b.fighter("A").has_status("封喉"))

    def test_three_hit_move_rolls_each_hit(self):
        b = fight()
        b.choose("A", "x20")
        b.choose("B", "d1")
        for winner in ("A", "B", "A"):                                     # 第 1、3 下打中
            b.answer(winner)
        self.assertEqual(b.fighter("B").hp, 100000 - 10000 - 30000)
        b = fight(a="巫师", b="欧阳修")                                    # 幻影 4：贼赢的那一下算 5 倍
        b.choose("A", "x20")
        b.choose("B", "d1")
        for winner in ("B", "A", "B"):
            b.answer(winner)
        self.assertEqual(b.fighter("B").hp, 300000 - 5 * 20000)

    def test_combined_wu_sheng_move_needs_the_second_life(self):
        b = fight(a="武圣")
        self.assertFalse(legal(b, "A")["t10"]["legal"])
        b.fighter("A").lives_remaining = 1
        play(b, "t10", "d1")
        foe = b.fighter("B")
        self.assertEqual(foe.hp, 100000 - 80000)
        for seal in ("封喉", "封品", "封生"):
            self.assertEqual(foe.statuses[seal].turns, 10)
        self.assertNotIn("t10", ids(fight(), "A"))                         # 别的人物没有这个招

    def test_tree_of_heaven_grows_on_the_player_and_unlocks_shen(self):
        b = fight(a=["范仲淹", "武圣"], b="欧阳修")                        # 欧阳修血厚，挨得住几个神技
        play(b, "x21", "d1")
        self.assertEqual(b.players["A"].tree, 1)
        b.fighter("A").scene = "雨林深处"
        play(b, "x21", "d1")
        self.assertEqual(b.players["A"].tree, 3)                           # 在雨林深处一次长两次；神树自己不限次数
        play(b, "35", "d1")                                                # 道威无极真气
        self.assertFalse(legal(b, "A")["35"]["legal"])                     # 没长满：神技每条命一次
        b.players["A"].tree = 10
        self.assertTrue(legal(b, "A")["35"]["legal"])                      # 长满了：不限次数
        self.assertFalse(legal(b, "A")["x21"]["legal"])
        play(b, "switch:1", "d1")
        play(b, "35", "d1")
        self.assertTrue(legal(b, "A")["35"]["legal"])                      # 换了人物，神树还是这个玩家的
        self.assertEqual(b.view()["players"]["A"]["tree"], 10)

    def test_taiji_sends_whoever_is_hit_to_the_deep_rainforest(self):
        b = fight()
        play(b, "x22", "d1")
        foe = b.fighter("B")
        self.assertEqual(foe.scene, "雨林深处")
        self.assertEqual(foe.hp, 100000)                                   # 挨 1 万，雨林深处每回合回 20%，回满
        b = fight()
        b.choose("A", "x22", on_self=True)                                 # 打自己：自己进去
        b.choose("B", "d1")
        self.assertEqual(b.fighter("A").scene, "雨林深处")

    def test_big_bang_decides_the_whole_game(self):
        b = fight(a=["范仲淹", "武圣"], b=["范仲淹", "武圣"])
        self.assertFalse(legal(b, "A")["x23"]["legal"])
        b.fighter("A").resources["星体能量"] = 50
        play(b, "x23", "d2")
        self.assertTrue(b.done)
        self.assertEqual(b.winner, "A")                                    # 没人防住，自己赢
        b = fight(a=["范仲淹", "武圣"], b=["范仲淹", "武圣"])
        b.fighter("A").resources["星体能量"] = 50
        play(b, "x23", "d1")
        self.assertEqual(b.winner, "B")                                    # 对手出了防御 1，对手赢

    def test_burning_fang_is_the_glutton_move_plus_ignite(self):
        b = fight(a="饕餮")
        b.fighter("A").hp = 100000
        play(b, "t11", "d1")
        self.assertTrue(b.fighter("B").has_status("点燃"))
        self.assertEqual(b.fighter("B").statuses["点燃"].turns, 4)
        self.assertGreater(b.fighter("A").hp, 100000)                      # 和饕餮牙一样吸血
        self.assertFalse(b.fighter("A").has_status("封喉"))                 # 自己的大招不封喉
        self.assertIn("t11", ids(fight(a="肥饕餮"), "A"))
        self.assertNotIn("t11", ids(fight(), "A"))

    def test_everyone_gets_a_weak_typhoon_and_the_dragon_keeps_his_own(self):
        b = fight()
        play(b, "x24", "d1")
        foe = b.fighter("B")
        self.assertEqual(foe.scene, "黑暗之城深处")
        self.assertEqual(foe.hp, 100000 - 10000 - 20000)                   # 1 万，再加黑暗之城深处每回合扣 20%
        self.assertIn("B的范仲淹获得昏睡（1回合）。", b.log)
        b = fight(a="龙王")
        settle(b)                                                          # 龙王回合开始先问要不要移动对手
        self.assertNotIn("x24", ids(b, "A"))
        play(b, "c_dragon_typhoon", "d1")
        self.assertEqual(b.fighter("B").scene, "黑暗之城深处")

    def test_bora_freezes_instead_of_sending_to_antarctica(self):
        b = fight()
        play(b, "x11", "d1")
        foe = b.fighter("B")
        self.assertEqual((foe.scene, foe.hp), ("地面", 100000 - 10000))
        self.assertEqual(foe.statuses["冰封"].turns, 3)
        self.assertFalse(legal(b, "B")["0"]["legal"])                      # 冰封：不能出打对手的招
        self.assertIn("冰封", legal(b, "B")["0"]["reason"])
        self.assertTrue(legal(b, "B")["0"]["self_ok"])                     # 打自己可以
        self.assertTrue(legal(b, "B")["d1"]["legal"])                      # 防御、学内功都可以
        self.assertTrue(legal(b, "B")["learn:幸运"]["legal"])

    def test_death_note_sends_the_target_to_the_dark_city(self):
        b = fight()
        play(b, "7", "d1", zei="B")                                        # 没有秒杀
        foe = b.fighter("B")
        self.assertEqual(foe.scene, "黑暗之城")
        self.assertEqual(foe.hp, 100000 - 20000 - 10000)                   # 2 万，再加黑暗之城每回合扣 10%


class NewScenes(unittest.TestCase):
    def test_numbers(self):
        self.assertEqual(SCENES["雨林深处"]["heal"], 0.20)
        self.assertEqual(SCENES["黑暗之城"]["hp_loss"], 0.10)
        self.assertEqual(SCENES["黑暗之城深处"]["hp_loss"], 0.20)
        self.assertEqual(SCENES["地心深处"]["hp_loss"], 0.40)

    def test_ten_quakes_drop_you_into_the_deep_core_where_you_hit_twice_as_hard(self):
        b = fight()
        b.fighter("B").counters["quaked"] = 9
        b.fighter("B").hp = 100000
        play(b, "9", "d1")                                                 # 第 10 下地震
        foe = b.fighter("B")
        self.assertEqual(foe.scene, "地心深处")
        self.assertIn("被地震震了10下", "".join(b.log))
        b.fighter("B").hp = 100000
        a = b.fighter("A")
        a.hp, a.scene = 200000, "地心深处"                                  # 让甲也下去，乙才够得着他
        play(b, "d2", "0")                                                 # 在地心深处的人打别人：普通攻击 1 万变 2 万
        self.assertEqual(b.fighter("A").hp, 200000 - 20000 - 40000)        # 再加地心深处每回合扣 40%

    def test_the_deep_core_cannot_be_picked_directly(self):
        b = Battle(["牛顿"], ["范仲淹"], seed=1, true_body=False)            # 牛顿回合开始可以自己选场景
        names = [o["id"] for o in b.pending["options"]]
        self.assertIn("黑暗之城", names)
        self.assertNotIn("地心深处", names)


class Parasites(unittest.TestCase):
    def test_blood_fluke_doubles_every_turn(self):
        b = fight()
        b.fighter("A").hp = 50000
        play(b, "x25", "d2")
        self.assertEqual(b.fighter("B").hp, 100000 - 1000)                 # 1%
        play(b, "d1", "d1")
        play(b, "d1", "d1")
        self.assertEqual(b.fighter("B").hp, 100000 - 1000 - 2000 - 4000)   # 2%、4%
        self.assertEqual(b.fighter("A").hp, 50000 + 7000)                  # 吸到的加给自己

    def test_death_fluke_drains_and_sleeps_every_other_turn(self):
        b = fight()
        play(b, "x26", "d1")
        self.assertEqual(b.fighter("B").hp, 100000 - 10000)
        self.assertTrue(b.fighter("B").has_status("昏睡"))                 # 虫子的第 1 回合：让他睡
        self.assertEqual(b.waiting_for(), ["A"])                           # 所以下一回合乙出不了招
        b.choose("A", "d1")
        self.assertEqual(b.fighter("B").hp, 100000 - 20000)
        self.assertFalse(b.fighter("B").has_status("昏睡"))                # 虫子的第 2 回合：不睡
        play(b, "d1", "d1")
        self.assertTrue(b.fighter("B").has_status("昏睡"))                 # 第 3 回合又睡
        self.assertFalse(legal(fight(a="生化大师"), "A")["x26"]["legal"])   # 生化大师不能用

    def test_seed_spreads_to_the_bench_and_stays_there(self):
        b = fight(b=["范仲淹", "武圣", "拳术宗师"])
        b.fighter("A").hp = 50000
        play(b, "x29", "d1")
        team = b.players["B"].team
        self.assertEqual(team[0].hp, 100000 - 10000)
        self.assertEqual(b.fighter("A").hp, 50000 + 10000)                 # 吸到的加给放种子的人
        seeded = [f.name for f in team[1:] if "寄生种子" in f.parasites]
        self.assertEqual(len(seeded), 1)                                   # 传给了场下的一个人物
        benched = next(f for f in team[1:] if "寄生种子" in f.parasites)
        self.assertEqual(benched.hp, benched.max_hp)                       # 场下的不扣
        play(b, "d1", f"switch:{team.index(benched)}")
        self.assertIn("寄生种子", b.players["B"].team[0].parasites)         # 换下场，种子还在
        self.assertEqual(b.fighter("B").hp, benched.max_hp - int(benched.max_hp * 0.10))   # 一上场就开始扣

    def test_liver_fluke_steals_luck_and_survival(self):
        b = fight(b="饕餮")                                                # 饕餮有大难不死 3
        foe = b.fighter("B")
        foe.hp = 200000                                                    # 超出上限 5 万
        b.fighter("A").hp = 20000
        play(b, "x30", "d1")
        foe = b.fighter("B")
        self.assertEqual(foe.inner_level("大难不死"), 0)                    # 被吸走了
        self.assertEqual(foe.hp, 150000 - 15000)                           # 超出的一下被吸走，再吸 10%
        self.assertEqual(b.fighter("A").hp, 20000 + 50000 + 15000)
        b.fighter("B").hp = 140000
        play(b, "d1", "t1")                                                # 饕餮牙吸血：不能超过上限，也不能加命
        foe = b.fighter("B")
        self.assertEqual(foe.lives_total, 1)
        self.assertLessEqual(foe.hp, foe.max_hp)

    def test_liver_fluke_can_survive_a_cleanse(self):
        b = fight(b="饕餮")
        b.fighter("B").resources["万灵丹"] = 2
        play(b, "x30", "d1")
        b.choose("A", "d1")
        b.choose("B", "37")                                                # 万灵丹
        self.assertEqual(b.pending["reason"], "B的饕餮身上的华支睾吸虫靠吸来的大难不死活不活得下来")
        b.answer("A")                                                      # 放虫的人贼赢：虫子活下来
        settle(b)
        self.assertIn("华支睾吸虫", b.fighter("B").parasites)
        b.choose("A", "d1")
        b.choose("B", "37")
        b.answer("B")                                                      # 这次虫子没活下来
        settle(b, zei="B")
        self.assertNotIn("华支睾吸虫", b.fighter("B").parasites)
        self.assertEqual(b.fighter("B").inner_level("大难不死"), 3)         # 内功回来了

    def test_liver_fluke_blocks_evolution(self):
        b = fight(b="饕餮")
        foe = b.fighter("B")
        foe.lives_total = foe.lives_remaining = 5
        foe.parasites["华支睾吸虫"] = Parasite("华支睾吸虫", 1, "A")
        play(b, "d1", "d1")
        self.assertEqual(b.fighter("B").name, "饕餮")                       # 满 5 条命也进化不了

    def test_control_worm_lets_the_owner_pick_every_fifth_turn(self):
        b = fight()
        play(b, "x27", "d1")
        for _ in range(2):
            play(b, "d1", "d1")
            self.assertEqual(b.chooser("B"), "B")
        play(b, "d1", "d1")
        self.assertEqual(b.round, 5)
        self.assertEqual(b.chooser("B"), "A")                              # 第 5 个回合：B 的招由 A 来选
        self.assertEqual(b.view()["control"], {"B": "A"})
        play(b, "d1", "d1")
        self.assertEqual(b.chooser("B"), "B")

    def test_death_tapeworm_drains_or_takes_control(self):
        b = fight()
        b.choose("A", "x28")
        b.choose("B", "d1")
        self.assertEqual(b.pending["reason"], "B的范仲淹身上的死亡绦虫吸不吸得到")
        b.answer("A")                                                      # 三分之一：这种贼只出一次，放虫的人赢了才算
        settle(b)
        self.assertEqual(b.fighter("B").hp, 100000 - 75000)
        b.choose("A", "d1")
        b.choose("B", "d1")
        b.answer("B")                                                      # 没吸成
        self.assertEqual(b.pending["reason"], "死亡绦虫没吸成，能不能控制B的范仲淹")
        b.answer("A")                                                      # 控制住了
        settle(b)
        self.assertEqual(b.chooser("B"), "A")                              # 下一回合由 A 替 B 选招


class ControlOverTheNetwork(unittest.TestCase):
    def test_the_controller_picks_both_moves(self):
        room = Room("1", rng=random.Random(1))
        room.join("甲")
        room.join("乙")
        room.handle("A", {"t": "config", "team_size": 1, "zei": False, "timers": False})
        room.handle("A", {"t": "team", "names": ["范仲淹"]})
        room.handle("B", {"t": "team", "names": ["范仲淹"]})
        room.battle.fighter("B").counters["controlled_next"] = "A"
        room.handle("A", {"t": "choose", "action": "d1"})
        room.handle("B", {"t": "choose", "action": "d1"})                  # 第 1 回合照常
        self.assertEqual(room.battle.control, {"B": "A"})
        self.assertEqual(room.state_for("B")["need"], "wait")              # 乙被控制，等甲替他选
        state = room.state_for("A")
        self.assertEqual((state["need"], state["choose_for"]), ("choose", "A"))
        room.handle("A", {"t": "choose", "action": "d1"})
        state = room.state_for("A")
        self.assertEqual((state["need"], state["choose_for"]), ("choose", "B"))   # 选完自己的，再替乙选
        room.handle("A", {"t": "choose", "action": "0", "on_self": True})          # 让乙打他自己
        self.assertEqual(room.battle.round, 3)
        self.assertEqual(room.battle.fighter("B").hp, 100000 - 10000)
        self.assertEqual(room.state_for("B")["need"], "choose")            # 下一回合乙自己选


if __name__ == "__main__":
    unittest.main()
