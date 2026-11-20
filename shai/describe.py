"""给人看的说明文字：每个招的特效、每种内功和状态是干什么的、每个人物的魂印。

网页上的悬浮描述框和图鉴用的是同一份文字。这里只描述规则，不改规则：
数字都从 ``data.py`` 里现取，规则改了数字，这里的文字跟着变。
写不进数字里的那些话（比如“把对手打进南极”）照 ``actions.py`` 和 ``rules.py`` 里的结算写。

每一行是一对 ``(样式, 文字)``。样式只有四种：
- ``flag``：先手、必中这类标记；
- ``stat``：威力、用什么防御能防住；
- ``text``：特效；
- ``note``：某个人物用的时候不一样的地方。
"""

from __future__ import annotations

from math import inf
from typing import Any

from .initials import INITIALS
from .data import (
    ATMOSPHERE_TOP, BIG_BANG_COST, CHARACTERS, DECAY_AFTER_TURNS, DECAY_BELOW_LIVES, DEFERRED_NAMES,
    EVOLVE_AFTER_TURNS, EVOLVE_AT_LIVES, EVOLVED_NAMES, FIRST_STRIKE_IDS, HIDDEN_SKILL_IDS, INNER_VALUES,
    LEARN_MULTIPLIER, LEARN_THRESHOLDS, NOT_YET_IMPLEMENTED_SKILLS, SCENES, SEAL_BY_ATTRIBUTE, SELECTABLE_NAMES,
    SELF_BUFFS, SIGNATURE_SKILL_NAMES, SKILLS, SPACE, SURE_HIT_IDS, TRUE_BODY_ID, UNBLOCKABLE_CHARACTERS, UNIVERSE_NAMES, UP_REACH,
)

Line = tuple[str, str]


def wan(amount: float) -> str:
    """15000 -> “1.5 万”。不到一万的照原样写。"""
    amount = int(amount)
    if amount < 10000:
        return str(amount)
    text = f"{amount / 10000:.2f}".rstrip("0").rstrip(".")
    return f"{text} 万"


def chance(p: float) -> str:
    for value, text in ((1 / 8, "八分之一"), (1 / 4, "四分之一"), (1 / 3, "三分之一"), (0.33, "三分之一"),
                        (1 / 2, "一半"), (2 / 3, "三分之二")):
        if abs(p - value) < 0.006:
            return text
    return f"{round(p * 100)}%"


def percent(p: float) -> str:
    return f"{round(p * 100)}%"


# ---------- 状态 ----------

STATUS_TEXT: dict[str, str] = {
    "昏睡": "不能出招；受到基础伤害会醒",
    "封印": "不能出招",
    "冰封": "不能出打对手的招",
    "封内": "内功不起作用",
    "点燃": "每回合烧掉当前体力的三分之一",
    "烧伤": "每回合烧掉体力上限的 10%",
    "超燃": "每回合烧掉体力上限的三分之二",
    "真火": "每回合烧掉体力上限的八分之一",
    "透视": "选招时他先选，对面看到他选了什么以后再选",
    "虚空": "他出的招只有四分之一的可能打中",
    "狂龙": "自己的伤害乘 3",
    "道威": "打出多少伤害，自己就回多少体力",
    "氪": "X光对自己无效",
    "真空": "别人给自己加的不良状态，回合数减半",
    "心眼": "自己所有的招必中",
    "无敌": "什么招都打不动",
    "万能胶": "场景不会被改变，自己也动不了",
}
for _attribute, _seal in SEAL_BY_ATTRIBUTE.items():
    STATUS_TEXT.setdefault(_seal, f"不能出{_attribute}的招")
GOOD_STATUSES = set(SELF_BUFFS) | {"无敌", "万能胶"}

