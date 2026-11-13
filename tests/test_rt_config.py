"""`fleet_rt.config` / `fleet_rt.providers` 검사 - 설정 읽기, 공급자 판별, 자리 세기, 준비 점검 (네트워크 없음)."""
import _fleet_env
import io
import json
import os
import pathlib
import http.server
import socket
import tempfile
import threading
import unittest
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
        self.assertEqual(cfg.manager_mode(), "resident")

    def test_time_zone(self):
        self.assertEqual(config.load(self.root).time_zone(), "Asia/Seoul")      # 파일이 없으면 기본
        (self.root / "fleet.toml").write_text('[time]\nzone = "UTC"\n', encoding="utf-8")
        self.assertEqual(config.load(self.root).time_zone(), "UTC")

    def test_timezone_apply_sets_tz_and_ignores_bad_names(self):
        import os  # noqa: PLC0415
        from unittest import mock  # noqa: PLC0415
        from fleet_rt import timezone  # noqa: PLC0415
        with mock.patch.dict(os.environ, {"TZ": "UTC"}):
            (self.root / "fleet.toml").write_text('[time]\nzone = "Asia/Seoul"\n', encoding="utf-8")
            self.assertEqual(timezone.apply(self.root), "Asia/Seoul")
            self.assertEqual(os.environ["TZ"], "Asia/Seoul")
            (self.root / "fleet.toml").write_text('[time]\nzone = "Not/AZone"\n', encoding="utf-8")
            self.assertIsNone(timezone.apply(self.root))
            self.assertEqual(os.environ["TZ"], "Asia/Seoul")    # 틀린 이름은 건드리지 않는다
        import time  # noqa: PLC0415
        time.tzset()

    def test_manager_mode(self):
        """`[manager] mode` - 기본은 상주(resident). 표가 없는 옛 설정도 상주. 모르는 값·표가 아닌 것은 거절 (설계 5.9)."""
        self.assertEqual(config.load(REPO).manager_mode(), "resident")         # 저장소의 설정은 상주 그대로
        def root_with(text):          # 변형마다 새 폴더 - 같은 파일을 고쳐 쓰면 mtime 캐시가 끼어든다
            d = pathlib.Path(tempfile.mkdtemp(dir=self.root))
            (d / "fleet.toml").write_text(text, encoding="utf-8")
            return d
        self.assertEqual(config.load(root_with('[providers.a]\nmodels = ["x"]\n')).manager_mode(), "resident")
        self.assertEqual(config.load(root_with('[manager]\nmode = "calls"\n')).manager_mode(), "calls")
        for bad in ('[manager]\nmode = "call"\n', 'manager = "calls"\n', '[manager]\nmode = 1\n'):
            with self.assertRaises(config.ConfigError, msg=bad):
                config.load(root_with(bad))

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
        self.assertEqual(keys, ["kisti/kistillm", "exaone/k-exaone_v2.5", "openrouter/deepseek/deepseek-v4.1-flash",
                                "opencode/deepseek-v4.1-flash-free"])
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
        self.assertEqual(providers.room(self.cfg, self.root), {"kisti": 0, "exaone": 1, "openrouter": 3, "opencode": 1, "anthropic": 2})



class _Srv:
    """127.0.0.1 위의 작은 HTTP 서버 - 받은 (경로, Authorization) 를 적는다. 바깥 네트워크에는 나가지 않는다."""

    def __init__(self, code=200, location=None):
        got = self.got = []

        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                got.append((self.path, self.headers.get("Authorization")))
                self.send_response(code)
                if location:
                    self.send_header("Location", location)
                self.send_header("Content-Length", "0")
                self.end_headers()

            def log_message(self, *a):
                pass

        self.srv = http.server.HTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.srv.server_address[1]}/v1"
        self.t = threading.Thread(target=self.srv.serve_forever, daemon=True)
        self.t.start()

    def close(self):
        self.srv.shutdown()
        self.srv.server_close()


def _cfg(base_url, probe="models"):
    p = {"base_url": base_url, "env_key": "KISTI_API_KEY", "models": ["kistillm"]}
    if probe:
        p["probe"] = probe
    return config.Config({"providers": {"kisti": p, "anthropic": {"models": ["opus"]}},
                          "harness": {"claude": {"providers": ["anthropic"]}}})


