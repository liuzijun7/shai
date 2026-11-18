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
SELF_BUFFS = set(_gd.SELF_BUFFS) | {"心眼"}      # 给自己加的好状态
ALL_INNER_NAMES = _gd.ALL_INNER_NAMES

MAX_INNER_LEVEL = 4  # 雨晨：内功封顶 4 级

# 内功各级的数值：1 到 3 级按刘同学的引擎；4 级是按本子的规律补的。
INNER_VALUES = copy.deepcopy(_gd.INNER_VALUES)
_LEVEL4 = {
    "幸运": 2 / 3, "大难不死": 2 / 3, "虚空神术": 2 / 3,
    "凌波微步": 4, "幻影": 5,          # 幻影 4 级：每回合一个招算 5 个招（雨晨）
    "蛮力": 0.70, "铁布衫": 0.70, "弹性形变": 0.70, "生机勃勃": 0.40,
    "重于泰山": 1, "轻于鸿毛": 1, "昏沉大法": 2, "放射性": 5,
}
for _name, _value in _LEVEL4.items():
    INNER_VALUES[_name][4] = _value

# 引擎里原来没有、本子内功表里有的三种内功。
INNER_VALUES["暴击"] = {1: 1 / 8, 2: 1 / 4, 3: 1 / 2, 4: 2 / 3}      # 这么大的概率伤害翻倍
INNER_VALUES["重贼"] = {1: 1, 2: 2, 3: 3, 4: 3}                      # 贼输了可以重来几次
INNER_VALUES["内功栏"] = {1: 1, 2: 2, 3: 3, 4: 3}                    # 可以多学几种内功

# ---------- 学内功 ----------
# 雨晨：学一次占一个回合的出招；任何内功都能学；进度跟着人物；开局自带的不算在上限里；
# 上限先做成可以调的。学多少次升一级按本子的内功表。
MAX_LEARNED_INNER = 3
LEARN_THRESHOLDS = {
    "大难不死": (5, 10, 20, 30), "凌波微步": (5, 10, 20, 30), "幻影": (5, 10, 20, 30),
    "生机勃勃": (5, 10, 20), "虚空神术": (5, 10, 20, 30), "轻于鸿毛": (5, 10, 15),
    "重于泰山": (5, 10, 15), "幸运": (5, 10, 20, 30), "蛮力": (5, 10, 20), "铁布衫": (5, 10, 20),
    "暴击": (20, 40, 60), "弹性形变": (5, 10, 20, 40), "重贼": (50, 100, 200),
    "昏沉大法": (30, 60, 90), "内功栏": (50, 100, 200), "放射性": (100, 200, 350, 500),
}
LEARN_MULTIPLIER = {"陶渊明": 3, "宋濂": 3, "欧阳修": 5}                # 学一下算几下

# ---------- 招式 ----------

SKILLS = copy.deepcopy(_gd.SKILLS)

# 招的属性，雨晨 2026-11-18 逐个定的（引擎原来的写法在括号里）。
SKILLS["12"]["attributes"] = ("特技",)                 # 昏睡咒（魔法）
SKILLS["3"]["attributes"] = ("魔法",)                  # 点穴手（物理）
SKILLS["5"]["attributes"] = ("物理",)                  # 吼，也就是狮子吼（魔法）
SKILLS["9"]["attributes"] = ("物理", "地理")           # 地震（地理）
SKILLS["10"]["attributes"] = ("物理", "地理")          # 寒潮（地理）
SKILLS["21"]["attributes"] = ("物理", "魔法", "特技")  # 雷神之怒（特技）
SKILLS["28"]["attributes"] = ("化学", "特技")          # 硫酸（化学）
SKILLS["29"]["attributes"] = ("化学", "特技")          # 乙醚（化学）
# 摄魂大法本来就是魔法。昏睡绦虫、蚂蟥、太阳黑子爆照引擎，不改。

# 能往上打的招（雨晨）。不能打全宇宙的人物，在下面只有用这几个招、或者神技，才打得到上面的人。
UP_REACH_IDS = {"6", "x7", "x8", "21", "c_newton_cloud"}   # 圣六式空凌、一零二仙折、七八五重雷、雷神之怒、云端之星
LOAN_TURNS = 5                                              # 宋濂借一种内功最多借这么多回合（本子）

