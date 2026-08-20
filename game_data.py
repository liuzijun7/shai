"""《晒》的静态规则数据。

首版把 Excel 中会影响双角色规则测试的内容固化在程序中，从而让打包后的程序
不依赖 Excel、pandas 或网络。后续可把本文件替换为 JSON/Excel 导入层。
"""

from __future__ import annotations

from math import inf


SCENES = {
    "内地核": {"height": -3, "hp_loss": 0.30, "learn_multiplier": 3},
    "外地核": {"height": -2, "hp_loss": 0.20},
    "地幔": {"height": -1, "hp_loss": 0.10},
    "洞穴": {"height": -1, "dodge": 0.25},
    "地面": {"height": 0},
    "南极": {"height": 0, "sleep_every": 3},
    "雨林": {"height": 0, "heal": 0.10, "oxygen_multiplier": 2},
    "对流层": {"height": 1},
    "平流层": {"height": 2},
    "电离层": {"height": 3, "hp_loss": 0.10},
    "宇宙": {"height": 4, "vacuum": True, "collect_star": True},
    "外太空": {"height": 8, "vacuum": True, "collect_star": True, "collect_supernova": True},
    "宇宙边缘": {
        "height": 12,
        "vacuum": True,
        "collect_star": True,
        "collect_supernova": True,
        "collect_multiplier": 2,
        "random_radiation": True,
    },
}

VERTICAL_SCENES = ["内地核", "外地核", "地幔", "地面", "对流层", "平流层", "电离层", "宇宙", "外太空", "宇宙边缘"]

INNER_VALUES = {
    "幸运": {1: 0.25, 2: 0.33, 3: 0.50},
    "大难不死": {1: 0.25, 2: 0.33, 3: 0.50},
    "凌波微步": {1: 1, 2: 2, 3: 3},
    "虚空神术": {1: 0.25, 2: 0.33, 3: 0.50},
    "幻影": {1: 2, 2: 3, 3: 4},
    "蛮力": {1: 0.20, 2: 0.30, 3: 0.50},
    "铁布衫": {1: 0.20, 2: 0.30, 3: 0.50},
    "弹性形变": {1: 0.20, 2: 0.30, 3: 0.50},
    "生机勃勃": {1: 0.10, 2: 0.20, 3: 0.30},
    "重于泰山": {1: 5, 2: 3, 3: 1},
    "轻于鸿毛": {1: 5, 2: 3, 3: 1},
    "昏沉大法": {1: 6, 2: 4, 3: 3},
    "放射性": {1: 1, 2: 2, 3: 5},
}

ALL_INNER_NAMES = tuple(INNER_VALUES)

SEAL_BY_ATTRIBUTE = {
    "物理": "封物",
    "魔法": "封魔",
    "特技": "封喉",
    "物品": "封品",
    "神技": "封神",
    "地理": "封土",
    "化学": "封化",
    "生物": "封生",
}

CONTROL_STATUSES = {
    "封物", "封魔", "封喉", "封品", "封神", "封土", "封化", "封生",
    "昏睡", "封印", "透视", "虚空", "封内", "万能胶",
}

DAMAGE_STATUSES = {"烧伤", "点燃", "超燃"}
SELF_BUFFS = {"氪", "真空", "狂龙", "道威"}


def skill(skill_id, name, attributes=(), damage=0, statuses=(), defense=None,
          distance=0, target="enemy", effect=None, description="", character=None,
          action_kind="skill"):
    return {
        "id": str(skill_id),
        "name": name,
        "attributes": tuple(attributes),
        "damage": int(damage),
        "statuses": tuple(statuses),
        "defense": defense,
        "distance": int(distance),
        "target": target,
        "effect": effect,
        "description": description,
        "character": character,
        "action_kind": action_kind,
    }


