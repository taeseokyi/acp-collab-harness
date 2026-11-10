const DEMO = location.search.includes('demo');

const WEIGHTS = {
  TODO: 0,
  ASSIGNED: 0.1,
  'IN-PROGRESS': 0.5,
  REVIEW: 0.8,
  DONE: 1,
  BLOCKED: 0,
};

const STATUS_CLASS = {
  TODO: 'todo',
  ASSIGNED: 'assigned',
  'IN-PROGRESS': 'inprogress',
  REVIEW: 'review',
  DONE: 'done',
  BLOCKED: 'blocked',
  NEW: 'new',
  PLANNED: 'planned',
  REJECTED: 'rejected',
  running: 'running',
  done: 'done',
  lost: 'lost',
  unknown: 'unknown',
};

const DEMO_STATE = {
  generated: '2026-11-09T17:05:00',
  aimem: {
    rev: 109,
    lines: 523,
    updated: '2026-11-09 16:40 KST',
    goal: { text: '함대 모니터링 웹 UI 를 만든다', status: '진행 중' },
  },
  slots: [
    { slot: 'S1', harness: 'claude', role: '린터 / 보드 CLI', note: 'CLI 작업자', model: 'opus[1m]', model_source: 'openclaw.json agents.entries.claude.model' },
    { slot: 'S2', harness: 'codex', role: '계약 테스트', note: '테스트 작성자', model: 'gpt-5-codex', model_source: 'openclaw.json agents.entries.codex.model' },
    { slot: 'S3', harness: 'opencode', role: '커밋 훅 / 검수', note: 'CLI 작업자', model: 'kistillm', model_source: 'openclaw.json agents.entries.opencode.model' },
    { slot: '관리자', harness: 'claude', role: '합류점 / 서버', note: 'server.py 소유', model: 'opus[1m]', model_source: 'openclaw.json agents.entries.claude.model' },
  ],
  board: [
    { id: 'T-036', task: '데이터 계층', slot: 'S1', status: 'REVIEW', handoff: '-', artifact: '`reader.py`' },
    { id: 'T-037', task: '계약 테스트', slot: 'S2', status: 'DONE', handoff: 'T-036', artifact: '`tests/test_aimem_monitor.py`' },
    { id: 'T-038', task: '웹 UI 정적 프런트엔드', slot: 'S3', status: 'IN-PROGRESS', handoff: 'T-039', artifact: '`tools/aimem_monitor/static/**`' },
    { id: 'T-039', task: '웹 UI 서버', slot: '관리자', status: 'DONE', handoff: 'T-038', artifact: '`server.py`' },
    { id: 'T-040', task: '통합·교차검수', slot: 'S3', status: 'TODO', handoff: 'T-036~039', artifact: '-' },
    { id: 'T-041', task: '요청 분담 CLI', slot: '미배정', status: 'ASSIGNED', handoff: 'T-039', artifact: '-' },
    { id: 'T-042', task: '모델 표기 점검', slot: '미배정', status: 'BLOCKED', handoff: '-', artifact: '-' },
  ],
  queue: [
    { order: '1', task: '통합·교차검수', slots: 'S3', handoff: 'T-036~039', note: '라운드 4. 자기채점 금지' },
    { order: '2', task: '요청 -> 서브태스크 분담 CLI', slots: '관리자', handoff: 'T-039', note: '지금은 손으로 고쳐야 함' },
    { order: '3', task: '모델 표기 정리', slots: '-', handoff: '-', note: '대기' },
  ],
  log: [
    { when: '2026-11-09 16:40', text: 'REV 109. 웹 UI 라운드 3 시작.' },
    { when: '2026-11-09 16:31', text: 'S1 스모크 실행 기록.' },
  ],
  runs: [
    { id: '20261109-170500-S3', slot: 'S3', harness: 'opencode', model: 'kistillm', label: 'T-038 프런트엔드 작성', rev: 109, write: ['tools/aimem_monitor/static/index.html', 'app.js', 'style.css'], started: '2026-11-09T17:05:00', state: 'running', rc: null, elapsed_sec: 31, report_head: '작업 중 - 정적 3파일 작성, 데모 경로 포함' },
    { id: '20261109-164500-S2', slot: 'S2', harness: 'codex', model: 'gpt-5-codex', label: '계약 테스트 작성', rev: 109, write: ['tests/test_aimem_monitor.py'], started: '2026-11-09T16:45:00', state: 'done', rc: 0, elapsed_sec: 68, report_head: 'DONE - 계약 테스트 4건 통과' },
    { id: '20261109-163112-S1', slot: 'S1', harness: 'claude', model: 'opus[1m]', label: '스모크 S1', rev: 109, write: [], started: '2026-11-09T16:31:12', state: 'done', rc: 0, elapsed_sec: 11, report_head: 'DONE - lint 0 errors' },
    { id: '20261109-160000-S1', slot: 'S1', harness: 'claude', model: 'opus[1m]', label: '리더 스캔', rev: 108, write: [], started: '2026-11-09T16:00:00', state: 'lost', rc: 2, elapsed_sec: 34, report_head: 'LOST - stderr: AIMEM.md parse error' },
  ],
  eta: {
    by_harness: {
      claude: { median_sec: 11, samples: 2, source: ['20261109-163112-S1', '20261109-160000-S1'] },
      codex: { median_sec: 68, samples: 1, source: ['20261109-164500-S2'] },
      opencode: { median_sec: 31, samples: 1, source: ['20261109-170500-S3'] },
    },
    overall: { median_sec: 55, samples: 4 },
  },
  kisti: {
    ok: true,
    fetched: '2026-11-09T17:20:31',
    age_sec: 3,
    error: null,
    busy: false,
    queued: 0,
    phase: 'reading the prompt',
    prompt_tokens: 197084,
    generated: 0,
    max_tokens: 8192,
    reasoning_recoveries: 0,
    thinking_budget: 6144,
  },
  graphs: [
    {
      id: 'R-002',
      request: '라운드2: 밝은 모드 UI + KISTI 상태 카드 + ETA 초과 + 린터 + 교차검수',
      created: '2026-11-09T17:23:23',
      updated: '2026-11-09T17:26:18',
      percent: 42.0,
      eta_seconds: 610,
      eta_at: '2026-11-09T17:55',
      counts: { done: 2, running: 1, todo: 2 },
      source: 'fleet_graph.progress',
      nodes: [
        { id: 'N1', title: 'ETA 초과 처리 (reader.py)', slot: 'S1', harness: 'claude', status: 'done', deps: [], attempts: 1, max_attempts: 2, last_run: '20261109-172329-S1' },
        { id: 'N2', title: '린터 보드 담당 허용 (aimem_lint.py)', slot: 'S1', harness: 'claude', status: 'done', deps: ['N1'], attempts: 1, max_attempts: 2, last_run: '20261109-172446-S1' },
        { id: 'N3', title: '웹 UI 밝은 모드 + 가독성·정렬 + KISTI 카드 + 그래프 트리', slot: 'S3', harness: 'opencode', status: 'running', deps: [], attempts: 2, max_attempts: 2, last_run: '20261109-172618-S3' },
      ],
    },
  ],
  requests: [
    {
      id: '20261109-170500-3f2a',
      created: '2026-11-09T17:05:00',
      requester: '태석',
      title: '함대 모니터 웹 UI 요청',
      detail: '함대 현황, 실행 상태, 보드/큐, 요청 폼, 분담 트리를 한 화면에서 본다.',
      status: 'IN-PROGRESS',
      subtasks: [
        { id: 'T-036', title: '데이터 계층', slot: 'S1', harness: 'claude', status: 'DONE', run_id: '20261109-163112-S1' },
        { id: 'T-037', title: '계약 테스트', slot: 'S2', harness: 'codex', status: 'REVIEW', run_id: '20261109-164500-S2' },
        { id: 'T-038', title: '웹 UI 프런트엔드', slot: 'S3', harness: 'opencode', status: 'IN-PROGRESS', run_id: '20261109-170500-S3' },
        { id: 'T-041', title: '요청 분담 CLI', slot: 'S1', harness: 'claude', status: 'BLOCKED', run_id: '20261109-160000-S1' },
      ],
      progress_pct: 42.5,
      eta_sec: 180,
      eta_at: '2026-11-09T17:08:00',
      eta_basis: 'claude 중앙값 11s(표본 2) 중 최댓값, 병렬 가정',
    },
    {
      id: '20261109-165000-9b1e',
      created: '2026-11-09T16:50:00',
      requester: '태석',
      title: '모델 표기 점검 요청',
      detail: '슬롯 명부의 model_source 가 실제 하네스 설정과 일치하는지 본다.',
      status: 'PLANNED',
      subtasks: [],
      progress_pct: null,
      eta_sec: null,
      eta_at: null,
      eta_basis: '분담 전 - 관리자가 서브태스크를 만들면 ETA 가 계산된다',
    },
  ],
  errors: [],
};

const state = {
  data: null,
  fetchedAt: 0,
  error: null,
  busy: false,
  autoRefresh: true,
  timer: null,
  expanded: new Set(),
  known: new Set(),
  detailOpen: false,
  detailBound: false,
  detailSeq: 0,
  detailReturnFocus: null,
  runsShowAll: false,
  logShowAll: false,
  boardFilter: 'open',
  graphOpen: new Set(),
  graphKnown: new Set(),
  editing: null,
  fleetBusy: null,
  fleetMsg: null,
};

function $(id) {
  return document.getElementById(id);
}

function show(value, fallback = '-') {
  if (value === null || value === undefined) return fallback;
  if (typeof value === 'string' && value.trim() === '') return fallback;
  return String(value);
}

function fmtDateTime(value) {
  if (!value) return '-';
  return String(value).replace('T', ' ').slice(0, 16);
}

function fmtElapsed(sec) {
  if (sec === null || sec === undefined || sec === '') return '-';
  const n = Number(sec);
  if (!Number.isFinite(n)) return '-';
  const s = Math.max(0, Math.round(n));
  if (s < 60) return `${s}초`;
  const m = Math.floor(s / 60);
  const r = s % 60;
  if (m < 60) return r ? `${m}분 ${r}초` : `${m}분`;
  const h = Math.floor(m / 60);
  const mm = m % 60;
  return mm ? `${h}시간 ${mm}분` : `${h}시간`;
}

function fmtPct(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return '-';
  return (Number.isInteger(n) ? String(n) : n.toFixed(1)) + '%';
}

function mono(value) {
  const span = document.createElement('span');
  span.className = 'mono';
  span.textContent = show(value);
  return span;
}

function badge(text, cls) {
  const span = document.createElement('span');
  span.className = 'badge ' + (cls ? 'badge-' + cls : 'badge-neutral');
  span.textContent = show(text);
  return span;
}

function statusBadge(value) {
  const raw = show(value);
  const key = raw.toLowerCase();
  const cls = key === 'lost' ? 'neutral' : (STATUS_CLASS[raw] || STATUS_CLASS[raw.toUpperCase()] || 'neutral');
  const span = badge(raw, cls);
  if (key === 'lost') span.title = '작업자가 보고/종료코드 없이 사라짐';
  return span;
}

function emptyP(text) {
  const p = document.createElement('p');
  p.className = 'empty';
  p.textContent = text;
  return p;
}

function newTable(headers, rows, rowClasses, opts = {}) {
  const table = document.createElement('table');
  if (opts.className) table.className = opts.className;

  const numeric = new Set(opts.num || []);
  const centered = new Set(opts.center || []);
  const ellipsis = new Set(opts.ellipsis || []);

  if (opts.widths) {
    const colgroup = document.createElement('colgroup');
    for (const w of opts.widths) {
      const col = document.createElement('col');
      if (w) col.style.width = w;
      colgroup.appendChild(col);
    }
    table.appendChild(colgroup);
  }

  const thead = document.createElement('thead');
  const tr = document.createElement('tr');
  headers.forEach((h, index) => {
    const th = document.createElement('th');
    th.textContent = h;
    if (numeric.has(index)) th.classList.add('col-num');
    else if (centered.has(index)) th.classList.add('col-center');
    else th.classList.add('col-text');
    tr.appendChild(th);
  });
  thead.appendChild(tr);
  table.appendChild(thead);

  const tbody = document.createElement('tbody');
  rows.forEach((row, rowIndex) => {
    const trb = document.createElement('tr');
    if (rowClasses && rowClasses[rowIndex]) trb.className = rowClasses[rowIndex];
    row.forEach((raw, index) => {
      const td = document.createElement('td');
      if (numeric.has(index)) td.classList.add('col-num');
      else if (centered.has(index)) td.classList.add('col-center');
      else td.classList.add('col-text');
      if (ellipsis.has(index)) {
        td.classList.add('elide');
        td.title = raw instanceof Node ? raw.textContent : show(raw, '');
      }
      if (raw instanceof Node) td.appendChild(raw);
      else td.textContent = show(raw);
      trb.appendChild(td);
    });
    tbody.appendChild(trb);
    const runId = opts.rowRunIds && opts.rowRunIds[rowIndex];
    const opener = opts.rowOpen && opts.rowOpen[rowIndex];   // {fn, title} - 실행 상세가 아닌 다른 상세
    if (opener) makeRowOpenable(trb, null, opener);
    else if (runId) makeRowOpenable(trb, runId);
  });
  table.appendChild(tbody);
  return table;
}

