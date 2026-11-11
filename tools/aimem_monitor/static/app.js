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
  panelCleanups: [],
  runsShowAll: false,
  logShowAll: false,
  models: null,          // GET /api/models 결과 (슬롯 편집 폼의 모델 선택지)
  slotMsg: null,
  boardFilter: 'open',
  graphOpen: new Set(),
  graphKnown: new Set(),
  showClosedRequests: false,
  showClosedGraphs: false,
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
        const full = raw instanceof Node ? raw.textContent : show(raw, '');
        td.title = full;
        // 폰에는 호버가 없어 title 을 볼 길이 없다 - 눌러서 그 자리에 펼친다 (요청 Q-261111-2e0f)
        if (full && full !== '-') {
          td.tabIndex = 0;
          td.setAttribute('role', 'button');
          td.setAttribute('aria-expanded', 'false');
          td.setAttribute('aria-label', '전문 보기: ' + full);
          const toggleFull = (event) => {
            event.preventDefault();
            event.stopPropagation();          // 행 전체의 '상세 보기' 가 같이 열리지 않게
            const open = td.classList.toggle('elide-open');
            td.setAttribute('aria-expanded', open ? 'true' : 'false');
          };
          td.addEventListener('click', toggleFull);
          td.addEventListener('keydown', (event) => {
            if (event.key === 'Enter' || event.key === ' ') toggleFull(event);
          });
        }
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

function runPanelCleanups() {
  const fns = state.panelCleanups;
  state.panelCleanups = [];
  for (const f of fns) {
    try { f(); } catch { /* 하나가 던져도 나머지는 돈다 */ }
  }
}
window.addEventListener('pagehide', runPanelCleanups);

function closeDetail() {
  runPanelCleanups();
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
  runPanelCleanups();
  state.detailReturnFocus = document.activeElement;
  const overlay = bindDetailControls();
  state.detailOpen = true;
  state.detailSeq += 1;   // 늦게 오는 /api/runs 응답이 이 내용을 덮지 못하게
  const label = $('detail-label');
  if (label) label.textContent = title;
  const body = $('detail-body');
  body.textContent = '';
  body.classList.remove('detail-app');
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
  runPanelCleanups();
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
  runPanelCleanups();
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

  const rev = document.createElement('div');
  rev.className = 'meta-stat';
  rev.textContent = show(aimem.rev);
  box.appendChild(metaItem('AIMEM REV', rev));
  box.appendChild(metaItem('최종 갱신', show(aimem.updated)));

  const fl = data.fleet || {};
  const lr = fl.last_round || null;
  const roundWrap = document.createElement('div');
  roundWrap.className = 'goal-value';
  const roundText = document.createElement('span');
  roundText.textContent = lr && lr.round
    ? 'R' + lr.round + (lr.at ? ' · ' + fmtDateTime(lr.at) : '')
    : '띄운 라운드 없음';
  roundWrap.appendChild(roundText);
  const roundStatus = document.createElement('span');
  roundStatus.className = 'goal-status';
  roundStatus.textContent = lr && lr.report_status ? '보고 ' + lr.report_status
                                                   : (fl.label || show(fl.mode, '-'));
  roundWrap.appendChild(roundStatus);
  const roundItem = metaItem('이번 라운드', roundWrap);
  roundItem.classList.add('meta-goal');
  box.appendChild(roundItem);

  const brandRev = $('brand-rev');
  if (brandRev) brandRev.textContent = aimem.rev ? 'REV ' + aimem.rev : '';
}

const MODE_BADGE = { running: 'running', paused: 'partial', stopped: 'blocked', ready: 'done' };
const FLEET_BUTTONS = [
  { act: 'prepare', label: '준비', title: '관리자·작업자를 띄울 수 있는지 점검합니다. 통과하면 준비 상태 (작업자는 띄우지 않음)' },
  { act: 'run', label: '실행', title: "멈춘 라운드를 이어 돌립니다 (일시 중지·완전 중지 뒤). 새 요청은 '라운드 실행' 으로 띄웁니다" },
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

function focusRequestForm() {
  const sec = document.getElementById('request-form-section');
  const title = document.getElementById('req-title');
  if (!sec || !title) return;
  sec.scrollIntoView({ behavior: 'smooth', block: 'start' });
  sec.classList.add('flash');
  setTimeout(() => sec.classList.remove('flash'), 1600);
  title.focus({ preventScroll: true });
}

// 이어 달리기 (REV 155) - 프로젝트 목표가 남으면 라운드가 끝난 뒤 다음 라운드를 함대가 스스로 띄운다.
// `#fleet-control` 은 5초마다 통째로 다시 그려지므로, 이 줄은 그 **바깥**에 한 번 만들고 내용이 바뀔 때만 다시 그린다 -
// 프로젝트를 고르는 중에 목록이 닫히거나 입력이 지워지지 않게.
async function chainAction(on, target, maxRounds) {
  state.chainBusy = on ? 'on' : 'off';
  state.chainMsg = null;
  if (state.data) renderFleetChain(state.data);
  try {
    let body;
    if (DEMO) {
      body = { ok: true };
    } else {
      const res = await fetch('/api/fleet/chain', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify(on
          ? { on: true, all: !!target.all, fleet: !!target.fleet, projects: target.projects || [], max_rounds: maxRounds,
            renew: !!target.renew, autonomous: !!target.auto }
          : { on: false }),
      });
      body = await res.json().catch(() => ({ ok: false, error: 'HTTP ' + res.status }));
    }
    state.chainMsg = body.ok === false ? (body.error || '바꾸지 못했습니다') : null;
  } catch (err) {
    state.chainMsg = err && err.message ? err.message : String(err);
  } finally {
    state.chainBusy = null;
    for (let i = 0; i < 50 && state.busy; i += 1) await new Promise((r) => setTimeout(r, 100));
    await refresh();
  }
}

// 대상은 셋 가운데 고른다 (2026-11-11 태석님): 전체(프로젝트+함대) · 함대 · 프로젝트(여러 개 체크).
// 아무것도 안 고르고 켜면 단추가 꺼져 있는 것이 아니라 그 자리에 이유가 나온다.
function chainTargetText(t) {
  if (t.all) return '전체(프로젝트+함대)';
  const parts = [];
  if (t.fleet) parts.push('함대');
  for (const p of t.projects || []) parts.push('프로젝트 ' + p);
  return parts.join(' + ');
}

