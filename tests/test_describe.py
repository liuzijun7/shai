"""说明文字（悬浮描述框、人物详情、图鉴）：每个招、每个人物、每种内功和状态都要有话可说。

加了新招、新人物以后，如果这里有测试不过：
- “没有拼音首字母”：重新生成 ``shai/initials.py``。办法是装一次 pypinyin
  （``pip install --no-cache-dir --target D:\\pylibs pypinyin``），对每个名字取
  ``lazy_pinyin(name, style=Style.FIRST_LETTER)`` 连起来，写进那个文件；多音字手工改。
- “状态没有说明”：在 ``shai/describe.py`` 的 ``STATUS_TEXT`` 里补一句。
"""

import json
import unittest

from shai.data import CHARACTERS, INNER_VALUES, SKILLS
from shai.describe import (PARASITE_TEXT, STATUS_TEXT, TRAIT_TEXT, all_skill_specs, character_lines, codex,
                           inner_text, skill_lines, wan)
from shai.initials import INITIALS


class DescribeTests(unittest.TestCase):
    def test_numbers_read_naturally(self):
        self.assertEqual(wan(15000), "1.5 万")
        self.assertEqual(wan(10000), "1 万")
        self.assertEqual(wan(300000), "30 万")
        self.assertEqual(wan(9000), "9000")

    def test_every_listed_move_has_text(self):
        for spec in all_skill_specs():
            lines = skill_lines(spec)
            self.assertTrue(lines, spec["name"])
            for style, text in lines:
                self.assertIn(style, {"flag", "stat", "text", "note"}, spec["name"])
                self.assertTrue(text.strip(), spec["name"])
                self.assertNotIn("None", text, spec["name"])

    def test_no_line_is_said_twice(self):
        for spec in all_skill_specs():
            texts = [text for _, text in skill_lines(spec)]
            self.assertEqual(len(texts), len(set(texts)), spec["name"])

    def test_every_status_and_parasite_is_explained(self):
        for spec in SKILLS.values():
            for name, _ in spec["statuses"]:
                self.assertTrue(STATUS_TEXT.get(name), f"状态没有说明：{name}（{spec['name']}）")
            if spec.get("parasite"):
                self.assertIn(spec["parasite"], PARASITE_TEXT, spec["name"])

    def test_every_inner_level_is_explained(self):
        for name, levels in INNER_VALUES.items():
            for level in levels:
                self.assertTrue(inner_text(name, level), f"{name} {level} 级")

    def test_every_character_has_a_soul_text_in_plain_words(self):
        for data in CHARACTERS.values():
            lines = character_lines(data)
            self.assertTrue(lines[0][1].startswith("体力"), data["name"])
            for trait in data["traits"]:
                self.assertIn(trait, TRAIT_TEXT, f"{data['name']}的特点“{trait}”没有说明")

    def test_facts_follow_the_rules_data(self):
        by_name = {spec["name"]: " ".join(text for _, text in skill_lines(spec)) for spec in all_skill_specs()
                   if not spec.get("character")}
        self.assertIn("威力 1.5 万", by_name["寒潮"])
        self.assertIn("防御 3 能防住", by_name["寒潮"])
        self.assertIn("最高到电离层", by_name["寒潮"])             # 雨晨：寒潮只能打大气层之内
        self.assertIn("最高到宇宙", by_name["太阳黑子爆"])
        self.assertIn("多高的地方都打得到", by_name["雷神之怒"])
        self.assertIn("先手", by_name["雷神之怒"])
        self.assertIn("只有憋神技能防", by_name["惊天混元掌"])
        self.assertIn("每条命只能用一次", by_name["惊天混元掌"])
        self.assertNotIn("每条命只能用一次", by_name["通天神树"])
        self.assertIn("自己封喉 3 回合", by_name["昏睡咒"])            # 特技用完自己封喉
        self.assertNotIn("封喉 3 回合", by_name["天雷"])

    def test_signature_moves_do_not_mention_self_seal(self):
        fire = next(spec for spec in all_skill_specs() if spec["name"] == "千步烈烧")       # 库巴自己的大招
        self.assertNotIn("自己封喉", " ".join(text for _, text in skill_lines(fire)))

    def test_every_name_can_be_searched_by_pinyin_initials(self):
        names = [spec["name"] for spec in all_skill_specs()] + [c["name"] for c in CHARACTERS.values()] + list(INNER_VALUES)
        for name in names:
            self.assertTrue(INITIALS.get(name), f"没有拼音首字母：{name}")
        self.assertEqual(INITIALS["寒潮"], "hc")

    def test_codex_is_plain_data_the_page_can_load(self):
        book = json.loads(json.dumps(codex(), ensure_ascii=False))
        self.assertGreater(len(book["skills"]), 80)
        self.assertEqual({card["kind"] for card in book["skills"]}, {"技能", "神技", "防御", "物品", "专属"})
        names = [card["name"] for card in book["characters"]]
        self.assertIn("武圣", names)
        self.assertNotIn("三鲍太监", names)                           # 还没开放的人物不进图鉴
        self.assertNotIn("动感光波", [card["name"] for card in book["skills"]])      # 做了但不显示的招

    def test_server_serves_the_codex(self):
        import os
        import sys
        try:
            import fastapi  # noqa: F401
        except ImportError:                               # 这台电脑把库装在 D:\pylibs
            if os.path.isdir(r"D:\pylibs"):
                sys.path.append(r"D:\pylibs")
            try:
                import fastapi  # noqa: F401
            except ImportError:
                self.skipTest("没有装 fastapi")
        from server.app import get_codex
        self.assertEqual(get_codex()["skills"][0]["name"], "普通攻击")


if __name__ == "__main__":
    unittest.main()
