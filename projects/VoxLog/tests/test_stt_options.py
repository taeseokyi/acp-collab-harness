import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from voxlog.stt_options import (
    CONTEXT_MAX,
    PREPROCESS,
    SPEAKERS_MAX,
    SPEAKERS_MIN,
    form_fields,
    normalize,
    used_from_result,
)


class NormalizeTest(unittest.TestCase):
    # 1
    def test_none_and_empty_become_empty(self):
        self.assertEqual(normalize(None), {})
        self.assertEqual(normalize({}), {})

    # 2
    def test_null_values_are_dropped(self):
        self.assertEqual(
            normalize({
                "preprocess": None,
                "num_speakers": None,
                "context": None,
                "auto": None,
                "review": None,
            }),
            {},
        )

    # 3
    def test_not_dict_rejected(self):
        for value in ([], "denoise", 3, True):
            with self.assertRaises(ValueError):
                normalize(value)

    # 4
    def test_unknown_key_rejected(self):
        with self.assertRaises(ValueError):
            normalize({"language": "ko"})
        with self.assertRaises(ValueError):
            normalize({"preprocess": "none", "min_speakers": 1})

    # 5
    def test_preprocess_all_allowed_and_bad_values(self):
        for value in PREPROCESS:
            self.assertEqual(normalize({"preprocess": value}), {"preprocess": value})
        for value in ("Denoise", "normal", "basic ", ""):
            with self.assertRaises(ValueError):
                normalize({"preprocess": value})

    # 6
    def test_num_speakers_boundaries_and_types(self):
        self.assertEqual(normalize({"num_speakers": SPEAKERS_MIN}), {"num_speakers": 1})
        self.assertEqual(normalize({"num_speakers": SPEAKERS_MAX}), {"num_speakers": 20})
        for value in (0, 21, -1, True, False, "3", 3.0):
            with self.assertRaises(ValueError):
                normalize({"num_speakers": value})

    # 7
    def test_context_trim_empty_and_length_limit(self):
        self.assertEqual(normalize({"context": "  인용  "}), {"context": "인용"})
        self.assertEqual(normalize({"context": " \t\n "}), {})
        self.assertEqual(
            normalize({"context": "가" * CONTEXT_MAX}),
            {"context": "가" * CONTEXT_MAX},
        )
        with self.assertRaises(ValueError):
            normalize({"context": "가" * (CONTEXT_MAX + 1)})
        with self.assertRaises(ValueError):
            normalize({"context": 123})

    # 8
    def test_auto_review_bools(self):
        self.assertEqual(
            normalize({"auto": True, "review": False}),
            {"auto": True, "review": False},
        )
        for value in ("true", "1", 1, 0, "false"):
            with self.assertRaises(ValueError):
                normalize({"auto": value})
            with self.assertRaises(ValueError):
                normalize({"review": value})

    # 9
    def test_does_not_mutate_input_and_returns_new_dict(self):
        opts = {"preprocess": "denoise", "num_speakers": 2}
        norm = normalize(opts)
        self.assertIsNot(norm, opts)
        norm["preprocess"] = "none"
        self.assertEqual(opts["preprocess"], "denoise")

    # 10
    def test_error_messages_are_korean_one_line(self):
        messages = []
        for obj in (
            "x",
            {"oops": 1},
            {"preprocess": "bad"},
            {"num_speakers": 0},
            {"context": "가" * (CONTEXT_MAX + 1)},
            {"auto": "1"},
        ):
            try:
                normalize(obj)
            except ValueError as exc:
                messages.append(str(exc))
        self.assertTrue(messages)
        for message in messages:
            self.assertNotIn("\n", message)
            self.assertTrue(any("\uac00" <= ch <= "\ud7a3" for ch in message))


class FormFieldsTest(unittest.TestCase):
    # 11
    def test_empty_options_give_no_fields(self):
        self.assertEqual(form_fields(None), {})
        self.assertEqual(form_fields({}), {})

    # 12
    def test_fields_shape_and_strings(self):
        fields = form_fields({
            "preprocess": "denoise",
            "num_speakers": 2,
            "context": "  이름  ",
            "auto": True,
            "review": False,
        })
        self.assertEqual(fields, {
            "preprocess": "denoise",
            "num_speakers": "2",
            "context": "이름",
            "auto": "1",
            "review": "0",
        })

    # 13
    def test_false_and_zero_flags(self):
        self.assertEqual(form_fields({"auto": False, "review": False}),
                         {"auto": "0", "review": "0"})
        self.assertEqual(form_fields({"auto": True, "review": True}),
                         {"auto": "1", "review": "1"})

    # 14
    def test_bad_options_raise(self):
        with self.assertRaises(ValueError):
            form_fields({"num_speakers": 21})


class UsedFromResultTest(unittest.TestCase):
    # 15
    def test_not_dict_result_gives_empty(self):
        for value in (None, [], "done", 3):
            self.assertEqual(used_from_result(value), {})

    # 16
    def test_full_result_shape(self):
        self.assertEqual(
            used_from_result({
                "preprocess": "denoise",
                "mode": "context",
                "speakers": [{"speaker": 1}, {"speaker": 2}],
                "auto": {"num_speakers": 2},
                "review": {"changed": True},
            }),
            {
                "preprocess": "denoise",
                "mode": "context",
                "speakers": 2,
                "auto": True,
                "review": True,
            },
        )

    # 17
    def test_speakers_list_length_and_int(self):
        self.assertEqual(used_from_result({"speakers": [1, 2, 3]})["speakers"], 3)
        self.assertEqual(used_from_result({"speakers": 4})["speakers"], 4)
        for value in (None, "2", True, 2.0, {"a": 1}):
            self.assertIsNone(used_from_result({"speakers": value})["speakers"])

    # 18
    def test_auto_dict_none_and_bool(self):
        self.assertTrue(used_from_result({"auto": {"x": 1}})["auto"])
        self.assertFalse(used_from_result({"auto": None})["auto"])
        self.assertFalse(used_from_result({})["auto"])
        self.assertFalse(used_from_result({"auto": False})["auto"])
        self.assertTrue(used_from_result({"auto": True})["auto"])
        self.assertFalse(used_from_result({"auto": "0"})["auto"])

    # 19
    def test_review_present_is_true(self):
        self.assertTrue(used_from_result({"review": {}})["review"])
        self.assertTrue(used_from_result({"review": False})["review"])
        self.assertFalse(used_from_result({"review": None})["review"])
        self.assertFalse(used_from_result({})["review"])

    # 20
    def test_texts_truncated_to_40_chars(self):
        got = used_from_result({
            "preprocess": "x" * 60,
            "mode": "y" * 50,
        })
        self.assertEqual(got["preprocess"], "x" * 40)
        self.assertEqual(got["mode"], "y" * 40)
        self.assertIsNone(used_from_result({"preprocess": 3})["preprocess"])
        self.assertIsNone(used_from_result({})["mode"])


if __name__ == "__main__":
    unittest.main()