class ProbeTest(unittest.TestCase):
    """준비 점검은 키를 **보내지 않는다** (2026-11-12 검수 `probe_repro.py`): `base_url` 은 작업자도 고치는 `fleet.toml`
    에서 오므로, 키를 실어 보내면 그 주소 주인이 키를 받는다. 응답 = 아무 HTTP 응답(401·3xx 포함)."""

    def setUp(self):
        self.env = {"KISTI_API_KEY": SECRET}

    def serve(self, **kw):
        s = _Srv(**kw)
        self.addCleanup(s.close)
        return s

    def test_never_sends_the_key_even_to_a_planted_base_url(self):
        s = self.serve()
        ok, detail = providers.probe(_cfg(s.url), "kisti", self.env)
        self.assertTrue(ok, detail)
        self.assertEqual(s.got, [("/v1/models", None)])        # 요청은 갔지만 Authorization 은 없다
        self.assertNotIn(SECRET, detail)

    def test_any_http_answer_counts_including_401(self):
        for code in (401, 403, 404, 500):
            s = self.serve(code=code)
            ok, detail = providers.probe(_cfg(s.url), "kisti")
            self.assertTrue(ok, (code, detail))
            self.assertIn(str(code), detail)

    def test_redirect_is_not_followed(self):
        target = self.serve()
        s = self.serve(code=302, location=target.url + "/models")
        ok, detail = providers.probe(_cfg(s.url), "kisti", self.env)
        self.assertTrue(ok, detail)                              # 3xx 도 '응답함'
        self.assertIn("302", detail)
        self.assertEqual(target.got, [])                         # 넘겨준 곳에는 가지 않는다

    def test_connection_refused_and_timeout_fail(self):
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        sock.close()                                             # 아무도 듣지 않는 자리
        ok, detail = providers.probe(_cfg(f"http://127.0.0.1:{port}/v1"), "kisti", self.env, timeout=2)
        self.assertFalse(ok)
        self.assertIn("연결 실패", detail)
        mute = socket.socket()                                   # 연결은 받지만 답하지 않는 자리
        mute.bind(("127.0.0.1", 0))
        mute.listen(1)
        self.addCleanup(mute.close)
        ok, detail = providers.probe(_cfg(f"http://127.0.0.1:{mute.getsockname()[1]}/v1"), "kisti", self.env, timeout=0.5)
        self.assertFalse(ok)
        self.assertIn("시간 초과", detail)

    def test_not_an_http_url(self):
        ok, detail = providers.probe(_cfg("file:///etc/passwd"), "kisti")
        self.assertFalse(ok)
        self.assertIn("http", detail)

    def test_key_presence_is_a_separate_name_only_check(self):
        cfg = _cfg("http://127.0.0.1:9/v1")
        self.assertEqual(providers.key_present(cfg, "kisti", self.env), (True, "KISTI_API_KEY 있음"))
        ok, detail = providers.key_present(cfg, "kisti", {})
        self.assertFalse(ok)
        self.assertIn("KISTI_API_KEY", detail)
        self.assertEqual(providers.key_present(cfg, "anthropic", {}), (True, "키 없이 씀"))
        self.assertFalse(providers.key_present(cfg, "zzz", {})[0])

    def test_no_probe_configured(self):
        with mock.patch("urllib.request.OpenerDirector.open") as u:
            self.assertEqual(providers.probe(_cfg("http://127.0.0.1:9/v1", probe=None), "kisti", {}), (True, "점검 없음"))
            self.assertEqual(providers.probe(config.load(REPO), "anthropic", {}), (True, "점검 없음"))
        u.assert_not_called()

    def test_unknown_provider(self):
        self.assertFalse(providers.probe(config.load(REPO), "zzz", {})[0])


class SessionKeyName(unittest.TestCase):
    """세션은 `.env` 에서 자기 공급자의 키 **하나만** 받는다 (2026-11-12 검수 - 작업자가 `.env` 에 더한 줄이 관리자를 조종)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name)

    def toml(self, text):
        (self.root / "fleet.toml").write_text(text, encoding="utf-8")

    def test_rules(self):
        from fleet_rt import env as rt_env
        self.toml('[providers.kisti]\nenv_key = "KISTI_API_KEY"\n[providers.anthropic]\nmodels = ["opus"]\n'
                  '[providers.bad]\nenv_key = "BASH_ENV"\n[providers.bad2]\nenv_key = "LD_PRELOAD"\n'
                  '[providers.bad3]\nenv_key = "ANTHROPIC_BASE_URL"\n[providers.low]\nenv_key = "kisti_api_key"\n')
        self.assertEqual(rt_env.session_key_name(self.root, "kisti"), "KISTI_API_KEY")
        for p in ("anthropic", "bad", "bad2", "bad3", "low", "nope", None, ""):
            self.assertIsNone(rt_env.session_key_name(self.root, p), p)
        self.assertIsNone(rt_env.session_key_name(None, "kisti"))
        self.toml("[providers\n")                                    # 깨진 설정 - 아무것도 넘기지 않는다
        self.assertIsNone(rt_env.session_key_name(self.root, "kisti"))


if __name__ == "__main__":
    unittest.main()