PARASITE_TEXT: dict[str, str] = {
    "猪带绦虫": "每回合吸走体力上限的 10% 给放虫的人；每 5 回合数量翻倍",
    "昏睡绦虫": "每 3 回合让宿主昏睡 1 回合",
    "蚂蟥": "每条每回合吸走体力上限的 20% 给放虫的人",
    "血吸虫": "每回合吸血给放虫的人：第 1 回合 1%，以后每回合翻倍，封顶 100%",
    "死亡吸虫": "每回合吸走体力上限的 10%；隔一回合让宿主昏睡一次",
    "控制绦虫": "放上去的下一回合，宿主出什么招由放虫的人来选；以后每 5 回合再控制一次",
    "死亡绦虫": "每回合三分之一的可能吸走 75% 体力；没吸成的话，三分之一的可能下一回合由放虫的人替宿主选招",
    "寄生种子": "每回合吸走体力上限的 10%，还会随机传给宿主那一方场下的一个人物；换下场也还在",
    "华支睾吸虫": "吸走宿主的幸运和大难不死；每回合吸走体力上限的 10%；宿主的体力不能超过上限、不能加命、不能进化",
}


# ---------- 内功 ----------

def inner_text(name: str, level: int) -> str:
    """这种内功在这一级是干什么的。"""
    value = INNER_VALUES[name][level]
    if name == "幸运":
        return f"回合开始时身上有不良状态或虫子的话，{chance(value)}的可能全部解除"
    if name == "大难不死":
        return f"体力被打到 0 时，{chance(value)}的可能保住这条命，回到体力上限的 {percent(value)}"
    if name == "凌波微步":
        return {1: "出招算先手", 2: "出招算先手", 3: "出招和神技一样快"}.get(level, "出招比神技还快")
    if name == "虚空神术":
        return f"{chance(value)}的可能躲开对手的招；神技和必中的招躲不开"
    if name == "幻影":
        count, every = int(value), max(1, 5 - int(value))
        when = "每回合" if every == 1 else f"每 {every} 回合有一回合"
        return f"{when}出的招算 {count} 个；一个招最多打掉一个盾牌或一条命"
    if name == "蛮力":
        return f"自己的基础伤害加 {percent(value)}"
    if name == "铁布衫":
        return f"受到的基础伤害减少 {percent(value)}"
    if name == "弹性形变":
        return f"挨打时把受到伤害的 {percent(value)} 弹回给对手"
    if name == "生机勃勃":
        return f"每回合回体力上限的 {percent(value)}"
    if name in {"重于泰山", "轻于鸿毛"}:
        every = "每回合" if int(value) == 1 else f"每 {int(value)} 回合"
        return f"{every}自己往{'下沉' if name == '重于泰山' else '上飘'}一层"
    if name == "昏沉大法":
        return f"每 {int(value)} 回合全场昏睡 1 回合，自己也睡"
    if name == "放射性":
        return f"每回合让对手累计辐射 {int(value)} 次"
    if name == "暴击":
        return f"{chance(value)}的可能伤害翻倍"
    if name == "重贼":
        return f"贼输了可以重来 {int(value)} 次"
    if name == "内功栏":
        return f"除了自带的，可以多学 {int(value)} 种内功"
    return ""


def inner_card(name: str) -> dict[str, Any]:
    levels = sorted(INNER_VALUES[name])
    lines: list[Line] = [("text", f"{level} 级：{inner_text(name, level)}。") for level in levels]
    needs = LEARN_THRESHOLDS.get(name)
    if needs:
        lines.append(("stat", "学 " + "、".join(str(n) for n in needs) + " 下，各升一级。"))
    return {"name": name, "py": INITIALS.get(name, ""), "lines": lines}


# ---------- 招 ----------

