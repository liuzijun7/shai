"""对局里的数据结构：状态、寄生虫、人物、玩家。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .data import LEARN_THRESHOLDS, MAX_INNER_LEVEL, SCENES


def _new_resources() -> dict[str, int]:
    return {"氧气": 10, "星体能量": 0, "超新星": 0, "万灵丹": 0, "海洋之心": 0, "酒": 0, "万能胶": 0}


@dataclass
class Status:
    name: str
    turns: int
    source: str | None = None       # 谁加的（"A" 或 "B"）
    layer: str = "body"             # "body" 作用在人身上，"shield" 作用在盾牌上
    unremovable: bool = False
    fresh: bool = True              # 刚加上的这一回合不减回合数


@dataclass
class Parasite:
    name: str
    count: int
    source: str
    age: int = 0
    layer: str = "body"


@dataclass
class Fighter:
    side: str
    character_id: str
    name: str
    max_hp: float
    hp: int
    distance: float
    inner: dict[str, int]
    initial_inner: dict[str, int]
    max_shield: int = 0
    shield: int = 0
    lives_total: int = 1
    lives_remaining: int = 1
    scene: str = "地面"
    statuses: dict[str, Status] = field(default_factory=dict)
    parasites: dict[str, Parasite] = field(default_factory=dict)
    resources: dict[str, int] = field(default_factory=_new_resources)
    radiation: int = 0
    counters: dict[str, Any] = field(default_factory=dict)
    defeated: bool = False
    used_shen: set[str] = field(default_factory=set)   # 这条命里已经用过的神技
    is_true_body: bool = False
    entered: bool = False           # 是否上过场（首次登场的被动只触发一次）
    # 每种内功学了多少下。学来的内功归玩家：同一个玩家的所有人物共用这一份（雨晨）。
    # 人物自带的内功（比如陶渊明的凌波微步 3 级）只有他自己有，换了人物就没有。
    learn_progress: dict[str, int] = field(default_factory=dict)
    devices: dict[str, int] = field(default_factory=dict)          # 造的装置：名字 -> 造了多少下
    # 借内功（宋濂）：现在向谁借。借的是对面场上的人物；那个人物下场或者死了，借来的内功就没有了。
    lender: "Fighter | None" = field(default=None, repr=False, compare=False)

    @property
    def scene_height(self) -> int:
        return int(SCENES[self.scene]["height"])

    def has_status(self, name: str) -> bool:
        return name in self.statuses and self.statuses[name].turns > 0

    def inner_level(self, name: str) -> int:
        """这种内功现在几级：自带的、学来的、借来的，取最高的。"""
        if self.has_status("封内"):
            return 0
        return max(self.own_level(name), self.borrowed_level(name))

    def learned_level(self, name: str) -> int:
        progress = int(self.learn_progress.get(name, 0))
        return min(MAX_INNER_LEVEL, sum(1 for need in LEARN_THRESHOLDS.get(name, ()) if progress >= need))

    def own_level(self, name: str) -> int:
        """不算借来的：人物自带的和玩家学来的，取高的。"""
        return max(int(self.inner.get(name, 0)), self.learned_level(name))

    def borrowed_level(self, name: str) -> int:
        lender = self.lender
        if lender is None or lender.defeated:
            return 0
        return lender.own_level(name)

    def own_inner(self) -> dict[str, int]:
        names = set(self.inner) | set(self.learn_progress)
        return {name: self.own_level(name) for name in names if self.own_level(name) > 0}

    def all_inner(self) -> dict[str, int]:
        """自带的、学来的、借来的内功合在一起，每种取最高的等级。"""
        merged = self.own_inner()
        if self.lender is not None and not self.lender.defeated:
            for name, level in self.lender.own_inner().items():
                merged[name] = max(int(merged.get(name, 0)), int(level))
        return merged

    def reset_resources(self) -> None:
        self.resources = _new_resources()


@dataclass
class Player:
    side: str
    team: list[Fighter]
    active: int = 0                 # 场上人物在 team 里的下标
    learn_progress: dict[str, int] = field(default_factory=dict)   # 学内功的进度：这个玩家所有的人物共用

    def __post_init__(self) -> None:
        for fighter in self.team:
            fighter.learn_progress = self.learn_progress

    @property
    def fighter(self) -> Fighter:
        return self.team[self.active]

    def bench(self) -> list[int]:
        """场下还活着、可以换上来的人物下标（真身不能主动换上）。"""
        return [i for i, f in enumerate(self.team)
                if i != self.active and not f.defeated and not f.is_true_body]

    def alive_any(self) -> bool:
        return any(not f.defeated for f in self.team)


class RuleError(ValueError):
    """玩家做了规则不允许的事（比如选了不能出的招）。"""


class NeedDecision(Exception):
    """结算到一半需要问玩家（贼、选下一个上场的人物）时抛出。

    引擎接住它，把局面退回到这次结算开始之前，把问题放进 ``Battle.pending``。
    玩家回答后，引擎从退回的局面重新结算，这一次直接用记下的答案。
    """

    def __init__(self, request: dict[str, Any]):
        super().__init__(request.get("reason", "需要玩家决定"))
        self.request = request
