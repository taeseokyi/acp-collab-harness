"""`fleet_rt.config` / `fleet_rt.providers` 검사 - 설정 읽기, 공급자 판별, 자리 세기, 준비 점검 (네트워크 없음)."""
import _fleet_env
import io
import json
import os
import pathlib
import tempfile
import unittest
import urllib.error
from unittest import mock

from fleet_rt import config, providers, sessions

REPO = pathlib.Path(__file__).resolve().parent.parent
SECRET = "sk-SECRET-VALUE-123"


def fake_session(root, sid, provider, pid, end=False):
    d = pathlib.Path(root) / sid
    d.mkdir(parents=True)
    if pid == "live":
        pid = _fleet_env.marked_pid(root, sid)   # 살아 있는 감독 = 그 세션의 표식을 단 프로세스
    (d / "meta.json").write_text(json.dumps({"id": sid, "provider": provider, "supervisor_pid": pid,
                                             "proc_start": sessions.proc_start(pid)}), encoding="utf-8")
    if end:
        (d / "end.json").write_text(json.dumps({"state": "done", "rc": 0}), encoding="utf-8")
    return d


def dead_pid():
    pid = 4_000_000
    while os.path.exists(f"/proc/{pid}"):
        pid += 1
    return pid


class ConfigTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name)

    def test_repo_file_matches_defaults(self):
        cfg = config.load(REPO)
        self.assertEqual(cfg.data, config.DEFAULTS)

    def test_missing_file_gives_defaults(self):
        cfg = config.load(self.root)
        self.assertIsNone(cfg.source)
        self.assertEqual(cfg.max_concurrent("kisti"), 1)
        self.assertEqual(cfg.idle_timeout("anthropic"), 600.0)

    def test_malformed_raises(self):
        (self.root / "fleet.toml").write_text("[providers.x\nfoo =", encoding="utf-8")
        with self.assertRaises(config.ConfigError):
            config.load(self.root)

    def test_bad_types_raise(self):
        (self.root / "fleet.toml").write_text('[providers.x]\nmax_concurrent = "many"\n', encoding="utf-8")
        with self.assertRaises(config.ConfigError):
            config.load(self.root)

    def test_unknown_provider_in_harness_raises(self):
        (self.root / "fleet.toml").write_text('[harness.h]\nproviders = ["nope"]\n', encoding="utf-8")
        with self.assertRaises(config.ConfigError):
            config.load(self.root)

    def test_reload_on_mtime_change(self):
        f = self.root / "fleet.toml"
        f.write_text('[providers.a]\nmax_concurrent = 2\n', encoding="utf-8")
        self.assertEqual(config.load(self.root).max_concurrent("a"), 2)
        f.write_text('[providers.a]\nmax_concurrent = 5\n', encoding="utf-8")
        os.utime(f, ns=(1, 2_000_000_000))
        self.assertEqual(config.load(self.root).max_concurrent("a"), 5)

    def test_accessors(self):
        cfg = config.load(REPO)
        self.assertIn("kisti", cfg.providers())
        self.assertEqual(cfg.provider("kisti")["env_key"], "KISTI_API_KEY")
        self.assertEqual(cfg.harness("codex")["binary"], "codex")
        self.assertIsNone(cfg.provider("zzz"))
        self.assertEqual(cfg.max_concurrent("zzz"), 1)
        self.assertIsNone(cfg.idle_timeout("zzz"))

    def test_provider_of(self):
        cfg = config.load(REPO)
        table = [("opencode", "kisti/kistillm", "kisti"), ("opencode", "exaone/k-exaone_v2.5", "exaone"),
                 ("claude", "opus", "anthropic"), ("claude", "sonnet", "anthropic"),
                 ("claude", "claude-opus-5-5", "anthropic"), ("claude", "anthropic/claude-sonnet-5-5", "anthropic"),
                 ("claude", "claude-cli/opus", "anthropic"),
                 ("claude", None, "anthropic"), ("codex", None, "kisti"), ("opencode", None, "kisti"),
                 ("codex", "kistillm", "kisti"), ("codex", "mystery-model", None),
                 ("nohar", None, None), ("nohar", "gpt-9", None)]
        for h, m, want in table:
            with self.subTest(h=h, m=m):
                self.assertEqual(cfg.provider_of(h, m), want)

    def test_models_for(self):
        cfg = config.load(REPO)
        self.assertEqual(cfg.models_for("claude"),
                         [{"key": k, "name": k, "provider": "anthropic"} for k in ("opus", "sonnet", "haiku")])
        keys = [m["key"] for m in cfg.models_for("opencode")]
        self.assertEqual(keys, ["kisti/kistillm", "exaone/k-exaone_v2.5", "openrouter/deepseek/deepseek-v4.1-flash"])
        self.assertEqual(cfg.models_for("codex")[0], {"key": "kisti/kistillm", "name": "kistillm", "provider": "kisti"})
        self.assertEqual(cfg.models_for("nohar"), [])


class GateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name)
        self.cfg = config.load(REPO)

    def test_running_by_provider(self):
        fake_session(self.root, "a", "kisti", "live")
        fake_session(self.root, "b", "anthropic", "live")
        fake_session(self.root, "c", "anthropic", "live")
        fake_session(self.root, "dead", "kisti", dead_pid())            # 감독이 죽음
        fake_session(self.root, "ended", "kisti", dead_pid(), end=True)  # 끝남
        (self.root / "nometa").mkdir()
        self.assertEqual(providers.running_by_provider(self.root), {"kisti": 1, "anthropic": 2})
        self.assertEqual(providers.running_by_provider(self.root / "missing"), {})

    def test_has_room_and_room(self):
        self.assertTrue(providers.has_room(self.cfg, self.root, "kisti"))
        fake_session(self.root, "a", "kisti", "live")
        fake_session(self.root, "b", "anthropic", "live")
        self.assertFalse(providers.has_room(self.cfg, self.root, "kisti"))
        self.assertTrue(providers.has_room(self.cfg, self.root, "anthropic"))
        self.assertTrue(providers.has_room(self.cfg, self.root, None))
        self.assertEqual(providers.room(self.cfg, self.root), {"kisti": 0, "exaone": 1, "openrouter": 3, "anthropic": 2})



class ProbeTest(unittest.TestCase):
    def setUp(self):
        self.cfg = config.load(REPO)
        self.env = {"KISTI_API_KEY": SECRET}

    def _resp(self, code=200):
        r = mock.MagicMock()
        r.status = code
        r.getcode.return_value = code
        r.__enter__.return_value = r
        return r

    def test_ok_sends_bearer(self):
        with mock.patch("urllib.request.urlopen", return_value=self._resp()) as u:
            ok, detail = providers.probe(self.cfg, "kisti", self.env)
        self.assertTrue(ok)
        req = u.call_args[0][0]
        self.assertEqual(req.full_url, "https://aida.kisti.re.kr:10430/v1/models")
        self.assertEqual(req.get_header("Authorization"), f"Bearer {SECRET}")
        self.assertNotIn(SECRET, detail)

    def test_missing_key(self):
        with mock.patch("urllib.request.urlopen") as u:
            ok, detail = providers.probe(self.cfg, "kisti", {})
        self.assertFalse(ok)
        self.assertIn("KISTI_API_KEY", detail)
        self.assertIn("환경변수 없음", detail)
        u.assert_not_called()

    def test_timeout(self):
        for exc in (TimeoutError("t"), urllib.error.URLError(TimeoutError("t"))):
            with mock.patch("urllib.request.urlopen", side_effect=exc):
                ok, detail = providers.probe(self.cfg, "kisti", self.env)
            self.assertFalse(ok)
            self.assertIn("시간 초과", detail)
            self.assertNotIn(SECRET, detail)

    def test_http_401(self):
        err = urllib.error.HTTPError("u", 401, "Unauthorized", {}, io.BytesIO(SECRET.encode()))
        with mock.patch("urllib.request.urlopen", side_effect=err):
            ok, detail = providers.probe(self.cfg, "kisti", self.env)
        self.assertFalse(ok)
        self.assertIn("401", detail)
        self.assertNotIn(SECRET, detail)

    def test_connection_refused_has_no_key(self):
        with mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError(ConnectionRefusedError(SECRET))):
            ok, detail = providers.probe(self.cfg, "kisti", self.env)
        self.assertFalse(ok)
        self.assertNotIn(SECRET, detail)

    def test_no_probe_configured(self):
        with mock.patch("urllib.request.urlopen") as u:
            self.assertEqual(providers.probe(self.cfg, "anthropic", {}), (True, "점검 없음"))
        u.assert_not_called()

    def test_unknown_provider(self):
        self.assertFalse(providers.probe(self.cfg, "zzz", {})[0])


if __name__ == "__main__":
    unittest.main()