# 特效的文字。没写在这里的招用 data.py 里那一句 description。
SKILL_TEXT: dict[str, list[str]] = {
    "0": ["最普通的一下，没有属性。"],
    "1": ["一拳 1 万。每打完一拳贼一次：一半的可能再打一拳，可以一直打下去。"],
    "6": ["打完自己往上升一层。"],
    "7": ["八分之一的可能直接打掉对手这条命。", "没打掉的话，把对手打进黑暗之城。"],
    "8": ["水面升高一层。", "泡在水里的人每回合掉体力：在水面下第几层，就掉体力上限的百分之几十。"],
    "9": ["对手往下掉一层。", "同一个对手被地震震满 10 下，掉进地心深处。"],
    "10": ["把对手打进南极。在南极每 3 回合昏睡 1 回合。"],
    "11": ["对手往下掉一层。"],
    "13": ["对手在真空里（宇宙和更高的地方）时无效。"],
    "14": ["只能在南极用。"],
    "15": ["虫子留在对手身上：每回合吸走体力上限的 10% 给你。", "每 5 回合虫子数量翻倍。"],
    "16": ["对手马上昏睡 1 回合。", "虫子留在对手身上：每 3 回合再让他昏睡 1 回合。"],
    "17": ["虫子留在对手身上：每回合吸走体力上限的 20% 给你。"],
    "19": ["吸走对手体力上限的 80% 给自己，可以超过自己的上限。"],
    "20": ["对手累计辐射 5 次。辐射满 15 次丢一条命。", "对手有氪屏障时无效。"],
    "21": ["把天上的对手打回地面。"],
    "23": ["要花 3 个星体能量。", "把天上的对手打回地面。", "对手所有内功降一级。"],
    "24": ["要花 5 个星体能量和 1 个超新星。", "对手一次累计辐射 15 次，等于直接丢一条命，大难不死救不回来。",
           "八分之一的可能是臭伽马：对手强制昏睡 10 回合。", "对手无敌时无效。"],
    "29": ["对手过两个回合以后昏睡 5 回合。", "对手身上有烧伤或点燃时，先扣体力上限的一半。"],
    "36": ["清掉自己身上所有不良状态和虫子，体力回满。", "这一回合无敌。"],
    "37": ["清掉自己身上所有不良状态和虫子。", "不用收集，直接用。"],
    "38": ["只能在外太空和宇宙边缘收集。在宇宙边缘一次得两个。"],
    "39": ["只能在宇宙、外太空和宇宙边缘收集。在宇宙边缘一次得两个。"],
    "t1": ["打两下。打掉多少体力，自己就加多少。", "加到超过上限就多一条命。"],
    "t2": ["要到第二条命才能用。"],
    "t3": ["要到第二条命才能用。"],
    "t4": ["只有第一条命能用。"],
    "t5": ["只有第一条命能用。"],
    "t9": ["再往对手身上放 3 条蚂蟥：每条每回合吸走体力上限的 20% 给你。"],
    "t10": ["要到第二条命才能用。"],
    "t11": ["打两下。打掉多少体力，自己就加多少。", "加到超过上限就多一条命。"],
    "c_dragon_typhoon": ["对手除了氧气以外的物品全部清空。", "把对手刮进黑暗之城深处。"],
    "c_fan_build": ["造一下岳阳楼。每造满 5 下，自己所有内功升一级。"],
    "c_pharaoh_build": ["造一下金字塔。每造满 5 下，自己所有内功升一级。"],
    "c_ouyang_collect": ["收集 1 个酒。"],
    "c_ouyang_drink": ["喝掉 1 个酒：这一回合无敌。", "下一回合自己的伤害和特效回合数加倍。"],
    "sys_collect_glue": ["马上生效：5 回合内自己的场景不会被改变，自己也动不了。", "身上有烧伤或点燃时粘不住。"],
    "sys_collect_oxygen": ["只能在地面这一层收集。在雨林一次得两个。",
                           "在宇宙和更高的地方每回合用掉 1 个氧气；没有氧气每回合掉体力上限的 10%。"],
    "sys_build_accelerator": ["造满 10 下可以打：一下 3 万，加 3 次辐射。",
                              "造满 20 下：一下 5 万，加 5 次辐射，对手在哪个场景都打得到。"],
    "sys_fire_accelerator": ["造满 10 下才能打：一下 3 万，加 3 次辐射。",
                             "造满 20 下：一下 5 万，加 5 次辐射，对手在哪个场景都打得到。"],
    "d1": ["这回合挡住所有“防御 1 能防住”的招，不管谁先出手。"],
    "d2": ["这回合挡住所有“防御 2 能防住”的招，不管谁先出手。"],
    "d3": ["这回合挡住所有“防御 3 能防住”的招，不管谁先出手。"],
    "d4": ["这回合挡住所有“防御 4 能防住”的招，不管谁先出手。"],
    "dj": ["把“平面镜能弹回去”的招原样弹回给出招的人，不管谁先出手。"],
    "ds": ["这回合场上所有的神技作废，出神技的人封神 3 回合。", "被憋回去的神技不算用掉。"],
    "x7": ["除了神技，对手所有属性的招封 5 回合。", "把天上的对手打回地面。"],
    "x9": ["要花 3 个星体能量和 1 个超新星。", "把天上的对手打回地面，累计辐射 1 次。"],
    "x11": [],
    "x14": ["对面的虚空神术也躲不开。"],
    "x15": [],
    "x16": ["对手在南极的话，把他赶回地面。"],
    "x24": ["把对手打进黑暗之城深处。"],
    "x21": ["用一次神树长一次，在雨林深处一次长两次。", "长满 10 次以后，你所有的神技不再限“每条命一次”。", "神树记在玩家身上，换了人物也还在。"],
}

