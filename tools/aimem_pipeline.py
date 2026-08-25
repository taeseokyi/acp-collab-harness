#!/usr/bin/env python3
"""AIMEM.md 무인 파이프라인 드라이버. 표준 라이브러리만 사용.

`4.5 대기 큐` 가 빌 때까지 다음 사이클을 반복한다:
  1) tools/aimem_board.py queue-pop 으로 다음 태스크를 꺼낸다
  2) openclaw agent 블로킹 호출로 관리자 에이전트에게 배정+검증을 시킨다
  3) tools/aimem_lint.py 와 unittest 로 검증 게이트를 돈다
  4) 성공하면 board-set DONE + rev-bump, 실패하면 같은 태스크를 재시도(최대 2회).
     2회 실패하면 board-set BLOCKED 후 멈추고 사람이 읽을 요약을 stdout 에 낸다

이 스크립트는 tools/aimem_board.py 를 오직 서브프로세스 CLI 로만 호출한다
(내부 함수를 import 하지 않음 - 그 파일은 다른 슬롯 소유이므로 읽기 전용 의존만 진다).

종료코드: 0 = 정상 완료(큐 소진 또는 max-stages 도달), 1 = 태스크 BLOCKED 확정,
2 = 사람 개입 지점(0.6-3 대상)에 도달해 정지, 3 = 내부/설정 오류.
"""

import argparse
import datetime
import json
import re
import subprocess
import sys
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TOOLS_DIR.parent
BOARD_CLI = TOOLS_DIR / "aimem_board.py"
LINT_CLI = TOOLS_DIR / "aimem_lint.py"
LOG_PATH = REPO_ROOT / ".aimem" / "pipeline.log"

MAX_ATTEMPTS = 2  # 같은 태스크 최대 시도 횟수(0.6-3 / 태스크 지시 고정값)

NEXT_HEADING_RE = re.compile(r"^##(?!#)\s")

# 0.6-3 의 "사람에게 물어야 하는" 항목을 태스크 텍스트에서 미리 걸러내는 안전망.
# 완전한 의미 판단은 불가능하므로 키워드 매칭이다 - aimem_lint 의 "안전망 우선" 철학과 동일.
GATE_KEYWORDS = [
    ("git push", "git push"),
    ("git commit", "git commit / 커밋"),
    ("커밋", "git commit / 커밋"),
    ("install", "의존성 설치"),
    ("설치", "의존성/패키지 설치"),
    ("pip ", "의존성 설치"),
    ("npm ", "의존성 설치"),
    ("rm -rf", "파괴적 삭제"),
    ("삭제", "되돌리기 어려운 삭제 가능성"),
    ("permissionMode", "권한 설정 변경"),
    ("설정 변경", "설정 변경"),
    ("폴더 밖", "작업 폴더 밖 쓰기"),
    ("외부 네트워크", "외부 네트워크 접근"),
]

WORKER_GATE_RE = re.compile(r"/\s*(BLOCKED|NEEDS-LOCK|NEEDS-APPROVAL)\b")


def now_str():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log(stage, result, detail="", output=""):
    line = f"[{now_str()}] stage={stage} result={result}"
    if detail:
        line += f" detail={detail}"
    print(line)
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(line + "\n")
        if output:
            for out_line in output.splitlines():
                f.write(f"    {out_line}\n")


def run_and_log(cmd, stage, timeout, cwd=None):
    printable = " ".join(cmd)
    try:
        proc = subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout
        )
        rc, out, err = proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired as e:
        rc = 124
        out = e.stdout or ""
        err = f"TIMEOUT after {timeout}s: {printable}"
    combined_output = ""
    if rc != 0:
        combined_output = f"cmd: {printable}\n--- stdout ---\n{out}\n--- stderr ---\n{err}"
    log(stage, "OK" if rc == 0 else "FAIL", detail=printable if rc != 0 else "", output=combined_output)
    return rc, out, err


# ---- 읽기 전용 표 파서 (AIMEM.md 를 직접 읽는다 - 다른 슬롯 파일 import 안 함) ----

def split_row(line):
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    parts = re.split(r"(?<!\\)\|", s)
    return [p.strip().replace("\\|", "|") for p in parts]