function makeRowOpenable(tr, runId, opener) {
  const open = opener ? opener.fn : () => openDetail(runId);
  tr.classList.add('clickable-row');
  tr.tabIndex = 0;
  tr.title = opener ? (opener.title || '상세 보기') : '실행 상세 보기: ' + runId;
  tr.addEventListener('click', open);
  tr.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      open();
    }
  });
}

function markUnopenableRows(table, rowRunIds) {
  const rows = table.tBodies[0] ? Array.from(table.tBodies[0].rows) : [];
  for (let i = 0; i < rows.length; i += 1) {
    if (!rowRunIds || !rowRunIds[i]) rows[i].title = '연결된 실행 기록 없음';
  }
}

function ensureDetailPanel() {
  const existing = $('detail-overlay');
  if (existing) return existing;

  const overlay = document.createElement('div');
  overlay.id = 'detail-overlay';
  overlay.className = 'detail-overlay';
  overlay.hidden = true;

  const panel = document.createElement('section');
  panel.id = 'run-detail-panel';
  panel.className = 'detail-panel';
  panel.setAttribute('role', 'dialog');
  panel.setAttribute('aria-modal', 'true');
  panel.setAttribute('aria-labelledby', 'detail-label');

  const head = document.createElement('div');
  head.className = 'detail-head';
  const label = document.createElement('h2');
  label.id = 'detail-label';
  label.textContent = '실행 상세';
  const close = document.createElement('button');
  close.type = 'button';
  close.id = 'detail-close';
  close.className = 'detail-close';
  close.setAttribute('aria-label', '상세 닫기');
  close.textContent = '×';
  head.appendChild(label);
  head.appendChild(close);

  const body = document.createElement('div');
  body.id = 'detail-body';
  body.className = 'detail-body';

  panel.appendChild(head);
  panel.appendChild(body);
  overlay.appendChild(panel);
  document.body.appendChild(overlay);
  return overlay;
}

function closeDetail() {
  const returnFocus = state.detailReturnFocus;
  state.detailReturnFocus = null;
  state.detailOpen = false;
  state.detailSeq += 1;
  const overlay = $('detail-overlay');
  if (overlay) overlay.hidden = true;
  if (returnFocus && typeof returnFocus.focus === 'function' && document.contains(returnFocus)) {
    returnFocus.focus();
  }
}

// 요청 본문 '전체 보기' - 표시 여부 판단(순수 함수)과 기존 다이얼로그 재사용
function requestFullViewLabel(req) {
  if (!req || typeof req !== 'object') return null;
  if (req.detail_truncated !== true) return null;   // false/키 없음(옛 서버) → 버튼 없음
  const len = Number(req.detail_len);
  if (!Number.isFinite(len)) return null;            // 길이를 알 수 없으면 버튼 없음
  return '전체 보기 (' + len + '자)';
}

async function fetchRequestFull(req) {
  if (DEMO || req.detail_truncated !== true) return req;
  const res = await fetch('/api/requests/' + encodeURIComponent(req.id), { headers: { Accept: 'application/json' } });
  const body = await res.json().catch(() => ({}));
  if (!res.ok || !body.ok) throw new Error(body.error || ('HTTP ' + res.status));
  return Object.assign({}, req, { title: body.title, detail: body.detail, detail_truncated: false });
}

// ---- 상세 패널 공통 (2026-11-10: 탭마다 상세보기가 빠진 곳을 메움)
// 하나의 오버레이(`detail-overlay`)를 모든 상세가 같이 쓴다 - 포커스 저장·가둠·Esc 는 bindDetailControls 가 맡는다.
function openPanel(title, build) {
  state.detailReturnFocus = document.activeElement;
  const overlay = bindDetailControls();
  state.detailOpen = true;
  state.detailSeq += 1;   // 늦게 오는 /api/runs 응답이 이 내용을 덮지 못하게
  const label = $('detail-label');
  if (label) label.textContent = title;
  const body = $('detail-body');
  body.textContent = '';
  build(body);
  overlay.hidden = false;
  const close = $('detail-close');
  if (close) close.focus();
}

// ---- 마크다운 렌더러 (2026-11-10, 태석님 지시 "상세는 마크다운으로")
// 외부 라이브러리 없이(1절: CDN 금지) 작업자·관리자 보고와 요청 본문에 실제로 나오는 문법만 다룬다:
// 제목 / 문단 / 목록(중첩) / 코드 펜스 / 인용 / 표 / 구분선 / 인라인 코드·굵게·기울임·링크(http[s]만).
// **HTML 은 해석하지 않는다** - 모든 텍스트는 textContent 로만 들어간다(XSS 없음). 문단 안 줄바꿈은
// 입력 그대로 <br> 로 살린다(태석님 549a "줄바꿈 유지").
// 인라인은 정규식 하나로 풀지 않는다 - 백틱이 많은 긴 보고(관리자 단계 3,900자)에서 백트래킹으로 화면이
// 멈췄다(2026-11-10 실측). 왼쪽에서 오른쪽으로 한 번 훑는 선형 스캐너다.
const MD_LINK = /\[([^\]\n]+)\]\((https?:\/\/[^\s)]+)\)/y;
const MD_AUTOLINK = /https?:\/\/[^\s<>()\[\]`'"]*[^\s<>()\[\]`'".,;:!?]/y;

function mdInline(text, parent) {
  let buf = '';
  const flush = () => { if (buf) { parent.appendChild(document.createTextNode(buf)); buf = ''; } };
  const n = text.length;
  let i = 0;
  const closes = (mark, from) => {   // mark 가 from 이후 같은 줄 안에 다시 나오는 위치 (앞뒤 공백 규칙 포함)
    let k = text.indexOf(mark, from);
    while (k !== -1 && (k === from || /\s/.test(text[k - 1]))) k = text.indexOf(mark, k + 1);
    return k;
  };
  while (i < n) {
    const ch = text[i];
    if (ch === '`') {
      let run = 1;
      while (text[i + run] === '`') run += 1;
      const fence = '`'.repeat(run);
      const k = text.indexOf(fence, i + run);
      if (k !== -1) {
        flush();
        const code = document.createElement('code');
        code.textContent = text.slice(i + run, k).trim();
        parent.appendChild(code);
        i = k + run;
        continue;
      }
      buf += fence; i += run; continue;
    }
    if (ch === '*' && text[i + 1] === '*') {
      const k = closes('**', i + 2);
      if (k !== -1 && !/\s/.test(text[i + 2] || ' ')) {
        flush();
        const el = document.createElement('strong');
        mdInline(text.slice(i + 2, k), el);
        parent.appendChild(el);
        i = k + 2;
        continue;
      }
      buf += '**'; i += 2; continue;
    }
    if ((ch === '*' || ch === '_') && !/\w/.test(text[i - 1] || ' ') && !/\s/.test(text[i + 1] || ' ')) {
      let k = text.indexOf(ch, i + 1);
      while (k !== -1 && (/\s/.test(text[k - 1]) || /\w/.test(text[k + 1] || ' '))) k = text.indexOf(ch, k + 1);
      if (k !== -1 && k > i + 1) {
        flush();
        const el = document.createElement('em');
        mdInline(text.slice(i + 1, k), el);
        parent.appendChild(el);
        i = k + 1;
        continue;
      }
    }
    if (ch === '[') {
      MD_LINK.lastIndex = i;
      const m = MD_LINK.exec(text);
      if (m) {
        flush();
        const a = document.createElement('a');
        a.href = m[2]; a.target = '_blank'; a.rel = 'noopener noreferrer';
        mdInline(m[1], a);
        parent.appendChild(a);
        i += m[0].length;
        continue;
      }
    }
    if (ch === 'h' && text.startsWith('http', i) && !/\w/.test(text[i - 1] || ' ')) {
      MD_AUTOLINK.lastIndex = i;
      const m = MD_AUTOLINK.exec(text);
      if (m) {
        flush();
        const a = document.createElement('a');
        a.href = m[0]; a.target = '_blank'; a.rel = 'noopener noreferrer'; a.textContent = m[0];
        parent.appendChild(a);
        i += m[0].length;
        continue;
      }
    }
    buf += ch; i += 1;
  }
  flush();
}

const MD_LIST = /^(\s*)(?:([-*+])|(\d{1,3})[.)])\s+(.*)$/;
const MD_TABLE_SEP = /^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?\s*$/;
const isTableRow = (l) => /^\s*\|.*\|\s*$/.test(l);
const splitCells = (l) => {
  let t = l.trim();
  if (t.startsWith('|')) t = t.slice(1);
  if (t.endsWith('|')) t = t.slice(0, -1);
  return t.split('|').map((c) => c.trim());
};

