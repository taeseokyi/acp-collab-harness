#!/usr/bin/env python3
"""검사 실행기: 바뀐 경로에 해당하는 검사만, 또는 전부.

    python3 tools/check.py                # 작업 트리에서 바뀐 파일에 해당하는 검사
    python3 tools/check.py --staged       # 스테이징된 파일 기준
    python3 tools/check.py --all          # 전체 (푸시 전·라운드 마감)
    python3 tools/check.py tools/fleet_graph.py tests/test_fleet.py   # 경로를 직접

고치는 동안은 바뀐 곳과 닿는 검사만 돌리고, 전체는 푸시 전에 한 번 돌린다 (커밋 훅은 검사를 돌리지 않는다).
"""
import fnmatch
import pathlib
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
TESTS = ROOT / "tests"

#: 바뀐 경로(앞부분 일치) -> 돌릴 검사 파일 꼴. 여럿에 걸리면 가장 좁게 맞는 줄 하나. 어디에도 안 걸리는 tools/ 변경은 전체.
MAP = (
    ("tools/fleet_rt/harness/freebuff.py", ("test_rt_freebuff.py",)),
    ("tools/fleet_rt/harness/opencode.py", ("test_rt_opencode.py",)),
    ("tools/fleet_rt/harness/claude.py", ("test_rt_claude.py",)),
    ("tools/fleet_rt/harness/codex.py", ("test_rt_codex.py",)),
    ("tools/fleet_rt/sessions.py", ("test_rt_sessions.py",)),
    ("tools/fleet_rt/manager.py", ("test_rt_manager.py",)),
    ("tools/fleet_rt/config.py", ("test_rt_config.py", "test_rt_policy.py", "test_rt_autonomy.py")),
    ("tools/fleet_rt/sandbox.py", ("test_rt_sandbox.py",)),
    ("tools/fleet_rt/", ("test_rt_*.py", "test_fleet_graph.py", "test_fleet.py")),
    ("tools/fleet_graph.py", ("test_fleet_graph.py", "test_rt_integration.py", "test_rt_autonomy.py", "test_rt_sandbox.py")),
    ("tools/fleet.py", ("test_fleet*.py", "test_rt_integration.py")),
    ("tools/fleet_ctl.py", ("test_fleet_ctl.py", "test_rt_manager.py", "test_rt_policy.py", "test_rt_autonomy.py",
                            "test_fleet_project_round.py")),
    ("tools/aimem_monitor/", ("test_aimem_monitor*.py", "test_monitor_*.py", "test_archive_api.py")),
    ("tools/aimem_db.py", ("test_aimem_db_cli.py", "test_rt_db_sessions.py", "test_archive_api.py", "test_aimem_lint.py",
                           "test_aimem_monitor_state.py")),
    ("tools/aimem_lint.py", ("test_aimem_lint.py",)),
    ("tools/check.py", ()),          # 이 표를 고친 것은 검사할 대상이 없다
    ("fleet.toml", ("test_rt_config.py", "test_rt_policy.py", "test_rt_autonomy.py")),
)


def changed(staged):
    cmd = ["git", "diff", "--name-only", "--diff-filter=d"] + (["--cached"] if staged else ["HEAD"])
    out = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True).stdout.split("\n")
    return [p for p in out if p.strip()]


def pick(paths):
    """바뀐 경로들 -> (돌릴 검사 파일 이름 집합, 전체를 돌려야 하나)."""
    all_tests = sorted(p.name for p in TESTS.glob("test_*.py"))
    want, everything = set(), False
    for path in paths:
        if path.startswith("tests/"):
            name = pathlib.PurePosixPath(path).name
            if name.startswith("test_") and name in all_tests:
                want.add(name)
            elif name.startswith("_"):            # 검사 공통 도우미가 바뀌면 전부
                everything = True
            continue
        hits = sorted(((prefix, pats) for prefix, pats in MAP if path.startswith(prefix)), key=lambda h: -len(h[0]))[:1]
        hits = [pats for _prefix, pats in hits]          # 가장 좁게 맞는 줄 하나만
        if hits:
            for pats in hits:
                for pat in pats:
                    want.update(n for n in all_tests if fnmatch.fnmatch(n, pat))
        elif path.startswith("tools/"):
            everything = True
    return (set(all_tests), True) if everything else (want, False)


def run(names):
    sys.path.insert(0, str(TESTS))
    suite = unittest.TestSuite()
    for n in sorted(names):
        suite.addTests(unittest.TestLoader().discover(str(TESTS), pattern=n))
    return unittest.TextTestRunner(verbosity=1).run(suite).wasSuccessful()


def main(argv):
    args = [a for a in argv if not a.startswith("--")]
    if "--all" in argv:
        names, everything = set(p.name for p in TESTS.glob("test_*.py")), True
    else:
        names, everything = pick(args or changed("--staged" in argv))
    if not names:
        print("check: 해당하는 검사 없음")
        return 0
    print(f"check: {'전체' if everything else '바뀐 경로에 해당하는'} 검사 파일 {len(names)}개")
    return 0 if run(names) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
