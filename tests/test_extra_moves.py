"""本子里有、引擎里原来没有的招（第一批）。伤害是照同档的招类推的，等雨晨改。"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from shai import Battle  # noqa: E402
from shai.data import SKILLS, TIER_FIRST  # noqa: E402
from shai.model import Status  # noqa: E402
from test_battle import legal, play  # noqa: E402


def fight(a="武圣", b="武圣"):
    return Battle([a], [b], seed=1, true_body=False)


class ExtraMoves(unittest.TestCase):
    def test_thunder_hits_and_puts_to_sleep(self):
        b = fight()
        play(b, "x1", "d1")
        self.assertEqual(b.fighter("B").hp, 100000 - 15000)
        self.assertIn("B的武圣获得昏睡（1回合）。", b.log)

    def test_mangxing_and_qilin_seal_items_and_bio(self):
        b = fight()
        play(b, "x2", "d1")
        self.assertTrue(b.fighter("B").has_status("封品"))
        play(b, "x3", "d1")
        self.assertTrue(b.fighter("B").has_status("封生"))

    def test_vine_whip_sends_the_target_to_the_rainforest(self):
        b = fight()
        play(b, "x4", "d1")
        self.assertEqual(b.fighter("B").scene, "雨林")
        self.assertEqual(b.fighter("B").hp, 100000 - 20000 + 10000)     # 雨林每回合回 10%

    def test_mudslide_drops_the_target_one_layer(self):
        b = fight()
        play(b, "x5", "d2")
        self.assertEqual(b.fighter("B").scene_height, -1)

    def test_polar_ice_sends_to_antarctica_but_not_the_ice_immune(self):
        b = fight()
        play(b, "x6", "d1")
        self.assertEqual(b.fighter("B").scene, "南极")
        b = fight(b="宋濂")                                              # 宋濂免疫冰系
        play(b, "x6", "d1")
        self.assertEqual(b.fighter("B").scene, "地面")
        self.assertEqual(b.fighter("B").hp, 100000)

    def test_xianzhe_seals_everything_but_shen_and_always_hits(self):
        b = fight()
        foe = b.fighter("B")
        foe.scene = "平流层"
        foe.inner["虚空神术"] = 3
        self.assertEqual(legal(b, "A")["x7"]["tier"], TIER_FIRST)
        b.choose("A", "x7")
        b.choose("B", "d1")
        self.assertIsNone(b.pending)                                     # 必中：不用为闪避贼
        foe = b.fighter("B")
        self.assertEqual(foe.hp, 100000 - 20000)
        self.assertEqual(foe.scene, "地面")
        for seal in ("封物", "封魔", "封喉", "封品", "封土", "封化", "封生"):
            self.assertTrue(foe.has_status(seal), seal)
        self.assertFalse(foe.has_status("封神"))

    def test_planet_needs_resources_and_adds_radiation(self):
        b = fight()
        self.assertFalse(legal(b, "A")["x9"]["legal"])
        b.fighter("A").resources.update({"星体能量": 3, "超新星": 1})
        b.fighter("B").scene = "对流层"
        play(b, "x9", "d1")
        a, foe = b.fighter("A"), b.fighter("B")
        self.assertEqual((a.resources["星体能量"], a.resources["超新星"]), (0, 0))
        self.assertEqual(foe.hp, 100000 - 30000)
        self.assertEqual((foe.scene, foe.radiation), ("地面", 1))

    def test_foehn_blows_glue_away_and_brings_the_target_down(self):
        b = fight(b="范仲淹")                                            # 武圣免疫火系，换一个对手
        foe = b.fighter("B")
        foe.scene = "平流层"
        foe.statuses["万能胶"] = Status("万能胶", 5, "B")
        play(b, "x10", "d1")
        foe = b.fighter("B")
        self.assertFalse(foe.has_status("万能胶"))
        self.assertEqual(foe.scene, "地面")
        self.assertTrue(foe.has_status("点燃"))
        self.assertTrue(b.fighter("A").has_status("封喉"))               # 特技用完自己被封喉
        b = fight()                                                      # 武圣免疫火系：焚风整个无效
        b.fighter("B").scene = "平流层"
        play(b, "x10", "d1")
        self.assertEqual((b.fighter("B").scene, b.fighter("B").hp), ("平流层", 100000))

    def test_bora_no_longer_moves_or_sleeps(self):
        b = fight(b="范仲淹")                               # 雨晨改过：1 万，冰封 3 回合，不去南极也不昏睡
        play(b, "x11", "d1")
        self.assertEqual(b.fighter("B").scene, "地面")
        self.assertTrue(b.fighter("B").has_status("冰封"))
        self.assertFalse(b.fighter("B").has_status("昏睡"))

    def test_u92_seals_shen_and_may_put_to_sleep(self):
        b = fight()
        play(b, "x12", "d1", zei="A")
        foe = b.fighter("B")
        self.assertEqual(foe.hp, 100000 - 9000)
        self.assertTrue(foe.has_status("封神"))
        self.assertEqual(foe.radiation, 1)
        self.assertIn("B的武圣获得昏睡（3回合）。", b.log)
        b = fight()
        play(b, "x12", "d1", zei="B")
        self.assertNotIn("B的武圣获得昏睡（3回合）。", b.log)

    def test_xinyan_makes_every_move_hit_for_five_turns(self):
        b = fight(b="陶渊明")                               # 陶渊明有虚空神术 3
        play(b, "x14", "d1")
        self.assertTrue(b.fighter("A").has_status("心眼"))
        for _ in range(5):
            b.choose("A", "0")
            b.choose("B", "d2")
            self.assertIsNone(b.pending)                    # 不用为躲不躲得开贼
        self.assertEqual(b.fighter("B").hp, 150000 - 5 * 10000)
        self.assertFalse(b.fighter("A").has_status("心眼"))  # 5 回合用完了

    def test_sunspot_damage_is_forty_thousand(self):
        self.assertEqual(SKILLS["23"]["damage"], 40000)
        b = fight(b="范仲淹")
        b.fighter("A").resources["星体能量"] = 3
        play(b, "23", "d1")
        self.assertEqual(b.fighter("B").hp, 100000 - 40000)

    def test_panacea_needs_no_collecting_and_melamine_spoils_it(self):
        # 雨晨 2026-11-19：万灵丹不用收集，直接用。三聚氰胺让对手这条命里不能再用（这一条是我定的）。
        b = fight()
        actions = {a["id"]: a for a in b.legal_actions("B")}
        self.assertTrue(actions["37"]["legal"])
        self.assertNotIn("sys_collect_panacea", actions)
        play(b, "x13", "d2")
        blocked = {a["id"]: a for a in b.legal_actions("B")}["37"]
        self.assertFalse(blocked["legal"])
        self.assertIn("三聚氰胺", blocked["reason"])

    def test_da_gama_fires_gamma_rays_without_limit(self):
        # 雨晨 2026-11-19：达伽马的伽马射线可以无限用。不用花东西，不算“每条命一次”，用完也不给自己封喉。
        b = fight(a="达伽马", b="武圣")                                    # 武圣 2 条命
        b.choose("A", "24")
        b.choose("B", "d1")
        if b.pending:
            b.answer("B")                                                 # 臭伽马没出
        self.assertEqual(b.fighter("B").lives_remaining, 1)
        self.assertFalse(b.fighter("A").has_status("封喉"))
        self.assertTrue(legal(b, "A")["24"]["legal"])                     # 马上还能再放

    def test_every_extra_move_has_a_description_or_plain_effect(self):
        for key, spec in SKILLS.items():
            if key.startswith("x"):
                if spec["target"] == "enemy":
                    self.assertIn(spec["defense"], (1, 2, 3, 4, "j"), spec["name"])


if __name__ == "__main__":
    unittest.main()
