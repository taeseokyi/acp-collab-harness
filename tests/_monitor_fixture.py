# -*- coding: utf-8 -*-
"""브라우저 검사용 임시 저장소 자료 - 운영 `projects/` 와 `.aimem/` 을 읽지 않는다.

`write_wordle_project(root)` 는 진짜 웹워들 대신 **같은 약속(store.v1 보관함 · 격자 30칸 · 화면 키보드 · 도움말·설정 창)을
지키는 작은 앱**을 `projects/웹워들/` 에 쓴다. 미리보기·인증·격리 검사는 앱의 내용이 아니라 모니터가 그 앱을 여는 길을 잰다.
"""
import http.server
import json
import pathlib
import threading
from contextlib import contextmanager

INDEX_HTML = """<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="icon" href="data:,">
<title>웹워들 (검사용)</title>
<link rel="stylesheet" href="style.css">
</head>
<body>
<div id="board"></div>
<div id="keyboard"></div>
<button id="btn-settings" type="button">설정</button>
<div id="modal-help" class="modal"><p>도움말</p><button class="modal-close" type="button">닫기</button></div>
<div id="modal-settings" class="modal" hidden>
  <label><input type="checkbox" id="set-dark"> 어두운 테마</label>
  <button class="modal-close" type="button">닫기</button>
</div>
<script src="app.js"></script>
</body>
</html>
"""

STYLE_CSS = """body { margin: 0; font-family: sans-serif; }
#board { display: grid; grid-template-columns: repeat(5, 1fr); gap: 4px; padding: 8px; max-width: 320px; }
.row { display: contents; }
.tile { min-height: 40px; border: 2px solid #888; text-align: center; line-height: 40px; font-weight: bold; }
#keyboard { padding: 8px; }
.key { min-width: 28px; min-height: 40px; margin: 2px; }
.modal[hidden] { display: none; }
"""

APP_JS = """const post = (m) => parent.postMessage(Object.assign({ aimem: 'store.v1' }, m), '*');
const items = {};
const guesses = [];
const board = document.getElementById('board');
for (let r = 0; r < 6; r += 1) {
  const row = document.createElement('div');
  row.className = 'row';
  for (let c = 0; c < 5; c += 1) { const t = document.createElement('div'); t.className = 'tile'; row.appendChild(t); }
  board.appendChild(row);
}
const keyboard = document.getElementById('keyboard');
for (const ch of 'QWERTYUIOPASDFGHJKLZXCVBNM') {
  const b = document.createElement('button');
  b.type = 'button'; b.className = 'key'; b.textContent = ch;
  b.addEventListener('click', () => type(ch.toLowerCase()));
  keyboard.appendChild(b);
}
const rows = () => Array.from(board.querySelectorAll('.row'));
const typed = () => guesses.length;
function paint(row, word) {
  Array.from(rows()[row].children).forEach((t, i) => { t.textContent = word[i] ? word[i].toUpperCase() : ''; });
}
function type(ch) {
  const row = typed();
  const cur = Array.from(rows()[row].children).map((t) => t.textContent).join('');
  if (cur.length < 5) paint(row, cur.toLowerCase() + ch);
}
function submit() {
  const row = typed();
  const word = Array.from(rows()[row].children).map((t) => t.textContent).join('').toLowerCase();
  if (word.length < 5) return;
  Array.from(rows()[row].children).forEach((t) => { t.style.backgroundColor = '#6aaa64'; });
  guesses.push(word);
  const v = JSON.stringify(guesses);
  items['daily.fixture'] = v;
  post({ op: 'put', key: 'daily.fixture', value: v });
}
document.addEventListener('keydown', (e) => {
  if (e.key === 'Enter') submit();
  else if (/^[a-zA-Z]$/.test(e.key)) type(e.key.toLowerCase());
});
function restore() {
  if (items.seenHelp === 'true') document.getElementById('modal-help').hidden = true;
  try { document.getElementById('set-dark').checked = JSON.parse(items.settings).dark === true; } catch (err) { /* 없음 */ }
  try {
    JSON.parse(items['daily.fixture']).forEach((w, i) => {
      paint(i, w);
      Array.from(rows()[i].children).forEach((t) => { t.style.backgroundColor = '#6aaa64'; });
      guesses[i] = w;
    });
  } catch (err) { /* 없음 */ }
}
addEventListener('message', (e) => {
  const d = e.data;
  if (d && d.aimem === 'store.v1' && d.op === 'snapshot') { Object.assign(items, d.items); restore(); }
});
document.querySelector('#modal-help .modal-close').addEventListener('click', () => {
  document.getElementById('modal-help').hidden = true;
  post({ op: 'put', key: 'seenHelp', value: 'true' });
});
document.getElementById('btn-settings').addEventListener('click', () => { document.getElementById('modal-settings').hidden = false; });
document.querySelector('#modal-settings .modal-close').addEventListener('click', () => { document.getElementById('modal-settings').hidden = true; });
document.getElementById('set-dark').addEventListener('change', (e) => {
  post({ op: 'put', key: 'settings', value: JSON.stringify({ dark: e.target.checked }) });
});
post({ op: 'ready' });
"""


def write_wordle_project(root, name="웹워들"):
    """`projects/<name>/` 에 검사용 앱과 `PROGRESS.md`(체크 안 된 목표 하나 = 진행 중 프로젝트로 처음부터 보임)를 쓴다."""
    d = pathlib.Path(root) / "projects" / name
    (d / "web").mkdir(parents=True, exist_ok=True)
    (d / "app.json").write_text(json.dumps({"root": "web", "entry": "index.html", "title": name,
                                            "note": "검사용 - 정적 파일만"}, ensure_ascii=False), encoding="utf-8")
    (d / "web" / "index.html").write_text(INDEX_HTML, encoding="utf-8")
    (d / "web" / "style.css").write_text(STYLE_CSS, encoding="utf-8")
    (d / "web" / "app.js").write_text(APP_JS, encoding="utf-8")
    (d / "PROGRESS.md").write_text(f"# {name}\n\n## 목표\n- [x] 첫째\n- [ ] 둘째\n", encoding="utf-8")
    return d


@contextmanager
def serve(server, root, **handler_attrs):
    """인증 끈 평문 http 모니터를 임시 포트에 띄운다 (`serve_forever` 의 0.5초 폴링 대신 0.01초 - 끝낼 때 기다리지 않게)."""
    attrs = {"root": pathlib.Path(root), "require_auth": False, "tls": False, "access_token": None,
             "guard": server.LoginGuard(), "timeout": 5, "log_message": lambda *a, **k: None}
    attrs.update(handler_attrs)
    handler = type("H", (server.Handler,), attrs)
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    httpd.daemon_threads = True
    thread = threading.Thread(target=httpd.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()
    try:
        yield httpd, f"http://127.0.0.1:{httpd.server_address[1]}"
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=3)