# 纵目青铜怪的换血是一个要选的招，不是每回合自动（雨晨）。
SKILLS["c_swap_hp"] = _gd.skill(
    "c_swap_hp", "换血", distance=12, effect="swap_hp", character="纵目青铜怪",
    description="和对手互换体力和体力上限。",
)

# ---------- 本子里有、引擎里没有的招（第一批：本子上效果写得明白的） ----------
# 雨晨：无限模式下的伤害“你先照同档的招类推出一张表，我来改”。
# 伤害、防御、距离都在下面这张表里，要改就改这里的数字。
# 距离是引擎的概念，本子没有：本子写了“能打到天上”的招照雷神之怒给 3，其余给 0。
# 本子的防御有 5 档，引擎只有 4 档，本子写防 5 的这里记成 4（引擎对火山爆发、究极吸取也是这样处理的）。


def _extra(skill_id, name, attributes, damage, statuses, defense, distance, effect=None, description="", **more):
    spec = _gd.skill(skill_id, name, attributes, damage, statuses, defense, distance,
                     effect=effect, description=description)
    spec.update(more)
    SKILLS[skill_id] = spec


_SEAL_ALL_BUT_SHEN = [(seal, 5) for attribute, seal in SEAL_BY_ATTRIBUTE.items() if attribute != "神技"]

_extra("x1", "天雷", ["物理"], 15000, [("昏睡", 1)], 2, 3)
_extra("x2", "芒星", ["物理"], 10000, [("封品", 4)], 2, 0)
_extra("x3", "麒麟", ["物理"], 20000, [("封生", 4)], 2, 0)
_extra("x4", "藤蔓抽打", ["物理"], 20000, [], 3, 0, effect="to_scene", scene="雨林",
       description="把对手打进雨林。")
_extra("x5", "泥石流", ["地理"], 10000, [], 1, 0, effect="lower_target", description="对手往下掉一层。")
_extra("x6", "千里寒极冰", ["物理"], 40000, [], 4, 0, effect="to_scene", scene="南极",
       description="把对手打进南极。")
_extra("x7", "一零二仙折", ["物理"], 20000, _SEAL_ALL_BUT_SHEN, 4, 3, effect="drop_ground",
       description="除了神技，对手所有属性的招封 5 回合；对手掉到地面。先手，必中。")
_extra("x8", "七八五重雷", ["物理"], 0, [("昏睡", 2)], 4, 3)
_extra("x9", "行星撞地球", ["物理", "地理"], 90000, [("昏睡", 4)], 4, 3, effect="planet",
       description="要花 3 个星体能量和 1 个超新星。对手掉到地面，累计辐射 1 次。先手，必中。")
_extra("x10", "焚风", ["物理", "特技", "地理"], 20000, [("点燃", 2)], 3, 3, effect="foehn",
       description="吹掉对手的万能胶，把对手刮回地面。")
_extra("x11", "布拉风", ["物理", "特技", "地理"], 30000, [("昏睡", 5)], 4, 3, effect="to_scene", scene="南极",
       description="把对手刮到南极。")
_extra("x12", "九十二三弑", ["物理"], 9000, [("封神", 5)], 3, 0, effect="u92",
       description="一半的可能让对手昏睡 3 回合；累计辐射 1 次。")
_extra("x13", "三聚氰胺", ["化学", "物品"], 0, [], 1, 0, effect="melamine",
       description="对手手里的万灵丹全部失效。")

# 心眼（雨晨）：魔法。5 回合内自己所有的招必中，对面的虚空神术躲不开。
_extra("x14", "心眼", ["魔法"], 0, [("心眼", 5)], None, 0, effect="self_status", target="self",
       description="5 回合内自己所有的招必中，对面的虚空神术躲不开。")

EXTRA_SKILL_IDS = tuple(key for key in SKILLS if key.startswith("x"))

# 所有打对手的招都可以改成打自己（雨晨）。这几样对自己用没有意义，不让选。
NO_SELF_EFFECTS = {"swap_character", "swap_hp", "divination"}