function renderFleetChain(data) {
  const box = $('fleet-control');
  if (!box) return;
  let el = $('fleet-chain');
  if (!el) {
    el = document.createElement('div');
    el.id = 'fleet-chain';
    el.className = 'fleet-chain';
    box.after(el);
  }
  const f = (data && data.fleet) || {};
  const ch = f.chain || {};
  const names = Array.from(new Set([]
    .concat((data && Array.isArray(data.projects) ? data.projects : []).map((p) => p && p.name))
    .concat((data && Array.isArray(data.requests) ? data.requests : []).map((q) => q && q.project))
    .filter(Boolean))).sort();
  const sig = JSON.stringify([f.mode, !!ch.on, ch.label, ch.all, ch.fleet, ch.projects, ch.max_rounds, ch.autonomous, ch.renew, ch.cycles, ch.total_rounds, f.chain_modes, ch.rounds_done, ch.stopped_why, ch.stopped_kind, ch.stopped_at, names,
    !!state.chainBusy, state.chainMsg]);
  if (el.dataset.sig === sig) return;
  el.dataset.sig = sig;
  const keep = state.chainForm || { all: false, fleet: false, projects: [], max: 3 };
  el.textContent = '';
  if (!f.mode) return;
  const head = document.createElement('div');
  head.className = 'fleet-chain-line fleet-chain-head';
  const title = document.createElement('span');
  title.className = 'fleet-chain-title';
  title.textContent = '이어 달리기';
  head.appendChild(title);
  el.appendChild(head);
  if (ch.on) {
    head.appendChild(badge('켜짐', 'running'));
    const label = ch.label || chainTargetText({ all: ch.all, fleet: ch.fleet, projects: ch.projects }) || (ch.project ? '프로젝트 ' + ch.project : '전체(프로젝트+함대)');
    const what = document.createElement('span');
    what.className = 'fleet-chain-what';
    const cap = ch.max_rounds || 3;
    what.textContent = `${label} · 상한 ${cap} 라운드 · 닿으면 ${ch.autonomous ? '새로 이어 감 (완전 자율 종주)' : (ch.renew || !ch.max_rounds) ? '새로 이어 감 (끝날 때까지)' : '멈춤'}`;
    head.appendChild(what);
    const off = document.createElement('button');
    off.type = 'button';
    off.className = 'fc-btn fleet-chain-on';
    off.textContent = state.chainBusy === 'off' ? '끄는 중…' : '끄기';
    off.disabled = !!state.chainBusy;
    off.addEventListener('click', () => chainAction(false));
    head.appendChild(off);
    const t = document.createElement('div');
    t.className = 'fc-hint fleet-chain-note';
    t.textContent = ((ch.cycles ? `${ch.cycles + 1}번째 묶음 · ` : '') + `이번 묶음 ${ch.rounds_done || 0}/${cap} 라운드 끝남`
      + (ch.total_rounds ? ` (모두 ${ch.total_rounds} 라운드)` : '')
      + ' · 라운드가 끝나면 고른 대상에 열린 요청이나 체크 안 된 목표가 남았는지 보고, 새 관리자로 다음 라운드를 띄웁니다');
    el.appendChild(t);
  } else {
    // ---- 지난번에 왜 멈췄나: 다 끝낸 것인지, 상한·안전 상한인지, 막힌 것인지 종류별로 다르게 알린다 (2026-11-11 태석님)
    if (ch.stopped_why) {
      const KIND = {
        done: ['done', '다 끝냈습니다', '남은 일이 없어 스스로 멈췄습니다. 새 요청이 생기면 다시 켜면 됩니다'],
        cap: ['warn', '상한 라운드를 채워 멈췄습니다', "남은 일이 있습니다. 계속하려면 다시 켜거나, '새로 이어 달리기' 로 켜면 상한마다 새로 이어 갑니다"],
        safety: ['warn', '안전 상한(모두 30 라운드)에 닿아 멈췄습니다', '남은 일이 있습니다. 진행 상황을 한 번 확인한 뒤 다시 켜면 이어 갑니다'],
        stuck: ['bad', '진전이 없어 멈췄습니다', '한 라운드 동안 닫힌 요청도 늘어난 목표도 없었습니다. 그 라운드의 종료 보고를 보고 요청을 고치거나 나눈 뒤 다시 켜십시오'],
        report: ['bad', '관리자 보고가 DONE 이 아니어서 멈췄습니다', `그 라운드의 종료 보고(rounds/R${ch.stopped_round || '<N>'}/REPORT.md)를 확인하십시오. 고친 뒤 다시 켜면 이어 갑니다`],
        error: ['bad', '다음 라운드를 띄우지 못해 멈췄습니다', "준비 점검이나 관리자 기동에서 막혔습니다. 위의 '준비' 를 눌러 무엇이 막는지 확인하십시오"],
        wait: ['bad', '라운드가 끝나지 않아 기다리기를 그만두었습니다', '관리자 세션이 살아 있는지 확인하십시오'],
        off: ['info', '사람이 껐습니다', ''],
      };
      const [tone, head1, next] = KIND[ch.stopped_kind] || ['info', '지난번에 멈춘 이유', ''];
      const note = document.createElement('div');
      note.className = 'fleet-chain-stop is-' + tone;
      note.setAttribute('role', 'status');
      const h = document.createElement('div');
      h.className = 'fleet-chain-stop-head';
      h.textContent = head1
        + (ch.stopped_round ? ` · R${ch.stopped_round} 뒤` : '')
        + (ch.stopped_at ? ` · ${fmtDateTime(ch.stopped_at)}` : '');
      note.appendChild(h);
      const body = document.createElement('div');
      body.className = 'fleet-chain-stop-body';
      const ran = ch.total_rounds || ch.rounds_done || 0;
      body.textContent = show(ch.stopped_why) + (ran ? ` (이어 띄운 라운드 ${ran}회` + (ch.cycles ? `, 묶음 ${ch.cycles + 1}개` : '') + ')' : '');
      note.appendChild(body);
      if (next) {
        const n2 = document.createElement('div');
        n2.className = 'fleet-chain-stop-next';
        n2.textContent = next;
        note.appendChild(n2);
      }
      el.appendChild(note);
    }
    // ---- 대상: 함대 + 프로젝트들을 격자로 늘어놓고, '모두 선택 / 모두 해제' 단추 하나로 한꺼번에 켜고 끈다 (2026-11-11 태석님)
    const keepAll = !!keep.all;
    const picked = new Set(keepAll ? [''].concat(names) : (keep.fleet ? [''] : []).concat(keep.projects || []));
    const items = [{ value: '', text: '함대', tip: '프로젝트가 없는 요청 - 함대 자체의 일' }]
      .concat(names.map((n) => ({ value: n, text: n, tip: `프로젝트 ${n} 의 열린 요청과 남은 목표` })));
    const sec1 = document.createElement('div');
    sec1.className = 'fleet-chain-sec';
    const bar = document.createElement('div');
    bar.className = 'fleet-chain-bar';
    const lab1 = document.createElement('span');
    lab1.className = 'fleet-chain-lab';
    lab1.textContent = '대상';
    bar.appendChild(lab1);
    const count = document.createElement('span');
    count.className = 'fc-hint fleet-chain-count';
    bar.appendChild(count);
    const allBtn = document.createElement('button');
    allBtn.type = 'button';
    allBtn.className = 'fc-btn fleet-chain-all';
    bar.appendChild(allBtn);
    sec1.appendChild(bar);
    const grid = document.createElement('div');
    grid.className = 'fleet-chain-grid';
    grid.setAttribute('role', 'group');
    grid.setAttribute('aria-label', '이어 달릴 대상');
    const boxes = [];
    for (const it of items) {
      const lab = document.createElement('label');
      lab.className = 'fleet-chain-opt' + (it.value === '' ? ' is-fleet' : '');
      lab.title = it.tip;
      const cb = document.createElement('input');
      cb.type = 'checkbox';
      cb.checked = picked.has(it.value);
      cb.dataset.value = it.value;
      const tx = document.createElement('span');
      tx.className = 'fleet-chain-opt-text';
      tx.textContent = it.text;
      lab.appendChild(cb);
      lab.appendChild(tx);
      if (it.value !== '') {
        const kind = document.createElement('span');
        kind.className = 'fleet-chain-kind';
        kind.textContent = '프로젝트';
        lab.appendChild(kind);
      }
      grid.appendChild(lab);
      boxes.push(cb);
    }
    sec1.appendChild(grid);
    el.appendChild(sec1);

    // ---- 상한 라운드는 언제나 있다. 고르는 것은 "상한에 닿으면 무엇을 하느냐" 다 (2026-11-11 태석님:
    //      "끝까지 옵션도 내부적으로는 상한 라운드를 지켜야 해")
    const sec2 = document.createElement('div');
    sec2.className = 'fleet-chain-sec';
    const capLine = document.createElement('div');
    capLine.className = 'fleet-chain-bar';
    const lab2 = document.createElement('span');
    lab2.className = 'fleet-chain-lab';
    lab2.textContent = '상한';
    capLine.appendChild(lab2);
    const num = document.createElement('input');
    num.type = 'number';
    num.min = '1';
    num.max = '10';
    num.value = String(keep.max || 3);
    num.className = 'fleet-chain-max';
    num.setAttribute('aria-label', '상한 라운드');
    num.title = '한 묶음에서 이어 띄울 라운드 수 (1~10). 라운드마다 새 관리자가 뜹니다';
    capLine.appendChild(num);
    const capTxt = document.createElement('span');
    capTxt.className = 'fc-hint';
    capTxt.textContent = '라운드 (한 묶음)';
    capLine.appendChild(capTxt);
    sec2.appendChild(capLine);
    const lab3 = document.createElement('span');
    lab3.className = 'fleet-chain-lab';
    lab3.textContent = '상한에 닿으면';
    sec2.appendChild(lab3);
    const modes = document.createElement('div');
    modes.className = 'fleet-chain-modes';
    modes.setAttribute('role', 'radiogroup');
    modes.setAttribute('aria-label', '상한에 닿으면 할 일');
    const known = Array.isArray(f.chain_modes) ? f.chain_modes : [];
    const radios = {};
    const curMode = keep.mode || 'stop';
    const addMode = (key, text, sub, tip) => {
      const lab = document.createElement('label');
      lab.className = 'fleet-chain-opt fleet-chain-mode';
      lab.title = tip;
      const r = document.createElement('input');
      r.type = 'radio';
      r.name = 'fleet-chain-mode';
      r.value = key;
      r.checked = curMode === key;
      lab.appendChild(r);
      const tx = document.createElement('span');
      tx.className = 'fleet-chain-mode-text';
      const b1 = document.createElement('span');
      b1.textContent = text;
      const b2 = document.createElement('span');
      b2.className = 'fleet-chain-mode-sub';
      b2.textContent = sub;
      tx.appendChild(b1);
      tx.appendChild(b2);
      lab.appendChild(tx);
      modes.appendChild(lab);
      radios[key] = r;
    };
    addMode('stop', '멈춤', '상한만큼 돌고 끝', '상한 라운드를 채우면 멈춥니다. 남은 일이 있으면 다시 켭니다');
    addMode('renew', '새로 이어 달리기', '끝날 때까지',
      '상한을 채우면 새 묶음으로 넘어가 라운드 수를 다시 세며 이어 갑니다. 남은 일이 없을 때까지 갑니다. 보고가 DONE 이 아니거나 진전이 없으면 멈춥니다');
    if (known.includes('autonomous')) {                      // 서버가 아는 방식만 보인다
      addMode('autonomous', '완전 자율 종주', '막혀도 한 번 더',
        '새 묶음으로 이어 가며 끝까지 갑니다. 보고가 DONE 이 아니거나 진전이 없어도 한 번은 더 가 보고, 연달아 두 번 막히면 멈춥니다');
    }
    if (!Object.values(radios).some((r) => r.checked)) radios.stop.checked = true;
    sec2.appendChild(modes);
    el.appendChild(sec2);

    const on = document.createElement('button');
    on.type = 'button';
    on.className = 'fc-btn btn-primary fleet-chain-on';
    on.textContent = state.chainBusy === 'on' ? '켜는 중…' : '이어 달리기 켜기';
    on.disabled = !!state.chainBusy;

    const read = () => {
      const vals = boxes.filter((c) => c.checked).map((c) => c.dataset.value);
      const mode = (Object.values(radios).find((r) => r.checked) || radios.stop).value;
      return {
        all: boxes.length > 0 && vals.length === boxes.length,      // 다 고르면 '전체' - 나중에 생기는 프로젝트도 포함
        fleet: vals.includes(''),
        projects: vals.filter((v) => v !== ''),
        mode,
        renew: mode !== 'stop',
        auto: mode === 'autonomous',
        max: Number(num.value) || 0,
      };
    };
    const sync = () => {
      const t = read();
      const n = (t.fleet ? 1 : 0) + t.projects.length;
      count.textContent = t.all ? `전체 ${boxes.length}개 · 새 프로젝트도 포함` : `${boxes.length}개 중 ${n}개 선택`;
      allBtn.textContent = t.all ? '모두 해제' : '모두 선택';
      allBtn.setAttribute('aria-pressed', t.all ? 'true' : 'false');
      state.chainForm = t;
    };
    // 무언가 고치면 앞서 뜬 안내("하나 이상 체크하십시오")는 지운다 - 고쳤는데도 빨간 글이 남아 있으면 헷갈린다
    const clearMsg = () => {
      if (!state.chainMsg) return;
      state.chainMsg = null;
      for (const m of el.querySelectorAll('.fleet-chain-err')) m.remove();
      el.dataset.sig = '';
    };
    el.addEventListener('change', clearMsg, { once: false });
    allBtn.addEventListener('click', () => {
      const turnOn = !boxes.every((c) => c.checked);
      for (const c of boxes) c.checked = turnOn;
      clearMsg();
      sync();
    });
    for (const c of boxes) c.addEventListener('change', sync);
    for (const r of Object.values(radios)) r.addEventListener('change', sync);
    num.addEventListener('input', sync);
    const fail = (msg) => {
      state.chainMsg = msg;
      el.dataset.sig = '';
      renderFleetChain(data);
    };
    on.addEventListener('click', () => {
      sync();
      const t = state.chainForm;
      if (!t.fleet && !t.projects.length) return fail("무엇을 이어 달릴지 하나 이상 체크하십시오 - 함대나 프로젝트를 고르거나 '모두 선택' 을 누르십시오");
      if (!(t.max >= 1 && t.max <= 10)) return fail('상한 라운드는 1~10 으로 적어 주십시오');
      // 서버가 아직 '새로 이어 달리기' 를 모르면(다시 띄우기 전) 옛 방식(상한 0 = 끝날 때까지)으로 보낸다
      const rounds = (t.renew && !known.includes('renew')) ? 0 : t.max;
      const how = t.auto ? `상한 ${t.max} 라운드씩, 닿으면 새로 이어 가며 완전 자율 종주로`
        : t.renew ? `상한 ${t.max} 라운드씩, 닿으면 새로 이어 가며 끝날 때까지` : `최대 ${t.max}번까지`;
      if (!window.confirm(`${chainTargetText(t)} 에 열린 요청이나 체크 안 된 목표가 남아 있는 동안 라운드를 ${how} 이어 띄웁니다.\n`
        + '라운드마다 유료 관리자(Opus)가 한 번씩 뜹니다. '
        + (t.auto ? '보고가 DONE 이 아니거나 진전이 없어도 한 번은 더 가고, 연달아 두 번 막히면 멈춥니다. 남은 일이 없으면 끝납니다.\n'
          : '남은 일이 없거나, 보고가 DONE 이 아니거나, 한 라운드에 닫힌 요청도 늘어난 목표도 없으면 스스로 멈춥니다.\n')
        + "지금 도는 라운드가 있으면 그 라운드부터, 없으면 '라운드 실행' 을 누른 라운드부터 이어 갑니다. 켤까요?")) return undefined;
      return chainAction(true, t, rounds);
    });
    sync();
    const foot = document.createElement('div');
    foot.className = 'fleet-chain-foot';
    const hint = document.createElement('div');
    hint.className = 'fc-hint fleet-chain-note';
    hint.textContent = '꺼져 있습니다. 켜 두면 라운드가 끝났을 때 고른 대상에 열린 요청이나 체크 안 된 목표가 남아 있는 동안 다음 라운드를 스스로 띄웁니다';
    foot.appendChild(hint);
    foot.appendChild(on);
    el.appendChild(foot);
  }
  if (state.chainMsg) {
    const m = document.createElement('div');
    m.className = 'fc-hint fleet-chain-note fleet-chain-err';
    m.textContent = state.chainMsg;
    el.appendChild(m);
  }
}

