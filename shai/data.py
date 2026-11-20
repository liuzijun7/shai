"""新引擎用的静态数据。

人物表、招式表、场景表、内功表都从刘同学的 ``game_data.py`` 原样搬过来，
然后按雨晨 2026-11 的回答打补丁。补丁都集中在这个文件里，方便核对。
"""

from __future__ import annotations

import copy
from math import inf

import game_data as _gd

SCENES = dict(_gd.SCENES)

# 新场景（雨晨 2026-11-19 定的数）。火海、极乐世界先不做。
SCENES["雨林深处"] = {"height": 0, "heal": 0.20, "tree_multiplier": 2}     # 每回合回 20%；通天神树长得快一倍
SCENES["黑暗之城"] = {"height": 0, "hp_loss": 0.10}                        # 每回合扣 10%
SCENES["黑暗之城深处"] = {"height": 0, "hp_loss": 0.20}                    # 每回合扣 20%
# 地心深处：每回合扣 40%，学内功一下算三下，在这里的人打别人伤害加倍。
SCENES["地心深处"] = {"height": -4, "hp_loss": 0.40, "learn_multiplier": 3, "damage_multiplier": 2}
SPECIAL_ENTRY_SCENES = {"地心深处"}      # 不能直接选着去，也不会一层层掉进去：要被地震震满 10 下
QUAKES_TO_CORE = 10
TREE_GROWTHS = 10                        # 通天神树长满这么多次，这个玩家的神技不再限次数
BIG_BANG_COST = 50                       # 宇宙大爆炸要花的星体能量
VERTICAL_SCENES = _gd.VERTICAL_SCENES
SEAL_BY_ATTRIBUTE = _gd.SEAL_BY_ATTRIBUTE
CONTROL_STATUSES = set(_gd.CONTROL_STATUSES) | {"冰封"}     # 冰封：不能出打对手的招
DAMAGE_STATUSES = set(_gd.DAMAGE_STATUSES) | {"真火"}       # 真火：每回合烧掉体力上限的八分之一
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

# 伤害，雨晨 2026-11-19 逐个定的（引擎原来的数在括号里）。他觉得现在的伤害普遍偏高。
SKILLS["23"]["damage"] = 40000                         # 太阳黑子爆（10 万）
SKILLS["2"]["damage"] = 10000                          # 麒麟芒星（3 万）。牛顿用的还是他自己的 9 万
SKILLS["7"]["damage"] = 20000                          # 死亡笔记（3 万）
SKILLS["18"]["damage"] = 20000                         # 百步烈烧（3 万）
# 新招里：芒星、麒麟、千里寒极冰都是 1 万；行星撞地球 3 万。

# 能往上打的招，和它最高能打到哪一层（雨晨）。不能打全宇宙的人物，在下面只有用这些招、或者神技，
# 才打得到上面的人。在上面打下面、打同一层，什么招都行。
ATMOSPHERE_TOP = SCENES["电离层"]["height"]      # 大气层最高的一层
SPACE = SCENES["宇宙"]["height"]                 # 紧挨着大气层的那一层；它上面还有外太空、宇宙边缘
UP_REACH = {
    # 多高都打得到：圣六式空凌、一零二仙折、七八五重雷、雷神之怒、云端之星
    "6": inf, "x7": inf, "x8": inf, "21": inf, "c_newton_cloud": inf,
    # 只能打大气层之内（对流层、平流层、电离层）：天雷、布拉风、火山爆发、台风、寒潮、声波炮
    "x1": ATMOSPHERE_TOP, "x11": ATMOSPHERE_TOP, "11": ATMOSPHERE_TOP, "c_dragon_typhoon": ATMOSPHERE_TOP,
    "x24": ATMOSPHERE_TOP,
    "10": ATMOSPHERE_TOP, "13": ATMOSPHERE_TOP,
    # 最高只能打到宇宙，打不到外太空和宇宙边缘：行星撞地球、太阳黑子爆
    "x9": SPACE, "23": SPACE,
}
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
_extra("x3", "麒麟", ["物理"], 10000, [("封生", 4)], 2, 0)
_extra("x4", "藤蔓抽打", ["物理"], 20000, [], 3, 0, effect="to_scene", scene="雨林",
       description="把对手打进雨林。")
