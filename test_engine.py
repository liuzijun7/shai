import unittest

from engine import GameEngine, Status
from game_data import CHARACTERS
from extension_api import GameCommand, GameSessionAdapter
from rl_env import ShaiEnv


class EngineRuleTests(unittest.TestCase):
    def test_normal_attack_is_untyped_10000(self):
        game = GameEngine("陶渊明", "武圣", seed=1)
        game.step("0")
        self.assertEqual(game.fighters["B"].hp, 100000)  # A、B都选完才结算
        game.step("d2")
        self.assertEqual(game.fighters["B"].hp, 90000)

    def test_shield_takes_damage_without_overflow(self):
        game = GameEngine("陶渊明", "巫师", seed=1)
        game.fighters["B"].shield = 5000
        game.step("0")
        game.step("d2")
        self.assertEqual(game.fighters["B"].shield, 0)
        self.assertEqual(game.fighters["B"].hp, 50000)

    def test_sealed_attribute_is_greyed_but_normal_attack_remains(self):
        game = GameEngine("陶渊明", "武圣", seed=1)
        game.fighters["A"].statuses["封物"] = Status("封物", 3, "B", fresh=False)
        actions = {item["id"]: item for item in game.legal_actions()}
        self.assertFalse(actions["3"]["legal"])
        self.assertTrue(actions["0"]["legal"])

    def test_iron_shirt_means_only_take_p_percent(self):
        game = GameEngine("三鲍太监", "拳术宗师", seed=1)
        game.fighters["A"].shield = 0
        game.fighters["B"].shield = 0
        game.step("0")
        game.step("d2")
        self.assertEqual(game.fighters["B"].hp, 95000)

    def test_sleep_does_not_refresh(self):
        game = GameEngine("陶渊明", "武圣", seed=1)
        target = game.fighters["B"]
        game._apply_status(target, "昏睡", 1, "A", force_body=True)
        game._apply_status(target, "昏睡", 5, "A", force_body=True)
        self.assertEqual(target.statuses["昏睡"].turns, 1)

    def test_other_status_takes_longest_duration(self):
        game = GameEngine("陶渊明", "武圣", seed=1)
        target = game.fighters["B"]
        game._apply_status(target, "烧伤", 2, "A", force_body=True)
        game._apply_status(target, "烧伤", 5, "A", force_body=True)
        self.assertEqual(target.statuses["烧伤"].turns, 5)

    def test_radiation_kills_all_lives_and_ignores_revival(self):
        game = GameEngine("陶渊明", "宋濂", seed=1)
        game._add_radiation(game.fighters["B"], 15, "A", "测试辐射")
        self.assertTrue(game.fighters["B"].defeated)
        self.assertEqual(game.fighters["B"].lives_remaining, 0)

    def test_radiation_immunity_prevents_accumulation(self):
        game = GameEngine("陶渊明", "纵目青铜怪", seed=1)
        before = game.fighters["B"].radiation
        game._add_radiation(game.fighters["B"], 15, "A", "测试辐射")
        self.assertEqual(game.fighters["B"].radiation, before)
        self.assertFalse(game.fighters["B"].defeated)

    def test_character_plus_skill_range_uses_height_gap(self):
        game = GameEngine("拳术宗师", "武圣", seed=1)
        game.fighters["B"].scene = "宇宙"
        actions = {item["id"]: item for item in game.legal_actions()}
        self.assertFalse(actions["0"]["legal"])
        self.assertTrue(actions["6"]["legal"])

    def test_lost_life_resets_state_and_resources(self):
        game = GameEngine("陶渊明", "宋濂", seed=2)
        target = game.fighters["B"]
        target.hp = 1
        target.scene = "宇宙"
        target.resources["星体能量"] = 7
        target.statuses["烧伤"] = Status("烧伤", 3, "A")
        game._apply_basic_damage(game.fighters["A"], target, 10000, "测试")
        self.assertEqual(target.lives_remaining, 2)
        self.assertEqual(target.hp, target.max_hp)
        self.assertEqual(target.scene, "地面")
        self.assertEqual(target.resources["星体能量"], 0)
        self.assertEqual(target.statuses, {})

    def test_rl_environment_exposes_mask_and_step(self):
        env = ShaiEnv("陶渊明", "武圣", seed=1)
        self.assertEqual(env.action_mask()["0"], 1)
        observation, reward, terminated, truncated, info = env.step("0")
        self.assertEqual(observation["current_side"], "B")
        self.assertEqual(reward, 0)
        observation, reward, terminated, truncated, info = env.step("d2")
        self.assertGreater(info["rewards_by_side"]["A"], 0)
        self.assertLess(info["rewards_by_side"]["B"], 0)
        self.assertFalse(terminated)
        self.assertFalse(truncated)
        self.assertIn("action_mask", info)

    def test_every_character_can_execute_each_initially_legal_action(self):
        for data in CHARACTERS.values():
            probe = GameEngine(data["name"], "三鲍太监", seed=7)
            probe.fighters["A"].resources.update({"星体能量": 20, "超新星": 10, "万灵丹": 1, "酒": 2})
            legal_ids = [item["id"] for item in probe.legal_actions() if item["legal"]]
            for action_id in legal_ids:
                with self.subTest(character=data["name"], action=action_id):
                    game = GameEngine(data["name"], "三鲍太监", seed=7)
                    game.fighters["A"].resources.update({"星体能量": 20, "超新星": 10, "万灵丹": 1, "酒": 2})
                    destination = "宇宙边缘" if action_id == "c_newton_scene" else None
                    game.step(action_id, destination)
                    if not game.done:
                        game.step("d1")

    def test_transport_neutral_session_api(self):
        session = GameSessionAdapter(GameEngine("陶渊明", "武圣", seed=1))
        received = []
        unsubscribe = session.subscribe(received.append)
        result = session.submit(GameCommand(actor="A", action_id="0", client_action_id="test-1"))
        unsubscribe()
        self.assertTrue(result.accepted)
        self.assertEqual(result.client_action_id, "test-1")
        self.assertEqual(len(received), 1)
        self.assertEqual(result.snapshot["protocol"], "shai-session/1")
        self.assertIn('"accepted":true', result.to_json())

    def test_matching_numeric_defense_blocks_without_initiative(self):
        game = GameEngine("陶渊明", "武圣", seed=1)
        game.step("3")  # 点穴手的防御字段为1
        game.step("d1")
        self.assertNotIn("封物", game.fighters["B"].statuses)
        self.assertTrue(any("成功防御" in line for line in game.log))

    def test_wrong_numeric_defense_does_not_block(self):
        game = GameEngine("陶渊明", "武圣", seed=1)
        game.step("3")
        game.step("d2")
        self.assertIn("封物", game.fighters["B"].statuses)

    def test_mirror_reflects_j_skill_to_user(self):
        game = GameEngine("三鲍太监", "武圣", seed=1)
        game.step("20")  # X光可被j防御
        game.step("dj")
        self.assertEqual(game.fighters["A"].radiation, 5)
        self.assertEqual(game.fighters["B"].radiation, 0)

    def test_block_divine_turns_skill_into_normal_attack_and_seals_user(self):
        game = GameEngine("三鲍太监", "武圣", seed=1)
        game.step("31")
        game.step("ds")
        self.assertIn("封神", game.fighters["A"].statuses)
        self.assertEqual(game.fighters["B"].hp, 90000)

    def test_first_actor_can_seal_later_selected_skill_into_normal_attack(self):
        game = GameEngine("陶渊明", "武圣", seed=1)
        game.step("3")       # 凌波3，点穴手先施加封物
        game.step("t4")      # 武圣选择物理技能，结算时变普通攻击
        self.assertIn("封物", game.fighters["B"].statuses)
        self.assertTrue(any("自动改为普通攻击" in line for line in game.log))

    def test_panacea_must_be_collected_before_use(self):
        game = GameEngine("三鲍太监", "武圣", seed=1)
        actions = {item["id"]: item for item in game.legal_actions()}
        self.assertFalse(actions["37"]["legal"])
        game.step("sys_collect_panacea")
        game.step("d1")
        self.assertEqual(game.fighters["A"].resources["万灵丹"], 1)
        game.fighters["A"].statuses["烧伤"] = Status("烧伤", 3, "B", fresh=False)
        game.step("37")
        game.step("d1")
        self.assertNotIn("烧伤", game.fighters["A"].statuses)
        self.assertEqual(game.fighters["A"].resources["万灵丹"], 0)

    def test_collecting_glue_applies_it_immediately_and_fire_removes_it(self):
        game = GameEngine("三鲍太监", "武圣", seed=1)
        game.step("sys_collect_glue")
        game.step("d1")
        self.assertIn("万能胶", game.fighters["A"].statuses)
        game._apply_status(game.fighters["A"], "点燃", 2, "B", force_body=True)
        self.assertNotIn("万能胶", game.fighters["A"].statuses)


if __name__ == "__main__":
    unittest.main(verbosity=2)