function renderMarkdown(src) {
  const root = document.createElement('div');
  root.className = 'md';
  const lines = String(src === null || src === undefined ? '' : src).replace(/\r\n?/g, '\n').split('\n');
  let i = 0;
  const para = [];
  const flushPara = () => {
    if (!para.length) return;
    const p = document.createElement('p');
    para.forEach((ln, k) => { if (k) p.appendChild(document.createElement('br')); mdInline(ln, p); });
    root.appendChild(p);
    para.length = 0;
  };
  while (i < lines.length) {
    const ln = lines[i];
    if (!ln.trim()) { flushPara(); i += 1; continue; }
    let m;
    if ((m = /^\s*(`{3,}|~{3,})\s*(\S*)\s*$/.exec(ln))) {              // 코드 펜스
      flushPara();
      const fence = m[1]; const buf = []; i += 1;
      while (i < lines.length && !new RegExp('^\\s*' + fence[0] + '{' + fence.length + ',}\\s*$').test(lines[i])) { buf.push(lines[i]); i += 1; }
      i += 1;
      const pre = document.createElement('pre'); const code = document.createElement('code');
      if (m[2]) code.dataset.lang = m[2];
      code.textContent = buf.join('\n'); pre.appendChild(code); root.appendChild(pre); continue;
    }
    if ((m = /^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$/.exec(ln))) {              // 제목
      flushPara();
      const h = document.createElement('h' + m[1].length); mdInline(m[2], h); root.appendChild(h); i += 1; continue;
    }
    if (isTableRow(ln) && i + 1 < lines.length && MD_TABLE_SEP.test(lines[i + 1])) {   // 표
      flushPara();
      const head = splitCells(ln);
      const align = splitCells(lines[i + 1]).map((c) => (/^:-+:$/.test(c) ? 'center' : /-+:$/.test(c) ? 'right' : ''));
      const wrap = document.createElement('div'); wrap.className = 'md-table';
      const table = document.createElement('table');
      const thead = document.createElement('thead'); const tr = document.createElement('tr');
      head.forEach((c, k) => { const th = document.createElement('th'); if (align[k]) th.style.textAlign = align[k]; mdInline(c, th); tr.appendChild(th); });
      thead.appendChild(tr); table.appendChild(thead);
      const tbody = document.createElement('tbody'); i += 2;
      while (i < lines.length && isTableRow(lines[i])) {
        const r = document.createElement('tr');
        const cells = splitCells(lines[i]);
        head.forEach((_, k) => { const td = document.createElement('td'); if (align[k]) td.style.textAlign = align[k]; mdInline(cells[k] === undefined ? '' : cells[k], td); r.appendChild(td); });
        tbody.appendChild(r); i += 1;
      }
      table.appendChild(tbody); wrap.appendChild(table); root.appendChild(wrap); continue;
    }
    if (/^\s{0,3}([-*_])(\s*\1){2,}\s*$/.test(ln)) {                       // 구분선
      flushPara(); root.appendChild(document.createElement('hr')); i += 1; continue;
    }
    if (/^\s{0,3}>/.test(ln)) {                                              // 인용
      flushPara();
      const buf = [];
      while (i < lines.length && /^\s{0,3}>/.test(lines[i])) { buf.push(lines[i].replace(/^\s{0,3}>\s?/, '')); i += 1; }
      const bq = document.createElement('blockquote'); bq.appendChild(renderMarkdown(buf.join('\n'))); root.appendChild(bq); continue;
    }
    if ((m = MD_LIST.exec(ln))) {                                            // 목록 (들여쓰기로 중첩)
      flushPara();
      const items = [];
      while (i < lines.length) {
        const mm = MD_LIST.exec(lines[i]);
        if (mm) { items.push({ indent: mm[1].replace(/\t/g, '  ').length, ordered: mm[3] !== undefined, text: mm[4] }); i += 1; }
        else if (items.length && lines[i].trim() && /^\s{2,}/.test(lines[i])) { items[items.length - 1].text += '\n' + lines[i].trim(); i += 1; }   // 이어지는 줄
        else break;
      }
      const stack = [];
      const newList = (ordered) => document.createElement(ordered ? 'ol' : 'ul');
      for (const it of items) {
        while (stack.length && it.indent < stack[stack.length - 1].indent) stack.pop();
        if (stack.length && it.indent === stack[stack.length - 1].indent && it.ordered !== stack[stack.length - 1].ordered) {
          stack.pop();   // 같은 깊이에서 `-` ↔ `1.` 이 바뀌면 새 목록
          if (!stack.length) { const list = newList(it.ordered); root.appendChild(list); stack.push({ indent: it.indent, list, ordered: it.ordered }); }
          else { const list = newList(it.ordered); (stack[stack.length - 1].list.lastElementChild || stack[stack.length - 1].list).appendChild(list); stack.push({ indent: it.indent, list, ordered: it.ordered }); }
        } else if (!stack.length || it.indent > stack[stack.length - 1].indent) {
          const list = newList(it.ordered);
          if (stack.length) { const parentLi = stack[stack.length - 1].list.lastElementChild; (parentLi || stack[stack.length - 1].list).appendChild(list); }
          else root.appendChild(list);
          stack.push({ indent: it.indent, list, ordered: it.ordered });
        }
        const li = document.createElement('li');
        it.text.split('\n').forEach((t, k) => { if (k) li.appendChild(document.createElement('br')); mdInline(t, li); });
        stack[stack.length - 1].list.appendChild(li);
      }
      continue;
    }
    para.push(ln);
    i += 1;
  }
  flushPara();
  return root;
}

// 마크다운 블록 + '원문' 토글. update(text) 로 내용을 갈아끼울 수 있다(요청 전문이 늦게 올 때).
function mdBlock(text, emptyText) {
  const box = document.createElement('div');
  box.className = 'md-block';
  const bar = document.createElement('div');
  bar.className = 'md-bar';
  const toggle = document.createElement('button');
  toggle.type = 'button';
  toggle.className = 'btn-link md-toggle';
  bar.appendChild(toggle);
  const view = document.createElement('div');
  box.appendChild(bar);
  box.appendChild(view);
  let raw = false;
  let current = text;
  const paint = () => {
    view.textContent = '';
    const t = show(current, '');
    if (!t) { view.appendChild(emptyP(emptyText || '없음')); bar.hidden = true; return; }
    bar.hidden = false;
    toggle.textContent = raw ? '마크다운으로 보기' : '원문 보기';
    if (raw) { const pre = document.createElement('pre'); pre.className = 'detail-pre'; pre.textContent = t; view.appendChild(pre); }
    else view.appendChild(renderMarkdown(t));
  };
  toggle.addEventListener('click', () => { raw = !raw; paint(); });
  paint();
  box.update = (t) => { current = t; paint(); };
  return box;
}

function addTextSection(parent, title, text) {
  const section = document.createElement('section');
  section.className = 'detail-section';
  const h3 = document.createElement('h3');
  h3.textContent = title;
  section.appendChild(h3);
  section.appendChild(mdBlock(text, '없음'));   // 마크다운으로, '원문 보기' 토글 포함
  parent.appendChild(section);
}

function linkButton(text, onClick) {
  const btn = document.createElement('button');
  btn.type = 'button';
  btn.className = 'btn-link';
  btn.textContent = text;
  btn.addEventListener('click', onClick);
  return btn;
}

function runsForTask(taskId, data) {
  const prefix = String(taskId) + '-';
  const out = (Array.isArray(data.runs) ? data.runs : [])
    .filter((r) => r && String(r.id || '').indexOf(prefix) === 0);
  out.sort((a, b) => String(b.started || '').localeCompare(String(a.started || '')));
  return out;
}

function findSubtask(taskId, data) {
  for (const req of (Array.isArray(data.requests) ? data.requests : [])) {
    for (const st of (req && Array.isArray(req.subtasks) ? req.subtasks : [])) {
      if (st && st.id === taskId) return { req, st };
    }
  }
  return null;
}

function findGraphNode(taskId, data) {
  for (const g of (Array.isArray(data.graphs) ? data.graphs : [])) {
    for (const n of (g && Array.isArray(g.nodes) ? g.nodes : [])) {
      if (n && n.id === taskId) return { g, n };
    }
  }
  return null;
}

function taskKnown(taskId, data) {
  if (!taskId || !data) return false;
  if ((Array.isArray(data.board) ? data.board : []).some((b) => b && b.id === taskId)) return true;
  if (findSubtask(taskId, data)) return true;
  return runsForTask(taskId, data).length > 0;
}

function runsTable(runs) {
  const rows = runs.map((r) => {
    const rc = document.createElement('span');
    rc.textContent = (r.rc === null || r.rc === undefined) ? '-' : String(r.rc);
    if (r.rc !== null && r.rc !== undefined && Number(r.rc) !== 0) rc.className = 'warn-text';
    return [mono(r.id), show(r.slot), statusBadge(r.state), reportBadge(r.report_head), rc,
      fmtElapsed(r.elapsed_sec), fmtDateTime(r.started)];
  });
  return newTable(['run id', '슬롯', '상태', '보고', 'rc', '경과', '시작'], rows, null, {
    widths: ['196px', '52px', '80px', '108px', '40px', '80px', null],
    num: [4, 5], center: [2, 3],
    rowRunIds: runs.map((r) => r.id),
  });
}

// 태스크 상세: 보드 행 + 요청 안의 서브태스크 + 그래프 노드 + 이 태스크로 뜬 **모든** 실행(재시도 포함).
// 실행이 없는 태스크(관리자 직접분·미착수)도 열린다 - 전에는 그런 행이 아무 반응도 없었다.
function openTaskDetail(taskId, data) {
  data = data || state.data;
  if (!taskId || !data) return;
  const b = (Array.isArray(data.board) ? data.board : []).find((x) => x && x.id === taskId) || null;
  const sub = findSubtask(taskId, data);
  const gn = findGraphNode(taskId, data);
  const runs = runsForTask(taskId, data);
  if (sub && sub.st.run_id && !runs.some((r) => r.id === sub.st.run_id)) {
    const r = (Array.isArray(data.runs) ? data.runs : []).find((x) => x && x.id === sub.st.run_id);
    if (r) runs.push(r);
  }
  const title = b ? b.task : (sub ? sub.st.title : (gn ? gn.n.title : ''));
  openPanel('태스크 ' + show(taskId, ''), (body) => {
    const meta = document.createElement('div');
    meta.className = 'detail-meta';
    meta.appendChild(detailMetaItem('id', mono(taskId)));
    meta.appendChild(detailMetaItem('작업', plainText(title) || '-'));
    meta.appendChild(detailMetaItem('슬롯', show(b ? b.slot : (sub ? sub.st.slot : (gn ? gn.n.slot : null)))));
    if (b) {
      meta.appendChild(detailMetaItem('보드 상태', statusBadge(b.status)));
      meta.appendChild(detailMetaItem('핸드오프', show(b.handoff)));
      meta.appendChild(detailMetaItem('산출물', plainText(b.artifact) || '-'));
    } else {
      meta.appendChild(detailMetaItem('보드 상태', '보드에 없음'));
    }
    if (sub) {
      meta.appendChild(detailMetaItem('요청', show(sub.req.title)));
      meta.appendChild(detailMetaItem('요청 내 상태', statusBadge(sub.st.status)));
      if (sub.st.harness) meta.appendChild(detailMetaItem('하네스', show(sub.st.harness)));
    }
    if (gn) {
      meta.appendChild(detailMetaItem('그래프', show(gn.g.id) + ' · ' + show(gn.n.status)
        + ' · 시도 ' + show(gn.n.attempts) + '/' + show(gn.n.max_attempts)));
      if (Array.isArray(gn.n.deps) && gn.n.deps.length) meta.appendChild(detailMetaItem('의존', gn.n.deps.join(', ')));
    }
    body.appendChild(meta);
    if (sub) {
      const row = document.createElement('div');
      row.className = 'detail-actions';
      row.appendChild(linkButton('요청 상세 보기 → ' + show(sub.req.id, ''), () => openRequestDetail(sub.req)));
      body.appendChild(row);
    }
    const section = document.createElement('section');
    section.className = 'detail-section';
    const h3 = document.createElement('h3');
    h3.textContent = '실행 기록 ' + runs.length + '건' + (runs.length ? ' · 행을 누르면 실행 상세' : '');
    section.appendChild(h3);
    if (!runs.length) {
      section.appendChild(emptyP('이 태스크로 뜬 작업자 실행이 없습니다 - 관리자 직접분이거나 아직 미착수'));
    } else {
      const tw = document.createElement('div');
      tw.className = 'tablewrap';
      tw.appendChild(runsTable(runs));
      section.appendChild(tw);
    }
    body.appendChild(section);
  });
}

function openQueueDetail(q, data) {
  data = data || state.data;
  openPanel('대기 큐 ' + show(q.order, ''), (body) => {
    const meta = document.createElement('div');
    meta.className = 'detail-meta';
    meta.appendChild(detailMetaItem('순서', show(q.order)));
    meta.appendChild(detailMetaItem('슬롯', show(q.slots)));
    meta.appendChild(detailMetaItem('핸드오프', show(q.handoff)));
    body.appendChild(meta);
    const ho = String(q.handoff || '').trim();
    if (ho && data && taskKnown(ho, data)) {
      const row = document.createElement('div');
      row.className = 'detail-actions';
      row.appendChild(linkButton('태스크 상세 보기 → ' + ho, () => openTaskDetail(ho, data)));
      body.appendChild(row);
    }
    addTextSection(body, '작업', q.task);
    addTextSection(body, '비고', q.note);
  });
}

function openLogDetail(entry) {
  openPanel('핸드오프 로그 ' + show(entry.when, ''), (body) => {
    addTextSection(body, '내용', entry.text);
  });
}

function openManagerList(sessions) {
  openPanel('관리자 세션 ' + sessions.length + '개', (body) => {
    const rows = sessions.map((s) => [
      show(s.label),
      s.status === 'running' ? badge('실행 중', 'running')
        : badge(s.status === 'done' ? '끝남' : show(s.status), s.status === 'failed' ? 'blocked' : 'neutral'),
      fmtDateTime(s.started),
      fmtDateTime(s.updated),
      (s.record_kb === null || s.record_kb === undefined) ? '-'
        : (s.record_kb >= 1024 ? (s.record_kb / 1024).toFixed(1) + 'MB' : s.record_kb + 'KB'),
    ]);
    const tw = document.createElement('div');
    tw.className = 'tablewrap';
    tw.appendChild(newTable(['라벨', '상태', '시작', '갱신', '기록'], rows, null, {
      widths: [null, '80px', '150px', '150px', '70px'],
      center: [1], ellipsis: [0],
      rowOpen: sessions.map((s) => ({ fn: () => openManagerDetail(s), title: '관리자 세션 상세: ' + show(s.label, '') })),
    }));
    body.appendChild(tw);
  });
}

function openRequestDetail(req) {
  if (!req) return;
  state.detailReturnFocus = document.activeElement;  // T-083 포커스 저장 그대로
  const overlay = bindDetailControls();
  state.detailOpen = true;
  state.detailSeq += 1;   // 늦게 도착한 /api/runs 응답이 이 내용을 덮지 못하게
  const label = $('detail-label');
  if (label) label.textContent = show(req.title, '요청 상세');
  const body = $('detail-body');
  body.textContent = '';
  const wrap = mdBlock(req.detail, '본문 없음');   // 마크다운(HTML 은 해석하지 않음) + '원문 보기'
  body.appendChild(wrap);
  if (req.detail_truncated === true) {
    const len = Number(req.detail_len);
    if (Number.isFinite(len)) {
      const note = document.createElement('p');
      note.className = 'detail-note';
      note.textContent = '원본 ' + len + '자 중 앞 600자입니다. 전문은 .aimem/requests/'
        + show(req.id, '') + '.json 에 있습니다.';
      body.appendChild(note);
    }
  }
  overlay.hidden = false;
  const close = $('detail-close');
  if (close) close.focus();
  if (req.detail_truncated === true && !DEMO) {
    const seq = state.detailSeq;
    fetchRequestFull(req).then((full) => {
      if (seq !== state.detailSeq || !state.detailOpen) return;   // 그사이 다른 상세를 열었다
      wrap.update(full.detail);
      const note = body.querySelector('.detail-note');
      if (note) note.remove();
    }).catch(() => { /* 600자 미리보기와 안내문을 그대로 둔다 */ });
  }
}

function bindDetailControls() {
  const overlay = ensureDetailPanel();
  if (state.detailBound) return overlay;
  const close = $('detail-close');
  if (close) close.addEventListener('click', closeDetail);
  overlay.addEventListener('click', (event) => {
    if (event.target === overlay) closeDetail();
  });
  overlay.addEventListener('keydown', (event) => {
    if (event.key !== 'Tab' || !state.detailOpen) return;
    const panel = $('run-detail-panel');
    if (!panel) return;
    const focusable = Array.from(
      panel.querySelectorAll('a[href], button, textarea, input, select, [tabindex]:not([tabindex="-1"])')
    ).filter((el) => !el.disabled && el.offsetParent !== null);
    if (focusable.length === 0) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  });
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && state.detailOpen) {
      event.preventDefault();
      closeDetail();
    }
  });
  state.detailBound = true;
  return overlay;
}

function detailMetaItem(label, value) {
  const item = document.createElement('div');
  item.className = 'detail-meta-item';
  const l = document.createElement('div');
  l.className = 'detail-meta-label';
  l.textContent = label;
  item.appendChild(l);
  const v = document.createElement('div');
  v.className = 'detail-meta-value';
  if (value instanceof Node) v.appendChild(value);
  else v.textContent = show(value);
  item.appendChild(v);
  return item;
}

function addDetailSection(parent, title, text, plain = false) {
  const section = document.createElement('section');
  section.className = 'detail-section';
  const h3 = document.createElement('h3');
  h3.textContent = title;
  section.appendChild(h3);
  if (plain) {                       // stderr 같은 기계 출력은 그대로
    const pre = document.createElement('pre');
    pre.className = 'detail-pre';
    pre.textContent = show(text, '없음');
    section.appendChild(pre);
  } else {
    section.appendChild(mdBlock(text, '없음'));
  }
  parent.appendChild(section);
}

function renderDetail(detail) {
  const body = $('detail-body');
  body.textContent = '';

  const meta = document.createElement('div');
  meta.className = 'detail-meta';
  meta.appendChild(detailMetaItem('라벨', detail.label));
  meta.appendChild(detailMetaItem('id', mono(detail.id)));
  meta.appendChild(detailMetaItem('슬롯', show(detail.slot)));
  meta.appendChild(detailMetaItem('하네스', show(detail.harness)));
  meta.appendChild(detailMetaItem('모델', show(detail.model)));
  meta.appendChild(detailMetaItem('상태', statusBadge(detail.status)));
  const rc = detailMetaItem('rc', show(detail.rc));
  const rcValue = rc.querySelector('.detail-meta-value');
  if (rcValue && detail.rc !== null && detail.rc !== undefined && Number(detail.rc) !== 0) {
    rcValue.classList.add('warn-text');
  }
  meta.appendChild(rc);
  meta.appendChild(detailMetaItem('경과', fmtElapsed(detail.elapsed_s)));
  body.appendChild(meta);

  const errors = Array.isArray(detail.errors) ? detail.errors : [];
  if (errors.length) {
    const errBox = document.createElement('div');
    errBox.className = 'detail-error';
    const strong = document.createElement('strong');
    strong.textContent = '오류 ' + errors.length + '건';
    errBox.appendChild(strong);
    const ul = document.createElement('ul');
    for (const e of errors) {
      const li = document.createElement('li');
      li.textContent = show(e);
      ul.appendChild(li);
    }
    errBox.appendChild(ul);
    body.appendChild(errBox);
  }

  addDetailSection(body, '보고 본문', detail.report);
  addDetailSection(body, '지시 본문', detail.brief);
  addDetailSection(body, 'stderr', detail.stderr_tail, true);
}

async function serverErrorReason(res) {
  let data = null;
  try {
    data = await res.json();
  } catch (err) {
    return null;
  }
  if (data && typeof data.error === 'string' && data.error !== '') return data.error;
  return null;
}

async function openDetail(runId) {
  state.detailReturnFocus = document.activeElement;
  const overlay = bindDetailControls();
  const body = $('detail-body');
  state.detailOpen = true;
  state.detailSeq += 1;
  const seq = state.detailSeq;
  overlay.hidden = false;
  const close = $('detail-close');
  if (close) close.focus();
  const titleEl = $('detail-label');
  if (titleEl) titleEl.textContent = '실행 상세 ' + show(runId, '');   // 다른 상세(태스크·큐)에서 넘어와도 제목이 바뀐다
  body.textContent = '가져오는 중... (' + runId + ')';

  let res;
  try {
    res = await fetch('/api/runs/' + encodeURIComponent(runId), {
      headers: { Accept: 'application/json' },
    });
  } catch (err) {
    if (seq !== state.detailSeq) return;
    body.textContent = '가져오기 실패: ' + (err && err.message ? err.message : String(err));
    return;
  }

  if (res.status === 404) {
    if (seq !== state.detailSeq) return;
    const reason = await serverErrorReason(res);
    if (seq !== state.detailSeq) return;
    body.textContent = reason ? 'HTTP 404 - ' + reason : '404 - 실행 기록을 찾을 수 없습니다: ' + runId;
    return;
  }
  if (res.status === 400) {
    if (seq !== state.detailSeq) return;
    const reason = await serverErrorReason(res);
    if (seq !== state.detailSeq) return;
    body.textContent = reason ? 'HTTP 400 - ' + reason : '400 - 잘못된 실행 id 입니다: ' + runId;
    return;
  }
  if (!res.ok) {
    if (seq !== state.detailSeq) return;
    const reason = await serverErrorReason(res);
    if (seq !== state.detailSeq) return;
    body.textContent = reason
      ? 'HTTP ' + res.status + ' - ' + reason
      : '가져오기 실패: HTTP ' + res.status + ' ' + (res.statusText || '');
    return;
  }

  let detail;
  try {
    detail = await res.json();
  } catch (err) {
    if (seq !== state.detailSeq) return;
    body.textContent = '응답을 해석할 수 없습니다.';
    return;
  }

  if (seq !== state.detailSeq) return;
  if (!detail || detail.found === false) {
    body.textContent = '실행 기록을 찾을 수 없습니다: ' + runId;
    return;
  }
  renderDetail(detail);
}

function metaItem(label, value) {
  const item = document.createElement('div');
  item.className = 'meta-item';
  const l = document.createElement('div');
  l.className = 'meta-label';
  l.textContent = label;
  item.appendChild(l);
  const v = document.createElement('div');
  v.className = 'meta-value';
  if (value instanceof Node) v.appendChild(value);
  else v.textContent = show(value);
  item.appendChild(v);
  return item;
}

// 마크다운 강조·코드 표시(**, `)를 걷어 내고 사람이 읽는 문장으로 (마크업 해석은 하지 않음)
function plainText(value) {
  return show(value, '').replace(/\*\*/g, '').replace(/`/g, '').trim();
}

// 보고 첫 줄에서 DONE / PARTIAL / BLOCKED / NEEDS-* 를 읽는다 (fleet_graph 판정과 같은 방향, 표시용)
function reportStatus(head) {
  const s = show(head, '').replace(/^[\s*#>_`\-·]+/, '');
  const m = /^(?:상태|status|report status)?\s*[:：]?\s*\**\s*(DONE|PARTIAL|BLOCKED|NEEDS-[A-Z]+|REJECT(?:ED)?)\b/i.exec(s);
  return m ? m[1].toUpperCase() : null;
}

function reportBadge(head) {
  const st = reportStatus(head);
  if (!st) {
    const span = document.createElement('span');
    span.className = 'hint';
    span.textContent = '-';
    return span;
  }
  const cls = st === 'DONE' ? 'done' : st === 'PARTIAL' ? 'partial' : st.startsWith('NEEDS') ? 'needs' : 'blocked';
  return badge(st, cls);
}

function renderMeta(data) {
  const box = $('aimem-meta');
  box.textContent = '';
  const aimem = data.aimem || {};
  const goal = aimem.goal || {};

  const rev = document.createElement('div');
  rev.className = 'meta-stat';
  rev.textContent = show(aimem.rev);
  box.appendChild(metaItem('AIMEM REV', rev));
  box.appendChild(metaItem('최종 갱신', show(aimem.updated)));

  const goalWrap = document.createElement('div');
  goalWrap.className = 'goal-value';
  const goalText = document.createElement('span');
  goalText.textContent = plainText(goal.text) || '-';
  goalWrap.appendChild(goalText);
  if (goal.status) {
    const goalStatus = document.createElement('span');
    goalStatus.className = 'goal-status';
    goalStatus.textContent = plainText(goal.status);
    goalWrap.appendChild(goalStatus);
  }
  const goalItem = metaItem('현재 목표', goalWrap);
  goalItem.classList.add('meta-goal');
  box.appendChild(goalItem);

  const brandRev = $('brand-rev');
  if (brandRev) brandRev.textContent = aimem.rev ? 'REV ' + aimem.rev : '';
}

const MODE_BADGE = { running: 'running', paused: 'partial', stopped: 'blocked', ready: 'done' };
const FLEET_BUTTONS = [
  { act: 'prepare', label: '준비', title: '관리자·작업자를 띄울 수 있는지 점검합니다. 통과하면 준비 상태 (작업자는 띄우지 않음)' },
  { act: 'run', label: '실행', title: '진행 중이던 라운드만 이어 돌립니다. 새 관리자 라운드는 띄우지 않습니다' },
  { act: 'pause', label: '일시 중지', title: '새 작업자 투입을 멈춥니다. 돌고 있는 작업자는 끝까지 둡니다' },
  { act: 'stop', label: '완전 중지', title: '돌고 있는 작업자와 그래프 실행기를 즉시 종료합니다', danger: true,
    confirm: '돌고 있는 작업자와 그래프 실행기를 지금 종료합니다.\n중간 산출물이 반쯤 남을 수 있습니다. 계속할까요?' },
];

async function fleetAction(act, confirmText) {
  if (confirmText && !window.confirm(confirmText)) return;
  state.fleetBusy = act;
  state.fleetMsg = null;
  if (state.data) renderFleetControl(state.data);
  try {
    let body;
    if (DEMO) {
      body = { ok: true, note: '데모 모드 - 실제로 바꾸지 않습니다' };
    } else {
      const res = await fetch('/api/fleet/' + act, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: '{}',
      });
      body = await res.json().catch(() => ({ ok: false, error: 'HTTP ' + res.status }));
    }
    state.fleetMsg = { act, ok: body.ok !== false, body };
  } catch (err) {
    state.fleetMsg = { act, ok: false, body: { error: err && err.message ? err.message : String(err) } };
  } finally {
    state.fleetBusy = null;
    // 5초 폴링이 도는 중이면 refresh() 가 건너뛴다 - 끝나기를 기다렸다가 새로 읽는다
    for (let i = 0; i < 50 && state.busy; i += 1) await new Promise((r) => setTimeout(r, 100));
    await refresh();
  }
}

function fleetMsgText(m) {
  const b = m.body || {};
  const name = { prepare: '준비', run: '실행', pause: '일시 중지', stop: '완전 중지', round: '라운드 실행' }[m.act] || m.act;
  if (m.act === 'prepare' && Array.isArray(b.checks)) {
    const bad = b.checks.filter((c) => !c.ok && c.required).map((c) => c.name);
    return b.ok ? '준비 점검 통과 - 준비 상태입니다' : `준비 점검에서 막혔습니다: ${bad.join(', ')} (아래 목록)`;
  }
  if (!m.ok) return `${name} 실패: ${b.error || '알 수 없는 오류'}`;
  if (m.act === 'stop') {
    const k = (b.killed || []).length;
    return `완전 중지 - 작업자 ${k}개 종료` + ((b.halted_graphs || []).length ? `, 그래프 ${b.halted_graphs.join(', ')} 정리` : '') + '. ' + (b.note || '');
  }
  if (m.act === 'run') return '실행 - ' + ((b.resumed_graphs || []).length ? `그래프 ${b.resumed_graphs.join(', ')} 이어 돌림. ` : '') + (b.note || '');
  if (m.act === 'round') return `라운드 R${b.round} 실행 - 클로에게 전달했습니다 (${b.brief}). 관리자 세션이 뜨면 위에 나타납니다`;
  return name + ' 완료';
}

function renderFleetControl(data) {
  const box = $('fleet-control');
  const pill = $('fleet-mode-pill');
  const f = data.fleet || {};
  const md = f.mode;
  if (pill) {
    pill.textContent = md ? '함대: ' + show(f.label) : '';
    pill.className = 'mode-pill' + (md ? ' mode-' + md : '');
    pill.title = f.note ? `${show(f.label)} - ${f.note} (${fmtDateTime(f.at)}, ${show(f.by)})` : '';
  }
  if (!box) return;
  box.textContent = '';
  if (!md) {
    box.appendChild(emptyP('함대 제어 상태를 읽지 못했습니다' + (f.error ? ': ' + f.error : '')));
    return;
  }
  const head = document.createElement('div');
  head.className = 'fc-head';
  const title = document.createElement('span');
  title.className = 'manager-title';
  title.textContent = '함대';
  head.appendChild(title);
  head.appendChild(badge(show(f.label), MODE_BADGE[md] || 'neutral'));
  const meta = document.createElement('span');
  meta.className = 'fc-meta';
  const bits = [];
  if (f.at) bits.push(fmtDateTime(f.at) + ' · ' + show(f.by));
  if (f.default) bits.push('상태 파일 없음(기본값)');
  if (f.running_runs) bits.push(`작업자 ${f.running_runs}개 실행 중`);
  if (Array.isArray(f.graphs) && f.graphs.length) bits.push('미완 그래프 ' + f.graphs.map((g) => g.id + (g.runner ? '(실행기)' : '')).join(', '));
  meta.textContent = bits.join(' · ');
  head.appendChild(meta);
  box.appendChild(head);

  const can = f.can || {};
  const row = document.createElement('div');
  row.className = 'fc-buttons';
  for (const b of FLEET_BUTTONS) {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'fc-btn' + (b.danger ? ' fc-danger' : '');
    btn.textContent = state.fleetBusy === b.act ? b.label + '…' : b.label;
    btn.title = b.title;
    btn.disabled = !!state.fleetBusy || !can[b.act];
    btn.addEventListener('click', () => fleetAction(b.act, b.confirm));
    row.appendChild(btn);
  }
  const sep = document.createElement('span');
  sep.className = 'fc-sep';
  row.appendChild(sep);
  const brief = f.brief || {};
  const rb = document.createElement('button');
  rb.type = 'button';
  rb.className = 'fc-btn btn-primary';
  rb.textContent = state.fleetBusy === 'round' ? '라운드 실행…' : (brief.round ? `라운드 실행 ▸ R${brief.round}` : '라운드 실행');
  rb.disabled = !!state.fleetBusy || !can.round;
  rb.title = brief.file
    ? `새 관리자 라운드를 띄웁니다 (유료 Opus). 브리프: ${brief.file}` + (md !== 'ready' ? ' - 먼저 준비를 누르십시오' : '')
    : '확정된 다음 라운드 브리프가 없습니다' + (brief.drafts && brief.drafts.length ? ` (초안: ${brief.drafts.join(', ')})` : '');
  rb.addEventListener('click', () => fleetAction('round',
    `새 관리자 라운드 R${brief.round} 를 띄웁니다 (유료 Opus 세션).\n브리프: ${brief.file}\n계속할까요?`));
  row.appendChild(rb);
  box.appendChild(row);

  const hint = document.createElement('div');
  hint.className = 'fc-hint';
  hint.textContent = brief.file
    ? `다음 라운드 브리프: ${brief.file}`
    : '다음 라운드 브리프: 확정본 없음' + (brief.drafts && brief.drafts.length ? ` (초안 ${brief.drafts.join(', ')})` : '');
  box.appendChild(hint);

  const relay = f.relay;
  if (relay && relay.state && relay.state !== 'spawned') {
    const r = document.createElement('div');
    r.className = 'fc-hint';
    const last = Array.isArray(relay.log) && relay.log.length ? relay.log[relay.log.length - 1] : '';
    r.textContent = `R${relay.round} 전달: ${relay.state}${relay.nudged ? ' (재촉 1회)' : ''} - ${last}`;
    box.appendChild(r);
  }

  if (state.fleetMsg) {
    const msg = document.createElement('div');
    msg.className = 'fc-msg ' + (state.fleetMsg.ok ? 'ok' : 'err');
    msg.textContent = fleetMsgText(state.fleetMsg);
    box.appendChild(msg);
  }

  const prep = f.prepare;
  if (prep && Array.isArray(prep.checks)) {
    const det = document.createElement('details');
    det.className = 'fold-group';
    if (state.fleetMsg && state.fleetMsg.act === 'prepare') det.open = true;
    const sum = document.createElement('summary');
    const failed = prep.checks.filter((c) => !c.ok);
    sum.textContent = `준비 점검 ${fmtDateTime(prep.at)} - ${prep.ok ? '통과' : '막힘'}` + (failed.length ? ` (${failed.length}건 미통과)` : '');
    det.appendChild(sum);
    const ul = document.createElement('ul');
    ul.className = 'fc-checks';
    for (const c of prep.checks) {
      const li = document.createElement('li');
      li.className = c.ok ? 'ok' : (c.required ? 'err' : 'warn');
      li.textContent = `${c.ok ? '✓' : (c.required ? '✗' : '!')} ${c.name}` + (c.detail ? ` - ${c.detail}` : '') + (c.required ? '' : ' (참고)');
      ul.appendChild(li);
    }
    det.appendChild(ul);
    box.appendChild(det);
  }
}

function managerActivity(data) {
  const runs = Array.isArray(data.runs) ? data.runs : [];
  const running = runs.filter((r) => r && r.state === 'running');
  const graphs = Array.isArray(data.graphs) ? data.graphs : [];
  const live = graphs.filter((g) => !graphFinished(g) && !graphStale(g));
  if (live.length) {
    return `그래프 ${live.map((g) => g.id).join(', ')} 실행 중 · 작업자 ${running.length}개 가동`;
  }
  if (running.length) return `작업자 ${running.length}개 가동 중 (그래프 밖 단건 실행)`;
  return '직접 작업 중 (계획·검증·보고 작성) - 이 동안 작업자는 0개입니다';
}

const MANAGER_IDLE_WARN_SEC = 600;

function detailRows(parent, title, rows) {
  const sec = document.createElement('section');
  sec.className = 'detail-section';
  const h = document.createElement('h3');
  h.textContent = title;
  sec.appendChild(h);
  if (!rows.length) {
    sec.appendChild(emptyP('없음'));
  } else {
    const ol = document.createElement('ol');
    ol.className = 'mgr-list';
    for (const r of rows) {
      const li = document.createElement('li');
      if (r.cls) li.className = r.cls;
      if (r.head) {
        const b = document.createElement('span');
        b.className = 'mgr-head';
        b.textContent = r.head;
        li.appendChild(b);
      }
      const s = document.createElement(r.md ? 'div' : 'span');
      s.className = 'mgr-body';
      if (r.md) s.appendChild(renderMarkdown(r.body));   // 관리자 글은 마크다운(표·목록·코드)
      else s.textContent = r.body;
      li.appendChild(s);
      ol.appendChild(li);
    }
    sec.appendChild(ol);
  }
  parent.appendChild(sec);
  return sec;
}

async function openManagerDetail(cur, all = false) {
  if (!cur || !cur.id) return;
  state.detailReturnFocus = document.activeElement;
  const overlay = bindDetailControls();
  state.detailOpen = true;
  state.detailSeq += 1;
  const seq = state.detailSeq;
  $('detail-label').textContent = '관리자 - ' + show(cur.label);
  const body = $('detail-body');
  body.textContent = '';
  body.appendChild(emptyP('불러오는 중…'));
  overlay.hidden = false;
  const close = $('detail-close');
  if (close) close.focus();
  let d;
  try {
    if (DEMO) throw new Error('데모 모드에는 관리자 기록이 없습니다');
    const res = await fetch('/api/managers/' + encodeURIComponent(cur.id) + (all ? '?all=1' : ''), { headers: { Accept: 'application/json' } });
    d = await res.json().catch(() => ({}));
    if (!res.ok || !d.ok) throw new Error(d.error || ('HTTP ' + res.status));
  } catch (err) {
    if (seq !== state.detailSeq) return;
    body.textContent = '';
    body.appendChild(emptyP('관리자 상세를 읽지 못했습니다: ' + (err && err.message ? err.message : err)));
    return;
  }
  if (seq !== state.detailSeq || !state.detailOpen) return;
  body.textContent = '';
  const s = d.session || {};
  const meta = document.createElement('div');
  meta.className = 'detail-meta';
  const st = Date.parse(String(s.started || ''));
  const la = Date.parse(String(d.last_activity || ''));
  const isRun = s.status === 'running';
  meta.appendChild(detailMetaItem('상태', isRun ? '실행 중' : show(s.status)));
  meta.appendChild(detailMetaItem('시작', fmtDateTime(s.started)));
  meta.appendChild(detailMetaItem(isRun ? '경과' : '소요', Number.isFinite(st) ? fmtElapsed(((isRun ? Date.now() : (Number.isFinite(la) ? la : Date.now())) - st) / 1000) : '-'));
  meta.appendChild(detailMetaItem('마지막 활동', Number.isFinite(la) ? fmtDateTime(d.last_activity) + ` (${fmtElapsed((Date.now() - la) / 1000)} 전)` : '-'));
  meta.appendChild(detailMetaItem('단계', show(d.steps_total)));
  meta.appendChild(detailMetaItem('대화 기록', d.record_kb != null ? (d.record_kb >= 1024 ? (d.record_kb / 1024).toFixed(1) + 'MB' : d.record_kb + 'KB') : '-'));
  body.appendChild(meta);

  if (d.relay) {
    const r = d.relay;
    detailRows(body, `라운드 R${r.round} 전달 (${show(r.state)}${r.nudged ? ', 재촉 1회' : ''})`,
      [{ head: '브리프', body: show(r.brief) }].concat((r.log || []).map((l) => ({ body: l }))));
  }
  const steps = (d.steps || []).slice().reverse();
  const stepSec = detailRows(body, (all ? `전체 단계 ${steps.length}개` : `최근 단계 ${steps.length}개`) + ` (최신이 위, 전체 ${show(d.steps_total)}) - 명령 출력은 싣지 않습니다`,
    steps.map((x) => (x.kind === 'tool'
      ? { cls: 'is-tool', head: x.desc || '명령', body: x.text }
      : { cls: 'is-text', head: '관리자', body: x.text, md: true })));
  if (!all && Number(d.steps_total) > steps.length) {
    stepSec.appendChild(linkButton(`전체 ${show(d.steps_total)}단계·기록 전부 보기`, () => openManagerDetail(cur, true)));
  }
  detailRows(body, '이 라운드의 그래프', (d.graphs || []).map((g) => ({
    head: show(g.id) + ' · ' + fmtGraphPct(g.percent),
    body: plainText(g.request) + ' - ' + Object.entries(g.counts || {}).map(([k, v]) => `${k} ${v}`).join(', '),
  })));
  detailRows(body, all ? '이 라운드의 기록 전부 (aimem.db events, 최신이 위)' : '이 라운드의 기록 (aimem.db events, 최신이 위, 최근 30건)', (d.events || []).map((e) => ({
    head: `${fmtDateTime(e.at)} · ${show(e.kind)} · REV ${show(e.rev)}`,
    body: show(e.actor) + ': ' + show(e.body), md: true,
  })));
}

function renderManager(data) {
  const box = $('manager-card');
  if (!box) return;
  box.textContent = '';
  const m = data.managers || {};
  const sessions = Array.isArray(m.sessions) ? m.sessions : [];
  const head = document.createElement('div');
  head.className = 'manager-head';
  const title = document.createElement('span');
  title.className = 'manager-title';
  title.textContent = '관리자';
  head.appendChild(title);

  const cur = sessions.find((s) => s.status === 'running') || sessions[0];
  if (m.pending && !sessions.length) {
    head.appendChild(badge('조회 중', 'pending'));
    box.appendChild(head);
    return;
  }
  if (!cur) {
    head.appendChild(badge('없음', 'neutral'));
    const p = document.createElement('span');
    p.className = 'manager-what';
    p.textContent = m.error ? '세션 조회 실패: ' + m.error : '관리자 세션 기록 없음';
    head.appendChild(p);
    box.appendChild(head);
    return;
  }
  const isRun = cur.status === 'running';
  head.appendChild(isRun ? badge('실행 중', 'running') : badge(cur.status === 'done' ? '끝남' : show(cur.status), cur.status === 'failed' ? 'blocked' : 'neutral'));
  const label = document.createElement('span');
  label.className = 'manager-label';
  label.textContent = show(cur.label);
  head.appendChild(label);
  box.appendChild(head);

  const detailBtn = document.createElement('button');
  detailBtn.type = 'button';
  detailBtn.className = 'manager-detail-btn';
  detailBtn.textContent = '상세 보기';
  detailBtn.addEventListener('click', () => openManagerDetail(cur));
  head.appendChild(detailBtn);

  const what = document.createElement('div');
  what.className = 'manager-what';
  const relay = (data.fleet || {}).relay;
  if (!isRun && relay && ['launching', 'relaying'].includes(relay.state)) {
    what.textContent = `라운드 R${relay.round} 전달 중 - 클로가 관리자를 띄우는 중입니다` + (relay.nudged ? ' (재촉 1회)' : '');
  } else {
    what.textContent = isRun ? managerActivity(data) : '실행 중인 관리자 없음 - 함대는 다음 라운드 대기(정지) 상태입니다';
  }
  box.appendChild(what);

  if (isRun) {
    const act = document.createElement('div');
    act.className = 'manager-step';
    const la = Date.parse(String(cur.last_activity || ''));
    const idle = Number.isFinite(la) ? (Date.now() - la) / 1000 : null;
    const parts = [];
    if (idle !== null) parts.push('마지막 활동 ' + fmtElapsed(idle) + ' 전');
    if (cur.steps) parts.push(`${cur.steps}단계`);
    if (cur.last_step) parts.push('최근: ' + cur.last_step);
    act.textContent = parts.join(' · ');
    if (idle !== null && idle > MANAGER_IDLE_WARN_SEC) {
      act.classList.add('is-warn');
      act.title = '관리자 기록이 오래 바뀌지 않았습니다. 긴 작업자 대기(fleet_graph run)일 수도, 멈춘 것일 수도 있습니다 - 상세 보기로 확인';
    }
    box.appendChild(act);
  }

  const meta = document.createElement('div');
  meta.className = 'manager-meta';
  const st = Date.parse(String(cur.started || ''));
  const up = Date.parse(String(cur.updated || ''));
  const parts = ['시작 ' + fmtDateTime(cur.started)];
  if (Number.isFinite(st)) {
    const end = isRun ? Date.now() : (Number.isFinite(up) ? up : Date.now());
    parts.push((isRun ? '경과 ' : '소요 ') + fmtElapsed((end - st) / 1000));
  }
  if (cur.record_kb !== null && cur.record_kb !== undefined) {
    parts.push('대화 기록 ' + (cur.record_kb >= 1024 ? (cur.record_kb / 1024).toFixed(1) + 'MB' : cur.record_kb + 'KB'));
  }
  const others = sessions.length - 1;
  if (others > 0) parts.push(`지난 세션 ${others}개`);
  if (m.error) parts.push('갱신 실패(지난 값)');
  meta.textContent = parts.join(' · ');
  meta.title = sessions.map((s) => `${s.label} - ${s.status} - ${fmtDateTime(s.started)}`).join('\n');
  if (sessions.length > 1) {
    meta.appendChild(document.createTextNode(' · '));
    meta.appendChild(linkButton('세션 목록', () => openManagerList(sessions)));
  }
  box.appendChild(meta);
}

function latestBySlot(data) {
  const map = new Map();
  for (const r of (Array.isArray(data.runs) ? data.runs : [])) {
    if (r && r.slot) {
      const prev = map.get(r.slot);
      if (!prev || String(r.started || '') > String(prev.started || '')) map.set(r.slot, r);
    }
  }
  return map;
}

function runningBySlot(data) {
  const map = new Map();
  for (const r of (Array.isArray(data.runs) ? data.runs : [])) {
    if (r && r.state === 'running' && r.slot) {
      const prev = map.get(r.slot);
      if (!prev || String(r.started || '') > String(prev.started || '')) map.set(r.slot, r);
    }
  }
  return map;
}

function renderSlots(data) {
  const wrap = $('slots-table-wrap');
  wrap.textContent = '';
  const slots = Array.isArray(data.slots) ? data.slots : [];
  if (!slots.length) {
    wrap.appendChild(emptyP('슬롯 명부 없음'));
    return;
  }
  const running = runningBySlot(data);
  const latest = latestBySlot(data);
  const runIds = [];
  const rows = slots.map((s) => {
    const modelCell = document.createElement('div');
    modelCell.className = 'model-cell';
    const modelName = document.createElement('div');
    modelName.className = 'model-name';
    modelName.textContent = show(s.model);
    modelCell.appendChild(modelName);
    if (s.model_source) {
      const source = document.createElement('div');
      source.className = 'model-source';
      source.textContent = s.model_source;
      source.title = s.model_source;
      modelCell.appendChild(source);
    }
    const r = running.get(s.slot);
    const last = latest.get(s.slot);
    runIds.push(r ? r.id : (last ? last.id : null));   // 대기 중이면 마지막 실행 상세로
    const now = document.createElement('div');
    now.className = 'slot-state';
    now.appendChild(r ? badge('실행 중', 'running') : badge('대기', 'idle'));
    if (r) {
      const sub = document.createElement('span');
      sub.className = 'sub';
      sub.textContent = show(r.label) + ' · ' + fmtElapsed(r.elapsed_sec);
      sub.title = show(r.label, '');
      now.appendChild(sub);
    }
    return [mono(s.slot), now, show(s.harness), modelCell, show(s.role), plainText(s.note) || '-'];
  });
  const rowClasses = runIds.map((id) => (id ? 'row-running' : ''));
  wrap.appendChild(newTable(['슬롯', '지금', '하네스', '모델', '역할', '비고'], rows, rowClasses, {
    widths: ['64px', '230px', '100px', '250px', '180px', null],
    ellipsis: [3, 4, 5],
    rowRunIds: runIds,
  }));
}

const RUNS_PAGE = 20;

function renderRuns(data) {
  const wrap = $('runs-table-wrap');
  const more = $('runs-more');
  wrap.textContent = '';
  if (more) more.textContent = '';
  const all = Array.isArray(data.runs) ? data.runs.slice() : [];
  all.sort((a, b) => {
    const byStart = String(b.started || '').localeCompare(String(a.started || ''));
    if (byStart !== 0) return byStart;
    return String(b.id || '').localeCompare(String(a.id || ''));
  });
  if (!all.length) {
    wrap.appendChild(emptyP('실행 기록 없음'));
    return;
  }
  const runs = state.runsShowAll ? all : all.slice(0, RUNS_PAGE);
  const rowClasses = runs.map((r) => {
    if (r.state === 'running') return 'row-running';
    if (r.state === 'lost') return 'row-lost';
    return '';
  });
  const rows = runs.map((r) => {
    const rc = document.createElement('span');
    rc.textContent = (r.rc === null || r.rc === undefined) ? '-' : String(r.rc);
    if (r.rc !== null && r.rc !== undefined && Number(r.rc) !== 0) rc.className = 'warn-text';
    const head = document.createElement('span');
    head.className = 'report-head';
    head.textContent = plainText(r.report_head) || '-';
    head.title = show(r.report_head, '');
    return [
      mono(r.slot),
      mono(r.id),
      show(r.label),
      statusBadge(r.state),
      reportBadge(r.report_head),
      rc,
      fmtElapsed(r.elapsed_sec),
      head,
    ];
  });
  wrap.appendChild(newTable(['슬롯', 'run id', '라벨', '상태', '보고', 'rc', '경과', '보고 머리말'], rows, rowClasses, {
    widths: ['52px', '196px', '230px', '80px', '108px', '40px', '92px', null],
    num: [5, 6],
    center: [3, 4],
    ellipsis: [2, 7],
    rowRunIds: runs.map((r) => r.id),
  }));
  if (more && all.length > RUNS_PAGE) {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'btn-link';
    btn.textContent = state.runsShowAll
      ? `최근 ${RUNS_PAGE}건만 보기`
      : `이전 실행 ${all.length - RUNS_PAGE}건 더 보기 (전체 ${all.length}건)`;
    btn.addEventListener('click', () => {
      state.runsShowAll = !state.runsShowAll;
      if (state.data) renderRuns(state.data);
    });
    more.appendChild(btn);
  }
}

function resolveBoardRunId(taskId, data) {
  const requests = data && Array.isArray(data.requests) ? data.requests : [];
  for (const req of requests) {
    const subtasks = req && Array.isArray(req.subtasks) ? req.subtasks : [];
    for (const st of subtasks) {
      if (st && st.id === taskId && st.run_id) return st.run_id;
    }
  }
  const runs = data && Array.isArray(data.runs) ? data.runs : [];
  const prefix = String(taskId) + '-';
  let best = null;
  for (const r of runs) {
    if (!r || r.id === null || r.id === undefined) continue;
    if (String(r.id).indexOf(prefix) !== 0) continue;
    if (best === null || String(r.started || '') > String(best.started || '')) best = r;
  }
  return best ? best.id : null;
}

const BOARD_FILTERS = [
  { key: 'open', label: '미완료', test: (b) => !['DONE', 'REJECTED'].includes(String(b.status || '').toUpperCase()) },
  { key: 'done', label: '완료', test: (b) => String(b.status || '').toUpperCase() === 'DONE' },
  { key: 'all', label: '전체', test: () => true },
];

function renderBoard(data) {
  const wrap = $('board-table-wrap');
  const filterBox = $('board-filter');
  wrap.textContent = '';
  const all = Array.isArray(data.board) ? data.board : [];
  if (filterBox) {
    filterBox.textContent = '';
    for (const f of BOARD_FILTERS) {
      const chip = document.createElement('button');
      chip.type = 'button';
      chip.className = 'chip';
      chip.setAttribute('aria-pressed', String(state.boardFilter === f.key));
      chip.textContent = `${f.label} ${all.filter(f.test).length}`;
      chip.addEventListener('click', () => {
        state.boardFilter = f.key;
        if (state.data) renderBoard(state.data);
      });
      filterBox.appendChild(chip);
    }
  }
  const filter = BOARD_FILTERS.find((f) => f.key === state.boardFilter) || BOARD_FILTERS[0];
  const board = all.filter(filter.test).slice().reverse();   // 최신 태스크가 위
  if (!board.length) {
    wrap.appendChild(emptyP(all.length ? '이 필터에 해당하는 작업 없음' : '보드 없음'));
    return;
  }
  const runIndex = new Map((Array.isArray(data.runs) ? data.runs : []).map((r) => [r.id, r]));
  const rowRunIds = board.map((b) => resolveBoardRunId(b.id, data));
  const rows = board.map((b, i) => {
    const run = rowRunIds[i] ? runIndex.get(rowRunIds[i]) : null;
    const last = document.createElement('div');
    last.className = 'slot-state';
    if (!run) {
      last.textContent = '-';
    } else {
      const line = document.createElement('span');
      line.className = 'run-line';
      line.appendChild(statusBadge(run.state));
      line.appendChild(document.createTextNode(' '));
      line.appendChild(reportBadge(run.report_head));
      last.appendChild(line);
      const sub = document.createElement('span');
      sub.className = 'sub';
      sub.textContent = fmtDateTime(run.started).slice(5) + ' · ' + fmtElapsed(run.elapsed_sec);
      last.appendChild(sub);
    }
    return [
      mono(b.id),
      plainText(b.task) || '-',
      show(b.slot),
      statusBadge(b.status),
      last,
      plainText(b.artifact) || '-',
    ];
  });
  const table = newTable(['ID', '작업', '슬롯', '보드 상태', '최근 실행', '산출물'], rows, null, {
    widths: ['76px', '380px', '76px', '100px', '170px', null],
    center: [3],
    ellipsis: [1, 5],
    rowOpen: board.map((b) => ({ fn: () => openTaskDetail(b.id, state.data), title: '태스크 상세 보기: ' + show(b.id, '') })),
  });
  wrap.appendChild(table);
}

function renderQueue(data) {
  const wrap = $('queue-table-wrap');
  wrap.textContent = '';
  const queue = Array.isArray(data.queue) ? data.queue : [];
  if (!queue.length) {
    wrap.appendChild(emptyP('대기 큐 없음'));
    return;
  }
  const rows = queue.map((q) => [
    show(q.order),
    plainText(q.task) || '-',
    show(q.slots),
    show(q.handoff),
    plainText(q.note) || '-',
  ]);
  wrap.appendChild(newTable(['순서', '작업', '슬롯', '핸드오프', '비고'], rows, null, {
    widths: ['56px', '420px', '96px', '96px', null],
    num: [0],
    ellipsis: [1, 4],
    rowOpen: queue.map((q) => ({ fn: () => openQueueDetail(q, state.data), title: '큐 항목 전문 보기' })),
  }));
}

function kistiItem(label, value) {
  const span = document.createElement('span');
  span.className = 'kisti-item';
  const lab = document.createElement('span');
  lab.className = 'kisti-label';
  lab.textContent = label + ': ';
  const val = document.createElement('span');
  val.className = 'kisti-value';
  val.textContent = show(value);
  span.appendChild(lab);
  span.appendChild(val);
  return span;
}

function renderKisti(data) {
  const box = $('kisti-card');
  box.textContent = '';
  const k = data && data.kisti ? data.kisti : null;
  if (!k) {
    box.appendChild(emptyP('KISTI 상태 없음'));
    return;
  }
  const ok = k.ok !== false;
  const pending = k.pending === true;
  const line = document.createElement('div');
  line.className = 'kisti-line';

  if (!ok) line.appendChild(badge('오류', 'error'));
  else if (pending) line.appendChild(badge('조회 중', 'pending'));
  else if (k.busy === true) line.appendChild(badge('바쁨', 'busy'));
  else line.appendChild(badge('대기', 'idle'));
  if (k.stale === true) line.appendChild(badge('지난 값', 'stale'));

  line.appendChild(kistiItem('대기열', pending ? '-' : show(k.queued)));
  line.appendChild(kistiItem('단계', pending ? '-' : show(k.phase)));
  line.appendChild(kistiItem('프롬프트', (pending ? '-' : show(k.prompt_tokens)) + ' 토큰'));
  line.appendChild(
    kistiItem('생성', (pending ? '-' : show(k.generated)) + '/' + (pending ? '-' : show(k.max_tokens)))
  );
  if (k.age_sec !== null && k.age_sec !== undefined) {
    const age = document.createElement('span');
    age.className = 'kisti-age';
    age.textContent = show(k.age_sec) + (k.stale === true ? '초 전 값' : '초 전 읽음');
    line.appendChild(age);
  }
  box.appendChild(line);

  if (!ok) {
    const err = document.createElement('div');
    err.className = 'kisti-error';
    err.textContent = show(k.error, '상태 조회 실패');
    box.appendChild(err);
  } else if (k.busy === true || Number(k.queued) > 0) {
    const warn = document.createElement('div');
    warn.className = 'kisti-warn';
    warn.textContent = 'kistillm 이 바쁩니다 - 대기열이 아니라 긴 프롬프트를 읽는 중일 수 있습니다 (AIMEM 8.0-3)';
    box.appendChild(warn);
  }
}

function fmtGraphPct(value) {
  if (value === null || value === undefined) return '-';
  return fmtPct(value);
}

function fmtGraphEta(value) {
  if (value === null || value === undefined || value === '') return '-';
  return show(value) + 's';
}

function graphFinished(g) {
  const nodes = Array.isArray(g.nodes) ? g.nodes : [];
  if (!nodes.length) return Number(g.percent) >= 100;
  return nodes.every((n) => ['done', 'failed', 'blocked', 'skipped'].includes(String(n.status || '').toLowerCase()));
}

function foldButton(open, label, onToggle) {
  const btn = document.createElement('button');
  btn.type = 'button';
  btn.className = 'fold-btn';
  btn.setAttribute('aria-expanded', String(open));
  btn.setAttribute('aria-label', (open ? '접기: ' : '펼치기: ') + label);
  btn.textContent = open ? '▾' : '▸';
  btn.addEventListener('click', onToggle);
  return btn;
}

const GRAPH_STALE_SEC = 2 * 3600;

function graphStale(g) {
  const t = Date.parse(String(g.updated || g.created || ''));
  return Number.isFinite(t) && (Date.now() - t) / 1000 > GRAPH_STALE_SEC;
}

function graphStateBadge(g, finished) {
  const counts = g.counts || {};
  if (finished) {
    return (counts.failed || counts.blocked) ? badge('부분 완료', 'partial') : badge('완료', 'done');
  }
  const t = Date.parse(String(g.updated || g.created || ''));
  if (Number.isFinite(t) && (Date.now() - t) / 1000 > GRAPH_STALE_SEC) {
    const span = badge('멈춤', 'stale');
    span.title = '진행 중으로 남아 있지만 ' + fmtElapsed((Date.now() - t) / 1000) + ' 동안 갱신이 없습니다 (실행자가 끝난 그래프)';
    return span;
  }
  return badge('진행 중', 'running');
}

function graphBlock(g) {
  const key = show(g.id, '');
  const finished = graphFinished(g);
  if (!state.graphKnown.has(key)) {
    state.graphKnown.add(key);
    if (!finished && !graphStale(g)) state.graphOpen.add(key);   // 진행 중인 그래프만 펼친 채로 시작
  }
  const open = state.graphOpen.has(key);

  const block = document.createElement('div');
  block.className = 'graph-block' + (open ? '' : ' is-folded');

  const head = document.createElement('div');
  head.className = 'graph-head';
  head.appendChild(foldButton(open, key, () => {
    if (state.graphOpen.has(key)) state.graphOpen.delete(key);
    else state.graphOpen.add(key);
    if (state.data) renderGraphs(state.data);
  }));
  const id = document.createElement('span');
  id.className = 'graph-id';
  id.textContent = key || '-';
  head.appendChild(id);
  const req = document.createElement('span');
  req.className = 'graph-title elide';
  req.textContent = plainText(g.request) || '-';
  req.title = show(g.request, '');
  head.appendChild(req);
  const pct = document.createElement('span');
  pct.className = 'graph-meta';
  pct.textContent = fmtGraphPct(g.percent) + (finished ? '' : ' · ETA ' + fmtGraphEta(g.eta_seconds));
  head.appendChild(pct);
  head.appendChild(graphStateBadge(g, finished));
  block.appendChild(head);

  const counts = g.counts || {};
  const meta = document.createElement('div');
  meta.className = 'graph-counts';
  const parts = [];
  for (const [k, label] of [['done', '완료'], ['running', '진행'], ['todo', '대기'], ['failed', '실패'], ['blocked', '막힘']]) {
    if (counts[k]) parts.push(`${label} ${counts[k]}`);
  }
  if (g.updated) parts.push('갱신 ' + fmtDateTime(g.updated));
  if (!finished && g.eta_at) parts.push('도착 예상 ' + fmtDateTime(g.eta_at));
  meta.textContent = parts.join(' · ') || '-';
  block.appendChild(meta);

  if (open) {
    const nodes = Array.isArray(g.nodes) ? g.nodes : [];
    if (!nodes.length) {
      block.appendChild(emptyP('그래프 노드 없음'));
    } else {
      const rows = nodes.map((n) => [
        mono(n.id),
        plainText(n.title) || '-',
        show(n.slot),
        statusBadge(n.status),
        Array.isArray(n.deps) && n.deps.length ? n.deps.join(', ') : '-',
        show(n.attempts) + '/' + show(n.max_attempts),
        mono(n.last_run),
      ]);
      const runIds = nodes.map((n) => n.last_run || null);
      const openers = nodes.map((n) => (taskKnown(n.id, state.data)
        ? { fn: () => openTaskDetail(n.id, state.data), title: '태스크 상세 보기: ' + show(n.id, '') } : null));
      const tw = document.createElement('div');
      tw.className = 'tablewrap';
      const table = newTable(['노드', '제목', '슬롯', '상태', '의존', '시도', '마지막 실행'], rows, null, {
        widths: ['76px', '360px', '64px', '90px', '130px', '60px', null],
        num: [5],
        center: [3],
        ellipsis: [1, 4, 6],
        rowRunIds: runIds,
        rowOpen: openers,
      });
      markUnopenableRows(table, runIds.map((id, i) => id || (openers[i] ? 'task' : null)));
      tw.appendChild(table);
      block.appendChild(tw);
    }
  }
  return block;
}

function renderGraphs(data) {
  const list = $('graphs-list');
  list.textContent = '';
  const graphs = (Array.isArray(data.graphs) ? data.graphs.slice() : [])
    .sort((a, b) => String(b.updated || b.created || '').localeCompare(String(a.updated || a.created || '')));
  if (!graphs.length) {
    list.appendChild(emptyP('태스크 그래프가 없습니다'));
    return;
  }
  for (const g of graphs) list.appendChild(graphBlock(g));
}

function progressOf(req) {
  if (req.progress_pct !== null && req.progress_pct !== undefined && Number.isFinite(Number(req.progress_pct))) {
    return Number(req.progress_pct);
  }
  const subs = Array.isArray(req.subtasks) ? req.subtasks : [];
  if (!subs.length) return null;
  let sum = 0;
  for (const s of subs) {
    const raw = show(s.status, '');
    sum += WEIGHTS[raw] ?? WEIGHTS[raw.toUpperCase()] ?? 0;
  }
  return (sum / subs.length) * 100;
}

function etaText(req) {
  const parts = [];
  if (req.eta_at) parts.push(fmtDateTime(req.eta_at));
  if (req.eta_sec !== null && req.eta_sec !== undefined && req.eta_sec !== '') {
    parts.push(fmtElapsed(req.eta_sec));
  }
  return parts.length ? parts.join(' · ') : '-';
}

const REQ_CLOSED = new Set(['DONE', 'REJECTED']);

function canEditRequest(req) {
  return String(req.status || '').toUpperCase() === 'NEW'
    && !(Array.isArray(req.subtasks) && req.subtasks.length);
}

async function saveRequestEdit(req, form) {
  const msg = form.querySelector('.form-msg');
  const title = form.querySelector('input').value.trim();
  const detail = form.querySelector('textarea').value;
  if (!title) { msg.textContent = '제목은 비워 둘 수 없습니다'; msg.className = 'form-msg error'; return; }
  const buttons = form.querySelectorAll('button');
  buttons.forEach((b) => { b.disabled = true; });
  msg.textContent = '저장 중…'; msg.className = 'form-msg';
  try {
    if (DEMO) {
      req.title = title; req.detail = detail;
    } else {
      const res = await fetch('/api/requests/' + encodeURIComponent(req.id) + '/edit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify({ title, detail }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok || !body.ok) throw new Error(body.error || ('HTTP ' + res.status));
    }
    state.editing = null;
    await refresh();
  } catch (err) {
    msg.textContent = '저장 실패: ' + (err && err.message ? err.message : String(err));
    msg.className = 'form-msg error';
    buttons.forEach((b) => { b.disabled = false; });
  }
}

function requestEditForm(req) {
  const form = document.createElement('form');
  form.className = 'req-edit';
  form.autocomplete = 'off';
  const tl = document.createElement('label');
  tl.textContent = '제목';
  const ti = document.createElement('input');
  ti.type = 'text'; ti.required = true; ti.value = show(req.title, '');
  const dl = document.createElement('label');
  dl.textContent = '본문';
  const ta = document.createElement('textarea');
  ta.rows = 8; ta.value = show(req.detail, '');
  const row = document.createElement('div');
  row.className = 'form-row';
  const save = document.createElement('button');
  save.type = 'submit'; save.className = 'btn-primary'; save.textContent = '저장';
  const cancel = document.createElement('button');
  cancel.type = 'button'; cancel.textContent = '취소';
  cancel.addEventListener('click', () => { state.editing = null; if (state.data) renderRequests(state.data); });
  const msg = document.createElement('span');
  msg.className = 'form-msg'; msg.setAttribute('role', 'status');
  row.append(save, cancel, msg);
  form.append(tl, ti, dl, ta, row);
  form.addEventListener('submit', (e) => { e.preventDefault(); saveRequestEdit(req, form); });
  if (req.detail_truncated === true) {
    // 목록의 본문은 600자로 잘려 있다 - 잘린 채 저장하면 뒷부분이 사라지므로 전문을 받아 온 뒤에만 저장을 연다
    ta.disabled = true; save.disabled = true;
    msg.textContent = '전문을 불러오는 중…';
    fetchRequestFull(req).then((full) => {
      ti.value = show(full.title, ''); ta.value = show(full.detail, '');
      ta.disabled = false; save.disabled = false; msg.textContent = '';
    }).catch((err) => {
      msg.textContent = '전문을 불러오지 못해 수정할 수 없습니다: ' + (err && err.message ? err.message : err);
      msg.className = 'form-msg error';
    });
  }
  return form;
}

function renderRequests(data) {
  const list = $('requests-list');
  // 편집 중에는 5초 폴링이 폼을 지우지 않게 다시 그리지 않는다
  if (state.editing && list.querySelector('.req-edit')) return;
  list.textContent = '';
  const requests = Array.isArray(data.requests) ? data.requests : [];
  if (!requests.length) {
    list.appendChild(emptyP('작업 요청 없음'));
    return;
  }
  const runs = new Map();
  for (const r of (Array.isArray(data.runs) ? data.runs : [])) {
    runs.set(r.id, r);
  }

  const ordered = requests.slice().sort((a, b) => {
    const ca = REQ_CLOSED.has(String(a.status || '').toUpperCase()) ? 1 : 0;
    const cb = REQ_CLOSED.has(String(b.status || '').toUpperCase()) ? 1 : 0;
    if (ca !== cb) return ca - cb;
    return String(b.created || '').localeCompare(String(a.created || ''));
  });
  ordered.forEach((req, index) => {
    const key = show(req.id, '') || ('request-' + index);
    if (!state.known.has(key)) {
      state.known.add(key);
      if (!REQ_CLOSED.has(String(req.status || '').toUpperCase())) state.expanded.add(key);   // 끝난 요청은 접힌 채 시작
    }
    const open = state.expanded.has(key);

    const article = document.createElement('article');
    article.className = 'req-block';

    const top = document.createElement('div');
    top.className = 'req-top';

    const toggle = document.createElement('button');
    toggle.type = 'button';
    toggle.className = 'req-toggle fold-btn';
    toggle.setAttribute('aria-expanded', String(open));
    toggle.textContent = open ? '▾' : '▸';
    toggle.addEventListener('click', () => {
      if (state.expanded.has(key)) state.expanded.delete(key);
      else state.expanded.add(key);
      if (state.data) renderRequests(state.data);
    });

    const titleWrap = document.createElement('div');
    titleWrap.className = 'req-title-wrap';
    const h3 = document.createElement('h3');
    h3.textContent = show(req.title, '(제목 없음)');
    titleWrap.appendChild(h3);
    const metaLine = document.createElement('div');
    metaLine.className = 'req-meta';
    metaLine.textContent = `요청 ${fmtDateTime(req.created)} · 요청자 ${show(req.requester)}`;
    titleWrap.appendChild(metaLine);
    if (state.editing === key) {
      titleWrap.appendChild(requestEditForm(req));
    } else if (req.detail && open) {
      const detail = document.createElement('div');
      detail.className = 'req-detail req-preview';
      detail.appendChild(renderMarkdown(show(req.detail, '')));   // 카드에서도 마크다운으로 (HTML 비해석, 줄바꿈 보존)
      // 높이로 접어 두고(약 5줄), 실제로 잘렸는지(scrollHeight)나 서버가 잘랐는지(detail_truncated)로 '전체 보기' 를 켠다
      detail.classList.add('is-clamped');
      detail.addEventListener('click', () => openRequestDetail(req));
      detail.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); openRequestDetail(req); }
      });
      titleWrap.appendChild(detail);
      const fullLabel = requestFullViewLabel(req) || '전체 보기';
      if (fullLabel !== null) {
        const full = document.createElement('button');
        full.type = 'button';
        full.className = 'req-full';
        const markLong = () => {
          // 요청 트리 탭이 숨겨져 있으면(다른 탭에서 렌더) 높이가 0 으로 재어져 접기가 풀렸다(2026-11-10 실측).
          // 그때는 본문 길이로 판단하고, 보이는 상태에서만 실제 높이로 판단한다.
          const hidden = detail.clientHeight === 0;
          const text = show(req.detail, '');
          const long = req.detail_truncated === true
            || (hidden ? (text.split('\n').length > 5 || text.length > 280) : detail.scrollHeight > detail.clientHeight + 2);
          full.classList.toggle('is-on', long);
          if (long) {
            detail.title = '클릭하면 전체 내용을 봅니다';
            detail.tabIndex = 0;
            detail.setAttribute('role', 'button');
          } else {
            detail.classList.remove('is-clamped');
          }
        };
        requestAnimationFrame(markLong);
        full.textContent = fullLabel;
        full.addEventListener('click', () => openRequestDetail(req));
        titleWrap.appendChild(full);
      }
    }

    const badges = document.createElement('div');
    badges.className = 'req-badges';
    badges.appendChild(statusBadge(req.status));
    if (canEditRequest(req) && state.editing !== key) {
      const edit = document.createElement('button');
      edit.type = 'button';
      edit.className = 'req-edit-btn';
      edit.textContent = '수정';
      edit.title = '관리자가 분담하기 전(NEW)에만 고칠 수 있습니다';
      edit.addEventListener('click', () => {
        state.editing = key;
        state.expanded.add(key);
        if (state.data) renderRequests(state.data);
      });
      badges.appendChild(edit);
    }

    top.appendChild(toggle);
    top.appendChild(titleWrap);
    top.appendChild(badges);
    article.appendChild(top);

    const pct = progressOf(req);
    if (!open) {
      article.classList.add('is-folded');
      const line = document.createElement('div');
      line.className = 'req-meta';
      const subs = Array.isArray(req.subtasks) ? req.subtasks.length : 0;
      line.textContent = (pct === null ? '' : fmtPct(pct) + ' · ') + '서브태스크 ' + subs + '건';
      titleWrap.appendChild(line);
      list.appendChild(article);
      return;
    }
    const progressRow = document.createElement('div');
    progressRow.className = 'req-progress';
    const bar = document.createElement('div');
    bar.className = 'bar';
    const fill = document.createElement('div');
    fill.className = 'bar-fill';
    fill.style.width = (pct === null ? 0 : Math.max(0, Math.min(100, pct))) + '%';
    bar.appendChild(fill);
    const pctLabel = document.createElement('span');
    pctLabel.className = 'pct';
    pctLabel.textContent = pct === null ? '-' : fmtPct(pct);
    const etaLabel = document.createElement('span');
    etaLabel.className = 'eta';
    const closed = REQ_CLOSED.has(String(req.status || '').toUpperCase());
    etaLabel.textContent = closed ? '종료' : 'ETA ' + etaText(req);   // 끝난 요청에 남은 시간을 내지 않는다
    progressRow.appendChild(bar);
    progressRow.appendChild(pctLabel);
    progressRow.appendChild(etaLabel);
    article.appendChild(progressRow);

    const basis = document.createElement('div');
    basis.className = 'req-basis';
    basis.textContent = 'ETA 근거: ' + show(req.eta_basis, '근거 없음');
    article.appendChild(basis);

    const body = document.createElement('div');
    body.className = 'req-body';
    body.hidden = !open;
    const subtasks = Array.isArray(req.subtasks) ? req.subtasks : [];
    if (!subtasks.length) {
      body.appendChild(emptyP('관리자 분담 대기'));
    } else {
      const subRows = subtasks.map((st) => {
        const run = st.run_id ? runs.get(st.run_id) : null;
        const link = document.createElement('div');
        link.className = 'run-link';
        if (!st.run_id) {
          link.textContent = '-';
        } else if (!run) {
          link.textContent = show(st.run_id) + ' (실행 정보 없음)';
        } else {
          const runId = document.createElement('span');
          runId.className = 'run-id';
          runId.textContent = show(run.id);
          link.appendChild(runId);
          link.appendChild(document.createTextNode(' '));
          link.appendChild(statusBadge(run.state));
          const info = document.createElement('span');
          info.className = 'run-info';
          info.textContent = ' · ' + fmtElapsed(run.elapsed_sec) +
            (run.rc !== null && run.rc !== undefined ? ' · rc ' + run.rc : '');
          link.appendChild(info);
        }
        return [
          mono(st.id),
          show(st.title),
          show(st.slot),
          show(st.harness),
          statusBadge(st.status),
          run ? fmtElapsed(run.elapsed_sec) : '-',
          link,
        ];
      });
      const subRunIds = subtasks.map((st) => st.run_id || null);
      const subTable = newTable(
        ['ID', '제목', '슬롯', '하네스', '상태', '경과', '연결된 실행'],
        subRows,
        null,
        {
          className: 'subtasks',
          widths: ['76px', '320px', '64px', '90px', '100px', '90px', null],
          num: [5],
          center: [4],
          ellipsis: [1, 6],
          rowOpen: subtasks.map((st) => ({ fn: () => openTaskDetail(st.id, state.data), title: '태스크 상세 보기: ' + show(st.id, '') })),
        },
      );
      const tw = document.createElement('div');
      tw.className = 'tablewrap';
      tw.appendChild(subTable);
      body.appendChild(tw);
    }
    article.appendChild(body);
    list.appendChild(article);
  });
}

