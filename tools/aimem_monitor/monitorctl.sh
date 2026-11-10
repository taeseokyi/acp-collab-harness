#!/usr/bin/env bash
# AIMEM 함대 모니터 서버 띄우기/내리기 (2026-11-10, 접근 제어 보강).
#
#   tools/aimem_monitor/monitorctl.sh start [https|local]   # 기본 https
#   tools/aimem_monitor/monitorctl.sh stop | restart [https|local] | status
#
#   https : --tls --host 0.0.0.0 --port 18799  - HTTPS + 인증(토큰/GitHub). 외부 공개·평소 사용
#   local : --host 127.0.0.1 --port 18799      - http, 인증 없음. 개발 확인용 (공개 경로에 두지 말 것)
#
# 비밀값은 셸이 아니라 파일에서 읽습니다 - .aimem/tls/monitor.env (0600), KISTI 키는 ~/.openclaw/.env 도.
# pid 는 .aimem/monitor.pid, 로그는 .aimem/monitor.log. 끌 때는 **pid 로만** 죽입니다 (pkill -f 금지, AIMEM 8.0-5).
set -euo pipefail
# 출력이 `| head -1` 같은 파이프로 가다가 닫혀도 **동작은 끝까지** 합니다 (REV 147). 예전엔 stop 의 첫 줄 뒤에
# 파이프가 닫히면 SIGPIPE 로 스크립트가 죽어 restart 가 내리기만 하고 올리지 못했습니다.
trap '' PIPE
say() { echo "$@" 2>/dev/null || true; }
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PIDF="$ROOT/.aimem/monitor.pid"
LOG="$ROOT/.aimem/monitor.log"
MODEF="$ROOT/.aimem/monitor.mode"
PORT="${AIMEM_MONITOR_PORT:-18799}"

is_ours() {   # pid 가 살아 있고 정말 aimem_monitor 인가
  local pid="$1"
  # 검사와 읽기 사이에 프로세스가 사라질 수 있다 - 그때의 `tr: 읽기 오류` 는 소음이라 버린다
  [[ -n "$pid" && -r "/proc/$pid/cmdline" ]] && { tr '\0' ' ' < "/proc/$pid/cmdline" | grep -q -- "-m aimem_monitor"; } 2>/dev/null
}

cur_pid() { [[ -f "$PIDF" ]] && cat "$PIDF" || true; }

do_status() {
  local pid; pid="$(cur_pid)"
  if is_ours "$pid"; then
    say "실행 중 pid $pid ($(cat "$MODEF" 2>/dev/null || echo '?'))  $(tr '\0' ' ' < /proc/$pid/cmdline)"
  else
    say "꺼져 있음"; return 1
  fi
}

do_stop() {
  local pid; pid="$(cur_pid)"
  if is_ours "$pid"; then
    kill "$pid"
    for _ in $(seq 1 30); do is_ours "$pid" || break; sleep 0.2; done
    is_ours "$pid" && kill -9 "$pid" || true
    say "내렸습니다 (pid $pid)"
  else
    say "pid 파일의 프로세스가 없습니다"
  fi
  rm -f "$PIDF"
}

do_start() {
  local mode="${1:-https}" args
  if is_ours "$(cur_pid)"; then say "이미 실행 중입니다 - restart 를 쓰십시오"; do_status; return 1; fi
  case "$mode" in
    https) args=(--tls --host 0.0.0.0 --port "$PORT") ;;
    local) args=(--host 127.0.0.1 --port "$PORT") ;;
    *) echo "모드는 https 또는 local" >&2; return 2 ;;
  esac
  cd "$ROOT"
  PYTHONPATH=tools setsid nohup python3 -m aimem_monitor "${args[@]}" >>"$LOG" 2>&1 < /dev/null &
  echo $! > "$PIDF"; echo "$mode" > "$MODEF"
  chmod 600 "$LOG" 2>/dev/null || true
  sleep 1.5
  if is_ours "$(cur_pid)"; then
    local scheme=http; [[ "$mode" == https ]] && scheme=https
    say "띄웠습니다: $scheme://127.0.0.1:$PORT/  (pid $(cur_pid), 로그 $LOG)"
    [[ "$mode" == https ]] && say "  로그인 토큰: PYTHONPATH=tools python3 -m aimem_monitor admin token show"
  else
    say "시작 실패 - 로그 끝:" >&2; tail -20 "$LOG" >&2; return 1
  fi
}

case "${1:-status}" in
  start) do_start "${2:-https}" ;;
  stop) do_stop ;;
  restart) do_stop; do_start "${2:-$(cat "$MODEF" 2>/dev/null || echo https)}" ;;
  status) do_status ;;
  *) echo "사용법: $0 start [https|local] | stop | restart [https|local] | status" >&2; exit 2 ;;
esac