# 本子上圈了“先”字的招：比普通招先出手，比神技慢。
FIRST_STRIKE_IDS = {"21", "23", "24", "x7", "x9"}  # 雷神之怒、太阳黑子爆、伽马射线、一零二仙折、行星撞地球
# 本子上圈了“必”字的招：必中（γ 射线本来就不走闪避）。
SURE_HIT_IDS = {"x7", "x9"}
FIRE_SKILL_NAMES = {"火山爆发", "百步烈烧", "千步烈烧", "焚风"}             # “免疫火系”挡这些
ICE_SKILL_NAMES = {"寒潮", "极光", "灵气寒霜指", "千里寒极冰"}               # “免疫冰系”挡这些

# 出手顺序的档位，数字大的先出手。
TIER_NORMAL, TIER_FIRST, TIER_SHEN, TIER_LINGBO4, TIER_SWITCH, TIER_FAN_SWAP = 0, 20, 30, 40, 60, 70

# 范仲淹的换人（雨晨）：和对面场上的人物互换，对面那个人物连同内功和所有属性都归你，范仲淹归对面。
SKILLS["t7"]["description"] = "和对面场上的人物互换：那个人物连同内功、体力、状态都归你，范仲淹归对面。比普通换人还先生效。"

# ---------- 人物 ----------

CHARACTERS = copy.deepcopy(_gd.CHARACTERS)
_BY_NAME = {c["name"]: c for c in CHARACTERS.values()}

_BY_NAME["武圣"]["lives"] = 2  # 雨晨：2 条命
_BY_NAME["巫师"]["inner"]["幻影"] = 4  # 雨晨：巫师的幻影是 4 级
_BY_NAME["宋濂"]["lives"] = 1  # 本子：血十万，没写多条命。引擎原来给了 3 条命，雨晨说不对
_BY_NAME["宋濂"]["traits"].add("借内功")  # 从对面场上人物的内功里选一种来借；那个人物下场或者死了就没有了

# 能打全宇宙的人物（本子《人物总结》“全宇宙”一栏打勾的，加上进化版里写了“全宇宙”的）。
# 本子的注 ②：能打全场的人无论出什么招都可以打全场。
UNIVERSE_NAMES = {"武圣", "巫师", "纵目青铜怪", "龙王", "拳术宗师", "灵力圣使", "牛顿", "库巴", "达伽马",
                  "肥饕餮", "猪带小天王", "蚂蟥大仙", "魔法师", "肥龙王"}      # 肥龙王：雨晨说能
for _name in UNIVERSE_NAMES:
    _BY_NAME[_name]["distance"] = inf
_BY_NAME["拳术宗师"]["inner"]["暴击"] = 3  # 本子：暴击、蛮力、铁布衫 3 级
_BY_NAME["纵目青铜怪"]["traits"].discard("回合末换血")
_BY_NAME["纵目青铜怪"]["traits"].add("体力无上限")
_BY_NAME["纵目青铜怪"]["traits"].add("透视")   # 本子 ⑤。雨晨：对手先选，青铜怪看到后再选
_BY_NAME["纵目青铜怪"]["skills"] = tuple(_BY_NAME["纵目青铜怪"]["skills"]) + ("c_swap_hp",)

# 超级真身：一方的人物全部死光以后上场（本子 ⑫）。
TRUE_BODY_ID = "0"
# 内功按本子《人物总结》写的那几种：虚、大、幸、凌、幻、蛮、铁、暴 4 级（暴击还没做）。
_TRUE_BODY_INNER = ("虚空神术", "大难不死", "幸运", "凌波微步", "幻影", "蛮力", "铁布衫")
CHARACTERS[TRUE_BODY_ID] = _gd.character(
    0, "超级真身", 200000, inf, {name: 4 for name in _TRUE_BODY_INNER}, traits=["真身"],
    description="虚空神术、大难不死、幸运、凌波微步、幻影、蛮力、铁布衫 4 级；体力 2 万以下自动回满；大难不死后回满。",
)

# 进化版里本子明写、引擎里没有的两条。
_BY_NAME["猪带小天王"]["traits"].add("体力无上限")   # 本子：上限无限
_BY_NAME["蚂蟥大仙"]["inner"]["重贼"] = 2             # 本子：含重贼 2

