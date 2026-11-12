"""`server.claude_usage()` 계약 (G-045, T-231): `.aimem/claude-usage.json` 을 읽어 함대 탭에 쓸 행을 만든다."""
import datetime
import http.server
import json
import pathlib
import sys
import tempfile
import threading
import unittest
import urllib.request
from contextlib import contextmanager
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from aimem_monitor import reader, server  # noqa: E402

KEYS = ["five_hour", "seven_day", "seven_day_opus", "seven_day_sonnet"]
LABELS = ["5시간", "주간", "주간·Opus", "주간·Sonnet"]
DEEP_PAD = "[" * 1500 + "]" * 1500
DEEP_PAYLOAD = (
    '{"at": "2026-11-12T14:03:11", '
    '"rate_limits": {"five_hour": {"used_percentage": 40}}, '
    '"pad": ' + DEEP_PAD + "}"
)


@contextmanager
def monitor_server(root):
    handler = type("H", (server.Handler,), {
        "root": root, "require_auth": False, "tls": False,
        "access_token": None, "guard": server.LoginGuard(),
        "timeout": 5, "log_message": lambda *a, **k: None,
    })
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    httpd.daemon_threads = True
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_address[1]}"
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=3)


class ClaudeUsageTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name).resolve()
        (self.root / ".aimem").mkdir(parents=True)
        self.path = self.root / ".aimem" / "claude-usage.json"

    def _write(self, data):
        self.path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def _usage(self, data):
        self._write(data)
        return server.claude_usage(self.root)

    def test_missing_file_is_none(self):
        self.assertIsNone(server.claude_usage(self.root))

    def test_broken_json_is_none(self):
        self.path.write_text("{not valid json", encoding="utf-8")
        self.assertIsNone(server.claude_usage(self.root))

    def test_missing_rate_limits_is_none(self):
        self.assertIsNone(self._usage({"at": "2026-11-12T14:03:11"}))

    def test_empty_rate_limits_is_none(self):
        self.assertIsNone(self._usage({"at": "2026-11-12T14:03:11", "rate_limits": {}}))

    def test_over_64_kib_is_none(self):
        self.path.write_text(
            json.dumps({"at": "2026-11-12T14:03:11", "pad": "a" * 70000}),
            encoding="utf-8",
        )
        self.assertGreater(self.path.stat().st_size, 64 * 1024)
        self.assertIsNone(server.claude_usage(self.root))

    def test_rows_order_and_labels(self):
        out = self._usage({
            "at": "2026-11-12T14:03:11",
            "rate_limits": {
                "five_hour": {"used_percentage": 10},
                "seven_day": {"used_percentage": 20},
                "seven_day_opus": {"used_percentage": 30},
                "seven_day_sonnet": {"used_percentage": 40},
            },
        })
        self.assertEqual([r["key"] for r in out["rows"]], KEYS)
        self.assertEqual([r["label"] for r in out["rows"]], LABELS)

    def test_unknown_rate_limit_key_is_dropped(self):
        out = self._usage({
            "rate_limits": {
                "nonsense": {"used_percentage": 50},
                "five_hour": {"used_percentage": 10},
            },
        })
        self.assertEqual([r["key"] for r in out["rows"]], ["five_hour"])

    def test_percent_field_precedence(self):
        out = self._usage({
            "rate_limits": {
                "five_hour": {"used_percentage": 10, "utilization": 20, "percent": 30},
                "seven_day": {"utilization": 20, "percent": 30},
                "seven_day_opus": {"percent": 30},
                "seven_day_sonnet": {"used_percentage": "x", "utilization": 40, "percent": 50},
            },
        })
        got = {r["key"]: r["percent"] for r in out["rows"]}
        self.assertAlmostEqual(got["five_hour"], 10.0)
        self.assertAlmostEqual(got["seven_day"], 20.0)
        self.assertAlmostEqual(got["seven_day_opus"], 30.0)
        self.assertAlmostEqual(got["seven_day_sonnet"], 40.0)

    def test_non_numeric_rows_are_dropped(self):
        out = self._usage({
            "rate_limits": {
                "five_hour": {"used_percentage": "많음"},
                "seven_day": {"used_percentage": True, "utilization": True},
                "seven_day_opus": {"used_percentage": 50},
            },
        })
        self.assertEqual([r["key"] for r in out["rows"]], ["seven_day_opus"])
        self.assertAlmostEqual(out["rows"][0]["percent"], 50.0)

    def test_percent_is_clamped(self):
        out = self._usage({
            "rate_limits": {
                "five_hour": {"used_percentage": -5},
                "seven_day": {"used_percentage": 150},
            },
        })
        got = {r["key"]: r["percent"] for r in out["rows"]}
        self.assertAlmostEqual(got["five_hour"], 0.0)
        self.assertAlmostEqual(got["seven_day"], 100.0)

    def test_epoch_resets_at_becomes_local_iso(self):
        epoch = 1700000000
        out = self._usage({"rate_limits": {"five_hour": {"used_percentage": 10, "resets_at": epoch}}})
        expected = datetime.datetime.fromtimestamp(epoch).isoformat(timespec="seconds")
        self.assertEqual(out["rows"][0]["resets_at_iso"], expected)

    def test_tz_resets_at_becomes_local_iso(self):
        raw = "2026-11-12T18:00:00Z"
        out = self._usage({"rate_limits": {"five_hour": {"used_percentage": 10, "resets_at": raw}}})
        expected = (
            datetime.datetime.fromisoformat(raw.replace("Z", "+00:00"))
            .astimezone()
            .replace(tzinfo=None)
            .isoformat(timespec="seconds")
        )
        self.assertEqual(out["rows"][0]["resets_at_iso"], expected)

    def test_missing_or_garbage_resets_at_is_none_but_row_remains(self):
        out = self._usage({
            "rate_limits": {
                "five_hour": {"used_percentage": 10},
                "seven_day": {"used_percentage": 20, "resets_at": "soon"},
            },
        })
        self.assertEqual(len(out["rows"]), 2)
        self.assertIsNone(out["rows"][0]["resets_at_iso"])
        self.assertIsNone(out["rows"][1]["resets_at_iso"])

    def test_age_seconds(self):
        at = (datetime.datetime.now() - datetime.timedelta(minutes=20)).isoformat(timespec="seconds")
        out = self._usage({"at": at, "rate_limits": {"five_hour": {"used_percentage": 10}}})
        self.assertGreaterEqual(out["age_seconds"], 1100)
        self.assertLessEqual(out["age_seconds"], 1300)
        self.assertIs(type(out["age_seconds"]), int)

    def test_future_at_one_hour_has_zero_age(self):
        at = (datetime.datetime.now() + datetime.timedelta(hours=1)).isoformat(timespec="seconds")
        out = self._usage({"at": at, "rate_limits": {"five_hour": {"used_percentage": 10}}})
        self.assertIsNotNone(out)
        self.assertEqual(out["age_seconds"], 0)
        self.assertIs(type(out["age_seconds"]), int)

    def test_future_at_ten_days_has_zero_age(self):
        at = (datetime.datetime.now() + datetime.timedelta(days=10)).isoformat(timespec="seconds")
        out = self._usage({"at": at, "rate_limits": {"five_hour": {"used_percentage": 10}}})
        self.assertIsNotNone(out)
        self.assertEqual(out["age_seconds"], 0)
        self.assertIs(type(out["age_seconds"]), int)

    def test_past_at_two_hours_has_about_7200_age(self):
        at = (datetime.datetime.now() - datetime.timedelta(hours=2)).isoformat(timespec="seconds")
        out = self._usage({"at": at, "rate_limits": {"five_hour": {"used_percentage": 10}}})
        self.assertIsNotNone(out)
        self.assertGreaterEqual(out["age_seconds"], 7200 - 120)
        self.assertLessEqual(out["age_seconds"], 7200 + 120)

    def test_age_seconds_none_without_at(self):
        out = self._usage({"rate_limits": {"five_hour": {"used_percentage": 10}}})
        self.assertIsNone(out["age_seconds"])
        self.assertIsNone(out["at"])

    def test_empty_filtered_rows_is_none(self):
        self.assertIsNone(self._usage({"rate_limits": {"nonsense": {"used_percentage": 50}}}))
        self.assertIsNone(self._usage({"rate_limits": {"five_hour": {"used_percentage": "많음"}}}))

    def test_state_keys(self):
        blank = server._blank_keys(self.root)
        self.assertIn("claude_usage", blank)
        self.assertIsNone(blank["claude_usage"])

        patches = [
            mock.patch.object(server, "fleet_state", lambda *a, **k: {}),
            mock.patch.object(server, "collect_graphs", lambda *a, **k: {}),
            mock.patch.object(server, "manager_status", lambda *a, **k: {}),
            mock.patch.object(server, "list_projects", lambda *a, **k: {}),
            mock.patch.object(server, "_reader",
                              lambda: mock.Mock(collect=lambda root: {})),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.assertIn("claude_usage", server._empty_state(self.root, []))
        self.assertIn("claude_usage", server.collect_state(self.root))

    def test_directory_at_file_path_is_none(self):
        self.path.mkdir()
        self.assertIsNone(server.claude_usage(self.root))

    def test_deeply_nested_json_is_none_without_exception(self):
        self.path.write_text(DEEP_PAYLOAD, encoding="utf-8")
        try:
            out = server.claude_usage(self.root)
        except Exception as e:
            self.fail(
                "깊은 중첩 JSON 에서 claude_usage 가 예외를 던졌습니다: "
                f"{type(e).__name__}: {e}"
            )
        self.assertIsNone(out)

    def test_out_of_range_at_is_not_fatal(self):
        for at in ("0001-01-01T00:00:00+05:00", "9999-12-31T23:59:59-05:00"):
            with self.subTest(at=at):
                self._write({
                    "at": at,
                    "rate_limits": {"five_hour": {"used_percentage": 40}},
                })
                try:
                    out = server.claude_usage(self.root)
                except Exception as e:
                    self.fail(
                        f"{at} 에서 claude_usage 가 예외를 던졌습니다: "
                        f"{type(e).__name__}: {e}"
                    )
                self.assertIsNotNone(out)
                self.assertEqual([r["key"] for r in out["rows"]], ["five_hour"])
                self.assertAlmostEqual(out["rows"][0]["percent"], 40.0)

    def test_api_state_200_with_deeply_nested_usage(self):
        self.path.write_text(DEEP_PAYLOAD, encoding="utf-8")
        with monitor_server(self.root) as base:
            with urllib.request.urlopen(base + "/api/state", timeout=10) as resp:
                self.assertEqual(resp.status, 200)
                body = resp.read().decode("utf-8")
                content_type = resp.headers.get("Content-Type", "")
        self.assertIn("application/json", content_type)
        data = json.loads(body)
        self.assertIsInstance(data, dict)
        self.assertIn("claude_usage", data)

    def test_over_64_kib_with_normal_rate_limits_is_none(self):
        self._write({
            "at": "2026-11-12T14:03:11",
            "rate_limits": {
                "five_hour": {"used_percentage": 10},
                "seven_day": {"used_percentage": 20},
                "seven_day_opus": {"used_percentage": 30},
                "seven_day_sonnet": {"used_percentage": 40},
            },
            "pad": "a" * 70000,
        })
        self.assertGreater(self.path.stat().st_size, 64 * 1024)
        self.assertIsNone(server.claude_usage(self.root))

    def test_both_state_branches_have_claude_usage(self):
        normal = server.collect_state(self.root)
        self.assertIsInstance(normal, dict)
        self.assertIn("claude_usage", normal)

        with mock.patch.object(reader, "collect", side_effect=RuntimeError("boom")):
            failed = server.collect_state(self.root)
        self.assertIsInstance(failed, dict)
        self.assertIn("claude_usage", failed)
        self.assertIsInstance(failed.get("errors"), list)
        self.assertTrue(failed["errors"])

    def test_surrogate_at_returns_without_exception(self):
        self.path.write_text(
            '{"at": "\\ud800", "rate_limits": {"five_hour": {"used_percentage": 40}}}',
            encoding="utf-8",
        )
        try:
            out = server.claude_usage(self.root)
        except Exception as e:
            self.fail(
                "짝 없는 서러게이트 `at` 에서 claude_usage 가 예외를 던졌습니다: "
                f"{type(e).__name__}: {e}"
            )
        self.assertIsNotNone(out)
        self.assertIsNone(out["at"])
        self.assertEqual([r["key"] for r in out["rows"]], ["five_hour"])
        self.assertAlmostEqual(out["rows"][0]["percent"], 40.0)

    def test_api_state_200_with_surrogate_at_normal_branch(self):
        self.path.write_text(
            '{"at": "\\ud800", "rate_limits": {"five_hour": {"used_percentage": 40}}}',
            encoding="utf-8",
        )
        with monitor_server(self.root) as base:
            with urllib.request.urlopen(base + "/api/state", timeout=10) as resp:
                self.assertEqual(resp.status, 200)
                body = resp.read().decode("utf-8")
        data = json.loads(body)
        self.assertIsInstance(data, dict)
        self.assertIn("claude_usage", data)

    def test_api_state_200_with_surrogate_at_failed_branch(self):
        self.path.write_text(
            '{"at": "\\ud800", "rate_limits": {"five_hour": {"used_percentage": 40}}}',
            encoding="utf-8",
        )
        with mock.patch.object(reader, "collect", side_effect=RuntimeError("boom")):
            with monitor_server(self.root) as base:
                with urllib.request.urlopen(base + "/api/state", timeout=10) as resp:
                    self.assertEqual(resp.status, 200)
                    body = resp.read().decode("utf-8")
        data = json.loads(body)
        self.assertIsInstance(data, dict)
        self.assertIn("claude_usage", data)

    def test_side_card_failure_does_not_kill_normal_state(self):
        with mock.patch.object(server, "claude_usage", side_effect=RuntimeError("boom")):
            try:
                state = server.collect_state(self.root)
            except Exception as e:
                self.fail(
                    "곁다리 카드 실패가 collect_state 를 죽였습니다: "
                    f"{type(e).__name__}: {e}"
                )
        self.assertIsInstance(state, dict)
        self.assertIn("claude_usage", state)
        self.assertIsNone(state["claude_usage"])

    def test_side_card_failure_does_not_kill_failed_branch(self):
        with mock.patch.object(reader, "collect", side_effect=RuntimeError("boom")):
            with mock.patch.object(server, "claude_usage", side_effect=RuntimeError("boom")):
                try:
                    state = server.collect_state(self.root)
                except Exception as e:
                    self.fail(
                        "곁다리 카드 실패가 실패 갈래 collect_state 를 죽였습니다: "
                        f"{type(e).__name__}: {e}"
                    )
        self.assertIsInstance(state, dict)
        self.assertIn("claude_usage", state)
        self.assertIsNone(state["claude_usage"])
        self.assertIsInstance(state.get("errors"), list)
        self.assertTrue(state["errors"])

    def test_normal_branch_has_claude_usage_key(self):
        state = server.collect_state(self.root)
        self.assertIn("claude_usage", state)

    def test_failed_branch_has_claude_usage_key(self):
        with mock.patch.object(reader, "collect", side_effect=RuntimeError("boom")):
            state = server.collect_state(self.root)
        self.assertIn("claude_usage", state)


if __name__ == "__main__":
    unittest.main()