_extra("x5", "泥石流", ["地理"], 10000, [], 1, 0, effect="lower_target", description="对手往下掉一层。")
_extra("x6", "千里寒极冰", ["物理"], 10000, [], 4, 0, effect="to_scene", scene="南极",
       description="把对手打进南极。")
_extra("x7", "一零二仙折", ["物理"], 20000, _SEAL_ALL_BUT_SHEN, 4, 3, effect="drop_ground",
       description="除了神技，对手所有属性的招封 5 回合；对手掉到地面。先手，必中。")
_extra("x8", "七八五重雷", ["物理"], 0, [("昏睡", 2)], 4, 3)
_extra("x9", "行星撞地球", ["物理", "地理"], 30000, [("昏睡", 4)], 4, 3, effect="planet",
       description="要花 3 个星体能量和 1 个超新星。对手掉到地面，累计辐射 1 次。先手，必中。")
_extra("x10", "焚风", ["物理", "特技", "地理"], 20000, [("点燃", 2)], 3, 3, effect="foehn",
       description="吹掉对手的万能胶，把对手刮回地面。")
# 布拉风（雨晨改过）：1 万；不再把对手刮到南极，也不昏睡；对手冰封 3 回合。
_extra("x11", "布拉风", ["物理", "特技", "地理"], 10000, [("冰封", 3)], 4, 3,
       description="对手冰封 3 回合：不能出打对手的招。")
_extra("x12", "九十二三弑", ["物理"], 9000, [("封神", 5)], 3, 0, effect="u92",
       description="一半的可能让对手昏睡 3 回合；累计辐射 1 次。")
# 雨晨 2026-11-19：万灵丹不用收集，直接用。原来“对手手里的万灵丹全部失效”就没东西可废了，
# 先做成“对手这条命里不能再用万灵丹”（我定的，等雨晨确认）。
_extra("x13", "三聚氰胺", ["化学", "物品"], 0, [], 1, 0, effect="melamine",
       description="对手这条命里不能再用万灵丹。")

# 心眼（雨晨）：魔法。5 回合内自己所有的招必中，对面的虚空神术躲不开。
_extra("x14", "心眼", ["魔法"], 0, [("心眼", 5)], None, 0, effect="self_status", target="self",
       description="5 回合内自己所有的招必中，对面的虚空神术躲不开。")

# ---------- 第二批：雨晨 2026-11-19 逐个定的 ----------
_extra("x15", "真火", ["物理"], 10000, [("真火", 3)], 1, 0,
       description="对手被烧 3 回合，每回合烧掉体力上限的八分之一。")
_extra("x16", "九里烧真火", ["物理"], 30000, [("真火", 10)], 4, 0, effect="leave_antarctic",
       description="对手被烧 10 回合，每回合烧掉体力上限的八分之一。对手在南极的话赶回地面。")
_extra("x17", "激光", ["物理"], 10000, [], "j", 0, effect="laser",
       description="累计辐射 1 次。打中以后选三个属性，每个和对手贼一次，赢了那个属性封 3 回合。幻影对它不起作用。")
# 动感光波：雨晨说“先做，但是不显示，以后可能有用”。
_extra("x18", "动感光波", list(SEAL_BY_ATTRIBUTE), 0,
       [(seal, 10) for seal in SEAL_BY_ATTRIBUTE.values()] + [("昏睡", 10)], "j", 0,
       description="封全属性 10 回合，昏睡 10 回合。只有平面镜能防。")
_extra("x19", "通灵之手", ["魔法"], 0, [], 1, 0, effect="dispel",
       description="消掉自己身上一个坏特效，或者对手身上一个好特效，自己选。")
_extra("x20", "排山倒海", ["特技"], 0, [], 3, 0, effect="three_hits", hits=(10000, 20000, 30000),
       description="打三下：1 万、2 万、3 万。每下各贼一次，赢了才打中。")