SKILLS = {
    "0": skill(0, "普通攻击", damage=10000, distance=1, description="无属性，造成10000基础伤害。"),
    "1": skill(1, "流星", ["物理"], 10000, defense=1, effect="meteor", description="每拳后50%概率继续。"),
    "2": skill(2, "麒麟芒星", ["物理"], 30000, [("封品", 4), ("封生", 4)], 4),
    "3": skill(3, "点穴手", ["物理"], 0, [("封物", 4)], 1),
    "4": skill(4, "摄魂大法", ["魔法"], 0, [("封魔", 4)], 1),
    "5": skill(5, "狮子吼", ["魔法"], 15000, [("封喉", 5)], 1),
    "6": skill(6, "圣六式空凌", ["物理"], 20000, [("封土", 4)], 3, 3, effect="rise_self"),
    "7": skill(7, "死亡笔记", ["特技"], 30000, defense=4, effect="death_note", description="12.5%概率杀死当前命。"),
    "8": skill(8, "洪水", ["地理"], 15000, defense=3, effect="flood"),
    "9": skill(9, "地震", ["地理"], 15000, defense=3, effect="lower_target"),
    "10": skill(10, "寒潮", ["地理"], 15000, [("昏睡", 1)], 3, 3, effect="antarctic"),
    "11": skill(11, "火山爆发", ["地理", "特技"], 20000, [("点燃", 2)], 4, 3, effect="lower_target"),
    "12": skill(12, "昏睡咒", ["魔法"], 0, [("昏睡", 3)], 1),
    "13": skill(13, "声波炮", ["物理"], 0, [("昏睡", 2)], "j", 3, effect="sound_wave"),
    "14": skill(14, "极光", ["物理"], 0, [("昏睡", 4)], "j", 3, effect="aurora"),
    "15": skill(15, "猪带绦虫", ["生物"], defense=2, effect="pork_tapeworm"),
    "16": skill(16, "昏睡绦虫", ["生物"], defense=2, effect="sleep_tapeworm"),
    "17": skill(17, "蚂蟥", ["生物"], defense=3, effect="leech"),
    "18": skill(18, "百步烈烧", ["特技"], 30000, [("点燃", 2)], 3, 3),
    "19": skill(19, "究极吸取", ["特技"], defense=4, effect="ultimate_drain", description="吸取目标体力上限80%。"),
    "20": skill(20, "X光", ["物理"], defense="j", distance=3, effect="xray"),
    "21": skill(21, "雷神之怒", ["特技"], 20000, [("昏睡", 4)], 4, 3, effect="drop_ground"),
    "22": skill(22, "摄魂点穴手", ["物理", "魔法", "特技"], 0, [("封物", 10), ("封魔", 10)], 3),
    "23": skill(23, "太阳黑子爆", ["物理"], 100000, defense=4, distance=3, effect="sunspot"),
    "24": skill(24, "伽马射线", ["物理", "魔法", "特技", "物品", "神技", "地理", "化学", "生物"], defense="j", distance=3, effect="gamma"),
    "25": skill(25, "臭伽马", ["物理", "魔法", "特技", "物品", "神技", "地理", "化学", "生物"], defense="j", effect="stinky_gamma", description="只能由伽马射线1/3概率触发。"),
    "26": skill(26, "氪屏障", ["化学"], statuses=[("氪", 5)], target="self", effect="self_status"),
    "27": skill(27, "真空屏障", ["神技"], statuses=[("真空", 5)], defense="s", target="self", effect="self_status"),
    "28": skill(28, "硫酸", ["化学"], statuses=[("点燃", 2)], defense=2, effect="sulfuric_acid"),
    "29": skill(29, "乙醚", ["化学"], defense=2, effect="ether"),
    "30": skill(30, "悬心拳", ["物理"], 10000, [("封内", 5)], 1),
    "31": skill(31, "狂龙傲天拳", ["神技"], 50000, [("狂龙", 3)], "s", 3, "self", "self_status_and_damage"),
    "32": skill(32, "惊天混元掌", ["神技"], 50000, [("封印", 2)], "s", 3),
    "33": skill(33, "灵气寒霜指", ["神技"], 50000, [("透视", 3)], "s", 3),
    "34": skill(34, "八卦迷踪腿", ["神技"], 50000, [("虚空", 3)], "s", 3),
    "35": skill(35, "道威无极真气", ["神技"], 50000, [("道威", 3)], "s", 3, "self", "self_status_and_damage"),
    "36": skill(36, "浴火重生", ["神技"], defense="s", target="self", effect="rebirth"),
    "37": skill(37, "万灵丹", ["物品"], target="self", effect="panacea"),
    "38": skill(38, "收集超新星", ["物品"], target="self", effect="collect_supernova", action_kind="collect"),
    "39": skill(39, "收集星体能量", ["物品"], target="self", effect="collect_star", action_kind="collect"),
    "t1": skill("t1", "饕餮牙", ["物理"], 40000, defense=4, distance=4, effect="taotie_fang", character="饕餮"),
    "t2": skill("t2", "禁十二式燃", ["魔法"], 50000, [("封喉", 5)], 4, 3, character="武圣"),
    "t3": skill("t3", "武七式折空", ["物理"], 40000, [("封化", 5)], 4, 3, character="武圣"),
    "t4": skill("t4", "武一式九殇", ["物理"], 20000, [("封神", 5)], 4, 1, character="武圣"),
    "t5": skill("t5", "武二式八荒", ["魔法"], 30000, [("封喉", 5)], 4, 2, character="武圣"),
    "t6": skill("t6", "千步烈烧", ["特技"], 50000, [("超燃", 2)], 4, 4, character="库巴"),
    "t7": skill("t7", "换人", damage=0, defense=1, distance=12, effect="swap_character", character="范仲淹"),
    "t8": skill("t8", "占卜", distance=12, effect="divination", character="占卜大师"),
    "t9": skill("t9", "蚂蟥冲击波", ["生物", "特技"], 50000, defense=4, distance=12, effect="leech_wave", character="蚂蟥大仙"),
    "c_dragon_typhoon": skill("c_dragon_typhoon", "台风", damage=50000, effect="typhoon", character="龙王"),
    "c_newton_cloud": skill("c_newton_cloud", "云端之星", damage=60000, character="牛顿"),
    "c_newton_scene": skill("c_newton_scene", "选择场景", target="self", effect="choose_scene", character="牛顿", action_kind="scene"),
    "c_fan_build": skill("c_fan_build", "建造岳阳楼", target="self", effect="build_yueyang", character="范仲淹", action_kind="build"),
    "c_pharaoh_build": skill("c_pharaoh_build", "建造金字塔", target="self", effect="build_pyramid", character="埃及法老", action_kind="build"),
    "c_ouyang_collect": skill("c_ouyang_collect", "收集酒", ["物品"], target="self", effect="collect_wine", character="欧阳修", action_kind="collect"),
    "c_ouyang_drink": skill("c_ouyang_drink", "喝酒", ["物品"], target="self", effect="drink_wine", character="欧阳修"),
    "sys_collect_panacea": skill("sys_collect_panacea", "收集万灵丹", ["物品"], target="self", effect="collect_panacea", action_kind="collect", description="收集后进入物品栏，至少有1个才能使用万灵丹。"),
    "sys_collect_glue": skill("sys_collect_glue", "收集万能胶", ["物品"], target="self", effect="collect_glue", action_kind="collect", description="收集当回合直接生效，使场景5回合不能移动。"),
    "d1": skill("d1", "防御1", target="self", effect="defend", action_kind="defense", description="无论先后手，阻挡防御字段为1的技能。"),
    "d2": skill("d2", "防御2", target="self", effect="defend", action_kind="defense", description="无论先后手，阻挡防御字段为2的技能。"),
    "d3": skill("d3", "防御3", target="self", effect="defend", action_kind="defense", description="无论先后手，阻挡防御字段为3的技能。"),
    "d4": skill("d4", "防御4", target="self", effect="defend", action_kind="defense", description="无论先后手，阻挡防御字段为4的技能。"),
    "dj": skill("dj", "平面镜", target="self", effect="mirror", action_kind="defense", description="无论先后手，把防御字段为j的技能完整反弹给使用者。"),
    "ds": skill("ds", "憋神技", target="self", effect="block_divine", action_kind="defense", description="令本回合所有神技变成普通攻击，并给神技使用者附加封神3。"),
}


