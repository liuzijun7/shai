"""不依赖 gymnasium 的强化学习接口雏形。

训练时可以直接使用 ShaiEnv；后续若安装 Gymnasium，只需写一个很薄的 Adapter，
不需要改动战斗规则。
"""

from __future__ import annotations

from typing import Any

from engine import GameEngine
from game_data import SCENES, SKILLS


class ShaiEnv:
    """双智能体依次选招、回合统一结算的环境。

    ``step`` 返回 Gymnasium 风格的五元组，但动作暂时使用可读的技能编号字符串。
    ``current_side`` 表示下一步该由哪个智能体决策。
    """

    def __init__(self, character_a: str = "陶渊明", character_b: str = "武圣", seed: int | None = None):
        self.character_a = character_a
        self.character_b = character_b
        self.engine = GameEngine(character_a, character_b, seed)
        self._previous_hp = self._hp_snapshot()

    def reset(self, seed: int | None = None, character_a: str | None = None,
              character_b: str | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
        if character_a:
            self.character_a = character_a
        if character_b:
            self.character_b = character_b
        observation = self.engine.reset(self.character_a, self.character_b, seed)
        self._previous_hp = self._hp_snapshot()
        return observation, self._info()

    def legal_actions(self) -> list[dict[str, Any]]:
        return [action for action in self.engine.legal_actions() if action["legal"]]

    def action_mask(self) -> dict[str, int]:
        return {action["id"]: int(action["legal"]) for action in self.engine.legal_actions()}

    def step(self, action_id: str, destination: str | None = None):
        acting_side = self.engine.current_side
        result = self.engine.step(action_id, destination)
        rewards_by_side = {
            side: self._reward(side) if result.get("round_resolved") else 0.0
            for side in ("A", "B")
        }
        reward = rewards_by_side[acting_side]
        self._previous_hp = self._hp_snapshot()
        terminated = result["done"]
        truncated = False
        return result["observation"], reward, terminated, truncated, self._info(result["events"], rewards_by_side)

    def numeric_observation(self, perspective: str | None = None) -> list[float]:
        """提供一个稳定的基础向量；后续可在不动引擎的情况下扩充编码。"""
        perspective = perspective or self.engine.current_side
        order = (perspective, self.engine.other_side(perspective))
        vector: list[float] = []
        for side in order:
            f = self.engine.fighters[side]
            vector.extend([
                f.hp / max(1, f.max_hp),
                f.shield / max(1, f.max_shield) if f.max_shield else 0.0,
                f.lives_remaining / max(1, f.lives_total),
                f.radiation / 15.0,
                (f.scene_height + 3) / 15.0,
                f.resources["氧气"] / 10.0,
                f.resources["星体能量"] / 10.0,
                f.resources["超新星"] / 5.0,
                len(f.statuses) / 16.0,
                sum(p.count for p in f.parasites.values()) / 20.0,
            ])
        vector.append(1.0 if self.engine.current_side == perspective else 0.0)
        return vector

    def _reward(self, acting_side: str) -> float:
        other = self.engine.other_side(acting_side)
        now = self._hp_snapshot()
        damage_dealt = self._previous_hp[other] - now[other]
        damage_taken = self._previous_hp[acting_side] - now[acting_side]
        reward = (damage_dealt - damage_taken) / 100000.0
        if self.engine.done:
            if self.engine.winner == acting_side:
                reward += 10.0
            elif self.engine.winner == other:
                reward -= 10.0
        return reward

    def _hp_snapshot(self) -> dict[str, int]:
        return {side: f.hp + f.shield for side, f in self.engine.fighters.items()}

    def _info(self, events: list[str] | None = None, rewards_by_side: dict[str, float] | None = None) -> dict[str, Any]:
        return {
            "current_side": self.engine.current_side,
            "winner": self.engine.winner,
            "events": list(events or []),
            "rewards_by_side": dict(rewards_by_side or {"A": 0.0, "B": 0.0}),
            "action_mask": self.action_mask() if not self.engine.done else {},
        }