const LOG_PAGE = 10;

function renderLog(data) {
  const wrap = $('log-table-wrap');
  const more = $('log-more');
  if (!wrap) return;
  wrap.textContent = '';
  if (more) more.textContent = '';
  const all = Array.isArray(data.log) ? data.log : [];   // reader 가 최신 먼저로 준다
  if (!all.length) {
    wrap.appendChild(emptyP('핸드오프 로그 없음'));
    return;
  }
  const log = state.logShowAll ? all : all.slice(0, LOG_PAGE);
  const rows = log.map((e) => [show(e.when), plainText(e.text) || '-']);
  wrap.appendChild(newTable(['시각', '내용'], rows, null, {
    widths: ['130px', null],
    ellipsis: [1],
    rowOpen: log.map((e) => ({ fn: () => openLogDetail(e), title: '로그 전문 보기' })),
  }));
  if (more && all.length > LOG_PAGE) {
    more.appendChild(linkButton(state.logShowAll ? `최근 ${LOG_PAGE}건만 보기` : `이전 ${all.length - LOG_PAGE}건 더 보기 (전체 ${all.length}건)`,
      () => { state.logShowAll = !state.logShowAll; if (state.data) renderLog(state.data); }));
  }
}

function renderErrors(data) {
  const box = $('errors');
  const errors = Array.isArray(data.errors) ? data.errors : [];
  if (!errors.length) {
    box.hidden = true;
    box.textContent = '';
    return;
  }
  box.hidden = false;
  box.textContent = '';
  const strong = document.createElement('strong');
  strong.textContent = '수집 오류 ' + errors.length + '건';
  box.appendChild(strong);
  const ul = document.createElement('ul');
  for (const e of errors) {
    const li = document.createElement('li');
    li.textContent = show(e);
    ul.appendChild(li);
  }
  box.appendChild(ul);
}