def find_section(lines, heading_re):
    start = None
    for i, line in enumerate(lines):
        if heading_re.match(line):
            start = i
            break
    if start is None:
        return None
    end = len(lines)
    for i in range(start + 1, len(lines)):
        if NEXT_HEADING_RE.match(lines[i]):
            end = i
            break
    return start, end


def parse_table(lines, start, end):
    pipe_idxs = [i for i in range(start, end) if lines[i].strip().startswith("|")]
    if not pipe_idxs:
        return None
    block = [pipe_idxs[0]]
    for i in pipe_idxs[1:]:
        if i == block[-1] + 1:
            block.append(i)
        else:
            break
    if len(block) < 2:
        return None
    header = split_row(lines[block[0]])
    rows = [split_row(lines[i]) for i in block[2:]]
    return header, rows


def col_index(header, name):
    for i, h in enumerate(header):
        if name in h:
            return i
    return None


def peek_queue(text, limit):
    lines = text.splitlines()
    section = find_section(lines, re.compile(r"^##(?!#)\s*4\.5\s"))
    if section is None:
        return []
    table = parse_table(lines, *section)
    if table is None:
        return []
    header, rows = table
    tc, sc, hc, nc = (col_index(header, n) for n in ("태스크", "후보 슬롯", "이어받음", "비고"))
    out = []
    for cells in rows[:limit]:
        task_text = cells[tc] if tc is not None else ""
        m = re.match(r"^(T-\d+[A-Za-z]?)\b", task_text)
        out.append({
            "task_id": m.group(1) if m else None,
            "task_text": task_text,
            "candidate_slot": cells[sc] if sc is not None else "-",
            "handoff": cells[hc] if hc is not None else "-",
            "note": cells[nc] if nc is not None else "-",
        })
    return out


def peek_session_key(text, slot):
    lines = text.splitlines()
    section = find_section(lines, re.compile(r"^##(?!#)\s*2\.\s"))
    if section is None:
        return None
    table = parse_table(lines, *section)
    if table is None:
        return None
    header, rows = table
    slot_c, key_c = col_index(header, "슬롯"), col_index(header, "세션키")
    if slot_c is None or key_c is None:
        return None
    for cells in rows:
        if cells[slot_c].strip("` ") == slot:
            key = cells[key_c].strip("` ")
            return key if key and key != "-" else None
    return None


def check_gate(task):
    haystack = f"{task['task_text']} {task['note']}"
    for kw, reason in GATE_KEYWORDS:
        if kw in haystack:
            return f"태스크 텍스트에 '{kw}' 감지 - {reason} 은 0.6-3 대상. 관리자가 직접 판단해야 함"
    if not task["candidate_slot"] or task["candidate_slot"] == "-":
        return "후보 슬롯이 지정되지 않음 - 자동 배정 불가"
    return None


def board_cmd(args_, sub, extra, timeout, stage, dry_run=False):
    cmd = [sys.executable, str(BOARD_CLI), sub, *extra, "--file", args_.file]
    if dry_run:
        cmd.append("--dry-run")
    return run_and_log(cmd, stage, timeout)


def call_worker(args_, task, session_key):
    instruction = (
        f"AIMEM REV {args_.aimem_rev} 기준. 태스크 {task['task_id']} ({task['task_text']}) 를 "
        f"슬롯 {task['candidate_slot']}(세션키 {session_key})에 배정하고 완료까지 검증하십시오. "
        f"이어받음: {task['handoff']}. 비고: {task['note']}. "
        f"완료 후 board 상태/아웃박스 보고를 이 응답에 요약하십시오."
    )
    cmd = [
        "openclaw", "agent",
        "--agent", args_.agent,
        "--session-key", session_key or args_.manager_session_key,
        "-m", instruction,
        "--json",
        "--timeout", str(args_.assign_timeout),
    ]
    return run_and_log(cmd, f"ASSIGN:{task['task_id']}", args_.assign_timeout + 30)


def detect_worker_gate(stdout):
    text = stdout
    try:
        obj = json.loads(stdout)
        for key in ("reply", "message", "text", "result", "output"):
            if isinstance(obj, dict) and isinstance(obj.get(key), str):
                text = obj[key]
                break
    except (json.JSONDecodeError, TypeError):
        pass
    m = WORKER_GATE_RE.search(text)
    return m.group(1) if m else None