_extra("x21", "通天神树", ["神技"], 0, [], None, 0, effect="grow_tree", target="self",
       description="用一次神树长一次（在雨林深处长两次），占一个回合。长满 10 次以后，你所有的神技不再限“每条命一次”。")
_extra("x22", "太极千叶闪", ["物理"], 10000, [], 4, 0, effect="to_scene", scene="雨林深处",
       description="打谁谁进雨林深处。")
_extra("x23", "宇宙大爆炸", [], 0, [], 1, 0, effect="big_bang",
       description="要花 50 个星体能量。对手这回合出了防御 1，对手赢整局；否则你赢整局。")
# 谁都能用的弱台风。龙王用他自己那个强的，不出现这一个。
_extra("x24", "台风", ["地理", "特技"], 10000, [("昏睡", 1)], 4, 0, effect="to_scene", scene="黑暗之城深处",
       description="把对手打进黑暗之城深处，昏睡 1 回合。")

# 虫子（雨晨 2026-11-19 定的效果，有几种和本子不一样，是他改过的）。
_extra("x25", "血吸虫", ["生物"], 0, [], 1, 0, effect="parasite", parasite="血吸虫",
       description="每回合吸血给自己：第 1 回合吸 1%，以后每回合翻倍，封顶 100%。")
_extra("x26", "死亡吸虫", ["物理", "特技", "生物"], 0, [], 4, 0, effect="parasite", parasite="死亡吸虫",
       description="每回合吸 10% 体力给自己；隔一回合让对手昏睡一次。生化大师一系不能用。")
_extra("x27", "控制绦虫", ["生物", "特技"], 0, [], 3, 0, effect="parasite", parasite="控制绦虫",
       description="放上去的下一回合，对手出什么招由你来选。以后每 5 回合再控制一次。")
_extra("x28", "死亡绦虫", ["特技", "生物"], 0, [], 4, 0, effect="parasite", parasite="死亡绦虫",
       description="每回合三分之一的可能吸走 75% 体力；没吸成的话，三分之一的可能下一回合由你替对手选招。")
_extra("x29", "寄生种子", ["生物"], 0, [], 2, 0, effect="parasite", parasite="寄生种子",
       description="每回合吸 10% 体力给自己，还会随机传给对手场下的一个人物。场下的不扣，上场就开始扣。换下场也还在。")
_extra("x30", "华支睾吸虫", ["生物"], 0, [], 3, 0, effect="parasite", parasite="华支睾吸虫",
       description="吸走对手的幸运和大难不死；每回合吸 10% 体力给自己；对手的体力不能超过上限、不能加命、不能进化。")
NO_DEATH_FLUKE = {"生化大师", "猪带小天王", "蚂蟥大仙"}       # 本子：生化大师不能使用死亡吸虫
BENCH_PARASITES = {"寄生种子"}                              # 换下场也还在身上的虫子
STOLEN_BY_FLUKE = ("大难不死", "幸运")                      # 华支睾吸虫吸走的两种内功

HIDDEN_SKILL_IDS = {"x18"}                      # 做了但不出现在按钮里
EXTRA_SKILL_IDS = tuple(key for key in SKILLS if key.startswith("x") and key not in HIDDEN_SKILL_IDS)

# 人物专属的新招。
SKILLS["t10"] = _gd.skill(
    "t10", "禁十二麒麟芒星", ["物理", "特技"], 80000, [("封喉", 10), ("封品", 10), ("封生", 10)], 4, 3,
    character="武圣", description="合成的招。只有武圣能用，和禁十二式燃一样要到第二条命。")
SKILLS["t11"] = _gd.skill(
    "t11", "燃烧饕餮牙", ["特技"], 40000, [("点燃", 4)], 4, 4, effect="taotie_fang",
    character="饕餮", description="和饕餮牙一样打两下、吸血，另外点燃 4 回合。")
SKILLS["c_dragon_typhoon"]["statuses"] = (("昏睡", 1),)      # 龙王的台风加上本子写的昏睡 1 回合；进黑暗之城深处写在效果里