function setTabCount(id, n, hot) {
  const el = $(id);
  if (!el) return;
  el.textContent = n ? String(n) : '';
  el.classList.toggle('is-hot', !!hot && n > 0);
}

function renderTabCounts(data) {
  const runs = Array.isArray(data.runs) ? data.runs : [];
  const running = runs.filter((r) => r && r.state === 'running').length;
  setTabCount('tab-count-fleet', running, true);
  const queue = Array.isArray(data.queue) ? data.queue.length : 0;
  setTabCount('tab-count-board', queue, false);
  const reqs = Array.isArray(data.requests) ? data.requests : [];
  const active = reqs.filter((r) => !REQ_CLOSED.has(String(r.status || '').toUpperCase())).length;
  setTabCount('tab-count-requests', active, true);
  const f = $('tab-count-fleet');
  if (f) f.title = '실행 중인 작업자';
  const b = $('tab-count-board');
  if (b) b.title = '대기 큐 항목';
  const q = $('tab-count-requests');
  if (q) q.title = '끝나지 않은 요청';
}

function renderAll(data) {
  renderErrors(data);
  renderTabCounts(data);
  renderFleetControl(data);
  renderManager(data);
  renderMeta(data);
  renderSlots(data);
  renderKisti(data);
  renderRuns(data);
  renderBoard(data);
  renderQueue(data);
  renderLog(data);
  renderGraphs(data);
  renderRequests(data);
}