def character(char_id, name, hp, distance, inner=None, shield=0, lives=1,
              skills=(), traits=(), description=""):
    return {
        "id": str(char_id), "name": name, "hp": int(hp), "distance": distance,
        "inner": dict(inner or {}), "shield": int(shield), "lives": int(lives),
        "skills": tuple(skills), "traits": set(traits), "description": description,
    }


def all_inner(level):
    return {name: level for name in ALL_INNER_NAMES}


CHARACTERS = {
    "1": character(1, "陶渊明", 150000, 0, {"虚空神术": 3, "凌波微步": 3}, traits=["必中", "免疫不良", "特效时长2"]),
    # “命”列按用户回答解释为生命条数，因此这里采用3命；人物备注中的“两条命”列入歧义清单。
    "2": character(2, "武圣", 100000, 8, lives=3, skills=["t2", "t3", "t4", "t5"], traits=["免疫火系"]),
    "3": character(3, "纵目青铜怪", 100000, 8, traits=["免疫辐射", "回合末换血", "首次X光"]),
    "4": character(4, "巫师", 50000, 8, {"幻影": 3}, shield=100000, traits=["神技无限"]),
    "5": character(5, "龙王", 100000, 8, skills=["c_dragon_typhoon"], traits=["免疫水压", "龙王技能覆盖"]),
    "6": character(6, "饕餮", 150000, 2, {"大难不死": 3}, skills=["t1"]),
    "7": character(7, "埃及法老", 100000, 2, all_inner(1), skills=["c_pharaoh_build"]),
    "8": character(8, "生化大师", 100000, 4, all_inner(1), traits=["生化覆盖"]),
    "9": character(9, "占卜大师", 100000, 4, all_inner(1), skills=["t8"], traits=["初登场无敌3"]),
    "10": character(10, "拳术宗师", 100000, 2, {"蛮力": 3, "铁布衫": 3}),
    "11": character(11, "灵力圣使", 200000, 4, traits=["魔法2", "圣六式覆盖"]),
    "13": character(13, "牛顿", 100000, inf, shield=200000, skills=["c_newton_cloud", "c_newton_scene"], traits=["免疫物理"]),
    "14": character(14, "范仲淹", 100000, 0, skills=["t7", "c_fan_build"], traits=["洪水覆盖"]),
    "15": character(15, "欧阳修", 300000, 0, {"轻于鸿毛": 3}, skills=["c_ouyang_collect", "c_ouyang_drink"]),
    "16": character(16, "宋濂", 100000, 0, {"铁布衫": 3}, lives=3, traits=["免疫魔法", "免疫冰系"]),
    "17": character(17, "库巴", 100000, inf, shield=100000, lives=3, skills=["t6"], traits=["库巴"]),
    "18": character(18, "达伽马", 100000, 4, traits=["收集5"]),
    "19": character(19, "三鲍太监", 100000, 0, shield=100000, lives=3),
    "20": character(20, "肥饕餮", 300000, 4, {"幸运": 3, "大难不死": 3}, skills=["t1"]),
    "21": character(21, "肥龙王", 100000, 12, all_inner(2), traits=["肥龙王"]),
    "22": character(22, "猪带小天王", 200000, 8, all_inner(2), traits=["生化覆盖"]),
    "23": character(23, "蚂蟥大仙", 200000, 12, all_inner(3), skills=["t9"]),
    "24": character(24, "魔法师", 200000, 12, all_inner(3), skills=["t8"]),
    "25": character(25, "赵先龙", 200000, 4, traits=["丝袜"]),
}

CHARACTER_NAME_TO_ID = {value["name"]: key for key, value in CHARACTERS.items()}

COMMON_SKILL_IDS = tuple(str(i) for i in range(40) if str(i) != "25")
SYSTEM_ACTION_IDS = (
    "sys_collect_panacea", "sys_collect_glue",
    "d1", "d2", "d3", "d4", "dj", "ds",
)


def character_skill_ids(character_data):
    """所有人物拥有通用技能，另加人物专属按钮；臭伽马不能主动选择。"""
    return COMMON_SKILL_IDS + SYSTEM_ACTION_IDS + tuple(character_data.get("skills", ()))