# 某个人物用的时候不一样的地方。
USER_NOTES: dict[str, list[str]] = {
    "2": ["牛顿用：威力 9 万。"],
    "6": ["灵力圣使用：威力 9 万，自己升两层。"],
    "8": ["范仲淹、肥龙王用：威力 8 万。"],
    "9": ["龙王用：威力 5 万，对手一次掉 4 层。", "肥龙王用：威力 8 万。"],
    "10": ["龙王用：威力 5 万，再昏睡 3 回合。", "肥龙王用：威力 8 万。"],
    "11": ["肥龙王用：威力 8 万。"],
    "15": ["生化大师、猪带小天王用：虫子每多待一回合，多吸 10%。"],
    "19": ["肥饕餮用：吸 100%。"],
    "24": ["达伽马用：不用花东西，不限次数，用完也不封喉。"],
    "28": ["生化大师、猪带小天王用：不点燃，改成一半的可能直接打掉对手这条命。"],
    "29": ["生化大师、猪带小天王用：对手直接昏睡 5 回合。"],
    "x24": ["龙王用的是他自己的台风：威力 5 万，清空对手的物品。"],
}

DEFENSE_NAME = {1: "防御 1", 2: "防御 2", 3: "防御 3", 4: "防御 4", "j": "平面镜", "s": "憋神技"}
_OXYGEN_CARD = {
    "id": "sys_collect_oxygen", "name": "收集氧气", "attributes": ("物品",), "damage": 0, "statuses": (),
    "defense": None, "target": "self", "effect": "collect_oxygen", "character": None, "action_kind": "collect",
    "description": "",
}


def skill_kind(spec: dict[str, Any]) -> str:
    """这个招算哪一类。和网页上选招的分类一样。"""
    if spec["action_kind"] == "defense":
        return "防御"
    if "神技" in spec["attributes"]:
        return "神技"
    if spec.get("character"):
        return "专属"
    if "物品" in spec["attributes"] or spec["action_kind"] in {"collect", "build", "scene"}:
        return "物品"
    return "技能"


def _sentences(text: str) -> list[str]:
    return [part + "。" for part in text.replace("。 ", "。").split("。") if part.strip()]


def skill_lines(spec: dict[str, Any]) -> list[Line]:
    skill_id, attributes = spec["id"], tuple(spec["attributes"])
    shen = "神技" in attributes
    hits_foe = spec["target"] == "enemy" or spec["effect"] == "self_status_and_damage"
    lines: list[Line] = []

    flags = []
    if skill_id in FIRST_STRIKE_IDS:
        flags.append("先手")
    if skill_id in SURE_HIT_IDS or (shen and hits_foe) or (spec.get("character") and hits_foe):
        flags.append("必中")                              # 人物的专属招是他的大招，大招都必中
    if flags:
        lines.append(("flag", "　".join(flags)))

    stat = []
    if spec["damage"]:
        stat.append(f"威力 {wan(spec['damage'])}")
    if spec["action_kind"] == "skill" and hits_foe:
        defense = spec["defense"]
        if defense == "j":
            stat.append("只有平面镜能防：原样弹回去")
        elif defense == "s":
            stat.append("只有憋神技能防")
        elif defense is None:
            stat.append("什么防御都防不住")
        else:
            stat.append(f"{DEFENSE_NAME[defense]} 能防住")
    if stat:
        lines.append(("stat", "　".join(stat)))

    statuses = list(spec["statuses"])
    if 0 < len(statuses) <= 3:
        for name, turns in statuses:
            who = "自己" if name in SELF_BUFFS or spec["target"] == "self" else "对手"
            lines.append(("text", f"{who}【{name}】{turns} 回合：{STATUS_TEXT.get(name, '')}。"))

    texts = SKILL_TEXT.get(skill_id)
    if texts is None:
        texts = _sentences(spec.get("description") or "")
    lines += [("text", text) for text in texts]

    if spec["action_kind"] == "skill" and hits_foe and not shen:
        top = UP_REACH.get(skill_id)
        if top == inf:
            lines.append(("text", "对手在多高的地方都打得到。"))
        elif top == ATMOSPHERE_TOP:
            lines.append(("text", "对手在天上也打得到，最高到电离层。"))
        elif top == SPACE:
            lines.append(("text", "对手在天上也打得到，最高到宇宙。"))
    if shen and hits_foe:
        lines.append(("text", "不看距离，对手在哪儿都打得到。"))
    if shen and spec["effect"] != "grow_tree":
        lines.append(("text", "每条命只能用一次。"))
    if "特技" in attributes and spec["action_kind"] == "skill" and not spec.get("character"):
        lines.append(("text", "特技用完，自己封喉 3 回合；自己的大招不算。"))
    lines += [("note", text) for text in USER_NOTES.get(skill_id, [])]
    owners = [name for name, names in SIGNATURE_SKILL_NAMES.items() if spec["name"] in names]
    if owners and not spec.get("character") and hits_foe and "必中" not in flags:
        lines.append(("note", f"是{'、'.join(owners)}的大招：他{'们' if len(owners) > 1 else ''}用的时候必中。"))
    return lines


