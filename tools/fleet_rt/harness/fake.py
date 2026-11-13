"""가짜 하네스 - 검사용. 진짜 모델을 부르지 않고 지시문에 적힌 각본대로 사건을 낸다.

`AIFLEET_HARNESS=fake` 면 어댑터 선택이 무조건 이것이다(`harness/__init__.py`). 그래서 각본 꼴이
다른 검사들과 맞물린다 - 바꿀 때는 지시어를 **더하기만** 한다.

각본: 지시문(brief.md)에서 `FAKE:` 로 시작하는 줄만 위에서부터 차례로 실행한다. 나머지 줄은 무시.

    FAKE: emit <글>               {"type":"text","text":<글>}
    FAKE: tool <이름> <요약>       {"type":"tool","name":..,"summary":..}
    FAKE: usage <in> <out> [비용]  {"type":"usage","tokens_in":..,"tokens_out":..,"cost_usd":..}
    FAKE: env <이름>               {"type":"text","text":"<이름>=<값>"} (없으면 `<이름>=` ) - 환경 표식 확인용
    FAKE: write <상대경로> <글>    작업 폴더(cwd) 아래에 파일을 쓴다. 절대 경로·`..` 은 거절(rc 2)
    FAKE: sleep <초>               잠깐 쉰다
    FAKE: busy-read <초>          사건 없이 그만큼 데이터를 계속 읽는다 (긴 생성 중인 하네스 - 침묵으로 치면 안 된다)
    FAKE: hang                     사건 하나({"type":"text","text":"hang"}) 내고 영원히 잔다 (침묵 감지·끊기 검사)
    FAKE: ignore-term              SIGTERM 을 무시한다 (SIGKILL 길 검사)
    FAKE: child <초>               같은 프로세스 그룹에 `sleep <초>` 손자를 띄운다. 사건 {"type":"tool","name":"child","pid":..}
    FAKE: detach-child <초>        setsid 한 `sleep <초>` 손자 (고아 청소 검사). 사건 {"type":"tool","name":"detach-child","pid":..}
    FAKE: stderr <글>              stderr 로 한 줄
    FAKE: error <글>               {"type":"error","text":..,"retry":true,"timeout":true} (기반 장애 흉내, 끝내지 않음)
    FAKE: limit                    {"type":"error","text":"usage limit","limit":true} 내고 rc 1 로 끝
    FAKE: report <글…>             마지막 보고문을 정한다. `\\n` 은 줄바꿈
    FAKE: exit <rc>                각본을 여기서 끝내고 rc 로 나간다

끝에는(`exit`·각본 끝) {"type":"end","ok":rc==0,"result":<보고문>,"session_id":"fake-<세션 id>"} 를 낸다.
지시어가 하나도 없으면 보고문은 "DONE\\nfake 하네스" 이고 rc 0.
손자 프로세스의 stdio 는 /dev/null 이다 - 감독기의 stdout 파이프를 붙잡지 않게.
"""
import json
import os
import pathlib
import signal
import subprocess
import sys
import time

if __package__:
    from ..base import Command, Event, ProbeResult, ENV_SESSION, read_event_lines
else:   # `python3 fake.py <brief>` 로 각본을 돌릴 때 - 꾸러미 밖이라 상대 import 가 안 된다
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
    from fleet_rt.base import Command, Event, ProbeResult, ENV_SESSION, read_event_lines

_SELF = str(pathlib.Path(__file__).resolve())
DEFAULT_REPORT = "DONE\nfake 하네스"


class FakeHarness:
    name = "fake"

    def command(self, spec):
        # 진짜 어댑터와 달리 저장소 검사는 없다(검사는 임시 폴더에서 돈다). 없는 폴더만 거절 - Popen 에서 터지기 전에.
        if not os.path.isdir(str(spec.cwd)):
            raise ValueError(f"작업 폴더가 없습니다: {spec.cwd}")
        return Command(argv=[sys.executable, _SELF, str(spec.brief_path)], cwd=str(spec.cwd))

    def parse_event(self, line):
        line = (line or "").strip()
        if not line:
            return None
        try:
            d = json.loads(line)
        except ValueError:
            return Event("raw", raw=line)
        if not isinstance(d, dict):
            return Event("raw", raw=line)
        t = d.get("type")
        if t == "text":
            return Event("text", str(d.get("text", "")), raw=line)
        if t == "tool":
            name = str(d.get("name", ""))
            data = {k: v for k, v in d.items() if k != "type"}
            return Event("tool", f"{name}: {d.get('summary', '')}".rstrip(": "), data, line)
        if t == "usage":
            data = {k: d[k] for k in ("tokens_in", "tokens_out", "cost_usd") if d.get(k) is not None}
            return Event("usage", "", data, line)
        if t == "error":
            data = {"limit": bool(d.get("limit")), "retry": bool(d.get("retry")), "timeout": bool(d.get("timeout"))}
            return Event("error", str(d.get("text", "")), data, line)
        if t == "end":
            return Event("end", str(d.get("result") or ""), {
                "ok": bool(d.get("ok")), "result": d.get("result"),
                "harness_session_id": d.get("session_id")}, line)
        return Event("raw", raw=line)

    def _events(self, session_dir):
        for _at, raw in read_event_lines(session_dir):
            ev = self.parse_event(raw)
            if ev is not None:
                yield ev

    def final_report(self, session_dir):
        out = ""
        for ev in self._events(session_dir):
            if ev.kind == "end" and ev.data.get("result"):
                out = str(ev.data["result"])
        return out

    def limit_signal(self, session_dir):
        for ev in self._events(session_dir):
            if ev.kind == "error" and ev.data.get("limit"):
                return True
        return None

    def resume_command(self, spec, harness_session_id, message_path):
        return None

    def probe(self):
        return ProbeResult(ok=True, binary=_SELF, version="fake", detail="")


