"""envcheck 통합 러너. 표준 라이브러리만 사용.

세 계층(`sessions` / `runtime` / `terminal`)을 한 번에 돌리고, **누적 판정**을 낸다.

왜 러너가 누적을 맡는가 (`AIMEM.md` REV 103 ⑦):
`check()` 가 돌려주는 3튜플은 **그 순간의 관측**이다. 거기에 표본 수를 끼우면
항목마다 반환의 의미가 달라져 계층 간 계약이 깨진다. 그래서 모듈은 관측만 하고,
시계열은 러너가 `.aimem/envcheck-state.json` 에 쌓는다. 합류점이 하나여야
슬롯 셋이 협의 없이 병렬로 일할 수 있다.

누적 규칙:

    OK 가 한 번이라도 나왔다        -> 기록이 확인된 항목이다
    CHANGED                          -> 즉시 수정 대상. 기록이 현실과 어긋났다
    UNKNOWN 만 N회 연속              -> 그것도 신호다. 현상이 사라졌을 수 있고,
                                        그렇다면 그 기록을 고칠 근거가 된다

`N` 은 러너 실행 빈도를 쥔 관리자가 정한다(`--unknown-streak`, 기본 3).
**UNKNOWN 을 침묵으로 두지 않는 것이 이 규칙의 요점이다** - 임계값이 없으면
UNKNOWN 은 장식이고, 검사기가 아무것도 못 보는 상태가 영원히 유지된다.

종료코드: 0 = 조치 불요 / 1 = `CHANGED` 있음 / 2 = `UNKNOWN` 연속 임계 도달
          3 = 러너 자체 오류(계층 import 실패 등)
"""

from __future__ import annotations

import argparse
import datetime
import importlib
import json
import sys
from pathlib import Path

from . import CHANGED, LAYERS, OK, STATUSES, UNKNOWN

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_STATE = REPO_ROOT / ".aimem" / "envcheck-state.json"

# 구조적으로 UNKNOWN 인 항목 (REV 106, 옥티 §6 지적 반영).
#
# `check()` 3튜플 계약은 건드리지 않는다 - 이 목록은 러너 쪽에서만 쓴다.
# 여기 있는 항목은 부작용 없이는 원리상 관측 불가능하다(확증하려면 실제
# 스폰을 하거나, 타임아웃이 실제로 만료돼야 한다). streak 임계를 넘겨도
# "신호"로 올리지 않고 "관측불가로 선언됨"으로만 표시한다 - 검사 고장이
# 아니라 검사의 설계 한계라서다.
#
# **이 목록에서 이름을 빼면 그 항목은 다시 일반 규칙(streak 임계 도달 시
# 신호)을 탄다.** 목록에 넣어 둔 채로 잊지 말 것 - 조건이 바뀌면(예: 부작용을
# 감수하는 별도 검증 경로가 생기면) 여기서 빼야 다시 울린다.
#
# `runtime.wsl_dns_first_lookup` 은 재현되면 OK 로 돌아오는 항목이라 여기
# 넣지 않는다 - 구조적 불가와 "아직 재현 안 됨"은 다르다.
STRUCTURAL_UNKNOWN = frozenset({
    "sessions.acp.can_create_sessions",
    "terminal.pan_run.recovery_reachability",
})

EXIT_OK = 0
EXIT_CHANGED = 1
EXIT_UNKNOWN_STREAK = 2
EXIT_RUNNER_ERROR = 3


def _now() -> str:
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def run_layer(layer: str) -> tuple[list[tuple[str, str, str]], str | None]:
    """한 계층을 돌린다. (결과, 오류) 를 돌려준다.

    한 계층이 죽어도 나머지는 돈다. 관측 도구가 자기 고장으로 전체를 막으면
    그 도구 자신이 장애 원인이 된다.
    """
    try:
        mod = importlib.import_module("envcheck.{}".format(layer))
    except Exception as exc:  # noqa: BLE001 - 어떤 import 실패든 계층 하나만 죽인다
        return [], "import 실패: {}: {}".format(type(exc).__name__, exc)

    check = getattr(mod, "check", None)
    if not callable(check):
        return [], "check() 가 없거나 호출 가능하지 않음"

    try:
        raw = check()
    except Exception as exc:  # noqa: BLE001
        return [], "check() 예외: {}: {}".format(type(exc).__name__, exc)

    results = []
    for item in raw or []:
        try:
            name, status, evidence = item
        except (TypeError, ValueError):
            return [], "계약 위반 - 3튜플이 아님: {!r}".format(item)
        if status not in STATUSES:
            return [], "계약 위반 - 알 수 없는 status {!r} ({})".format(status, name)
        results.append(("{}.{}".format(layer, name), status, str(evidence)))
    return results, None