# ---------- 进化和衰变 ----------
# 回合数只算在场上的回合。衰变时放的射线写在最后一格。
EVOLVE_AFTER_TURNS = {"生化大师": (10, "猪带小天王"), "猪带小天王": (20, "蚂蟥大仙")}
DECAY_AFTER_TURNS = {"蚂蟥大仙": (10, "猪带小天王", "γ"), "猪带小天王": (10, "生化大师", "β")}
EVOLVE_AT_LIVES = {"饕餮": (5, "肥饕餮")}              # 命数达到这么多就进化
DECAY_BELOW_LIVES = {"肥饕餮": (5, "饕餮", "β")}       # 命数少于这么多就衰变
BETA_RAY = {"hp_ratio": 0.30, "radiation": 2}          # 本子招式表：β 射线 30%，累计辐射 2 次

# 大招憋不回去的人物（本子《人物总结》“憋大招：不”，加上雨晨说的牛顿）。
# 猪带小天王是生化大师进化来的，本子没单独写，先和生化大师一样。
UNBLOCKABLE_CHARACTERS = {"陶渊明", "纵目青铜怪", "龙王", "生化大师", "猪带小天王", "范仲淹", "库巴", "牛顿"}

# 各人物的“大招”：专属招之外，还包括由人物改写了数值的通用招。
SIGNATURE_SKILL_NAMES = {
    "龙王": {"洪水", "寒潮", "地震", "台风"},
    "肥龙王": {"洪水", "寒潮", "地震", "火山爆发"},
    "范仲淹": {"洪水"},
    "牛顿": {"麒麟芒星", "云端之星"},
    "生化大师": {"硫酸", "乙醚", "猪带绦虫", "昏睡绦虫", "蚂蟥"},
    "猪带小天王": {"硫酸", "乙醚", "猪带绦虫", "昏睡绦虫", "蚂蟥"},
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

# ---------- 粒子加速器（本子 ⑩） ----------
# 造 10 下可以打：一下 3 万加 3 次辐射。再造 10 下：一下 5 万加 5 次辐射，不限场景。
# 雨晨：造一下占一个回合；“冷 1”在无限模式下不算。
ACCELERATOR_SMALL = {"builds": 10, "damage": 30000, "radiation": 3}
ACCELERATOR_BIG = {"builds": 20, "damage": 50000, "radiation": 5}
SKILLS["sys_build_accelerator"] = _gd.skill(
    "sys_build_accelerator", "造粒子加速器", target="self", effect="build_accelerator", action_kind="build")
SKILLS["sys_fire_accelerator"] = _gd.skill(
    "sys_fire_accelerator", "粒子加速器", damage=ACCELERATOR_SMALL["damage"], effect="accelerator")


def accelerator_level(builds: int) -> dict | None:
    """造了这么多下的粒子加速器现在是哪一档；还没造好返回 None。"""
    if builds >= ACCELERATOR_BIG["builds"]:
        return ACCELERATOR_BIG
    if builds >= ACCELERATOR_SMALL["builds"]:
        return ACCELERATOR_SMALL
    return None


COMMON_SKILL_IDS = _gd.COMMON_SKILL_IDS
SYSTEM_ACTION_IDS = _gd.SYSTEM_ACTION_IDS + ("sys_build_accelerator", "sys_fire_accelerator")

# 不出现在招式按钮里的专属动作：占卜和牛顿选场景都改成了回合开始时的免费选择。
NOT_YET_IMPLEMENTED_SKILLS = {"t8", "c_newton_scene"}


def character_skill_ids(character_data: dict) -> tuple[str, ...]:
    extra = tuple(s for s in character_data.get("skills", ()) if s not in NOT_YET_IMPLEMENTED_SKILLS)
    return COMMON_SKILL_IDS + EXTRA_SKILL_IDS + SYSTEM_ACTION_IDS + extra


def is_signature(character_name: str, spec: dict) -> bool:
    """这个招是不是这个人物的大招。"""
    return spec.get("character") == character_name or spec["name"] in SIGNATURE_SKILL_NAMES.get(character_name, ())