# 所有打对手的招都可以改成打自己（雨晨）。这几样对自己用没有意义，不让选。
NO_SELF_EFFECTS = {"swap_character", "swap_hp", "divination", "big_bang"}

# 本子上圈了“先”字的招：比普通招先出手，比神技慢。
# 雷神之怒、太阳黑子爆、伽马射线、一零二仙折、行星撞地球、宇宙大爆炸
FIRST_STRIKE_IDS = {"21", "23", "24", "x7", "x9", "x23"}
# 本子上圈了“必”字的招：必中（γ 射线本来就不走闪避）。
SURE_HIT_IDS = {"x7", "x9", "x23"}
FIRE_SKILL_NAMES = {"火山爆发", "百步烈烧", "千步烈烧", "焚风", "真火", "九里烧真火", "燃烧饕餮牙"}   # “免疫火系”挡这些
ICE_SKILL_NAMES = {"寒潮", "极光", "灵气寒霜指", "千里寒极冰", "布拉风"}                              # “免疫冰系”挡这些

# 出手顺序的档位，数字大的先出手。
TIER_NORMAL, TIER_FIRST, TIER_SHEN, TIER_LINGBO4, TIER_SWITCH, TIER_FAN_SWAP = 0, 20, 30, 40, 60, 70

# 范仲淹的换人（雨晨）：和对面场上的人物互换，对面那个人物连同内功和所有属性都归你，范仲淹归对面。
SKILLS["t7"]["description"] = "和对面场上的人物互换：那个人物连同内功、体力、状态都归你，范仲淹归对面。比普通换人还先生效。"

# ---------- 人物 ----------

CHARACTERS = copy.deepcopy(_gd.CHARACTERS)
_BY_NAME = {c["name"]: c for c in CHARACTERS.values()}

_BY_NAME["武圣"]["lives"] = 2  # 雨晨：2 条命
_BY_NAME["武圣"]["skills"] = tuple(_BY_NAME["武圣"]["skills"]) + ("t10",)       # 禁十二麒麟芒星
for _name in ("饕餮", "肥饕餮"):
    _BY_NAME[_name]["skills"] = tuple(_BY_NAME[_name]["skills"]) + ("t11",)     # 燃烧饕餮牙
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
    "达伽马": {"伽马射线"},              # 雨晨 2026-11-19：达伽马的伽马射线可以无限用（本子：可以任意放 γ 射线）
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
# 雨晨 2026-11-19：万灵丹不用收集，直接用。所以“收集万灵丹”不再列出来。
SYSTEM_ACTION_IDS = tuple(key for key in _gd.SYSTEM_ACTION_IDS if key != "sys_collect_panacea") + (
    "sys_build_accelerator", "sys_fire_accelerator")

# 不出现在招式按钮里的专属动作：占卜和牛顿选场景都改成了回合开始时的免费选择。
NOT_YET_IMPLEMENTED_SKILLS = {"t8", "c_newton_scene"}


def character_skill_ids(character_data: dict) -> tuple[str, ...]:
    extra = tuple(s for s in character_data.get("skills", ()) if s not in NOT_YET_IMPLEMENTED_SKILLS)
    shared = EXTRA_SKILL_IDS
    if "c_dragon_typhoon" in extra:                     # 龙王有他自己的台风，不再列谁都能用的那个弱台风
        shared = tuple(key for key in shared if key != "x24")
    return COMMON_SKILL_IDS + shared + SYSTEM_ACTION_IDS + extra


def is_signature(character_name: str, spec: dict) -> bool:
    """这个招是不是这个人物的大招：他的专属招，或者在他手里改了数值的通用招。

    进化形态用原形态的专属招也算（肥饕餮的饕餮牙）。
    """
    if spec["name"] in SIGNATURE_SKILL_NAMES.get(character_name, ()):
        return True
    if not spec.get("character"):
        return False
    own = CHARACTERS[CHARACTER_NAME_TO_ID[character_name]]["skills"] if character_name in CHARACTER_NAME_TO_ID else ()
    return spec["character"] == character_name or spec["id"] in own