function demoState() {
  DEMO_STATE.generated = new Date().toISOString().slice(0, 19);
  return DEMO_STATE;
}

function demoCreateRequest(payload) {
  const id = 'demo-' + Date.now().toString(36);
  DEMO_STATE.requests.unshift({
    id,
    created: new Date().toISOString().slice(0, 19),
    requester: payload.requester || '데모 요청자',
    title: payload.title,
    detail: payload.detail,
    status: 'NEW',
    subtasks: [],
    progress_pct: null,
    eta_sec: null,
    eta_at: null,
    eta_basis: '데모 모드 - 서버 분담이 아직 적용되지 않았다',
  });
  return { ok: true, id, path: '.aimem/requests/' + id + '.json' };
}

async function fetchState() {
  if (DEMO) return demoState();
  const res = await fetch('/api/state', { headers: { Accept: 'application/json' } });
  if (res.status === 401) {
    // 세션 만료·토큰 교체 - 로그인 화면으로 (인증이 켜진 서버에서만 생긴다)
    location.href = '/login';
    throw new Error('로그인이 필요합니다');
  }
  if (!res.ok) {
    throw new Error(`GET /api/state ${res.status} ${res.statusText || ''}`.trim());
  }
  return res.json();
}

function updateLastRefresh() {
  const el = $('refresh-status');
  if (!el) return;
  if (state.error) {
    el.classList.add('is-error');
    el.textContent = '갱신 실패: ' + state.error;
    return;
  }
  el.classList.remove('is-error');
  if (!state.fetchedAt) {
    el.textContent = '마지막 갱신 -';
    return;
  }
  const seconds = Math.max(0, Math.floor((Date.now() - state.fetchedAt) / 1000));
  el.textContent = `마지막 갱신 ${seconds}초 전`;
}

