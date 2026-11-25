import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)
sys.path.insert(0, PROJECT)

from voxlog import tags  # noqa: E402


class TagsTest(unittest.TestCase):
    def value_error(self, fn, arg, message):
        with self.assertRaises(ValueError) as caught:
            fn(arg)
        self.assertEqual(str(caught.exception), message)

    # 1
    def test_clean_collapses_all_whitespace(self):
        self.assertEqual(tags.clean("  회의  "), "회의")
        self.assertEqual(tags.clean("a  b\n\tc\r\nd"), "a b c d")
        self.assertEqual(tags.clean(""), "")

    # 2
    def test_normalize_label_type_and_length(self):
        self.value_error(tags.normalize_label, None, "label 은 문자열이어야 합니다")
        self.value_error(tags.normalize_label, 7, "label 은 문자열이어야 합니다")
        self.value_error(tags.normalize_label, ["회의"], "label 은 문자열이어야 합니다")
        self.assertEqual(tags.normalize_label("  회의\n이름  "), "회의 이름")
        self.assertEqual(tags.normalize_label("가" * tags.LABEL_MAX), "가" * 40)
        self.value_error(tags.normalize_label, "가" * (tags.LABEL_MAX + 1),
                         "이름은 40자 이하여야 합니다")

    # 3
    def test_normalize_tags_requires_string_list(self):
        self.value_error(tags.normalize_tags, "회의", "tags 는 문자열 목록이어야 합니다")
        self.value_error(tags.normalize_tags, ("회의",), "tags 는 문자열 목록이어야 합니다")
        self.value_error(tags.normalize_tags, None, "tags 는 문자열 목록이어야 합니다")
        self.value_error(tags.normalize_tags, ["회의", 1], "tags 는 문자열 목록이어야 합니다")
        self.assertEqual(tags.normalize_tags([]), [])

    # 4
    def test_normalize_tags_empty_length_and_case_duplicates(self):
        self.assertEqual(
            tags.normalize_tags(["", "  ", "\n", "회의", " 회의 ", "회의"]),
            ["회의"],
        )
        self.assertEqual(tags.normalize_tags(["AI", "ai", "Ai"]), ["AI"])
        self.assertEqual(tags.normalize_tags(["가" * tags.TAG_MAX]), ["가" * 20])
        self.value_error(tags.normalize_tags, ["가" * (tags.TAG_MAX + 1)],
                         "태그는 하나당 20자 이하여야 합니다")

    # 5
    def test_normalize_tags_counts_after_dedupe(self):
        ten = ["t%d" % i for i in range(tags.TAGS_MAX)]
        self.assertEqual(tags.normalize_tags(ten), ten)
        self.value_error(tags.normalize_tags, ten + ["t10"],
                         "태그는 최대 10개입니다")
        # 11 raw items, but one case-insensitive duplicate, so 10 remain.
        self.assertEqual(tags.normalize_tags(ten + ["T0"]), ten)

    # 6
    def test_tag_key_is_casefold(self):
        self.assertEqual(tags.tag_key("AI"), "ai")
        self.assertEqual(tags.tag_key("Ä"), tags.tag_key("ä"))

    # 7
    def test_merge_tags_human_first_overlap_and_cap(self):
        self.assertEqual(tags.merge_tags(["사람"], ["사람", "AI"]), ["사람", "AI"])
        self.assertEqual(
            tags.merge_tags(["a", "b"], ["A", "B", "c", "C", "d"]),
            ["a", "b", "c", "d"],
        )
        human = ["h%d" % i for i in range(8)]
        merged = tags.merge_tags(human, ["auto1", "auto2", "auto3"])
        self.assertEqual(merged, human + ["auto1", "auto2"])
        self.assertEqual(len(merged), tags.TAGS_MAX)

    # 8
    def test_parse_tag_output_bullets_numbers_quotes_and_punctuation(self):
        text = "\n".join([
            "- 회의",
            "* 가짜 태그",
            "• 세번째",
            "· 네번째",
            "# 다섯번째",
            "1. 여섯번째",
            "2) 일곱번째",
            "① 여덟번째",
            '"아홉번째"',
            "`열번째`",
            "열한번째.",
            "열두번째。",
        ])
        self.assertEqual(
            tags.parse_tag_output(text, limit=20),
            ["회의", "가짜 태그", "세번째", "네번째", "다섯번째", "여섯번째",
             "일곱번째", "여덟번째", "아홉번째", "열번째", "열한번째", "열두번째"],
        )

    # 9
    def test_parse_tag_output_splits_commas(self):
        self.assertEqual(
            tags.parse_tag_output("회의, 가짜 태그、세번째, - 네번째"),
            ["회의", "가짜 태그", "세번째", "네번째"],
        )

    # 10
    def test_parse_tag_output_drops_bad_and_duplicate_tags(self):
        long20 = "가" * tags.TAG_MAX
        text = "\n".join([
            long20,
            "나" * (tags.TAG_MAX + 1),
            "<태그>",
            "꺾쇠>",
            "AI",
            "ai",
            "   ",
        ])
        self.assertEqual(tags.parse_tag_output(text, limit=20), [long20, "AI"])
        self.assertEqual(tags.parse_tag_output(None), [])

    # 11
    def test_parse_tag_output_limit(self):
        text = "\n".join(["tag%d" % i for i in range(6)])
        self.assertEqual(tags.parse_tag_output(text), ["tag0", "tag1", "tag2", "tag3", "tag4"])
        self.assertEqual(tags.parse_tag_output(text, limit=2), ["tag0", "tag1"])
        self.assertEqual(tags.parse_tag_output(text, limit=0), [])

    # R49-N2
    def test_parse_tag_output_drops_sentences_and_strips_headers(self):
        self.assertEqual(
            tags.parse_tag_output("죄송합니다. 요약할 수 없습니다"), [])
        self.assertEqual(
            tags.parse_tag_output("Here are the tags:\n- 회의\n- 예산"),
            ["회의", "예산"])
        self.assertEqual(
            tags.parse_tag_output("태그: 회의, 예산"),
            ["회의", "예산"])
        self.assertEqual(
            tags.parse_tag_output("Error: rate limited"), [])
        self.assertEqual(tags.parse_tag_output("회의."), ["회의"])


if __name__ == "__main__":
    unittest.main()