def skill_card(spec: dict[str, Any]) -> dict[str, Any]:
    attributes = list(spec["attributes"])
    return {
        "id": spec["id"], "name": spec["name"], "kind": skill_kind(spec), "attributes": attributes,
        "py": INITIALS.get(spec["name"], ""),
        # 标题括号里写什么：属性；八种属性都有的写“全属性”；没有属性的写它是哪一类
        "tag": "全属性" if len(attributes) >= 8 else ("+".join(attributes) or
                                                 ("无属性" if skill_kind(spec) == "技能" else skill_kind(spec))),
        "damage": int(spec["damage"]), "defense": spec["defense"], "character": spec.get("character"),
        "lines": skill_lines(spec),
    }


def all_skill_specs() -> list[dict[str, Any]]:
    """图鉴里列的招：按技能、神技、防御、物品、专属排。做了但不显示的、还没做完的不列。"""
    skip = set(HIDDEN_SKILL_IDS) | set(NOT_YET_IMPLEMENTED_SKILLS) | {"25", "sys_collect_panacea"}
    specs = [spec for key, spec in SKILLS.items() if key not in skip] + [_OXYGEN_CARD]
    order = ["技能", "神技", "防御", "物品", "专属"]
    return sorted(specs, key=lambda spec: order.index(skill_kind(spec)))       # sorted 是稳定的，同一类里保持原来的顺序


# ---------- 人物 ----------

TRAIT_TEXT: dict[str, str] = {
    "必中": "所有的招必中。",
    "免疫不良": "别人加的不良状态对他无效。",
    "特效时长2": "他打出的特效，回合数加倍。",
    "免疫水压": "泡在水里不掉体力。",
    "首次X光": "第一次上场时，对手累计辐射 5 次。",
    "体力无上限": "回体力可以超过上限。",
    "免疫辐射": "辐射对他无效。",
    "透视": "透视：上场后第一个出招的回合起，每隔一回合，对手先选招，他看到以后再选。",
    "借内功": "回合开始时，从对面场上人物的内功里选一种来借。最多借 5 回合，到时候要换一种。",
    "神技无限": "神技不限次数。",
    "龙王技能覆盖": "寒潮、地震、台风威力 5 万。回合开始时可以把对手移到别的场景。",
    "肥龙王": "洪水、地震、寒潮、火山爆发威力 8 万。回合开始时可以把对手移到别的场景。",
    "生化覆盖": "硫酸、乙醚、猪带绦虫在他手里更强。不能用死亡吸虫。",
    "洪水覆盖": "洪水威力 8 万。",
    "魔法2": "魔法的招伤害加倍、特效回合数加倍，加上的特效消不掉。",
    "圣六式覆盖": "圣六式空凌威力 9 万，自己升两层。",
    "收集5": "收集东西一次得 5 个。",
    "库巴": "每回合开始，对手可以把他扔到别的场景，他也可以自己跑；都要贼赢了才算。",
    "初登场无敌3": "第一次上场无敌 3 回合。",
    "真身": "体力掉到 2 万以下自动回满；大难不死发动后体力回满。",
    "免疫物理": "物理的招对他无效。",
    "免疫魔法": "魔法的招对他无效。",
    "免疫火系": "火系的招对他无效。",
    "免疫冰系": "冰系的招对他无效。",
    "丝袜": "一下最多受 3 万伤害。",
}