async function refresh() {
  if (state.busy) return;
  state.busy = true;
  try {
    const data = await fetchState();
    state.data = data;
    state.fetchedAt = Date.now();
    state.error = null;
    renderAll(data);
  } catch (err) {
    state.error = err && err.message ? err.message : String(err);
  } finally {
    state.busy = false;
    updateLastRefresh();
  }
}

function schedule() {
  if (state.timer) clearInterval(state.timer);
  state.timer = null;
  if (state.autoRefresh) {
    state.timer = setInterval(refresh, 5000);
  }
}

async function onSubmit(event) {
  event.preventDefault();
  const titleEl = $('req-title');
  const detailEl = $('req-detail');
  const requesterEl = $('req-requester');
  const msg = $('form-msg');
  const button = $('request-submit');
  const title = titleEl.value.trim();
  if (!title) {
    msg.className = 'form-msg error';
    msg.textContent = '제목은 필수입니다.';
    titleEl.focus();
    return;
  }
  const payload = {
    title,
    detail: detailEl.value,
    requester: requesterEl.value.trim(),
  };
  button.disabled = true;
  msg.className = 'form-msg';
  msg.textContent = '보내는 중...';
  try {
    let result;
    if (DEMO) {
      result = demoCreateRequest(payload);
    } else {
      const res = await fetch('/api/requests', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify(payload),
      });
      let body = null;
      try {
        body = await res.json();
      } catch (err) {
        body = null;
      }
      if (!res.ok || !body || body.ok === false) {
        const reason = body && body.error
          ? body.error
          : `POST /api/requests ${res.status} ${res.statusText || ''}`.trim();
        throw new Error(reason);
      }
      result = body;
    }
    $('request-form').reset();
    msg.className = 'form-msg success';
    msg.textContent = '요청 생성됨: ' + show(result.id, '-') +
      (result.path ? ' · ' + result.path : '');
    await refresh();
  } catch (err) {
    msg.className = 'form-msg error';
    msg.textContent = err && err.message ? err.message : String(err);
  } finally {
    button.disabled = false;
  }
}

