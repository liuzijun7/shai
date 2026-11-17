"""随机对局：让两个随机出招的机器人打很多局，检查引擎不会出错、不会卡死。"""

import os
import random
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shai import Battle  # noqa: E402
from shai.data import SCENES, SELECTABLE_NAMES  # noqa: E402


def random_game(seed: int, zei: bool, team_size: int = 3, max_rounds: int = 200) -> Battle:
    rng = random.Random(seed)
    battle = Battle(rng.sample(SELECTABLE_NAMES, team_size), rng.sample(SELECTABLE_NAMES, team_size),
                    seed=seed, zei=zei)
    steps = 0
    while not battle.done and battle.round <= max_rounds:
        steps += 1
        assert steps < 20000, "对局没有推进"
        if battle.pending:
            request = battle.pending
            if request["kind"] == "choose":
                battle.answer(rng.choice(request["options"])["id"])
            else:
                options = list(request["sides"]) + ([None] if request["mode"] == "single" else [])
                battle.answer(rng.choice(options))
            continue
        for side in battle.waiting_for():
            actions = [a for a in battle.legal_actions(side) if a["legal"]]
            assert actions, f"{side} 没有任何能出的招"
            action = rng.choice(actions)
            destination = rng.choice(list(SCENES)) if action["effect"] == "choose_scene" else None
            battle.choose(side, action["id"], destination)
            if battle.pending or battle.done:
                break
    return battle


class Fuzz(unittest.TestCase):
    def test_random_games_with_zei(self):
        for seed in range(150):
            with self.subTest(seed=seed):
                random_game(seed, zei=True)

    def test_random_games_without_zei(self):
        finished = 0
        for seed in range(150):
            with self.subTest(seed=seed):
                finished += random_game(seed, zei=False).done
        self.assertGreater(finished, 0)


if __name__ == "__main__":
    unittest.main()