function renderFleetControl(data) {
  renderFleetChain(data);
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
  if (f.idle) bits.push('도는 라운드 없음');
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
  const briefName = brief.standard ? '표준 브리프 (할 일 = 웹 NEW 요청)' : brief.file;
  rb.title = brief.file
    ? `새 관리자 라운드를 띄웁니다 (유료 Opus). 브리프: ${briefName}`
      + (can.round ? (f.idle ? ' - 준비 점검을 먼저 돌린 뒤 띄웁니다' : '') : (md === 'running' ? ' - 지금 라운드가 끝난 뒤에' : ' - 먼저 준비를 누르십시오'))
    : '확정된 다음 라운드 브리프가 없습니다' + (brief.drafts && brief.drafts.length ? ` (초안: ${brief.drafts.join(', ')})` : '');
  rb.addEventListener('click', () => {
    const reqs = (data && Array.isArray(data.requests)) ? data.requests : [];
    const nNew = reqs.filter((q) => String(q.status || '').toUpperCase() === 'NEW').length;
    const todo = brief.standard
      ? (nNew ? `할 일: 새 작업 요청 ${nNew}건` : "할 일: 새 작업 요청이 없습니다 - 관리자는 점검만 하고 끝냅니다. 시킬 일이 있으면 취소하고 '할 일 쓰기' 로 먼저 넣으십시오")
      : `브리프: ${briefName}`;
    fleetAction('round', `새 관리자 라운드 R${brief.round} 를 띄웁니다 (유료 Opus 세션).\n${todo}\n계속할까요?`);
  });
  row.appendChild(rb);
  box.appendChild(row);

  const hint = document.createElement('div');
  hint.className = 'fc-hint';
  {
    // 작업 요청 폼의 프로젝트 자동완성 - 브리프 종류와 상관없이 채운다
    const dl = document.getElementById('project-list');
    if (dl) {
      const names = (data && Array.isArray(data.projects) ? data.projects : []).map((x) => x && x.name).filter(Boolean);
      if (dl.dataset.names !== names.join('|')) {     // 바뀔 때만 다시 채운다 (입력 중 목록이 깜박이지 않게)
        dl.dataset.names = names.join('|');
        dl.replaceChildren(...names.map((n) => { const o = document.createElement('option'); o.value = n; return o; }));
      }
    }
  }
  if (brief.file && brief.standard) {
    // 라운드가 할 일 = '작업 요청' 폼으로 넣은 NEW 요청. 폼은 넓은 화면에선 오른쪽, 좁은 화면에선 맨 아래라
    // 잘 안 보인다(2026-11-10 태석님) - 여기서 바로 가는 버튼과 지금 쌓인 건수를 보인다.
    const reqs = (data && Array.isArray(data.requests)) ? data.requests : [];
    const fresh = reqs.filter((q) => String(q.status || '').toUpperCase() === 'NEW');
    const txt = document.createElement('span');
    // 라운드가 도는 중에는 '지금 도는 라운드' 를 먼저 보인다 - 다음 번호만 보여 R7 이 도는데 R8 로 읽혔다 (2026-11-10 R7 실측)
    const curRound = (md === 'running' && !f.idle && f.relay && f.relay.round) ? f.relay : null;
    if (curRound) {
      const now = document.createElement('div');
      now.className = 'fc-hint-now';
      now.textContent = `지금 R${curRound.round} 실행 중` + (curRound.workspace ? ` · 라운드 보고 ${curRound.workspace}/` : '');
      hint.appendChild(now);
    } else if (f.idle) {
      // 라운드가 끝났다 - 다음 요청은 '라운드 실행' 한 번이면 된다 (준비 점검은 그 안에서 돈다)
      const now = document.createElement('div');
      now.className = 'fc-hint-now';
      now.textContent = (f.relay && f.relay.round ? `R${f.relay.round} 은 끝났습니다` : '도는 라운드가 없습니다')
        + " - 새 요청은 '라운드 실행' 을 누르면 됩니다";
      hint.appendChild(now);
    }
    txt.textContent = `${curRound ? '다음 ' : ''}R${brief.round} 가 할 일 = 새 작업 요청 ${fresh.length}건`
      + (fresh.length ? ` (${fresh.slice(0, 3).map((q) => show(q.title)).join(' / ')}${fresh.length > 3 ? ' …' : ''})` : (curRound ? '' : ' - 요청이 없으면 관리자는 점검만 하고 끝냅니다'))
      + ' ';
    hint.appendChild(txt);
    const go = document.createElement('button');
    go.type = 'button';
    go.className = 'fc-btn fc-write';
    go.textContent = '할 일 쓰기';
    go.title = "'작업 요청' 폼으로 갑니다. 제목과 본문을 적고 '요청 보내기' 를 누른 뒤 라운드를 실행하십시오";
    go.addEventListener('click', focusRequestForm);
    hint.appendChild(go);
    // 경로는 둘째 줄로 (REV 145) - 한 문장에 건수·버튼·경로가 섞여 읽기 어려웠다
    const projs = Array.from(new Set(fresh.map((q) => q.project).filter(Boolean)));
    const where = [];
    if (projs.length) where.push(`결과물 ${projs.map((n) => `projects/${n}/`).join(', ')}`);
    if (brief.workspace && !curRound) where.push(`라운드 보고 ${brief.workspace}/`);
    if (where.length) {
      const tail = document.createElement('div');
      tail.className = 'fc-hint-where';
      tail.textContent = where.join(' · ');
      hint.appendChild(tail);
    }
  } else {
    hint.textContent = brief.file
      ? `다음 라운드 브리프: ${brief.file}` + (brief.workspace ? ` · 라운드 보고 ${brief.workspace}/` : '')
      : '다음 라운드 브리프: 확정본 없음' + (brief.drafts && brief.drafts.length ? ` (초안 ${brief.drafts.join(', ')})` : '');
  }
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
    // 5초마다 다시 그리므로 펼친 상태를 기억한다 (2026-11-10 태석님: 펼치면 새로고침에 닫혀 볼 수가 없다).
    // '준비' 를 방금 눌렀으면 결과를 보이려고 한 번 펼친다 - 그 뒤 사람이 접으면 접힌 채 둔다.
    if (state.fleetMsg && state.fleetMsg.act === 'prepare' && state.prepShownFor !== state.fleetMsg) {
      state.prepShownFor = state.fleetMsg;
      state.expanded.add('fleet-prepare');
    }
    det.open = state.expanded.has('fleet-prepare');
    det.addEventListener('toggle', () => {
      if (det.open) state.expanded.add('fleet-prepare');
      else state.expanded.delete('fleet-prepare');
    });
    const sum = document.createElement('summary');
    const failed = prep.checks.filter((c) => !c.ok);
    // 준비 점검은 누른 순간의 결과다. 오래된 결과가 '막힘' 으로 계속 떠 있으면 지금 상태로 읽힌다 (REV 145)
    const ageMin = (Date.now() - Date.parse(prep.at)) / 60000;
    const old = Number.isFinite(ageMin) && ageMin > 30;
    const ageText = !old ? '' : (ageMin < 90 ? `${Math.round(ageMin)}분 전` : (ageMin < 48 * 60 ? `${Math.round(ageMin / 60)}시간 전` : `${Math.round(ageMin / 1440)}일 전`));
    sum.textContent = (old ? '지난 준비 점검 ' : '준비 점검 ') + `${fmtDateTime(prep.at)} - ${prep.ok ? '통과' : '막힘'}`
      + (failed.length ? ` (${failed.length}건 미통과)` : '')
      + (old ? ` · ${ageText} 결과라 지금 상태가 아닙니다 - '준비' 를 누르면 다시 점검합니다` : '');
    if (old) det.classList.add('fc-prep-old');
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
  runPanelCleanups();
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
  // 끝난 관리자 세션은 게이트웨이 목록에서 사라진다 - 그러면 `sessions[0]` 은 한참 전 라운드(R6)다.
  // 라운드가 끝났고(idle) 가장 최근에 띄운 라운드가 목록의 맨 앞과 다르면, 전달 기록과 보고 파일로 그 라운드를 보인다 (REV 155).
  const fl = data.fleet || {};
  const lr = fl.last_round;
  if (fl.idle && lr && lr.state === 'spawned' && !(cur && cur.status === 'running') && !(cur && cur.label === lr.label)) {
    const st = lr.report_status;
    head.appendChild(badge(st ? '끝남 · ' + st : '끝남', st === 'DONE' ? 'done' : (st ? 'blocked' : 'neutral')));
    const label = document.createElement('span');
    label.className = 'manager-label';
    label.textContent = show(lr.label || ('관리자 R' + lr.round));
    head.appendChild(label);
    box.appendChild(head);
    const what = document.createElement('div');
    what.className = 'manager-what';
    what.textContent = (lr.report ? `종료 보고 ${lr.report}` : `R${lr.round} 종료 보고가 아직 없습니다`)
      + ` · 띄운 때 ${fmtDateTime(lr.at)} · 실행 중인 관리자 없음`;
    box.appendChild(what);
    return;
  }
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

// ---- 슬롯 관리 (2026-11-10, 태석님 지시) - 추가/변경/삭제, 모델은 openclaw 설정 목록에서
async function loadModels(force = false) {
  if (state.models && !force) return state.models;
  if (DEMO) { state.models = { ok: true, models: [] }; return state.models; }
  try {
    const res = await fetch('/api/models', { headers: { Accept: 'application/json' } });
    state.models = await res.json();
  } catch (err) {
    state.models = { ok: false, models: [], error: err && err.message ? err.message : String(err) };
  }
  return state.models;
}

async function slotRequest(url, payload) {
  const res = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json', Accept: 'application/json' }, body: JSON.stringify(payload) });
  const body = await res.json().catch(() => ({ ok: false, error: 'HTTP ' + res.status }));
  return { ok: res.ok && body.ok !== false, body };
}

function modelOptions(models, harness, current) {
  const sel = document.createElement('select');
  sel.className = 'slot-model';
  const def = document.createElement('option');
  def.value = ''; def.textContent = '(하네스 기본 모델)';
  sel.appendChild(def);
  const list = (models && Array.isArray(models.models) ? models.models : []).filter((m) => !m.harnesses || m.harnesses.includes(harness));
  if (harness === 'claude') {
    for (const alias of ['opus', 'sonnet', 'haiku']) {
      const o = document.createElement('option'); o.value = alias; o.textContent = `${alias} (Claude CLI 별칭)`; sel.appendChild(o);
    }
  }
  for (const m of list) {
    const o = document.createElement('option');
    o.value = m.key;
    o.textContent = m.key + (m.aliases && m.aliases.length ? ` (${m.aliases.join(', ')})` : '') + (m.context ? ` · ${Math.round(m.context / 1000)}k` : '');
    sel.appendChild(o);
  }
  if (current && !Array.from(sel.options).some((o) => o.value === current)) {
    const o = document.createElement('option'); o.value = current; o.textContent = current + ' (목록에 없음 - 현재 값)'; sel.appendChild(o);
  }
  sel.value = current || '';
  return sel;
}

function openSlotForm(existing) {
  const isNew = !existing;
  openPanel(isNew ? '슬롯 추가' : `슬롯 ${existing.slot} 변경`, (body) => {
    const form = document.createElement('form');
    form.className = 'slot-form';
    const field = (label, el) => {
      const w = document.createElement('label'); w.className = 'slot-field';
      const l = document.createElement('span'); l.textContent = label; w.appendChild(l); w.appendChild(el); form.appendChild(w); return el;
    };
    const slotIn = document.createElement('input'); slotIn.placeholder = '비우면 다음 번호'; slotIn.pattern = 'S\\d{1,3}';
    if (!isNew) { slotIn.value = existing.slot; slotIn.disabled = true; }
    field('슬롯 id', slotIn);
    const harnessSel = document.createElement('select');
    for (const h of ['claude', 'codex', 'opencode']) { const o = document.createElement('option'); o.value = h; o.textContent = h; harnessSel.appendChild(o); }
    harnessSel.value = existing ? existing.harness : 'claude';
    field('하네스', harnessSel);
    const modelWrap = document.createElement('div'); modelWrap.className = 'slot-model-wrap';
    const modelNote = document.createElement('div'); modelNote.className = 'hint'; modelNote.textContent = '모델 목록을 읽는 중…';
    modelWrap.appendChild(modelNote);
    field('모델 (openclaw 설정)', modelWrap);
    // 역할·비고는 라운드 관리자가 정한다(8.0-1) - 여기서는 보여만 준다
    if (!isNew) {
      const roleRo = document.createElement('div'); roleRo.className = 'slot-ro'; roleRo.textContent = show(existing.role, '-'); field('역할 (관리자 지정)', roleRo);
      const noteRo = document.createElement('div'); noteRo.className = 'slot-ro'; noteRo.textContent = show(existing.note, '-'); field('비고 (관리자 지정)', noteRo);
    }
    const gov = document.createElement('p'); gov.className = 'hint';
    gov.textContent = isNew
      ? '역할·비고는 여기서 적지 않습니다 - 새 슬롯은 "(미배정)" 으로 들어가고, 라운드 관리자가 다음 라운드 시작 때 역할을 정해 적습니다. 여기서는 어떤 엔진(하네스·모델)을 둘지만 정합니다.'
      : '여기서 바꿀 수 있는 것은 하네스·모델입니다. 역할·비고는 라운드 관리자가 브리프 의도에 따라 정합니다(aimem_db.py slot set --role/--note).';
    form.appendChild(gov);
    const actions = document.createElement('div'); actions.className = 'slot-actions';
    const save = document.createElement('button'); save.type = 'submit'; save.className = 'btn-primary'; save.textContent = isNew ? '추가' : '저장';
    const msg = document.createElement('div'); msg.className = 'slot-msg';
    actions.appendChild(save);
    if (!isNew) {
      const del = document.createElement('button'); del.type = 'button'; del.className = 'btn-danger'; del.textContent = '이 슬롯 삭제';
      del.addEventListener('click', async () => {
        if (!window.confirm(`${existing.slot} 을(를) 명부에서 지웁니다. 끝나지 않은 태스크가 있으면 거절됩니다. 계속할까요?`)) return;
        del.disabled = true;
        const r = await slotRequest(`/api/slots/${existing.slot}/remove`, {});
        if (!r.ok && /끝나지 않은 태스크/.test(r.body.error || '') && window.confirm(r.body.error + '\n\n그래도 강제로 지울까요?')) {
          const r2 = await slotRequest(`/api/slots/${existing.slot}/remove`, { force: true });
          Object.assign(r, r2);
        }
        if (r.ok) { closeDetail(); state.slotMsg = { ok: true, text: `${existing.slot} 삭제됨` + (r.body.notice ? ` · 관리자 통지 요청 ${r.body.notice} 생성` : '') }; await refresh(); }
        else { del.disabled = false; msg.textContent = r.body.error || '실패'; msg.classList.add('is-error'); }
      });
      actions.appendChild(del);
    }
    form.appendChild(actions); form.appendChild(msg);
    let modelSel = null;
    const rebuildModels = (models, keepCurrent = true) => {
      modelWrap.textContent = '';
      const cur = !keepCurrent ? '' : (modelSel ? modelSel.value : (existing ? show(existing.model_raw || existing.model, '') : ''));
      modelSel = modelOptions(models, harnessSel.value, cur);
      modelWrap.appendChild(modelSel);
      if (models && models.ok === false) { const e = document.createElement('div'); e.className = 'hint is-error'; e.textContent = '모델 목록 실패: ' + show(models.error, ''); modelWrap.appendChild(e); }
      const src = document.createElement('div'); src.className = 'hint'; src.textContent = '출처: openclaw models list (설정된 모델). claude 는 Anthropic 모델만, codex/opencode 는 그 밖.'; modelWrap.appendChild(src);
    };
    harnessSel.addEventListener('change', () => rebuildModels(state.models, false));   // 하네스가 바뀌면 모델은 다시 고른다
    loadModels().then(rebuildModels);
    form.addEventListener('submit', async (e) => {
      e.preventDefault(); save.disabled = true; msg.textContent = ''; msg.classList.remove('is-error');
      const payload = { harness: harnessSel.value, model: modelSel ? modelSel.value : '' };
      let r;
      if (isNew) { if (slotIn.value.trim()) payload.slot = slotIn.value.trim().toUpperCase(); r = await slotRequest('/api/slots', payload); }
      else r = await slotRequest(`/api/slots/${existing.slot}/set`, payload);
      if (r.ok) {
        closeDetail();
        const notice = r.body.notice ? ` · 관리자 통지 요청 ${r.body.notice} 생성` : '';
        state.slotMsg = { ok: true, text: (isNew ? `${(r.body.slot || {}).slot} 추가됨` : `${existing.slot} 저장됨` + (r.body.changes && r.body.changes.length ? ' (' + r.body.changes.join(', ') + ')' : ' - 바뀐 것 없음')) + notice };
        await refresh();
      }
      else { save.disabled = false; msg.textContent = r.body.error || '실패'; msg.classList.add('is-error'); }
    });
    body.appendChild(form);
  });
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
    const bar = document.createElement('div'); bar.className = 'slot-bar'; bar.appendChild(linkButton('+ 슬롯 추가', () => openSlotForm(null))); wrap.appendChild(bar);
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
    const manage = document.createElement('div');
    manage.className = 'slot-manage';
    const edit = linkButton('변경', () => openSlotForm(s));
    edit.title = r ? '작업자가 도는 중 - 모델·역할·비고는 바꿀 수 있고 하네스는 끝난 뒤' : '하네스·모델·역할·비고 변경, 삭제';
    manage.appendChild(edit);
    return [mono(s.slot), now, show(s.harness), modelCell, show(s.role), plainText(s.note) || '-', manage];
  });
  const rowClasses = runIds.map((id) => (id ? 'row-running' : ''));
  wrap.appendChild(newTable(['슬롯', '지금', '하네스', '모델', '역할', '비고', '관리'], rows, rowClasses, {
    className: 'slots-table',
    widths: ['52px', '160px', '92px', '230px', '170px', null, '80px'],
    ellipsis: [3, 4, 5],
    rowRunIds: runIds,
  }));
  // 관리 열의 버튼은 행 클릭(실행 상세)과 겹치지 않게
  wrap.querySelectorAll('.slot-manage button').forEach((b) => b.addEventListener('click', (e) => e.stopPropagation()));
  const bar = document.createElement('div');
  bar.className = 'slot-bar';
  bar.appendChild(linkButton('+ 슬롯 추가', () => openSlotForm(null)));
  if (state.slotMsg) {
    const m = document.createElement('span'); m.className = 'slot-msg' + (state.slotMsg.ok ? '' : ' is-error'); m.textContent = state.slotMsg.text; bar.appendChild(m);
    setTimeout(() => { if (state.slotMsg && state.slotMsg.text === m.textContent) { state.slotMsg = null; } }, 8000);
  }
  wrap.appendChild(bar);
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
    const proj = document.createElement('span');
    proj.className = r.project ? 'proj-tag' : 'proj-tag none';
    const projName = document.createElement('span');
    projName.className = 'proj-name';
    projName.textContent = r.project || '함대';
    proj.appendChild(projName);
    if (r.round) {
      const projRound = document.createElement('span');
      projRound.className = 'proj-round';
      projRound.textContent = ` · R${r.round}`;
      proj.appendChild(projRound);
    }
    proj.title = r.project
      ? `프로젝트 ${r.project} (projects/${r.project}/)` + (r.round ? ` · 라운드 R${r.round}` : '')
      : '프로젝트 없음 - 함대 자체의 일이거나 옛 기록' + (r.round ? ` · 라운드 R${r.round}` : '');
    // 라벨 아래에 run id 를 작게 (REV 145) - run id 칸이 196px 를 차지해 '보고 머리말' 이 두 글자로 줄었다.
    // 상태·보고를 앞에 둔다: 좁은 화면에서 가로로 밀지 않아도 보이게.
    const what = document.createElement('div');
    what.className = 'run-what';
    const lab = document.createElement('span');
    lab.className = 'run-label';
    lab.textContent = show(r.label);
    const rid = document.createElement('span');
    rid.className = 'sub mono';
    rid.textContent = show(r.id);
    what.append(lab, rid);
    what.title = `${show(r.label, '')}\n${show(r.id, '')}`;
    return [
      mono(r.slot),
      statusBadge(r.state),
      reportBadge(r.report_head),
      proj,
      what,
      fmtElapsed(r.elapsed_sec),
      rc,
      head,
    ];
  });
  wrap.appendChild(newTable(['슬롯', '상태', '보고', '프로젝트', '작업 · run id', '경과', 'rc', '보고 머리말'], rows, rowClasses, {
    className: 'runs-table',
    widths: ['52px', '80px', '100px', '130px', '250px', '104px', '40px', null],
    num: [5, 6],
    center: [1, 2],
    ellipsis: [3, 7],
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

// ---- 끝난 것 정리 (아카이브, 2026-11-10) - 8.0 보관·폐기를 웹에서. 미리보기(dry_run) → 확인 → 실행
async function archiveRequest(days, dryRun) {
  const res = await fetch('/api/archive', { method: 'POST', headers: { 'Content-Type': 'application/json', Accept: 'application/json' }, body: JSON.stringify({ days, dry_run: dryRun }) });
  const body = await res.json().catch(() => ({ ok: false, error: 'HTTP ' + res.status }));
  return { ok: res.ok && body.ok !== false, body };
}

function openArchivePanel() {
  openPanel('끝난 것 정리 (아카이브)', (body) => {
    // 무엇이 정리되는지 풀어서 적는다 (2026-11-11 태석님: 요청·그래프도 같이 정리되는 줄 몰랐다)
    const intro = document.createElement('div');
    intro.className = 'hint archive-intro';
    const lead = document.createElement('p');
    lead.textContent = '끝난 일을 화면에서 치웁니다. 보드의 태스크만이 아니라 요청 트리의 요청과 그래프도 함께 정리됩니다.';
    intro.appendChild(lead);
    const ul = document.createElement('ul');
    for (const [what, where] of [
      ['끝난 태스크 (DONE)', '보드에서 사라지고 archive/board-<월>.md 에 남습니다'],
      ['닫힌 작업 요청 (DONE·REJECTED)', '요청 트리에서 사라지고 archive/requests-<월>/ 로 옮겨집니다'],
      ['노드가 모두 끝난 그래프 (분담 트리)', '요청 트리의 태스크 그래프에서 사라지고, 브리프·로그·입력 파일과 함께 archive/graph-<월>/ 로 옮겨집니다'],
      ['작업자 실행 기록', '함대 탭 작업자 실행 상태에서 사라지고 archive/runs-<월>/ 로 옮겨집니다'],
      ['이벤트', '보드·큐 탭의 이벤트 목록에서 사라지고 archive/events-<월>.jsonl 로 옮겨집니다'],
      ['핸드오프 (최신 12건 제외)', 'archive/handoff-<월>.md 로 옮겨집니다 - 최신 12건은 무엇이든 남습니다'],
      ['전달 기록', '그 라운드의 그래프가 모두 정리되면 archive/relay-<월>/ 로 함께 옮겨집니다'],
      ['오래된 로그 줄', 'monitor.log·fleet-mode.log 의 기준 시각보다 오래된 줄만. 접속 기록(access.log)은 건드리지 않습니다'],
    ]) {
      const li = document.createElement('li');
      const b = document.createElement('strong');
      b.textContent = what;
      li.appendChild(b);
      li.appendChild(document.createTextNode(' - ' + where));
      ul.appendChild(li);
    }
    intro.appendChild(ul);
    const tail = document.createElement('p');
    tail.textContent = '지우는 것이 아니라 .aimem/archive/ 로 옮기는 것이라 나중에 찾아볼 수 있습니다. 아직 도는 그래프와 열린 요청은 건드리지 않고, '
      + '프로젝트 진행률에는 정리한 요청도 계속 셉니다. 먼저 미리보기로 무엇이 옮겨지는지 확인한 뒤 실행하십시오. '
      + '(관리자는 라운드를 닫을 때 14일 지난 것만 자동으로 정리합니다 - 최근에 끝난 것은 여기서 직접 정리합니다.)';
    intro.appendChild(tail);
    body.appendChild(intro);
    const row = document.createElement('div'); row.className = 'slot-actions';
    const sel = document.createElement('select');
    for (const [v, t] of [[14, '14일 지난 것 (규칙 기본)'], [7, '7일 지난 것'], [0, '지금 끝난 것 전부']]) { const o = document.createElement('option'); o.value = String(v); o.textContent = t; sel.appendChild(o); }
    const preview = linkButton('미리보기', () => run(true));
    const apply = document.createElement('button'); apply.type = 'button'; apply.className = 'btn-primary'; apply.textContent = '실행'; apply.disabled = true;
    row.appendChild(sel); row.appendChild(preview); row.appendChild(apply); body.appendChild(row);
    const out = document.createElement('div'); out.className = 'archive-out'; body.appendChild(out);
    const render = (r, dry) => {
      out.textContent = '';
      if (!r.ok) { const e = document.createElement('p'); e.className = 'hint is-error'; e.textContent = r.body.error || '실패'; out.appendChild(e); return; }
      const plan = r.body.plan || {};
      const h = document.createElement('p');
      h.textContent = (dry ? '옮길 것: ' : '옮김: ') + `태스크 ${(plan.tasks || []).length}건 · 요청 ${(plan.requests || []).length}건 · 그래프 ${(plan.graphs || []).length}개 (기준 ${fmtDateTime(plan.cutoff)})`;
      out.appendChild(h);
      const counts = dry ? plan.records : r.body.moved_counts;
      if (counts) {
        const line = document.createElement('p');
        line.className = 'hint';
        line.textContent = `실행 기록 ${counts.runs || 0}건 · 이벤트 ${counts.events || 0}건 · 핸드오프 ${counts.handoff || 0}건 · 전달 ${counts.relay || 0}개 · 로그 ${counts.log_lines || 0}줄`;
        out.appendChild(line);
      }
      const list = (title, items, fmt) => {
        if (!items.length) return;
        const sec = document.createElement('section'); sec.className = 'detail-section';
        const h3 = document.createElement('h3'); h3.textContent = title; sec.appendChild(h3);
        const ul = document.createElement('ul'); ul.className = 'mgr-list';
        for (const it of items) { const li = document.createElement('li'); li.textContent = fmt(it); ul.appendChild(li); }
        sec.appendChild(ul); out.appendChild(sec);
      };
      list('태스크', plan.tasks || [], (t) => `${t.id} · ${plainText(t.title)} · ${show(t.slot)}`);
      list('요청', plan.requests || [], (q) => `${q.id} · ${show(q.title)} · ${show(q.status)}`);
      list('그래프', plan.graphs || [], (g) => `${g.id} · ${plainText(g.request)} · 파일 ${g.files}`);
      apply.disabled = !dry || !(plan.total > 0);
    };
    const run = async (dry) => {
      preview.disabled = true; apply.disabled = true;
      const days = Number(sel.value);
      if (!dry && !window.confirm(`${days === 0 ? '지금 끝난 것 전부' : days + '일 지난 것'}를 아카이브로 옮깁니다. 계속할까요?`)) { preview.disabled = false; apply.disabled = false; return; }
      const r = await archiveRequest(days, dry);
      render(r, dry);
      preview.disabled = false;
      if (!dry && r.ok) { state.slotMsg = null; await refresh(); }
    };
    apply.addEventListener('click', () => run(false));
    sel.addEventListener('change', () => { apply.disabled = true; out.textContent = ''; });
    run(true);
  });
}

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
    const arch = linkButton('끝난 것 정리…', openArchivePanel);
    arch.title = '끝난 태스크·닫힌 요청·끝난 그래프를 한꺼번에 아카이브로 옮깁니다 (지우지 않음). 요청 트리에 쌓인 것도 여기서 정리됩니다';
    filterBox.appendChild(arch);
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

function graphArchivable(g) {
  const nodes = Array.isArray(g.nodes) ? g.nodes : [];
  if (!nodes.length) return false;
  return nodes.every((n) => ['done', 'failed', 'blocked'].includes(String(n.status || '').toLowerCase()));
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

function closedFoldButton(expanded, count, onToggle) {
  const btn = document.createElement('button');
  btn.type = 'button';
  btn.className = 'closed-fold fold-btn';
  btn.setAttribute('aria-expanded', String(expanded));
  btn.textContent = expanded ? `끝난 것 ${count}건 숨기기` : `끝난 것 ${count}건 보기`;
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
  const open = graphs.filter((g) => !graphArchivable(g));
  const closed = graphs.filter(graphArchivable);
  for (const g of open) list.appendChild(graphBlock(g));
  if (closed.length) {
    list.appendChild(closedFoldButton(state.showClosedGraphs, closed.length, () => {
      state.showClosedGraphs = !state.showClosedGraphs;
      if (state.data) renderGraphs(state.data);
    }));
    if (state.showClosedGraphs) for (const g of closed) list.appendChild(graphBlock(g));
  }
}

function progressOf(req) {
  const subs = Array.isArray(req.subtasks) ? req.subtasks : [];
  if (!subs.length) return null;
  if (req.progress_pct !== null && req.progress_pct !== undefined && Number.isFinite(Number(req.progress_pct))) {
    return Number(req.progress_pct);
  }
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
  const projEl = form.querySelector('.req-edit-project');
  const project = projEl ? projEl.value.trim() : '';
  if (!title) { msg.textContent = '제목은 비워 둘 수 없습니다'; msg.className = 'form-msg error'; return; }
  const buttons = form.querySelectorAll('button');
  buttons.forEach((b) => { b.disabled = true; });
  msg.textContent = '저장 중…'; msg.className = 'form-msg';
  try {
    if (DEMO) {
      req.title = title; req.detail = detail; if (projEl) req.project = project;
    } else {
      const res = await fetch('/api/requests/' + encodeURIComponent(req.id) + '/edit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify(projEl ? { title, detail, project } : { title, detail }),
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
  // 프로젝트도 여기서 바꾼다 (REV 146) - 잘못 고른 프로젝트를 고치려고 요청을 다시 쓰지 않게
  const pl = document.createElement('label');
  pl.textContent = '프로젝트 ';
  const ph = document.createElement('span');
  ph.className = 'hint';
  ph.textContent = '결과물이 쌓일 곳 · 비우면 함대 자체의 일';
  pl.appendChild(ph);
  const pi = document.createElement('input');
  pi.type = 'text'; pi.className = 'req-edit-project'; pi.maxLength = 40;
  pi.setAttribute('list', 'project-list'); pi.placeholder = '예: reefwiz-앱';
  pi.value = show(req.project, '');
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
  form.append(tl, ti, pl, pi, dl, ta, row);
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

// 서브태스크가 하나도 없을 때 그 자리에 뭐라고 적을지 - 상태마다 다릅니다 (요청 Q-261111-0afe)
function subtaskEmptyText(req) {
  switch (String(req && req.status || '').toUpperCase()) {
    case 'NEW': return '관리자 분담 대기';
    case 'PLANNED': return '분담 계획됨 - 아직 서브태스크가 없습니다';
    case 'IN-PROGRESS': return '진행 중 - 서브태스크 없이 관리자가 직접 하는 일입니다';
    case 'DONE': return '';
    case 'REJECTED': return '';
    default: return '서브태스크 없음';
  }
}

function renderRequests(data) {
  const list = $('requests-list');
  // 편집 중에는 5초 폴링이 폼을 지우지 않게 다시 그리지 않는다
  if (state.editing && list.querySelector('.req-edit')) return;
  list.textContent = '';
  const requests = Array.isArray(data.requests) ? data.requests : [];
  const tools = $('requests-tools');
  if (tools) {
    tools.textContent = '';
    const closedRequests = requests.filter((r) => REQ_CLOSED.has(String(r.status || '').toUpperCase()));
    const closedGraphs = (Array.isArray(data.graphs) ? data.graphs : []).filter(graphArchivable);
    const label = document.createElement('span');
    if (!closedRequests.length && !closedGraphs.length) {
      label.textContent = '끝난 요청 없음';
    } else {
      label.textContent = (closedRequests.length ? `끝난 요청 ${closedRequests.length}건` : '끝난 요청 없음')
        + ` · 끝난 그래프 ${closedGraphs.length}개`;
    }
    tools.appendChild(label);
    tools.appendChild(linkButton('끝난 것 정리…', openArchivePanel));
  }
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
  const drawRequest = (req, index) => {
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
    metaLine.textContent = `요청 ${fmtDateTime(req.created)} · 요청자 ${show(req.requester)}`
      + (req.project ? ` · 프로젝트 ${req.project} (projects/${req.project}/)` : '');
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
    const subtasks = Array.isArray(req.subtasks) ? req.subtasks : [];
    const closed = REQ_CLOSED.has(String(req.status || '').toUpperCase());
    if (!open) {
      article.classList.add('is-folded');
      const line = document.createElement('div');
      line.className = 'req-meta';
      line.textContent = (pct === null ? '' : fmtPct(pct) + ' · ')
        + (subtasks.length ? '서브태스크 ' + subtasks.length + '건' : subtaskEmptyText(req));
      titleWrap.appendChild(line);
      list.appendChild(article);
      return;
    }
    if (closed) {
      const doneLine = document.createElement('div');
      doneLine.className = 'req-done-line';
      doneLine.textContent = (String(req.status || '').toUpperCase() === 'REJECTED' ? '거절됨' : '끝남')
        + ' · ' + fmtDateTime(req.updated || req.created);
      article.appendChild(doneLine);
    } else if (!subtasks.length) {
      const waitLine = document.createElement('div');
      waitLine.className = 'req-wait-line';
      waitLine.textContent = String(req.status || '').toUpperCase() === 'IN-PROGRESS'
        ? '관리자가 서브태스크 없이 직접 하는 일입니다'
        : '아직 분담 전 - 관리자가 서브태스크로 나누면 진행률과 ETA 가 나옵니다';
      article.appendChild(waitLine);
    } else {
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
      const eta = etaText(req);
      etaLabel.textContent = eta === '-' ? 'ETA 미정' : 'ETA ' + eta;
      progressRow.appendChild(bar);
      progressRow.appendChild(pctLabel);
      progressRow.appendChild(etaLabel);
      article.appendChild(progressRow);

      const basis = document.createElement('div');
      basis.className = 'req-basis';
      basis.textContent = 'ETA 근거: ' + show(req.eta_basis, '근거 없음');
      article.appendChild(basis);
    }

    const body = document.createElement('div');
    body.className = 'req-body';
    body.hidden = !open;
    if (!subtasks.length) {
      const emptyText = subtaskEmptyText(req);
      if (emptyText) body.appendChild(emptyP(emptyText));
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
  };
  const openRequests = ordered.filter((r) => !REQ_CLOSED.has(String(r.status || '').toUpperCase()));
  const closedRequests = ordered.filter((r) => REQ_CLOSED.has(String(r.status || '').toUpperCase()));
  openRequests.forEach(drawRequest);
  if (closedRequests.length) {
    list.appendChild(closedFoldButton(state.showClosedRequests, closedRequests.length, () => {
      state.showClosedRequests = !state.showClosedRequests;
      if (state.data) renderRequests(state.data);
    }));
    if (state.showClosedRequests) closedRequests.forEach(drawRequest);
  }
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

// ---- 프로젝트 결과물 보기 (REV 146) - `projects/<이름>/` 의 파일 목록과 본문을 상세 패널에서
function fmtBytes(n) {
  const v = Number(n);
  if (!Number.isFinite(v)) return '-';
  if (v < 1024) return v + 'B';
  if (v < 1024 * 1024) return (v / 1024).toFixed(v < 10240 ? 1 : 0) + 'KB';
  return (v / 1048576).toFixed(1) + 'MB';
}

async function projectApi(name, tail) {
  const res = await fetch('/api/projects/' + encodeURIComponent(name) + tail, { headers: { Accept: 'application/json' } });
  const body = await res.json().catch(() => ({}));
  if (!res.ok || !body.ok) throw new Error(body.error || ('HTTP ' + res.status));
  return body;
}

function openProjectFiles(pr, filePath) {
  const name = show(pr.name, '');
  openPanel('프로젝트 ' + name + ' 결과물', (body) => {
    const seq = state.detailSeq;                 // 늦게 온 응답이 다른 상세를 덮지 않게
    const alive = () => state.detailOpen && state.detailSeq === seq;
    const note = (text, cls) => { const p = document.createElement('p'); p.className = cls || 'empty'; p.textContent = text; return p; };
    const showList = async () => {
      body.replaceChildren(note('목록을 불러오는 중…'));
      try {
        const d = DEMO ? { path: `projects/${name}/`, files: [], truncated: false } : await projectApi(name, '/files');
        if (!alive()) return;
        body.replaceChildren();
        const head = note(`${show(d.path, '')} · 파일 ${d.files.length}개` + (d.truncated ? ' (앞 500개만)' : '') + ' · 행을 누르면 본문', 'proj-meta');
        body.appendChild(head);
        if (!d.files.length) { body.appendChild(note('아직 파일이 없습니다')); return; }
        const tw = document.createElement('div');
        tw.className = 'tablewrap';
        tw.appendChild(newTable(['파일', '크기', '고친 때'], d.files.map((f) => [mono(f.path), fmtBytes(f.size), fmtDateTime(f.modified)]), null, {
          className: 'proj-files',
          widths: [null, '76px', '150px'], num: [1], ellipsis: [0],
          rowOpen: d.files.map((f) => ({ fn: () => showFile(f.path), title: '본문 보기: ' + f.path })),
        }));
        body.appendChild(tw);
      } catch (err) {
        if (alive()) body.replaceChildren(note('목록을 불러오지 못했습니다: ' + (err && err.message ? err.message : err), 'form-msg error'));
      }
    };
    const showFile = async (path) => {
      const back = linkButton('← 파일 목록', showList);
      body.replaceChildren(back, note('불러오는 중…'));
      try {
        const d = await projectApi(name, '/file?path=' + encodeURIComponent(path));
        if (!alive()) return;
        const meta = note(`projects/${name}/${show(d.path, '')} · ${fmtBytes(d.size)} · ${fmtDateTime(d.modified)}`
          + (d.truncated ? ' · 앞 200KB 만 보입니다' : ''), 'proj-meta');
        body.replaceChildren(back, meta);
        if (d.binary) { body.appendChild(note('텍스트가 아닌 파일이라 본문을 보이지 않습니다')); return; }
        if (/\.(md|markdown)$/i.test(path)) body.appendChild(mdBlock(d.text, '빈 파일'));
        else {
          const pre = document.createElement('pre');
          pre.className = 'proj-file-text';
          pre.textContent = d.text || '(빈 파일)';
          body.appendChild(pre);
        }
      } catch (err) {
        if (alive()) body.replaceChildren(back, note('파일을 불러오지 못했습니다: ' + (err && err.message ? err.message : err), 'form-msg error'));
      }
    };
    if (filePath) showFile(filePath); else showList();
  });
}

const ALLOWED_MSG_KEYS = {
  ready: ['aimem', 'op'],
  put: ['aimem', 'op', 'key', 'value'],
};

function openProjectApp(pr) {
  const name = show(pr.name, '');
  const app = pr.app || {};
  openPanel('프로젝트 ' + name + ' 실행', (body) => {
    body.classList.add('detail-app');
    const note = (text, cls) => { const p = document.createElement('p'); p.className = cls || 'empty'; p.textContent = text; return p; };
    body.appendChild(note(`projects/${name}/${show(app.root, '')}/${show(app.entry, '')} · 격리된 칸에서 돌아갑니다 - 기록(통계·설정)은 이 브라우저에만 남습니다`, 'proj-meta'));

    const tab = document.createElement('a');
    tab.href = '/app/' + encodeURIComponent(name) + '/';
    tab.target = '_blank';
    tab.rel = 'noopener noreferrer';
    tab.textContent = '새 탭에서 열기';
    tab.title = '더 큰 화면으로 봅니다. 여기서도 격리되어 새 탭에서는 기록이 남지 않습니다';
    body.appendChild(tab);

    if (DEMO) { body.appendChild(note('데모 화면에서는 실행할 수 없습니다')); return; }

    const part = 'aimem.app.v1.' + encodeURIComponent(name);
    function okKey(k) {
      return typeof k === 'string' && /^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/.test(k);
    }
    function okVal(v) {
      return v === null || (typeof v === 'string' && v.length <= 8192);
    }
    function loadPart(part) {
      const dict = new Map();
      let parsed;
      try {
        const raw = localStorage.getItem(part);
        if (raw === null) return dict;
        parsed = JSON.parse(raw);
      } catch {
        return dict;
      }
      if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return dict;
      for (const k of Object.keys(parsed)) {
        if (okKey(k) && okVal(parsed[k])) dict.set(k, parsed[k]);
      }
      return dict;
    }
    const dict = loadPart(part);
    let timer = null;
    function flushPut(part, dict) {
      try {
        localStorage.setItem(part, JSON.stringify(Object.fromEntries(dict)));
      } catch (err) {
        console.warn('보관함 쓰기 실패:', err);
      }
    }
    function putIfFits(dict, key, value) {
      const had = dict.has(key);
      const old = had ? dict.get(key) : undefined;
      const beforeSize = dict.size;
      const beforeLen = JSON.stringify(Object.fromEntries(dict)).length;
      if (value === null) dict.delete(key);
      else dict.set(key, value);
      const afterSize = dict.size;
      const afterLen = JSON.stringify(Object.fromEntries(dict)).length;
      if ((afterSize > 64 || afterLen > 65536) && afterSize >= beforeSize && afterLen >= beforeLen) {
        if (had) dict.set(key, old);
        else dict.delete(key);
        return;
      }
      if (!timer) timer = setTimeout(() => { timer = null; flushPut(part, dict); }, 250);
    }
    const rate = (() => {
      let readyCount = 0;
      let firstReady = 0;
      const puts = [];
      return {
        ready() {
          const now = Date.now();
          if (readyCount >= 2) return false;
          if (readyCount === 0) {
            readyCount = 1;
            firstReady = now;
            return true;
          }
          if (now - firstReady < 1000) return false;
          readyCount = 2;
          return true;
        },
        put() {
          const now = Date.now();
          while (puts.length && now - puts[0] >= 1000) puts.shift();
          if (puts.length >= 20) return false;
          puts.push(now);
          return true;
        },
      };
    })();

    const fr = document.createElement('iframe');
    fr.className = 'proj-app-frame';
    fr.src = '/app/' + encodeURIComponent(name) + '/';
    fr.setAttribute('sandbox', 'allow-scripts allow-popups allow-modals');
    fr.setAttribute('referrerpolicy', 'no-referrer');
    fr.title = (app.title || name) + ' 미리보기';
    function onMsg(ev) {
      const src = ev.source;
      if (!src || src !== fr.contentWindow || !fr.isConnected) return;
      if (ev.origin !== 'null') return;
      const m = ev.data;
      if (!m || typeof m !== 'object' || Array.isArray(m) || m.aimem !== 'store.v1') return;
      const allowed = ALLOWED_MSG_KEYS[m.op];
      if (!Array.isArray(allowed) || Object.keys(m).some((k) => !allowed.includes(k))) return;
      if (m.op === 'ready' && rate.ready()) {
        src.postMessage({ aimem: 'store.v1', op: 'snapshot', items: Object.fromEntries(dict) }, '*');
      } else if (m.op === 'put' && rate.put() && okKey(m.key) && okVal(m.value)) {
        putIfFits(dict, m.key, m.value);
      }
    }
    window.addEventListener('message', onMsg);
    state.panelCleanups.push(() => {
      window.removeEventListener('message', onMsg);
      clearTimeout(timer);
      flushPut(part, dict);
      fr.remove();
    });
    body.appendChild(fr);
  });
}

function renderProjects(data) {
  const box = document.getElementById('projects-list');
  if (!box) return;
  const list = Array.isArray(data.projects) ? data.projects : [];
  box.replaceChildren();
  if (!list.length) {
    const p = document.createElement('p');
    p.className = 'empty';
    p.textContent = "아직 프로젝트가 없습니다. '작업 요청' 의 프로젝트 칸에 이름을 적어 보내면 생깁니다.";
    box.appendChild(p);
    return;
  }
  for (const pr of list) {
    const key = 'project:' + show(pr.name, '');
    const item = document.createElement('article');
    item.className = 'proj-item';

    const head = document.createElement('div');
    head.className = 'proj-head';
    const name = document.createElement('h3');
    name.textContent = show(pr.name);
    head.appendChild(name);
    const rq = pr.requests || {};
    const meta = document.createElement('span');
    meta.className = 'proj-meta';
    const bits = [];
    bits.push(rq.total ? `요청 ${rq.done || 0}/${rq.total} 완료` : '요청 없음');
    if (rq.active) bits.push(`진행 중 ${rq.active}`);
    if (rq.new) bits.push(`대기 ${rq.new}`);
    const rounds = Array.isArray(pr.rounds) ? pr.rounds : [];
    bits.push(rounds.length
      ? `라운드 ${rounds.length}회 (${rounds.length > 6 ? 'R' + rounds[0] + ' … R' + rounds[rounds.length - 1] : rounds.map((n) => 'R' + n).join(' · ')})`
      : '아직 라운드 없음');
    meta.textContent = bits.join(' · ');
    head.appendChild(meta);
    if (pr.app && pr.app.runnable) {
      const run = linkButton('실행', () => openProjectApp(pr));
      run.classList.add('proj-run');
      run.title = `${pr.app.title} 을(를) 모니터 안에서 바로 돌려 봅니다 (projects/${pr.name}/${pr.app.root}/)`;
      head.appendChild(run);
    } else if (pr.app) {
      const bad = document.createElement('span');
      bad.className = 'proj-meta';
      bad.textContent = '실행 선언(app.json)에 문제가 있습니다: ' + show(pr.app.reason, '이유 없음');
      head.appendChild(bad);
    }
    if (pr.exists) {
      const view = linkButton('결과물 보기', () => openProjectFiles(pr));
      view.classList.add('proj-view');
      view.title = `projects/${show(pr.name, '')}/ 의 파일 목록과 본문`;
      head.appendChild(view);
    }
    item.appendChild(head);
    const when = [];
    if (pr.last_round_at) when.push(`마지막 라운드 R${pr.last_round} ${fmtDateTime(pr.last_round_at)}`);
    if (pr.updated) when.push(`기록 갱신 ${fmtDateTime(pr.updated)}`);
    if (when.length) {
      const w = document.createElement('div');
      w.className = 'proj-meta proj-when';
      w.textContent = when.join(' · ');
      item.appendChild(w);
    }

    const prog = document.createElement('div');
    prog.className = 'req-progress';
    const bar = document.createElement('div');
    bar.className = 'bar';
    const fill = document.createElement('div');
    fill.className = 'bar-fill';
    const pct = typeof pr.percent === 'number' ? Math.max(0, Math.min(100, pr.percent)) : 0;
    fill.style.width = pct + '%';
    bar.appendChild(fill);
    prog.appendChild(bar);
    const label = document.createElement('span');
    label.className = 'pct';
    const goals = pr.goals && pr.goals.total ? pr.goals : null;
    if (goals) {
      // 목표 대비 (관리자가 PROGRESS.md 의 '## 목표' 에 적은 체크리스트, REV 148)
      label.textContent = `목표 ${goals.done || 0}/${goals.total} · ${Math.round(pct)}%`;
      label.title = '관리자가 PROGRESS.md 의 "## 목표" 에 적은 목표 중 끝난 것'
        + (typeof pr.request_percent === 'number' ? ` (요청 기준 ${Math.round(pr.request_percent)}%)` : '');
    } else {
      label.textContent = typeof pr.percent === 'number' ? `요청 기준 ${Math.round(pct)}%` : '-';
      label.title = '목표가 아직 안 적혀 넣은 요청 중 끝난 비율로 셉니다 - 관리자가 PROGRESS.md 에 "## 목표" 를 쓰면 목표 대비로 바뀝니다';
    }
    prog.appendChild(label);
    item.appendChild(prog);

    if (pr.summary) {
      const det = document.createElement('details');
      det.className = 'fold-group';
      det.open = state.expanded.has(key);
      det.addEventListener('toggle', () => {
        if (det.open) state.expanded.add(key); else state.expanded.delete(key);
      });
      const sum = document.createElement('summary');
      sum.textContent = `최근 기록 (${show(pr.path)}PROGRESS.md)`;
      det.appendChild(sum);
      const body = document.createElement('div');
      body.className = 'proj-summary';
      body.appendChild(renderMarkdown(pr.summary));   // 관리자가 쓰는 PROGRESS.md 는 마크다운 (HTML 비해석)
      det.appendChild(body);
      item.appendChild(det);
    } else {
      const none = document.createElement('div');
      none.className = 'proj-meta';
      none.textContent = pr.exists ? '진행 기록(PROGRESS.md)이 아직 없습니다' : '폴더가 아직 없습니다 - 첫 라운드에서 만들어집니다';
      item.appendChild(none);
    }
    box.appendChild(item);
  }
}

function renderAll(data) {
  renderErrors(data);
  renderTabCounts(data);
  renderFleetControl(data);
  renderManager(data);
  renderProjects(data);
  renderMeta(data);
  renderSlots(data);
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
  const projectEl = $('req-project');
  const project = projectEl ? projectEl.value.trim() : '';
  const payload = {
    title,
    detail: detailEl.value,
    requester: requesterEl.value.trim(),
    project,
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
    if (projectEl) projectEl.value = project;   // 같은 프로젝트에 이어서 넣기 쉽게 남겨 둔다
    msg.className = 'form-msg success';
    msg.textContent = '요청 생성됨: ' + show(result.id, '-') +
      (project ? ` · 프로젝트 ${project}` : ' · 함대 자체');
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

// 폰 설치(PWA): 서비스 워커는 앱 껍데기만 캐시한다(API 금지 - sw.js 참조). 등록 실패는 조용히 넘긴다.
if ('serviceWorker' in navigator && !DEMO && location.protocol === 'https:') {
  window.addEventListener('load', () => { navigator.serviceWorker.register('/sw.js').catch(() => null); });
}