def load_state(path: Path) -> dict:
    try:
        with path.open(encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        return {"items": {}}
    except (OSError, json.JSONDecodeError) as exc:
        print("[경고] 상태 파일을 읽지 못했습니다 ({}). 새로 시작합니다.".format(exc),
              file=sys.stderr)
        return {"items": {}}
    if not isinstance(data, dict) or not isinstance(data.get("items"), dict):
        print("[경고] 상태 파일 형식이 예상과 다릅니다. 새로 시작합니다.", file=sys.stderr)
        return {"items": {}}
    return data


def save_state(path: Path, state: dict) -> None:
    """원자적으로 쓴다. 중간에 죽어도 반쪽 JSON 을 남기지 않는다."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(state, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")
    tmp.replace(path)


def fold(state: dict, results: list[tuple[str, str, str]], stamp: str) -> None:
    """이번 관측을 상태에 접는다. 시계열 전체가 아니라 판정에 필요한 것만 남긴다."""
    items = state.setdefault("items", {})
    for name, status, evidence in results:
        rec = items.setdefault(name, {
            "runs": 0,
            "ever_ok": False,
            "unknown_streak": 0,
            "first_seen": stamp,
            "last_status": None,
            "last_seen": None,
            "last_evidence": "",
            "ever_ok_at": None,
        })
        rec["runs"] += 1
        rec["last_status"] = status
        rec["last_seen"] = stamp
        rec["last_evidence"] = evidence
        if status == OK:
            if not rec["ever_ok"]:
                rec["ever_ok_at"] = stamp
            rec["ever_ok"] = True
        if status == UNKNOWN:
            rec["unknown_streak"] += 1
        else:
            rec["unknown_streak"] = 0


def verdict(rec: dict, streak_limit: int, name: str = "") -> tuple[str, str]:
    """누적 판정. (판정, 사유) 를 돌려준다."""
    status = rec["last_status"]
    if status == CHANGED:
        return "수정필요", "기록과 다릅니다 - 해당 기록을 고치십시오"
    if status == OK:
        return "확인됨", "이번 실행에서 기록대로였습니다"
    # UNKNOWN
    streak = rec["unknown_streak"]
    if name in STRUCTURAL_UNKNOWN:
        return ("관측불가로 선언됨",
                "구조적 UNKNOWN(STRUCTURAL_UNKNOWN) 목록에 있음 - 부작용 없이는 "
                "원리상 관측 불가. streak {}회는 신호로 올리지 않는다. "
                "목록에서 빼면 다시 일반 규칙을 탑니다".format(streak))
    if streak >= streak_limit:
        if rec["ever_ok"]:
            reason = ("UNKNOWN {}회 연속 - 전에는 OK 였습니다({}). "
                      "현상이 사라졌을 수 있고, 그렇다면 기록을 고칠 근거입니다"
                      ).format(streak, rec["ever_ok_at"])
        else:
            reason = ("UNKNOWN {}회 연속 - 한 번도 OK 가 나온 적이 없습니다. "
                      "검사가 대상을 못 찾고 있으니 검사 쪽을 의심하십시오").format(streak)
        return "신호", reason
    return "미판정", "UNKNOWN {}회 (임계 {}회)".format(streak, streak_limit)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python3 -m envcheck",
        description="envcheck 통합 러너 - 저장소 밖의 기록이 아직 맞는지 검사한다",
    )
    p.add_argument("--layer", action="append", choices=LAYERS,
                   help="이 계층만 돈다 (여러 번 지정 가능. 기본: 전부)")
    p.add_argument("--state", default=str(DEFAULT_STATE),
                   help="누적 상태 파일 경로 (기본: .aimem/envcheck-state.json)")
    p.add_argument("--unknown-streak", type=int, default=3, metavar="N",
                   help="UNKNOWN 이 N회 연속이면 신호로 올린다 (기본: 3)")
    p.add_argument("--no-state", action="store_true",
                   help="상태를 읽지도 쓰지도 않는다 (일회성 관측)")
    p.add_argument("--json", action="store_true", help="결과를 JSON 으로 낸다")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.unknown_streak < 1:
        print("--unknown-streak 은 1 이상이어야 합니다", file=sys.stderr)
        return EXIT_RUNNER_ERROR

    layers = args.layer or list(LAYERS)
    stamp = _now()

    results: list[tuple[str, str, str]] = []
    errors: list[tuple[str, str]] = []
    for layer in layers:
        got, err = run_layer(layer)
        if err:
            errors.append((layer, err))
        results.extend(got)

    state = {"items": {}} if args.no_state else load_state(Path(args.state))
    fold(state, results, stamp)
    state["last_run"] = stamp

    rows = []
    for name, status, evidence in results:
        v, reason = verdict(state["items"][name], args.unknown_streak, name)
        rows.append({
            "name": name, "status": status, "verdict": v,
            "reason": reason, "evidence": evidence,
            "runs": state["items"][name]["runs"],
        })

    if args.json:
        print(json.dumps({"stamp": stamp, "rows": rows,
                          "errors": [{"layer": l, "error": e} for l, e in errors]},
                         ensure_ascii=False, indent=2))
    else:
        print("envcheck {}  (계층 {})".format(stamp, ", ".join(layers)))
        print("-" * 78)
        for r in rows:
            print("{:<38} {:<8} {}".format(r["name"], r["status"], r["verdict"]))
            print("    {}".format(r["evidence"]))
            if r["verdict"] in ("수정필요", "신호", "관측불가로 선언됨"):
                print("    -> {}".format(r["reason"]))
        if not rows:
            print("(결과 없음)")
        for layer, err in errors:
            print("[계층 오류] {}: {}".format(layer, err), file=sys.stderr)

    if not args.no_state:
        try:
            save_state(Path(args.state), state)
        except OSError as exc:
            print("[경고] 상태를 저장하지 못했습니다: {}".format(exc), file=sys.stderr)

    if errors:
        return EXIT_RUNNER_ERROR
    if any(r["status"] == CHANGED for r in rows):
        return EXIT_CHANGED
    if any(r["verdict"] == "신호" for r in rows):
        return EXIT_UNKNOWN_STREAK
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