def run_validation_gates(args_):
    rc_lint, lint_out, lint_err = run_and_log(
        [sys.executable, str(LINT_CLI), args_.file], "VALIDATE:lint", args_.gate_timeout, cwd=str(REPO_ROOT)
    )
    rc_test, test_out, test_err = run_and_log(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests"],
        "VALIDATE:tests", args_.gate_timeout, cwd=str(REPO_ROOT),
    )
    ok = rc_lint == 0 and rc_test == 0
    detail = ""
    if not ok:
        detail = f"lint_rc={rc_lint} test_rc={rc_test}\nlint:\n{lint_out}{lint_err}\ntests:\n{test_out}{test_err}"
    return ok, detail


def print_dry_run_plan(args_, text):
    tasks = peek_queue(text, args_.max_stages)
    print(f"[dry-run] 파이프라인 계획 (최대 {args_.max_stages} 단계, 대상 파일: {args_.file})")
    if not tasks:
        print("대기 큐가 비어 있음 - 실행할 단계 없음")
        return 0
    stopped = False
    for i, task in enumerate(tasks, start=1):
        print(f"\n[단계 {i}] 태스크={task['task_id'] or '(ID 파싱 실패)'} {task['task_text']!r}")
        print(f"  후보 슬롯: {task['candidate_slot']}  이어받음: {task['handoff']}  비고: {task['note']}")
        if stopped:
            print("  (앞 단계에서 사람 개입 지점 도달 - 이 단계는 실행되지 않음)")
            continue
        gate = check_gate(task)
        if gate:
            print(f"  [게이트] 사람 개입 필요 - {gate}")
            print("  => 여기서 정지, 이후 단계는 실행되지 않음")
            stopped = True
            continue
        session_key = peek_session_key(text, task["candidate_slot"]) or "<세션키 미확인>"
        print(f"  게이트 점검: 통과 (해당 슬롯 세션키: {session_key})")
        print(f"  1) {sys.executable} {BOARD_CLI} queue-pop --file {args_.file}")
        print(
            f"  2) openclaw agent --agent {args_.agent} --session-key {session_key} "
            f"-m \"<배정 지시>\" --json --timeout {args_.assign_timeout}"
        )
        print(f"     (실패 시 worker 응답에서 BLOCKED/NEEDS-LOCK/NEEDS-APPROVAL 마커 검사 - 있으면 즉시 정지)")
        print(f"  3) {sys.executable} {LINT_CLI} {args_.file}")
        print(f"  4) {sys.executable} -m unittest discover -s tests")
        print(
            f"  5) 둘 다 통과 -> board-set {task['task_id']} DONE + rev-bump "
            f"/ 실패 -> 재시도(최대 {MAX_ATTEMPTS}회) 후 실패 시 board-set {task['task_id']} BLOCKED + 정지"
        )
    return 0