const THEME_KEY = 'aimem-theme';

function applyTheme(theme) {
  const resolved = theme === 'dark' ? 'dark' : 'light';
  document.documentElement.dataset.theme = resolved;
  const button = $('theme-toggle');
  if (button) {
    button.textContent = resolved === 'dark' ? '밝은 모드' : '어두운 모드';
    button.setAttribute('aria-pressed', String(resolved === 'dark'));
  }
}

function setTheme(theme) {
  applyTheme(theme);
  try {
    localStorage.setItem(THEME_KEY, theme);
  } catch {
  }
}

function initTheme() {
  let saved = null;
  try {
    saved = localStorage.getItem(THEME_KEY);
  } catch (err) {
    saved = null;
  }
  applyTheme(saved === 'dark' ? 'dark' : 'light');
  const button = $('theme-toggle');
  if (!button) return;
  button.addEventListener('click', () => {
    const current = document.documentElement.dataset.theme;
    setTheme(current === 'dark' ? 'light' : 'dark');
  });
}

async function initAuth() {
  if (DEMO) return;
  try {
    const res = await fetch('/api/authinfo', { headers: { Accept: 'application/json' } });
    const info = await res.json();
    if (!info || !info.auth_required) return;      // 인증이 꺼진 로컬 서버 - 표시하지 않는다
    $('auth-who').textContent = info.who ? info.who : '';
    $('auth-box').hidden = false;
    $('logout').addEventListener('click', async () => {
      try {
        await fetch('/api/logout', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
      } finally {
        location.href = '/login';
      }
    });
  } catch (err) {
    /* authinfo 를 못 읽어도 화면은 그대로 */
  }
}

function init() {
  initAuth();
  const demoBanner = $('demo-banner');
  demoBanner.hidden = !DEMO;
  initTheme();
  bindDetailControls();

  const autoRefreshBox = $('autoRefresh');
  autoRefreshBox.checked = state.autoRefresh;
  autoRefreshBox.addEventListener('change', (event) => {
    state.autoRefresh = event.target.checked;
    schedule();
    updateLastRefresh();
  });

  $('refresh-now').addEventListener('click', () => {
    refresh();
  });

  $('request-form').addEventListener('submit', onSubmit);

  setInterval(updateLastRefresh, 1000);
  schedule();
  refresh();
}

init();

// --- 탭 전환 (Q-261110-549a) ---------------------------------------------
const TABS = [
  { tab: 'tab-fleet', panel: 'panel-fleet', key: 'fleet' },
  { tab: 'tab-board', panel: 'panel-board', key: 'board' },
  { tab: 'tab-requests', panel: 'panel-requests', key: 'requests' },
];

function selectTab(key, moveFocus) {
  const found = TABS.some((t) => t.key === key);
  const target = found ? key : TABS[0].key;
  TABS.forEach((t) => {
    const on = t.key === target;
    const btn = document.getElementById(t.tab);
    const panel = document.getElementById(t.panel);
    if (btn) {
      btn.setAttribute('aria-selected', on ? 'true' : 'false');
      btn.tabIndex = on ? 0 : -1;
      if (on && moveFocus) btn.focus();
    }
    if (panel) panel.hidden = !on;      // 보이는 패널은 항상 정확히 1개
  });
  if (location.hash !== '#tab=' + target) {
    history.replaceState(null, '', '#tab=' + target);   // 기존 쿼리스트링(?demo=1)은 건드리지 않는다
  }
}

function initTabs() {
  TABS.forEach((t, i) => {
    const btn = document.getElementById(t.tab);
    if (!btn) return;
    btn.addEventListener('click', () => selectTab(t.key, false));
    btn.addEventListener('keydown', (e) => {
      let next = null;
      if (e.key === 'ArrowRight') next = TABS[(i + 1) % TABS.length].key;
      else if (e.key === 'ArrowLeft') next = TABS[(i - 1 + TABS.length) % TABS.length].key;
      else if (e.key === 'Home') next = TABS[0].key;
      else if (e.key === 'End') next = TABS[TABS.length - 1].key;
      if (next) { e.preventDefault(); selectTab(next, true); }
    });
  });
  const m = /(?:^|[#&])tab=([a-z]+)/.exec(location.hash || '');
  selectTab(m ? m[1] : TABS[0].key, false);
}

initTabs();

// 테스트(Playwright)에서 렌더러만 부를 수 있게 - 상태·데이터는 노출하지 않는다
window.__aimemMd = { renderMarkdown };
