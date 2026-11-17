"""新引擎用的静态数据。

人物表、招式表、场景表、内功表都从刘同学的 ``game_data.py`` 原样搬过来，
然后按雨晨 2026-11 的回答打补丁。补丁都集中在这个文件里，方便核对。
"""

from __future__ import annotations

import copy
from math import inf

import game_data as _gd

SCENES = _gd.SCENES
VERTICAL_SCENES = _gd.VERTICAL_SCENES
SEAL_BY_ATTRIBUTE = _gd.SEAL_BY_ATTRIBUTE
CONTROL_STATUSES = _gd.CONTROL_STATUSES
DAMAGE_STATUSES = _gd.DAMAGE_STATUSES
SELF_BUFFS = _gd.SELF_BUFFS
ALL_INNER_NAMES = _gd.ALL_INNER_NAMES

MAX_INNER_LEVEL = 4  # 雨晨：内功封顶 4 级

# 内功各级的数值：1 到 3 级按刘同学的引擎；4 级是按本子的规律补的。
INNER_VALUES = copy.deepcopy(_gd.INNER_VALUES)
_LEVEL4 = {
    "幸运": 2 / 3, "大难不死": 2 / 3, "虚空神术": 2 / 3,
    "凌波微步": 4, "幻影": 4,
    "蛮力": 0.70, "铁布衫": 0.70, "弹性形变": 0.70, "生机勃勃": 0.40,
    "重于泰山": 1, "轻于鸿毛": 1, "昏沉大法": 2, "放射性": 5,
}
for _name, _value in _LEVEL4.items():
    INNER_VALUES[_name][4] = _value

# ---------- 招式 ----------

SKILLS = copy.deepcopy(_gd.SKILLS)

# 纵目青铜怪的换血是一个要选的招，不是每回合自动（雨晨）。
SKILLS["c_swap_hp"] = _gd.skill(
    "c_swap_hp", "换血", distance=12, effect="swap_hp", character="纵目青铜怪",
    description="和对手互换体力和体力上限。",
)

# 本子上圈了“先”字的招：比普通招先出手，比神技慢。
FIRST_STRIKE_IDS = {"21", "23", "24"}  # 雷神之怒、太阳黑子爆、伽马射线

# 出手顺序的档位，数字大的先出手。
TIER_NORMAL, TIER_FIRST, TIER_SHEN, TIER_LINGBO4, TIER_SWITCH = 0, 20, 30, 40, 60

# ---------- 人物 ----------

CHARACTERS = copy.deepcopy(_gd.CHARACTERS)
_BY_NAME = {c["name"]: c for c in CHARACTERS.values()}

_BY_NAME["武圣"]["lives"] = 2  # 雨晨：2 条命
_BY_NAME["纵目青铜怪"]["traits"].discard("回合末换血")
_BY_NAME["纵目青铜怪"]["traits"].add("体力无上限")
_BY_NAME["纵目青铜怪"]["skills"] = tuple(_BY_NAME["纵目青铜怪"]["skills"]) + ("c_swap_hp",)

# 超级真身：一方的人物全部死光以后上场（本子 ⑫）。
TRUE_BODY_ID = "0"
# 内功按本子《人物总结》写的那几种：虚、大、幸、凌、幻、蛮、铁、暴 4 级（暴击还没做）。
_TRUE_BODY_INNER = ("虚空神术", "大难不死", "幸运", "凌波微步", "幻影", "蛮力", "铁布衫")
CHARACTERS[TRUE_BODY_ID] = _gd.character(
    0, "超级真身", 200000, inf, {name: 4 for name in _TRUE_BODY_INNER}, traits=["真身"],
    description="虚空神术、大难不死、幸运、凌波微步、幻影、蛮力、铁布衫 4 级；体力 2 万以下自动回满；大难不死后回满。",
)

# 大招憋不回去的人物（本子《人物总结》“憋大招：不”，加上雨晨说的牛顿）。
UNBLOCKABLE_CHARACTERS = {"陶渊明", "纵目青铜怪", "龙王", "生化大师", "范仲淹", "库巴", "牛顿"}

# 各人物的“大招”：专属招之外，还包括由人物改写了数值的通用招。
SIGNATURE_SKILL_NAMES = {
    "龙王": {"洪水", "寒潮", "地震", "台风"},
    "肥龙王": {"洪水", "寒潮", "地震", "火山爆发"},
    "范仲淹": {"洪水"},
    "牛顿": {"麒麟芒星", "云端之星"},
    "生化大师": {"硫酸", "乙醚", "猪带绦虫", "昏睡绦虫", "蚂蟥"},
    "灵力圣使": {"圣六式空凌"},
}

# 第一版可以选的人物。进化版要靠进化得到；赵先龙、三鲍太监在待办里。
EVOLVED_NAMES = {"肥饕餮", "肥龙王", "猪带小天王", "蚂蟥大仙", "魔法师"}
DEFERRED_NAMES = {"赵先龙", "三鲍太监"}
SELECTABLE_NAMES = tuple(
    c["name"] for c in CHARACTERS.values()
    if c["name"] not in EVOLVED_NAMES | DEFERRED_NAMES and c["id"] != TRUE_BODY_ID
)

CHARACTER_NAME_TO_ID = {c["name"]: key for key, c in CHARACTERS.items()}

COMMON_SKILL_IDS = _gd.COMMON_SKILL_IDS
SYSTEM_ACTION_IDS = _gd.SYSTEM_ACTION_IDS

# 还没做的专属招：先不出现在按钮里。
# 不出现在招式按钮里的专属动作：范仲淹换人、占卜还没做；牛顿选场景改成了回合开始时的免费选择。
NOT_YET_IMPLEMENTED_SKILLS = {"t7", "t8", "c_newton_scene"}


def character_skill_ids(character_data: dict) -> tuple[str, ...]:
    extra = tuple(s for s in character_data.get("skills", ()) if s not in NOT_YET_IMPLEMENTED_SKILLS)
    return COMMON_SKILL_IDS + SYSTEM_ACTION_IDS + extra


def is_signature(character_name: str, spec: dict) -> bool:
    """这个招是不是这个人物的大招。"""
    return spec.get("character") == character_name or spec["name"] in SIGNATURE_SKILL_NAMES.get(character_name, ())