def run_pipeline(args_):
    for stage in range(1, args_.max_stages + 1):
        text = Path(args_.file).read_text(encoding="utf-8")
        queued = peek_queue(text, 1)
        if not queued:
            log("QUEUE", "EMPTY")
            print("대기 큐가 비었음 - 정상 종료")
            return 0
        task = queued[0]

        gate = check_gate(task)
        if gate:
            log("GATE", "STOP", detail=gate)
            print(f"\n[정지] 사람 개입 필요 (0.6-3 대상): {gate}")
            print(f"태스크: {task['task_text']} (큐에서 아직 제거하지 않음)")
            return 2

        rc, out, err = board_cmd(args_, "queue-pop", [], args_.gate_timeout, f"QUEUE_POP:{task['task_id']}")
        if rc != 0:
            print("queue-pop 실패 - 파이프라인 정지")
            return 3
        if task["task_id"] is None:
            log("QUEUE_POP", "FAIL", detail="태스크 ID 를 파싱할 수 없음")
            print("태스크 ID 파싱 실패 - 큐 항목이 이미 제거됨. 수동 확인 필요")
            return 3

        task_id = task["task_id"]
        session_key = peek_session_key(text, task["candidate_slot"])
        if session_key is None:
            log("GATE", "STOP", detail=f"슬롯 {task['candidate_slot']} 세션키 없음")
            print(f"\n[정지] 슬롯 {task['candidate_slot']} 의 세션키를 명부에서 찾을 수 없음")
            return 2

        blocked = False
        for attempt in range(1, MAX_ATTEMPTS + 1):
            rc, out, err = call_worker(args_, task, session_key)
            worker_gate = detect_worker_gate(out) if rc == 0 else None
            if worker_gate:
                log("GATE", "STOP", detail=f"작업자 STATUS={worker_gate}")
                print(f"\n[정지] 작업자가 {worker_gate} 를 보고함 - 사람 개입 필요 (0.6-3)")
                print(f"태스크: {task_id}. 아웃박스(.aimem/outbox/{task['candidate_slot']}.md) 확인 요망")
                return 2
            if rc != 0:
                log("ASSIGN", "FAIL", detail=f"attempt={attempt}")
                if attempt >= MAX_ATTEMPTS:
                    blocked = True
                    break
                continue

            ok, detail = run_validation_gates(args_)
            if ok:
                board_cmd(args_, "board-set", [task_id, "DONE"], args_.gate_timeout, f"BOARD_SET:{task_id}")
                board_cmd(args_, "rev-bump", [], args_.gate_timeout, "REV_BUMP")
                log("STAGE", "DONE", detail=task_id)
                break
            else:
                log("VALIDATE", "FAIL", detail=f"attempt={attempt}", output=detail)
                if attempt >= MAX_ATTEMPTS:
                    blocked = True
                    break
        else:
            blocked = True

        if blocked:
            board_cmd(args_, "board-set", [task_id, "BLOCKED"], args_.gate_timeout, f"BOARD_SET:{task_id}")
            log("STAGE", "BLOCKED", detail=task_id)
            print(f"\n[정지] 태스크 {task_id} 가 {MAX_ATTEMPTS}회 시도 후에도 실패해 BLOCKED 로 확정됨")
            print(".aimem/pipeline.log 에서 상세 stdout/stderr 를 확인하십시오")
            return 1

    print(f"max-stages({args_.max_stages}) 도달 - 정상 종료")
    return 0


def build_parser():
    p = argparse.ArgumentParser(prog="aimem_pipeline.py", description="AIMEM.md 무인 파이프라인 드라이버")
    p.add_argument("--file", default="AIMEM.md", help="대상 AIMEM.md 경로 (기본: AIMEM.md)")
    p.add_argument("--dry-run", action="store_true", help="실제 호출 없이 계획만 출력")
    p.add_argument("--max-stages", type=int, default=5, help="한 실행에서 처리할 최대 태스크 수 (기본 5)")
    p.add_argument("--agent", default="coding", help="openclaw agent --agent 값 (기본 coding)")
    p.add_argument("--manager-session-key", default=None, help="세션키를 명부에서 못 찾을 때 쓸 대체값")
    p.add_argument("--assign-timeout", type=int, default=1800, help="openclaw agent 호출 타임아웃(초)")
    p.add_argument("--gate-timeout", type=int, default=300, help="board/lint/tests 호출 타임아웃(초)")
    p.add_argument("--aimem-rev", default="?", help="지시 메시지에 적을 REV 번호(로그용)")
    return p


def main(argv=None):
    args = argparse.Namespace()
    args = build_parser().parse_args(argv, namespace=args)

    try:
        text = Path(args.file).read_text(encoding="utf-8")
    except OSError as e:
        print(f"오류: 파일을 읽을 수 없음: {e}", file=sys.stderr)
        return 3

    if args.dry_run:
        return print_dry_run_plan(args, text)

    if not args.manager_session_key:
        peek_needed = peek_queue(text, 1)
        if peek_needed and peek_session_key(text, peek_needed[0]["candidate_slot"]) is None:
            print("오류: --manager-session-key 가 필요함 (명부에 세션키가 없는 슬롯)", file=sys.stderr)
            return 3

    return run_pipeline(args)


if __name__ == "__main__":
    sys.exit(main())
