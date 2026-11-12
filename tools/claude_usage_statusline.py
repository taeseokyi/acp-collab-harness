#!/usr/bin/env python3
"""Claude Code 상태줄 명령 - 계정의 사용 한도(5시간·주간)를 `.aimem/claude-usage.json` 에 남긴다 (2026-11-12 태석님).

Claude Code 는 상태줄 명령의 stdin 으로 세션 JSON 을 주고, 구독 계정이면 거기에 `rate_limits`
(`five_hour`·`seven_day`·…) 가 들어 있다. 이 스크립트는 그것을 그대로 파일에 옮겨 적고 짧은 한 줄을 찍는다.
모니터는 그 파일을 읽어 함대 탭에 보인다. **자격 증명은 읽지 않는다** - Claude Code 가 이미 받아 둔 값만 옮긴다.
대화형 Claude Code 가 돌 때만 갱신되므로 화면은 '몇 분 전 기준' 을 함께 보인다.

등록(사람이 한 번): `~/.claude/settings.json` 에
    "statusLine": {"type": "command", "command": "python3 /home/tsyi/work/ai-fleet/tools/claude_usage_statusline.py"}
"""
import datetime as dt
import json
import os
import pathlib
import sys

OUT = pathlib.Path(__file__).resolve().parents[1] / ".aimem" / "claude-usage.json"


def _pct(row):
    if not isinstance(row, dict):
        return None
    for k in ("used_percentage", "utilization", "percent"):
        if isinstance(row.get(k), (int, float)):
            return float(row[k])
    return None


def main():
    try:
        data = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        data = {}
    rl = data.get("rate_limits") if isinstance(data, dict) else None
    if isinstance(rl, dict) and rl:
        rec = {"at": dt.datetime.now().isoformat(timespec="seconds"), "rate_limits": rl}
        try:
            OUT.parent.mkdir(parents=True, exist_ok=True)
            tmp = OUT.with_name(f"{OUT.name}.{os.getpid()}.tmp")
            tmp.write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, OUT)
        except OSError:
            pass
    parts = []
    model = ((data.get("model") or {}).get("display_name") if isinstance(data, dict) else None) or ""
    if model:
        parts.append(model)
    if isinstance(rl, dict):
        for key, label in (("five_hour", "5시간"), ("seven_day", "주간")):
            p = _pct(rl.get(key))
            if p is not None:
                parts.append(f"{label} {p:.0f}%")
    print(" · ".join(parts))
    return 0


if __name__ == "__main__":
    sys.exit(main())