ADAPTER = FakeHarness()


# ---- 각본 실행기 (`python3 fake.py <brief>`) ----

def _out(obj):
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _script(brief_path):
    try:
        text = pathlib.Path(brief_path).read_text(encoding="utf-8")
    except OSError as e:
        print(f"fake: 지시문을 못 읽음: {e}", file=sys.stderr)
        return []
    steps = []
    for ln in text.splitlines():
        ln = ln.strip()
        if ln.startswith("FAKE:"):
            body = ln[len("FAKE:"):].strip()
            if body:
                word, _, rest = body.partition(" ")
                steps.append((word, rest.strip()))
    return steps


def _finish(rc, report):
    _out({"type": "end", "ok": rc == 0, "result": report,
          "session_id": "fake-" + os.environ.get(ENV_SESSION, "")})
    sys.exit(rc)


def _run(brief_path):
    steps = _script(brief_path)
    report = DEFAULT_REPORT
    quiet = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    for word, rest in steps:
        if word == "emit":
            _out({"type": "text", "text": rest})
        elif word == "tool":
            name, _, summary = rest.partition(" ")
            _out({"type": "tool", "name": name, "summary": summary})
        elif word == "usage":
            a = rest.split()
            ev = {"type": "usage", "tokens_in": int(a[0]), "tokens_out": int(a[1])}
            if len(a) > 2:
                ev["cost_usd"] = float(a[2])
            _out(ev)
        elif word == "env":
            _out({"type": "text", "text": f"{rest}={os.environ.get(rest, '')}"})
        elif word == "write":
            rel, _, body = rest.partition(" ")
            p = pathlib.PurePosixPath(rel)
            if not rel or p.is_absolute() or ".." in p.parts:
                print(f"fake: 쓰기 거절 {rel!r}", file=sys.stderr)
                sys.exit(2)
            dst = pathlib.Path.cwd() / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_text(body.replace("\\n", "\n"), encoding="utf-8")
        elif word == "sleep":
            time.sleep(float(rest))
        elif word == "busy-read":
            # 사건은 내지 않고 데이터만 계속 읽는다 - 긴 생성 중인 하네스(토큰이 소켓으로 들어오는 중)를 흉내 (침묵 오판 검사)
            end = time.time() + float(rest or "3")
            with open("/dev/urandom", "rb") as fh:
                while time.time() < end:
                    fh.read(65536)
                    time.sleep(0.05)
        elif word == "hang":
            _out({"type": "text", "text": "hang"})
            while True:
                time.sleep(3600)
        elif word == "ignore-term":
            signal.signal(signal.SIGTERM, signal.SIG_IGN)
        elif word in ("child", "detach-child"):
            p = subprocess.Popen(["sleep", rest or "60"], start_new_session=(word == "detach-child"), **quiet)
            _out({"type": "tool", "name": word, "summary": f"pid {p.pid}", "pid": p.pid})
        elif word == "stderr":
            print(rest, file=sys.stderr, flush=True)
        elif word == "error":
            _out({"type": "error", "text": rest, "retry": True, "timeout": True})
        elif word == "limit":
            _out({"type": "error", "text": "usage limit", "limit": True})
            _finish(1, report)
        elif word == "report":
            report = rest.replace("\\n", "\n")
        elif word == "exit":
            _finish(int(rest or 0), report)
        else:
            print(f"fake: 모르는 지시어 {word!r}", file=sys.stderr)
    _finish(0, report)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("쓰임: fake.py <brief.md>")
    _run(sys.argv[1])