SOUL_EXTRA: dict[str, list[str]] = {
    "武圣": ["第一条命能用：武一式九殇、武二式八荒。", "第二条命能用：禁十二式燃、武七式折空、禁十二麒麟芒星。",
           "进入第二条命时得到幸运 3 级、大难不死 2 级。"],
    "巫师": ["用过浴火重生以后，盾牌没有了。"],
    "占卜大师": ["每回合出招前可以占卜：猜对手这回合用什么属性的招，双方都看得到他猜了什么。",
             "猜中一次，体力和体力上限各加“猜中的次数 × 1 万”。猜中 3 次进化成魔法师。"],
    "魔法师": ["由占卜大师猜中 3 次进化来，可以接着占卜。"],
    "灵力圣使": ["倒下的时候，全场强制昏睡 3 回合。"],
    "牛顿": ["每回合开始可以把自己移到任意一个场景。万能胶粘不住他。"],
    "范仲淹": ["每造满 5 下岳阳楼，自己所有内功升一级。"],
    "埃及法老": ["每造满 5 下金字塔，自己所有内功升一级。"],
    "欧阳修": ["喝酒：这一回合无敌，下一回合伤害和特效回合数加倍。"],
    "达伽马": ["伽马射线不用花星体能量和超新星，不限次数。"],
    "超级真身": ["自己的人物全部倒下以后出场。"],
}


def _form_lines(name: str) -> list[str]:
    lines = []
    if name in EVOLVE_AT_LIVES:
        need, new = EVOLVE_AT_LIVES[name]
        lines.append(f"命数到 {need} 条时进化成{new}，体力回满。")
    if name in DECAY_BELOW_LIVES:
        need, new, ray = DECAY_BELOW_LIVES[name]
        lines.append(f"命数少于 {need} 条时衰变回{new}，衰变时向对手放 {ray} 射线。")
    if name in EVOLVE_AFTER_TURNS:
        need, new = EVOLVE_AFTER_TURNS[name]
        lines.append(f"在场上待满 {need} 回合进化成{new}，体力回满。")
    if name in DECAY_AFTER_TURNS:
        need, new, ray = DECAY_AFTER_TURNS[name]
        prefix = "衰变下来的" if name in EVOLVE_AFTER_TURNS else ""
        lines.append(f"{prefix}在场上待满 {need} 回合衰变回{new}，衰变时向对手放 {ray} 射线。")
    if lines and any("β" in line or "γ" in line for line in lines):
        lines.append("β 射线：扣体力上限的 30%，累计辐射 2 次。γ 射线：一次累计辐射 15 次。")
    return lines


def character_lines(data: dict[str, Any]) -> list[Line]:
    name = data["name"]
    stat = [f"体力 {wan(data['hp'])}"]
    if data["shield"]:
        stat.append(f"盾牌 {wan(data['shield'])}")
    if data["lives"] > 1:
        stat.append(f"{data['lives']} 条命")
    if data["distance"] == inf or name in UNIVERSE_NAMES:
        stat.append("能打全宇宙")
    lines: list[Line] = [("stat", "　".join(stat))]

    inner = {k: v for k, v in data["inner"].items() if v > 0}
    if inner:
        levels = sorted(set(inner.values()))
        common = max(levels, key=lambda level: sum(1 for v in inner.values() if v == level))
        same = [k for k, v in inner.items() if v == common]
        if len(same) >= 7:
            rest = "".join(f"，{k} {v} 级" for k, v in inner.items() if v != common)
            lines.append(("text", f"自带内功：{'、'.join(same)}，都是 {common} 级{rest}。"))
        else:
            lines.append(("text", "自带内功：" + "、".join(f"{k} {v} 级" for k, v in inner.items()) + "。"))
    for trait in sorted(data["traits"]):
        lines.append(("text", TRAIT_TEXT.get(trait, trait + "。")))
    own = [SKILLS[key]["name"] for key in data.get("skills", ()) if key not in NOT_YET_IMPLEMENTED_SKILLS]
    if own and name != "武圣":
        lines.append(("text", "专属的招：" + "、".join(own) + "。"))
    if name in LEARN_MULTIPLIER:
        lines.append(("text", f"学内功一下算 {LEARN_MULTIPLIER[name]} 下。"))
    big = sorted(SIGNATURE_SKILL_NAMES.get(name, ())) + [n for n in own if n not in SIGNATURE_SKILL_NAMES.get(name, ())]
    if big:
        more = "，也不会被先手的封招憋回去" if name in UNBLOCKABLE_CHARACTERS else ""
        lines.append(("text", f"他的大招（{'、'.join(big)}）必中{more}。"))
    lines += [("text", text) for text in SOUL_EXTRA.get(name, [])]
    lines += [("text", text) for text in _form_lines(name)]
    return lines


