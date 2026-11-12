# -*- coding: utf-8 -*-
"""웹 모니터의 관리자 카드·상세·모델 목록·.env 읽기 - openclaw 없이 세션 폴더·`fleet.toml`·`.env` 로만 (설계 2·3.6·5.6).

임시 루트만 쓴다 - 진짜 `.aimem/` 는 건드리지 않는다. 진짜 하네스도 `openclaw` 도 뜨지 않는다.
"""
import _fleet_env  # noqa: F401  (맨 위: 어댑터 선택을 fake 로)

import contextlib
import datetime
import http.client
import http.server
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest import mock

import aimem_db
from aimem_monitor import RUN_ID_RE, RUN_DETAIL_KEYS, server
from fleet_rt import sessions

import re

OLD = "2026-11-12T11:00:00"
ENDED = "2026-11-12T11:30:00"


def ev(**kw):
    return json.dumps(kw, ensure_ascii=False)


def mk_session(root, sid, *, role="manager", running=False, end=None, started=OLD, rnd=21, label=None,
               events=(), report=None, harness="fake"):
    sroot = root / ".aimem" / "sessions"
    d = sroot / sid
    d.mkdir(parents=True)
    meta = {"id": sid, "role": role, "harness": harness, "model": "opus", "provider": "anthropic",
            "round": rnd, "label": label if label is not None else f"R{rnd} 관리자", "started": started,
            "extra": {}}
    if role == "worker":
        meta.update({"slot": "S2", "task_id": "T-1"})
    if running:
        pid = _fleet_env.marked_pid(sroot, sid)
        meta["supervisor_pid"] = pid
        meta["proc_start"] = sessions.proc_start(pid)
    else:
        meta["supervisor_pid"] = 2 ** 22 + 12345      # 없는 pid
    (d / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    (d / "brief.md").write_text("지시문", encoding="utf-8")
    if events:
        (d / "events.jsonl").write_text("\n".join(f"{at}\t{raw}" for at, raw in events) + "\n", encoding="utf-8")
    if report is not None:
        (d / "report.md").write_text(report, encoding="utf-8")
    if end is not None:
        (d / "end.json").write_text(json.dumps(end), encoding="utf-8")
    return d


def done(state="done", rc=0, ended=ENDED):
    return {"state": state, "rc": rc, "ended": ended, "fail_kind": None, "why": None}


class NoOpenclawMixin:
    """`subprocess` 로 `openclaw` 를 부르면 그 자리에서 검사를 떨어뜨린다."""

    def setUp(self):
        super().setUp()
        self.calls = []
        real_run, real_popen = subprocess.run, subprocess.Popen

        def guard(argv):
            first = argv[0] if isinstance(argv, (list, tuple)) and argv else argv
            if os.path.basename(str(first)) == "openclaw":
                self.fail(f"openclaw 를 불렀습니다: {argv}")
            self.calls.append(argv)

        def run(argv, *a, **k):
            guard(argv)
            return real_run(argv, *a, **k)

        class Popen(real_popen):
            def __init__(inner, argv, *a, **k):
                guard(argv)
                super().__init__(argv, *a, **k)

        for target, name, value in ((subprocess, "run", run), (subprocess, "Popen", Popen)):
            p = mock.patch.object(target, name, value)
            p.start()
            self.addCleanup(p.stop)


class Base(NoOpenclawMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.root = pathlib.Path(self._t.name).resolve()
        # 이벤트·토큰을 읽는 DB 도 임시 것으로 (진짜 DB 를 열지 않게)
        for target, attr, value in ((aimem_db, "ROOT", self.root), (aimem_db, "DB", self.root / ".aimem" / "aimem.db")):
            p = mock.patch.object(target, attr, value)
            p.start()
            self.addCleanup(p.stop)
        import io
        with contextlib.redirect_stdout(io.StringIO()):
            aimem_db.cmd_init()


class ManagerStatusTest(Base):
    def test_rows_and_status_mapping(self):
        mk_session(self.root, "M-R21-110000", running=True, started="2026-11-12T11:40:00", events=[
            ("2026-11-12T11:40:05", ev(type="text", text="상태를 읽습니다")),
            ("2026-11-12T11:41:00", ev(type="tool", name="Bash", summary="python3 tools/fleet.py runs")),
            ("2026-11-12T11:41:01", ev(type="usage", tokens_in=1, tokens_out=2))])
        mk_session(self.root, "M-R20-100000", started="2026-11-12T10:00:00", rnd=20, end=done(), report="DONE 보고")
        mk_session(self.root, "M-R19-090000", started="2026-11-12T09:00:00", rnd=19, end=done("failed", 1))
        mk_session(self.root, "M-R18-080000", started="2026-11-12T08:00:00", rnd=18, end=done("stalled", 125))
        mk_session(self.root, "M-R17-070000", started="2026-11-12T07:00:00", rnd=17, end=done("timeout", 124))
        mk_session(self.root, "M-R16-060000", started="2026-11-12T06:00:00", rnd=16, end=done("killed", None))
        mk_session(self.root, "M-R15-050000", started="2026-11-12T05:00:00", rnd=15)           # end.json 없이 감독 없음 = lost
        mk_session(self.root, "T-1-S2-a1-100000", role="worker")                                  # 작업자는 목록에 없다
        out = server.manager_status(self.root)
        self.assertEqual((out["ok"], out["error"]), (True, None))
        self.assertNotIn("pending", out)
        rows = out["sessions"]
        self.assertEqual(len(rows), server.MANAGER_MAX)                                         # 상한
        self.assertEqual([r["id"] for r in rows][:2], ["M-R21-110000", "M-R20-100000"])       # 최신이 앞
        keys = {"label", "status", "started", "updated", "id", "record_kb", "last_activity", "steps", "last_step",
                "round", "session_state", "orphaned"}
        self.assertTrue(all(keys <= set(r) for r in rows))
        cur = rows[0]
        self.assertEqual((cur["status"], cur["session_state"], cur["round"]), ("running", "running", 21))
        self.assertEqual(cur["steps"], 2)                                                         # text + tool
        self.assertEqual(cur["last_step"], "▸ Bash: python3 tools/fleet.py runs")                 # 한 줄 요약 (도구는 ▸)
        self.assertEqual(cur["last_activity"], "2026-11-12T11:41:01")
        self.assertEqual(cur["label"], "R21 관리자")
        by = {r["id"]: r for r in rows}
        self.assertEqual(by["M-R20-100000"]["status"], "done")
        self.assertEqual(by["M-R19-090000"]["status"], "failed")
        self.assertEqual((by["M-R18-080000"]["status"], by["M-R18-080000"]["session_state"]), ("failed", "stalled"))
        self.assertEqual((by["M-R17-070000"]["status"], by["M-R17-070000"]["session_state"]), ("failed", "timeout"))
        self.assertEqual(by["M-R16-060000"]["status"], "killed")
        self.assertNotIn("M-R15-050000", by)                                                      # 7 개 중 6 개만
        self.assertFalse(any(r["id"].startswith("T-") for r in rows))

    def test_lost_session_is_failed(self):
        mk_session(self.root, "M-R15-050000", rnd=15)
        row = server.manager_status(self.root)["sessions"][0]
        self.assertEqual((row["status"], row["session_state"]), ("failed", "lost"))

    def test_no_sessions_dir_and_no_cache(self):
        self.assertEqual(server.manager_status(self.root), {"ok": True, "sessions": [], "error": None})
        mk_session(self.root, "M-R1-000001", end=done())
        self.assertEqual(len(server.manager_status(self.root)["sessions"]), 1)                  # 바로 보인다 (캐시 없음)

    def test_non_manager_role_with_manager_like_id_is_hidden(self):
        mk_session(self.root, "M-R3-000003", role="worker", end=done())
        self.assertEqual(server.manager_status(self.root)["sessions"], [])

    def test_state_endpoint_carries_managers_without_pending(self):
        mk_session(self.root, "M-R2-000002", end=done())
        with mock.patch.object(server, "fleet_state", lambda *a, **k: {"mode": "running"}):
            st = server.collect_state(self.root)
        self.assertEqual([s["id"] for s in st["managers"]["sessions"]], ["M-R2-000002"])
        self.assertNotIn("pending", st["managers"])
        self.assertEqual(st["fleet"], {"mode": "running"})


class ManagerDetailTest(Base):
    def setUp(self):
        super().setUp()
        self.events = [("2026-11-12T11:00:01", ev(type="text", text="먼저 상태를 읽겠습니다."))]
        self.events.append(("2026-11-12T11:00:02", ev(type="tool", name="Bash", summary=f"cat {self.root}/AIMEM.md",
                                                       input={"description": "읽기"})))
        self.events.append(("2026-11-12T11:00:03", ev(type="usage", tokens_in=3)))
        self.events.append(("2026-11-12T11:00:04", ev(type="text", text="상태: DONE")))
        self.d = mk_session(self.root, "M-R21-110000", started=OLD, end=done(), events=self.events,
                            report="# 보고\nDONE")
        rd = self.root / "rounds" / "R21"
        rd.mkdir(parents=True)
        (rd / "round.json").write_text(json.dumps({"round": 21, "at": OLD, "brief": "manager-round-standard.md",
                                                   "requests": ["Q-1"], "projects": ["p1"]}), encoding="utf-8")
        con = aimem_db.connect()
        with con:
            con.execute("INSERT INTO events(at,actor,rev,kind,body) VALUES(?,?,?,?,?)",
                        ("2026-11-12T11:10:00", "관리자", 5, "handoff", "창 안"))
            con.execute("INSERT INTO events(at,actor,rev,kind,body) VALUES(?,?,?,?,?)",
                        ("2026-11-12T12:10:00", "관리자", 6, "handoff", "창 밖"))
        con.close()

    def test_steps_report_round_and_events_window(self):
        code, body = server.manager_detail("M-R21-110000", self.root)
        self.assertEqual(code, 200)
        self.assertNotIn("relay", body)
        self.assertEqual(body["steps_total"], 3)                                                  # usage 는 단계가 아니다
        self.assertEqual([s["kind"] for s in body["steps"]], ["text", "tool", "text"])
        self.assertEqual(body["steps"][1]["desc"], "읽기")
        self.assertIn("# 보고", body["report"])
        self.assertEqual(body["round"]["round"], 21)
        self.assertEqual(body["round"]["requests"], ["Q-1"])
        self.assertEqual(body["session"]["id"], "M-R21-110000")
        self.assertEqual([e["body"] for e in body["events"]], ["창 안"])                         # 끝난 시각까지만
        self.assertNotIn(str(self.root), json.dumps(body, ensure_ascii=False))                    # 경로 가림

    def test_all_returns_everything_and_default_caps(self):
        many = [(f"2026-11-12T11:01:{i % 60:02d}", ev(type="text", text=f"단계 {i}")) for i in range(60)]
        mk_session(self.root, "M-R22-120000", started=OLD, end=done(), events=many)
        code, body = server.manager_detail("M-R22-120000", self.root)
        self.assertEqual((body["steps_total"], len(body["steps"])), (60, server.MANAGER_STEPS_MAX))
        self.assertEqual(body["steps"][-1]["text"], "단계 59")
        code, body = server.manager_detail("M-R22-120000", self.root, all_steps=True)
        self.assertEqual(len(body["steps"]), 60)

    def test_id_validation_rejects_traversal_and_worker_ids(self):
        mk_session(self.root, "T-1-S2-a1-100000", role="worker")
        for bad in ("../etc/passwd", "M-R21-110000/../../x", "M-R21-11000", "m-r21-110000", "M-R21-110000\n",
                    "T-1-S2-a1-100000", "abcdef12", "", None, "M-R-110000", "M-R21-110000-"):
            code, _ = server.manager_detail(bad, self.root)
            self.assertEqual(code, 400, repr(bad))
        self.assertEqual(server.manager_detail("M-R99-999999", self.root)[0], 404)
        self.assertEqual(server._manager_row.__name__, "_manager_row")
        # 라우트 정규식: 하위 경로·점·작업자 id 를 받지 않는다
        for path in ("/api/managers/M-R21-110000/x", "/api/managers/../M-R21-110000", "/api/managers/T-1-S2-a1-100000",
                     "/api/managers/M-R21-110000%2F..", "/api/managers/abcdef12"):
            self.assertIsNone(server._REQ_MGR_RE.match(path), path)
        self.assertTrue(server._REQ_MGR_RE.match("/api/managers/M-R21-110000"))
        self.assertTrue(server._REQ_MGR_RE.match("/api/managers/M-R21-110000-2"))

    def test_symlinked_session_folder_is_refused(self):
        outside = self.root / "outside"
        outside.mkdir()
        (outside / "meta.json").write_text(json.dumps({"role": "manager", "started": OLD}), encoding="utf-8")
        link = self.root / ".aimem" / "sessions" / "M-R30-000030"
        link.symlink_to(outside, target_is_directory=True)
        self.assertEqual(server.manager_detail("M-R30-000030", self.root)[0], 404)
        self.assertEqual([r["id"] for r in server.manager_status(self.root)["sessions"]], ["M-R21-110000"])

    def test_step_line_prefers_description(self):
        self.assertEqual(server._step_line({"kind": "tool", "text": "ls -la", "desc": "목록"}), "▸ 목록")
        self.assertEqual(server._step_line({"kind": "text", "text": "a\n  b"}), "a b")


class HttpTest(Base):
    def setUp(self):
        super().setUp()
        mk_session(self.root, "M-R21-110000", end=done(), events=[("2026-11-12T11:00:01", ev(type="text", text="안녕"))])
        mk_session(self.root, "T-1-S2-a1-100000", role="worker", end=done(), events=[
            ("2026-11-12T11:00:01", ev(type="tool", name="Bash", summary="ls")),
            ("2026-11-12T11:00:02", ev(type="text", text="작업자 말"))])
        (self.root / "fleet.toml").write_text(
            '[providers.kisti]\nmodels = ["kistillm"]\n[providers.anthropic]\nmodels = ["opus"]\n'
            '[harness.claude]\nproviders = ["anthropic"]\n[harness.codex]\nproviders = ["kisti"]\n', encoding="utf-8")
        root = self.root

        class H(server.Handler):
            def log_message(self, *a):
                pass
        H.root = root
        try:
            self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        except PermissionError:
            self.skipTest("이 환경은 소켓을 못 연다")
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self._stop)

    def _stop(self):
        self.httpd.shutdown()
        self.httpd.server_close()

    def get(self, path):
        c = http.client.HTTPConnection("127.0.0.1", self.httpd.server_address[1], timeout=10)
        c.request("GET", path)
        r = c.getresponse()
        raw = r.read()
        c.close()
        return r.status, json.loads(raw.decode("utf-8"))

    def test_models_from_fleet_toml(self):
        code, body = self.get("/api/models")
        self.assertEqual(code, 200)
        self.assertTrue(body["ok"])
        self.assertEqual(sorted(m["key"] for m in body["models"]), ["kisti/kistillm", "opus"])
        self.assertIn("fleet.toml", body["source"])
        self.assertNotIn("openclaw", json.dumps(body))

    def test_manager_routes(self):
        code, body = self.get("/api/managers/M-R21-110000")
        self.assertEqual((code, body["session"]["id"]), (200, "M-R21-110000"))
        self.assertEqual(self.get("/api/managers/T-1-S2-a1-100000")[0], 404)                      # 정규식에 안 맞는 경로
        self.assertEqual(self.get("/api/managers/M-R99-999999")[0], 404)
        self.assertEqual(self.get("/api/managers/..%2F..%2Fetc")[0], 404)

    def test_run_detail_has_events_for_sessions(self):
        code, body = self.get("/api/runs/T-1-S2-a1-100000")
        self.assertEqual(code, 200)
        self.assertIn("[tool] Bash: ls", body["events"])
        self.assertIn("[text] 작업자 말", body["events"])
        code, body = self.get("/api/runs/M-R21-110000")                                          # 관리자 id 도 run id 로 받는다
        self.assertEqual(code, 200)
        self.assertIn("[text] 안녕", body["events"])
        self.assertEqual(set(body), set(RUN_DETAIL_KEYS))
        self.assertEqual(self.get("/api/runs/M-R21-1100")[0], 400)

    def test_run_id_regex_accepts_manager_ids(self):
        for ok in ("M-R21-193012", "M-R21-193012-2", "T-053-S3-a3-181328", "20261109-172618-S3"):
            self.assertTrue(re.match(RUN_ID_RE, ok), ok)
        for bad in ("M-R21-19301", "M-R-193012", "M-21-193012", "M-R21-193012\n", "M-R21-193012/x"):
            self.assertFalse(re.match(RUN_ID_RE, bad), bad)


class ReviewFixesTest(Base):
    """2026-11-12 적대적 검수: 관리자 경로의 링크 따라가기·비밀 가림."""

    def test_symlinked_session_files_are_refused_in_manager_routes(self):
        outside = self.root / "outside"
        outside.mkdir()
        (outside / "secret.txt").write_text("저장소 밖 비밀 내용", encoding="utf-8")
        (outside / "meta.json").write_text(json.dumps({"role": "manager", "round": 9, "started": OLD}), encoding="utf-8")
        (outside / "end.json").write_text(json.dumps(done()), encoding="utf-8")
        (outside / "events.jsonl").write_text(f"{OLD}\t{ev(type='text', text='저장소 밖 비밀 내용')}\n", encoding="utf-8")
        for i, (name, target) in enumerate((("report.md", "secret.txt"), ("events.jsonl", "events.jsonl"),
                                            ("meta.json", "meta.json"), ("end.json", "end.json"))):
            sid = f"M-R4{i}-00000{i}"
            d = mk_session(self.root, sid, end=done(), rnd=40 + i)
            for f in (name,):
                (d / f).unlink(missing_ok=True)
                (d / f).symlink_to(outside / target)
            code, body = server.manager_detail(sid, self.root)
            self.assertEqual(code, 404, name)
            self.assertNotIn("저장소 밖 비밀", json.dumps(body, ensure_ascii=False))
            self.assertNotIn(sid, [r["id"] for r in server.manager_status(self.root)["sessions"]], name)
        # 실행 상세(`/api/runs/<id>`)도 같은 판정 - 작업자 세션의 report.md 링크
        w = mk_session(self.root, "T-1-S2-a1-100000", role="worker", end=done())
        (w / "report.md").symlink_to(outside / "secret.txt")
        d = server.run_detail("T-1-S2-a1-100000", self.root)
        self.assertNotIn("저장소 밖 비밀", json.dumps(d, ensure_ascii=False))
        self.assertTrue(any("심볼릭" in e for e in d["errors"]))

    def test_manager_text_is_redacted_like_run_detail(self):
        key_line = "OPENROUTER_API_KEY=or-live-abcdefghijklmnop"
        mk_session(self.root, "M-R50-000050", end=done(), label=f"관리자 {key_line}", report=f"보고 {key_line}",
                   events=[(OLD, ev(type="text", text=f"찍어 봄 {key_line}")),
                           (OLD, ev(type="tool", name="Bash", summary="env", input={"description": f"보기 {key_line}"}))])
        code, body = server.manager_detail("M-R50-000050", self.root, all_steps=True)
        text = json.dumps(body, ensure_ascii=False)
        self.assertEqual(code, 200)
        self.assertNotIn("or-live-abcdefghijklmnop", text)
        self.assertIn("OPENROUTER_API_KEY=***", text)                # 이름은 남고 값만 가린다
        rows = server.manager_status(self.root)["sessions"]
        self.assertNotIn("or-live-abcdefghijklmnop", json.dumps(rows, ensure_ascii=False))   # 카드의 label·last_step

    def test_secret_pattern_matches_any_key_token_secret_name(self):
        from aimem_monitor import reader
        for name in ("OPENROUTER_API_KEY", "EXAONE_API_KEY", "AIMEM_ACCESS_TOKEN", "GITHUB_CLIENT_SECRET", "MY_SECRET_X"):
            self.assertEqual(reader._redact(f"{name}=value-123456"), f"{name}=***", name)
        self.assertEqual(reader._redact('"KISTI_API_KEY": "v-123456789"'), '"KISTI_API_KEY": ***')
        self.assertEqual(reader._redact("max tokens: 5 / token: 3"), "max tokens: 5 / token: 3")   # 소문자 낱말은 그대로

    def test_every_env_value_is_scrubbed_from_responses(self):
        env = self.root / ".env"
        env.write_text("EXAONE_API_KEY=exaone-live-value-123\nSHORT=abc\n", encoding="utf-8")
        os.chmod(env, 0o600)
        # 작업자 기록에 이름 없이 값만 찍혔다 (패턴 가림으로는 못 잡는 꼴) - 응답의 값 일치 가림이 잡는다
        mk_session(self.root, "M-R51-000051", end=done(), report="값만 찍힘: exaone-live-value-123 abc")

        class H(server.Handler):
            def log_message(self, *a):
                pass
        H.root = self.root
        try:
            httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        except PermissionError:
            self.skipTest("이 환경은 소켓을 못 연다")
        t = threading.Thread(target=httpd.serve_forever, daemon=True)
        t.start()
        self.addCleanup(lambda: (httpd.shutdown(), httpd.server_close()))
        c = http.client.HTTPConnection("127.0.0.1", httpd.server_address[1], timeout=10)
        c.request("GET", "/api/managers/M-R51-000051")
        raw = c.getresponse().read().decode("utf-8")
        c.close()
        self.assertNotIn("exaone-live-value-123", raw)
        self.assertIn("abc", raw)                                    # 8자 미만 값은 본문을 뭉개지 않게 가리지 않는다


class EnvTest(NoOpenclawMixin, unittest.TestCase):
    KEYS = ("KISTI_API_KEY", "GITHUB_CLIENT_ID", "GITHUB_CLIENT_SECRET", "AIMEM_MONITOR_PUBLIC_HOSTS")

    def setUp(self):
        super().setUp()
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.root = pathlib.Path(self._t.name)
        p = mock.patch.dict(os.environ, {})
        p.start()
        self.addCleanup(p.stop)
        for k in self.KEYS:
            os.environ.pop(k, None)

    def write(self, mode):
        f = self.root / ".env"
        f.write_text("KISTI_API_KEY=k-secret-1\nGITHUB_CLIENT_ID=gid\nOPENROUTER_API_KEY=or\n", encoding="utf-8")
        os.chmod(f, mode)

    def test_mode_600_is_read_and_only_monitor_keys_are_set(self):
        self.write(0o600)
        os.environ.pop("OPENROUTER_API_KEY", None)
        loaded = server.load_monitor_env(self.root)
        self.assertEqual(os.environ["KISTI_API_KEY"], "k-secret-1")
        self.assertEqual(os.environ["GITHUB_CLIENT_ID"], "gid")
        self.assertNotIn("OPENROUTER_API_KEY", os.environ)                                        # 모니터 키만
        self.assertEqual(sorted(k for k, _ in loaded), ["GITHUB_CLIENT_ID", "KISTI_API_KEY"])
        self.assertNotIn("k-secret-1", json.dumps(loaded))                                        # 값은 돌려주지 않는다

    def test_mode_644_is_ignored_with_a_warning(self):
        self.write(0o644)
        lines = []
        with mock.patch.object(server, "log_line", lambda m, *a, **k: lines.append(m)):
            self.assertEqual(server.load_monitor_env(self.root), [])
        self.assertNotIn("KISTI_API_KEY", os.environ)
        self.assertTrue(any("chmod 600" in m for m in lines))
        self.assertNotIn("k-secret-1", " ".join(lines))

    def test_shell_environment_wins(self):
        self.write(0o600)
        os.environ["KISTI_API_KEY"] = "from-shell"
        server.load_monitor_env(self.root)
        self.assertEqual(os.environ["KISTI_API_KEY"], "from-shell")

    def test_missing_file_is_silent(self):
        lines = []
        with mock.patch.object(server, "log_line", lambda m, *a, **k: lines.append(m)):
            self.assertEqual(server.load_monitor_env(self.root), [])
        self.assertEqual(lines, [])

    def test_old_sources_are_gone(self):
        self.assertFalse(hasattr(server, "OPENCLAW_ENV_FILE"))
        self.assertEqual(server.MONITOR_ENV_FILE, ".env")


class NoOpenclawTest(Base):
    def test_state_collect_never_runs_openclaw(self):
        mk_session(self.root, "M-R2-000002", end=done())
        with mock.patch.object(server, "fleet_state", lambda *a, **k: {"mode": "running"}):
            server.collect_state(self.root)
        server.manager_status(self.root)
        server.fleet_models(self.root)
        self.assertFalse([c for c in self.calls if "openclaw" in str(c)])


if __name__ == "__main__":
    unittest.main()