def character_card(data: dict[str, Any]) -> dict[str, Any]:
    name = data["name"]
    if data["id"] == TRUE_BODY_ID:
        group = "真身"
    elif name in EVOLVED_NAMES:
        group = "进化形态"
    elif name in SELECTABLE_NAMES:
        group = "可以选的人物"
    else:
        group = "还没开放"
    return {"name": name, "group": group, "py": INITIALS.get(name, ""), "lines": character_lines(data)}


# ---------- 场景 ----------

def scene_lines(name: str) -> list[Line]:
    scene, texts = SCENES[name], []
    if scene.get("heal"):
        texts.append(f"每回合回体力上限的 {percent(scene['heal'])}。")
    if scene.get("hp_loss"):
        texts.append(f"每回合掉体力上限的 {percent(scene['hp_loss'])}。")
    if scene.get("dodge"):
        texts.append(f"在这里{chance(scene['dodge'])}的可能躲开对手的招。")
    if scene.get("sleep_every"):
        texts.append(f"每 {scene['sleep_every']} 回合昏睡 1 回合。可以用极光。")
    if scene.get("vacuum"):
        texts.append("真空：每回合用掉 1 个氧气，没有氧气每回合掉体力上限的 10%。声波炮打不到这里的人。")
    if scene.get("collect_star"):
        texts.append("可以收集星体能量" + ("和超新星。" if scene.get("collect_supernova") else "。"))
    if scene.get("collect_multiplier", 1) > 1:
        texts.append(f"收集东西一次得 {scene['collect_multiplier']} 倍。")
    if scene.get("oxygen_multiplier", 1) > 1:
        texts.append(f"收集氧气一次得 {scene['oxygen_multiplier']} 个。")
    if scene.get("random_radiation"):
        texts.append("每回合随机累计辐射 1、2 或 5 次。")
    if scene.get("learn_multiplier", 1) > 1:
        texts.append(f"在这里学内功一下算 {scene['learn_multiplier']} 下。")
    if scene.get("damage_multiplier", 1) > 1:
        texts.append(f"在这里的人打别人，伤害乘 {scene['damage_multiplier']}。")
    if scene.get("tree_multiplier", 1) > 1:
        texts.append(f"在这里用通天神树，一次长 {scene['tree_multiplier']} 次。")
    if name == "地心深处":
        texts.append("不能直接去：被地震震满 10 下才会掉进来。")
    return [("stat", f"高度 {scene['height']}")] + [("text", text) for text in texts]


# ---------- 整本图鉴 ----------

def codex() -> dict[str, Any]:
    """网页图鉴和悬浮描述框要的全部文字。内容只跟规则数据有关，和哪一局没有关系。"""
    characters = sorted(CHARACTERS.values(), key=lambda c: (
        ["可以选的人物", "进化形态", "真身", "还没开放"].index(character_card(c)["group"])))
    return {
        "skills": [skill_card(spec) for spec in all_skill_specs()],
        "characters": [character_card(c) for c in characters if c["name"] not in DEFERRED_NAMES],
        "inner": [inner_card(name) for name in INNER_VALUES],
        "statuses": [{"name": name, "good": name in GOOD_STATUSES, "text": text + "。"} for name, text in STATUS_TEXT.items()],
        "parasites": [{"name": name, "text": text + "。"} for name, text in PARASITE_TEXT.items()],
        "scenes": [{"name": name, "height": SCENES[name]["height"], "lines": scene_lines(name)}
                   for name in sorted(SCENES, key=lambda n: -SCENES[n]["height"])],
        "big_bang_cost": BIG_BANG_COST,
    }
