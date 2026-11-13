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
  projectFilter: null,      // null = 진행 중이 있으면 진행 중, 없으면 전체
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

// 화면의 모든 시각은 한 구역(fleet.toml 의 time_zone, 서버가 state.tz 로 알려 준다)으로 읽고 보인다.
// 서버의 시각 문자열은 오프셋 없는 그 구역의 시계다. 브라우저 구역(Date 의 지역 메서드)을 서버 시각에 쓰지 않는다.
let TZ = { name: 'Asia/Seoul', offset: '+09:00' };
function setTimeZone(tz) {
  if (!tz || typeof tz.name !== 'string' || !/^[+-]\d{2}:\d{2}$/.test(tz.offset || '')) return;
  try { new Intl.DateTimeFormat('ko-KR', { timeZone: tz.name }); } catch (e) { return; }
  TZ = { name: tz.name, offset: tz.offset };
}
const NAIVE_TIME_RE = /^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2})(\.\d+)?)?)?$/;
// 서버 시각 문자열(또는 epoch ms)을 epoch ms 로. Z·오프셋이 있으면 그대로, 없으면 설정 구역의 시계로 읽는다. 못 읽으면 NaN.
function parseTime(value) {
  if (typeof value === 'number') return value;
  const str = String(value === null || value === undefined ? '' : value).trim();
  if (!str) return NaN;
  const m = NAIVE_TIME_RE.exec(str);
  if (m) return Date.parse(`${m[1]}-${m[2]}-${m[3]}T${m[4] || '00'}:${m[5] || '00'}:${m[6] || '00'}${m[7] || ''}${TZ.offset}`);
  return Date.parse(str);
}
function zoneParts(ms) {
  const f = new Intl.DateTimeFormat('en-GB', { timeZone: TZ.name, hourCycle: 'h23', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' });
  const o = {};
  for (const p of f.formatToParts(new Date(ms))) o[p.type] = p.value;
  return o;
}
// 설정 구역의 'YYYY-MM-DD HH:MM[:SS]' (date:false 면 시각만)
function fmtTime(value, opts = {}) {
  const ms = parseTime(value);
  if (!Number.isFinite(ms)) return '-';
  const o = zoneParts(ms);
  const clock = `${o.hour}:${o.minute}` + (opts.seconds ? ':' + o.second : '');
  return opts.date === false ? clock : `${o.year}-${o.month}-${o.day} ${clock}`;
}
function fmtDateTime(value) {
  if (!value) return '-';
  const str = String(value);
  if (NAIVE_TIME_RE.test(str)) return str.replace('T', ' ').slice(0, 16);   // 이미 설정 구역의 시계
  const ms = parseTime(str);
  return Number.isFinite(ms) ? fmtTime(ms) : str.replace('T', ' ').slice(0, 16);
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

// 같은 상태는 어느 탭에서나 같은 말로 (2026-11-12 화면 점검). 도는 프로세스 = '실행 중', 요청의 IN-PROGRESS 만 '진행 중'.
// 원래 값은 data-status 와 title 에 남긴다 (검사·검색은 data-status 로)
const STATUS_LABEL = {
  done: '완료', running: '실행 중', 'in-progress': '진행 중', todo: '할 일', assigned: '배정됨', review: '검토 중',
  blocked: '막힘', failed: '실패', lost: '사라짐', new: '새 요청', planned: '계획됨', rejected: '거절',
  partial: '일부 완료', unknown: '모름', infra: '공급자 장애',
};
// 보드(와 요청 안 서브태스크)의 칸은 엔진이 그래프 노드를 따라 고친다 - REVIEW 는 관리자 판정 대기, BLOCKED 는 막힘이거나 실패
const BOARD_LABEL = { review: '관리자 확인 대기', blocked: '막힘·실패' };
function statusLabel(raw, over) {
  const key = String(raw || '').toLowerCase();
  if (over && over[key]) return over[key];
  if (STATUS_LABEL[key]) return STATUS_LABEL[key];
  if (key.startsWith('needs')) return '고칠 것 있음';
  if (key.startsWith('reject')) return '거절';
  return String(raw);
}
function statusBadge(value, over) {
  const raw = show(value);
  const key = raw.toLowerCase();
  const cls = key === 'lost' ? 'lost' : (STATUS_CLASS[raw] || STATUS_CLASS[raw.toUpperCase()] || (key === 'infra' ? 'blocked' : key === 'failed' ? 'failed' : key === 'todo' ? 'todo' : key === 'blocked' ? 'blocked' : 'neutral'));
  const label = statusLabel(raw, over);
  const span = badge(label, cls);
  span.dataset.status = raw;
  if (label !== raw) span.title = raw;
  if (key === 'lost') span.title = '감독이 사라진 실행 (종료 기록 없음)';
  return span;
}

function boardBadge(value) {
  return statusBadge(value, BOARD_LABEL);
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
        if (index === Math.min(...ellipsis)) td.classList.add('cell-main');   // 카드로 쌓일 때 제목 노릇을 하는 칸
        const full = raw instanceof Node ? raw.textContent : show(raw, '');
        td.title = full;
        makeElidable(td, full);
      }
      if (raw instanceof Node) td.appendChild(raw);
      else td.textContent = show(raw);
      // 좁은 화면에서는 행을 카드로 쌓는다(style.css '표 → 카드') - 칸 이름을 앞에 붙이고 빈 칸은 숨긴다
      td.dataset.label = headers[index] || '';
      const cellText = td.textContent.trim();
      if (!cellText || cellText === '-') td.classList.add('is-empty');
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

// 상세에서 다른 상세로 넘어가면(큐 → 태스크 → 실행) 돌아올 길이 없었다 - 지나온 패널을 쌓고 '← 이전' 으로 되돌아간다.
function notePanel(key, label, reopen) {
  if (!state.panelStack) state.panelStack = [];
  if (state.panelBack) state.panelBack = false;                       // 되돌아가는 중 - 쌓지 않는다
  else if (!state.detailOpen) state.panelStack = [];
  else if (state.panelCur && state.panelCur.key !== key) state.panelStack.push(state.panelCur);
  state.panelCur = { key, label, reopen };
  let back = $('detail-back');
  if (!back) {
    const head = document.querySelector('#detail-overlay .detail-head');
    if (!head) return;
    back = document.createElement('button');
    back.type = 'button'; back.id = 'detail-back'; back.className = 'detail-back btn-link';
    back.addEventListener('click', () => {
      const prev = state.panelStack && state.panelStack.pop();
      if (!prev) return;
      state.panelBack = true;
      prev.reopen();
    });
    head.insertBefore(back, head.firstChild);
  }
  const prev = state.panelStack[state.panelStack.length - 1];
  back.hidden = !prev;
  if (prev) { back.textContent = '← 이전'; back.title = prev.label + ' 로 돌아가기'; back.setAttribute('aria-label', prev.label + ' 로 돌아가기'); }
}

function closeDetail() {
  state.panelStack = []; state.panelCur = null; state.panelBack = false;
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
  if (req.detail_truncated !== true) return req;
  const { res, body } = await api('/api/requests/' + encodeURIComponent(req.id));
  if (!res.ok || !body.ok) throw new Error(body.error || ('HTTP ' + res.status));
  return Object.assign({}, req, { title: body.title, detail: body.detail, detail_truncated: false });
}

// ---- 상세 패널 공통 (2026-11-10: 탭마다 상세보기가 빠진 곳을 메움)
// 하나의 오버레이(`detail-overlay`)를 모든 상세가 같이 쓴다 - 포커스 저장·가둠·Esc 는 bindDetailControls 가 맡는다.
function openPanel(title, build) {
  notePanel('panel:' + title, title, () => openPanel(title, build));
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
    widths: ['196px', '52px', '80px', '108px', '40px', '100px', null],
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
      meta.appendChild(detailMetaItem('상태', boardBadge(b.status)));
      meta.appendChild(detailMetaItem('출처 태스크', show(b.handoff)));
      meta.appendChild(detailMetaItem('산출물', plainText(b.artifact) || '-'));
    } else {
      meta.appendChild(detailMetaItem('보드 상태', '보드에 없음'));
    }
    if (sub) {
      meta.appendChild(detailMetaItem('요청', show(sub.req.title)));
      meta.appendChild(detailMetaItem('요청 내 상태', boardBadge(sub.st.status)));
      if (sub.st.harness) meta.appendChild(detailMetaItem('하네스', show(sub.st.harness)));
    }
    if (gn) {
      meta.appendChild(detailMetaItem('그래프', show(gn.g.id) + ' · ' + (nodeIsInfra(gn.n) ? statusLabel('infra') : show(gn.n.status))
        + ' · 시도 ' + show(gn.n.attempts) + '/' + show(gn.n.max_attempts)));
      for (const note of nodeNotes(gn.n)) meta.appendChild(detailMetaItem('메모', note.text));
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
    const al = gn ? attemptList(gn.n) : null;
    if (al) {
      const sec2 = document.createElement('section');
      sec2.className = 'detail-section';
      const h4 = document.createElement('h3');
      h4.textContent = '시도 기록 ' + gn.n.attempt_log.length + '건';
      sec2.appendChild(h4);
      sec2.appendChild(al);
      body.appendChild(sec2);
    }
  });
}

function openQueueDetail(q, data) {
  data = data || state.data;
  openPanel('대기 큐 ' + show(q.order, '') + '번 - 후속 일', (body) => {
    const meta = document.createElement('div');
    meta.className = 'detail-meta';
    meta.appendChild(detailMetaItem('순서', show(q.order)));
    meta.appendChild(detailMetaItem('추천 슬롯', show(q.slots)));
    meta.appendChild(detailMetaItem('출처 태스크', show(q.handoff)));
    body.appendChild(meta);
    const ho = String(q.handoff || '').trim();
    if (ho && data && taskKnown(ho, data)) {
      const row = document.createElement('div');
      row.className = 'detail-actions';
      row.appendChild(linkButton('태스크 상세 보기 → ' + ho, () => openTaskDetail(ho, data)));
      body.appendChild(row);
    }
    addTextSection(body, '할 일', q.task);
    addTextSection(body, '비고', q.note);
  });
}

function openLogDetail(entry) {
  openPanel('라운드 핸드오프 로그 ' + show(entry.when, ''), (body) => {
    addTextSection(body, '내용', entry.text);
  });
}

function openManagerList(sessions) {
  openPanel('관리자 세션 ' + sessions.length + '개', (body) => {
    const sizeText = (s) => (s.record_kb === null || s.record_kb === undefined) ? '-'
      : (s.record_kb >= 1024 ? (s.record_kb / 1024).toFixed(1) + 'MB' : s.record_kb + 'KB');
    const rows = sessions.map((s) => [
      show(s.label),
      mgrStateBadge(s.session_state, s.status),
      fmtDateTime(s.started),
      fmtDateTime(s.updated),
      sizeText(s),
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
  notePanel('req:' + req.id, '요청 ' + show(req.id, ''), () => openRequestDetail(req));
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
  if (req.detail_truncated === true) {
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

function addDetailSection(parent, title, text, plain = false, folded = false) {
  if (folded && show(text, '')) {
    // 길고 덜 보는 글(지시 본문·stderr)은 접어 둔다 - 펼쳐 두면 실행 상세가 수만 px 가 되어 보고를 읽은 뒤에도 수십 화면이 남았다
    const det = document.createElement('details');
    det.className = 'fold-group detail-section detail-fold';
    const sum = document.createElement('summary');
    const len = String(text).length;
    sum.textContent = `${title} · ${len >= 1000 ? (len / 1000).toFixed(1) + '천 자' : len + '자'}`;
    det.appendChild(sum);
    if (plain) { const pre = document.createElement('pre'); pre.className = 'detail-pre'; pre.textContent = String(text); det.appendChild(pre); }
    else det.appendChild(mdBlock(text, '없음'));
    parent.appendChild(det);
    return;
  }
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
  addDetailSection(body, '지시 본문', detail.brief, false, true);
  addDetailSection(body, 'stderr', detail.stderr_tail, true, true);
  addDetailSection(body, '사건 (events.jsonl)', detail.events, true, true);
}

async function openDetail(runId) {
  notePanel('run:' + runId, '실행 ' + show(runId, ''), () => openDetail(runId));
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
  let detail;
  try {
    ({ res, body: detail } = await api('/api/runs/' + encodeURIComponent(runId)));
  } catch (err) {
    if (seq !== state.detailSeq) return;
    body.textContent = '가져오기 실패: ' + (err && err.message ? err.message : String(err));
    return;
  }
  if (seq !== state.detailSeq) return;
  if (!res.ok) {
    const reason = detail && typeof detail.error === 'string' && detail.error ? detail.error : null;
    const fallback = { 404: '404 - 실행 기록을 찾을 수 없습니다: ' + runId, 400: '400 - 잘못된 실행 id 입니다: ' + runId }[res.status]
      || '가져오기 실패: HTTP ' + res.status + ' ' + (res.statusText || '');
    body.textContent = reason ? 'HTTP ' + res.status + ' - ' + reason : fallback;
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
  const span = badge(statusLabel(st), cls);
  span.dataset.status = st;
  span.title = '작업자 보고: ' + st;
  return span;
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
  const mg0 = fl.manager || null;
  const lr = (mg0 && mg0.round) ? { round: mg0.round, at: mg0.at, report_status: null, state: mg0.state } : (fl.last_round || null);
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
                          : (lr && lr.state && MGR_STATE_TEXT[lr.state] ? '관리자 ' + MGR_STATE_TEXT[lr.state] : (fl.label || show(fl.mode, '-')));
  roundWrap.appendChild(roundStatus);
  const roundItem = metaItem('이번 라운드', roundWrap);
  roundItem.classList.add('meta-goal');
  box.appendChild(roundItem);

  const brandRev = $('brand-rev');
  if (brandRev) brandRev.textContent = aimem.rev ? 'REV ' + aimem.rev : '';
}

// ---- 관리자 세션 (.aimem/sessions/M-R<N>-…) - 상태 낱말은 서버가 준 것 그대로 (설계 5.6)
// 세션이 끝난 까닭의 낱말 - 실행 표·관리자 카드·상세가 같은 말을 쓴다. '사라짐' 은 진짜 lost(감독이 사라지고 종료 기록 없음)만.
const SESSION_END_TEXT = { stalled: '침묵으로 끊김', timeout: '시간 초과', failed: '실패', killed: '중단' };
const MGR_STATE_TEXT = Object.assign({ running: '실행 중', launching: '띄우는 중', done: '끝남', lost: '사라짐' }, SESSION_END_TEXT);
function mgrStateBadge(sessionState, status) {
  const key = sessionState || status || 'unknown';
  const cls = key === 'running' || key === 'launching' ? 'running' : (key === 'done' ? 'done'
    : (['failed', 'killed', 'timeout', 'stalled', 'lost'].includes(key) ? 'blocked' : 'neutral'));
  const b = badge(MGR_STATE_TEXT[key] || show(key), cls);
  b.dataset.status = key;
  return b;
}
function agoText(iso) {
  const t = parseTime(iso);
  return Number.isFinite(t) ? fmtElapsed((Date.now() - t) / 1000) + ' 전' : null;
}
// 실행 표·슬롯 카드의 "마지막 사건 N초 전 · <last_event>" (세션 실행만 값이 있다)
function lastEventText(r) {
  if (!r || r.state !== 'running' || !r.last_event_at) return '';
  const ago = agoText(r.last_event_at);
  return ago ? `마지막 사건 ${ago}` + (r.last_event ? ' · ' + r.last_event : '') : '';
}
// 실행 한 줄의 상태 - 세션 상태(session_state)를 먼저 본다. 옛 `state` 는 failed→done, killed→lost 로 접혀 있어 쓰지 않는다.
function runStatusBadge(r) {
  const ss = r && r.session_state;
  if (ss && SESSION_END_TEXT[ss]) {
    const b = badge(SESSION_END_TEXT[ss], 'blocked');
    b.dataset.status = ss;
    b.title = { stalled: '마지막 사건 뒤 침묵이 제한을 넘겨 감독이 끊음', timeout: '벽시계 제한을 넘겨 감독이 끊음',
      failed: '작업자가 실패로 끝남', killed: '사람이 중단함' }[ss];
    return b;
  }
  return statusBadge(ss || r.state);
}

// 운영 방식 (무료 중심 / 품질 중심 / 빠른 구현). `fleet.policy` 가 없으면 화면에 아무것도 안 낸다.
function fleetPolicy(data) {
  const p = data && data.fleet && data.fleet.policy;
  return p && Array.isArray(p.choices) && p.choices.length ? p : null;
}
function policyLabel(policy, key) {
  if (!policy || !key) return '';
  const c = policy.choices.find((x) => x && x.key === key);
  return c ? (c.label || c.key) : '';
}
// 가로로 붙은 라디오 단추 묶음. 폭이 좁으면 줄을 바꾼다. 선택한 항목의 설명은 한 줄로 아래에 보인다.
function policySegment(policy, selected, name, onChange) {
  const wrap = document.createElement('div');
  wrap.className = 'fc-policy';
  const lab = document.createElement('span');
  lab.className = 'fc-policy-lab';
  lab.textContent = '운영 방식';
  wrap.appendChild(lab);
  const seg = document.createElement('div');
  seg.className = 'fc-policy-seg';
  seg.setAttribute('role', 'radiogroup');
  seg.setAttribute('aria-label', '운영 방식');
  const desc = document.createElement('div');
  desc.className = 'fc-hint fc-policy-desc';
  const radios = [];
  const showDesc = () => {
    const r = radios.find((x) => x.checked);
    const c = r && policy.choices.find((x) => x.key === r.value);
    desc.textContent = c ? show(c.desc || '') : '';
  };
  for (const c of policy.choices) {
    const l = document.createElement('label');
    l.className = 'fc-policy-opt';
    l.title = c.desc || '';
    const r = document.createElement('input');
    r.type = 'radio';
    r.name = name;
    r.value = c.key;
    r.checked = c.key === selected;
    r.addEventListener('change', () => { showDesc(); onChange(c.key); });
    const t = document.createElement('span');
    t.textContent = c.label || c.key;
    l.appendChild(r);
    l.appendChild(t);
    seg.appendChild(l);
    radios.push(r);
  }
  if (!radios.some((x) => x.checked) && radios[0]) radios[0].checked = true;
  wrap.appendChild(seg);
  wrap.appendChild(desc);
  showDesc();
  return { el: wrap, get: () => (radios.find((x) => x.checked) || {}).value };
}
function policySelected(policy, key) {
  return policy.choices.some((c) => c.key === key) ? key : (policy.choices.some((c) => c.key === policy.default) ? policy.default : policy.choices[0].key);
}

const MODE_BADGE = { running: 'running', paused: 'partial', stopped: 'blocked', ready: 'done' };
const FLEET_BUTTONS = [
  { act: 'prepare', label: '준비', title: '관리자·작업자를 띄울 수 있는지 점검합니다. 통과하면 준비 상태 (작업자는 띄우지 않음)' },
  { act: 'run', label: '재개', title: "멈춘 라운드를 이어 돌립니다 (일시 중지·완전 중지 뒤). 새 요청은 '라운드 실행' 으로 띄웁니다" },
  { act: 'pause', label: '일시 중지', title: '새 작업자 투입을 멈춥니다. 돌고 있는 작업자는 끝까지 둡니다' },
  { act: 'stop', label: '완전 중지', title: '돌고 있는 작업자와 그래프 실행기를 즉시 종료합니다', danger: true,
    confirm: '돌고 있는 작업자와 그래프 실행기를 지금 종료합니다.\n중간 산출물이 반쯤 남을 수 있습니다. 계속할까요?' },
];

// 서버 호출 하나로: payload 가 있으면 POST(JSON), 없으면 GET. 본문이 JSON 이 아니면 {ok:false, error:'HTTP n'}.
async function api(url, payload) {
  const opt = { headers: { Accept: 'application/json' } };
  if (payload !== undefined) {
    opt.method = 'POST';
    opt.headers['Content-Type'] = 'application/json';
    opt.body = JSON.stringify(payload);
  }
  const res = await fetch(url, opt);
  const body = await res.json().catch(() => ({ ok: false, error: 'HTTP ' + res.status }));
  return { res, body };
}

async function fleetAction(act, confirmText, extraBody) {
  if (confirmText && !window.confirm(confirmText)) return;
  state.fleetBusy = act;
  state.fleetMsg = null;
  if (state.data) {
    renderFleetControl(state.data);
    renderClaudeUsage(state.data);
  }
  try {
    const { body } = await api('/api/fleet/' + act, extraBody || {});
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
  const name = { prepare: '준비', run: '재개', pause: '일시 중지', stop: '완전 중지', round: '라운드 실행' }[m.act] || m.act;
  if (m.act === 'prepare' && Array.isArray(b.checks)) {
    const bad = b.checks.filter((c) => !c.ok && c.required).map((c) => c.name);
    return b.ok ? '준비 점검 통과 - 준비 상태입니다' : `준비 점검에서 막혔습니다: ${bad.join(', ')} (아래 목록)`;
  }
  if (!m.ok) return `${name} 실패: ${b.error || '알 수 없는 오류'}`;
  if (m.act === 'stop') {
    const k = (b.killed || []).length;
    return `완전 중지 - 작업자 ${k}개 종료` + ((b.halted_graphs || []).length ? `, 그래프 ${b.halted_graphs.join(', ')} 정리` : '') + '. ' + (b.note || '');
  }
  if (m.act === 'run') return '재개 - ' + ((b.resumed_graphs || []).length ? `그래프 ${b.resumed_graphs.join(', ')} 이어 돌림. ` : '') + (b.note || '');
  if (m.act === 'round') return `라운드 R${b.round} 실행 - 관리자 세션을 띄웠습니다 (${b.brief}). 위 관리자 카드에 나타납니다`;
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
    const { body } = await api('/api/fleet/chain', on
      ? { on: true, all: !!target.all, fleet: !!target.fleet, projects: target.projects || [], max_rounds: maxRounds,
        renew: !!target.renew, autonomous: !!target.auto, ...(target.policy ? { policy: target.policy } : {}) }
      : { on: false });
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

// 이어 달리기의 상한 값은 엔진이 알려 준다(fleet.chain.limits). 없으면 지금까지의 값.
function chainLimits(f) {
  const l = (f && f.chain && f.chain.limits) || {};
  const n = (v, d) => (Number.isInteger(v) && v > 0 ? v : d);
  return { default: n(l.default, 3), max: n(l.max, 10), hard: n(l.hard, 30) };
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
  const lim = chainLimits(f);
  const names = Array.from(new Set([]
    .concat((data && Array.isArray(data.projects) ? data.projects : []).map((p) => p && p.name))
    .concat((data && Array.isArray(data.requests) ? data.requests : []).map((q) => q && q.project))
    .filter(Boolean))).sort();
  const sig = JSON.stringify([f.mode, !!ch.on, ch.label, ch.all, ch.fleet, ch.projects, ch.max_rounds, ch.autonomous, ch.renew, ch.cycles, ch.total_rounds, f.chain_modes, ch.rounds_done, ch.stopped_why, ch.stopped_kind, ch.stopped_at, names, f.policy ? [f.policy.default, f.policy.chain, f.policy.choices, state.policyChoice] : null, lim,
    !!state.chainBusy, state.chainMsg]);
  if (el.dataset.sig === sig) return;
  el.dataset.sig = sig;
  const keep = state.chainForm || { all: false, fleet: false, projects: [], max: lim.default };
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
    const label = ch.label || chainTargetText({ all: ch.all, fleet: ch.fleet, projects: ch.projects }) || '전체(프로젝트+함대)';
    const what = document.createElement('span');
    what.className = 'fleet-chain-what';
    const cap = ch.max_rounds || lim.default;
    const chPol = policyLabel(fleetPolicy(data), f.policy && f.policy.chain);
    what.textContent = `${label}${chPol ? ' · ' + chPol : ''} · 상한 ${cap} 라운드 · 닿으면 ${ch.autonomous ? '새로 이어 감 (완전 자율 종주)' : (ch.renew || !ch.max_rounds) ? '새로 이어 감 (끝날 때까지)' : '끝에서 멈춤'}`;
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
      + ' · 끝날 때마다 열린 요청·남은 목표를 보고 새 관리자로 다음 라운드를 띄웁니다');
    el.appendChild(t);
  } else {
    // ---- 지난번에 왜 멈췄나: 제목 한 줄 + 다음에 할 일 한 줄. 엔진이 적은 까닭(stopped_why)은 마우스를 올리면 보인다.
    if (ch.stopped_why) {
      const KIND = {
        done: ['done', '다 끝냈습니다', '새 요청이 생기면 다시 켜십시오'],
        cap: ['warn', '상한 라운드를 채워 멈췄습니다', "남은 일이 있습니다 - 다시 켜거나 '새로 이어 달리기' 로 켜십시오"],
        safety: ['warn', `안전 상한(모두 ${lim.hard} 라운드)에 닿아 멈췄습니다`, '진행 상황을 확인한 뒤 다시 켜십시오'],
        stuck: ['bad', '진전이 없어 멈췄습니다', '직전 라운드의 종료 보고를 보고 요청을 고치거나 나눈 뒤 다시 켜십시오'],
        report: ['bad', '관리자 보고가 DONE 이 아니어서 멈췄습니다', `rounds/R${ch.stopped_round || '<N>'}/REPORT.md 를 확인하고 다시 켜십시오`],
        error: ['bad', '다음 라운드를 띄우지 못해 멈췄습니다', "'준비' 를 눌러 무엇이 막는지 확인하십시오"],
        wait: ['bad', '라운드가 끝나지 않아 기다리기를 그만두었습니다', '관리자 세션이 살아 있는지 확인하십시오'],
        off: ['info', '', ''],
      };
      const [tone, head1, next] = KIND[ch.stopped_kind] || ['info', '', ''];
      const note = document.createElement('div');
      note.className = 'fleet-chain-stop is-' + tone;
      note.setAttribute('role', 'status');
      note.title = String(ch.stopped_why);
      const h = document.createElement('div');
      h.className = 'fleet-chain-stop-head';
      // 사람이 끈 경우의 제목은 엔진의 까닭 그대로 (한 번만 적는다)
      h.textContent = (head1 || show(ch.stopped_why))
        + (ch.stopped_round ? ` · R${ch.stopped_round} 뒤` : '')
        + (ch.stopped_at ? ` · ${fmtDateTime(ch.stopped_at)}` : '');
      note.appendChild(h);
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
    num.max = String(lim.max);
    num.value = String(keep.max || lim.default);
    num.className = 'fleet-chain-max';
    num.setAttribute('aria-label', '상한 라운드');
    num.title = `한 묶음에서 이어 띄울 라운드 수 (1~${lim.max}). 라운드마다 새 관리자가 뜹니다`;
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
    addMode('stop', '끝에서 멈춤', '상한만큼 돌고 끝', '상한 라운드를 채우면 멈춥니다. 남은 일이 있으면 다시 켭니다');
    addMode('renew', '새로 이어 달리기', '끝날 때까지',
      '상한을 채우면 새 묶음으로 넘어가 라운드 수를 다시 세며 이어 갑니다. 남은 일이 없을 때까지 갑니다. 보고가 DONE 이 아니거나 진전이 없으면 멈춥니다');
    addMode('autonomous', '완전 자율 종주', '막혀도 한 번 더',
      '새 묶음으로 이어 가며 끝까지 갑니다. 보고가 DONE 이 아니거나 진전이 없어도 한 번은 더 가 보고, 연달아 두 번 막히면 멈춥니다');
    if (!Object.values(radios).some((r) => r.checked)) radios.stop.checked = true;
    sec2.appendChild(modes);
    el.appendChild(sec2);

    // 운영 방식은 '라운드 실행' 옆의 한 곳에서 고른다 - 여기서는 지금 고른 것을 글로만 보인다
    const pol = fleetPolicy(data);
    const polKey = pol ? policySelected(pol, state.policyChoice) : null;
    if (pol) {
      const pt = document.createElement('div');
      pt.className = 'fc-hint fleet-chain-policy';
      pt.textContent = '운영 방식: ' + policyLabel(pol, polKey);
      el.appendChild(pt);
    }
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
        policy: polKey || undefined,
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
      if (!(t.max >= 1 && t.max <= lim.max)) return fail(`상한 라운드는 1~${lim.max} 으로 적어 주십시오`);
      return chainAction(true, t, t.max);
    });
    sync();
    const foot = document.createElement('div');
    foot.className = 'fleet-chain-foot';
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

// 작업 요청 폼의 프로젝트 고르기 - 있는 프로젝트는 고르고 없으면 새로 입력한다 (요청 Q-261112-a8be).
// renderFleetControl 안에 있던 것을 떼어 냈다 - 그 함수는 함대 상태를 못 읽으면 먼저 return 해서
// 목록이 영영 안 채워졌다.
function projectNameList(data) {
  return (data && Array.isArray(data.projects) ? data.projects : []).map((x) => x && x.name).filter(Boolean);
}

function syncNewProjectInput(sel, input, focus) {
  if (!sel || !input) return;
  if (sel.value === '__new__') {
    input.hidden = false;
    if (focus) input.focus();
  } else {
    input.hidden = true;
    input.value = '';
  }
}

// 프로젝트 고르기(<select> + 새 이름 입력) - 작업 요청 폼과 요청 수정 폼이 같이 쓴다. 이름 목록이 바뀔 때만 다시 채워
// 고르는 중에 목록이 깜박이지 않는다. `current` 가 있으면(수정 폼) 그 값을 고른 채로 시작한다.
function fillProjectPicker(sel, input, names, current) {
  const extra = current && !names.includes(current) ? current : null;   // 목록에 없는 현재 값도 고를 수 있게
  const key = names.join('|') + (extra ? '|+' + extra : '');
  if (sel.dataset.names !== key) {
    const keep = current !== undefined ? current : sel.value;
    const options = [];
    const mk = (value, text) => { const o = document.createElement('option'); o.value = value; o.textContent = text; options.push(o); };
    mk('', '(함대 자체의 일 - 프로젝트 없음)');
    for (const name of names) mk(name, name);
    if (extra) mk(extra, extra);
    mk('__new__', '+ 새 프로젝트…');
    sel.replaceChildren(...options);
    sel.dataset.names = key;
    sel.value = (keep === '__new__' || names.includes(keep) || keep === extra) ? keep : '';
  }
  if (!sel.dataset.bound) {
    sel.dataset.bound = '1';
    sel.addEventListener('change', () => syncNewProjectInput(sel, input, true));
  }
  syncNewProjectInput(sel, input, false);
}

function renderProjectPicker(data) {
  const sel = $('req-project-pick');
  if (sel) fillProjectPicker(sel, $('req-project'), projectNameList(data));
}

function fmtUsageReset(value) {
  if (typeof value !== 'string' || value === '') return null;
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(value)) return null;
  const ms = parseTime(value);
  if (!Number.isFinite(ms)) return null;
  const o = zoneParts(ms);
  const n = zoneParts(Date.now());
  const isToday = o.year === n.year && o.month === n.month && o.day === n.day;
  const time = o.hour + ':' + o.minute;
  return isToday ? '초기화 ' + time : '초기화 ' + Number(o.month) + '/' + Number(o.day) + ' ' + time;
}

function usageStaleText(ageSeconds) {
  const n = Number(ageSeconds);
  if (!Number.isFinite(n) || n <= 600) return '';
  const minutes = Math.floor(n / 60);
  if (minutes > 60) return Math.floor(minutes / 60) + '시간 전 기준';
  return minutes + '분 전 기준';
}

function renderClaudeUsage(data) {
  const box = $('claude-usage');
  const stale = $('usage-stale');
  if (stale) stale.textContent = '';
  if (!box) return;
  box.textContent = '';

  const usage = data && data.claude_usage;
  if (!usage || !Array.isArray(usage.rows) || usage.rows.length === 0) {
    box.appendChild(emptyP('상태줄 명령을 등록하면 보입니다'));
    return;
  }
  if (stale) stale.textContent = usageStaleText(usage.age_seconds);

  for (const item of usage.rows) {
    if (!item) continue;
    const percent = Number(item.percent);
    const pct = Number.isFinite(percent) ? Math.max(0, Math.min(100, percent)) : 0;
    const row = document.createElement('div');
    row.className = 'usage-row ' + (pct < 80 ? 'usage-ok' : (pct < 95 ? 'usage-warn' : 'usage-crit'));
    row.dataset.key = show(item.key, '');

    const label = document.createElement('span');
    label.className = 'usage-label';
    label.textContent = show(item.label, '');
    row.appendChild(label);

    const bar = document.createElement('span');
    bar.className = 'usage-bar';
    const fill = document.createElement('span');
    fill.className = 'usage-fill';
    fill.style.width = pct + '%';
    bar.appendChild(fill);
    row.appendChild(bar);

    const pctText = document.createElement('span');
    pctText.className = 'usage-pct';
    pctText.textContent = Math.round(pct) + '%';
    row.appendChild(pctText);

    const resetText = fmtUsageReset(item.resets_at_iso);
    if (resetText !== null) {
      const reset = document.createElement('span');
      reset.className = 'usage-reset';
      reset.textContent = resetText;
      row.appendChild(reset);
    }

    box.appendChild(row);
  }
}

// 함대가 '실행' 인데 도는 것이 하나도 없으면 '실행 (대기)' - '실행 중' 과 헷갈리지 않게
function fleetModeLabel(f) {
  return show(f.label) + (f.idle && f.mode === 'running' ? ' (대기)' : '');
}

// 유료 관리자 - 모델 이름은 엔진이 알려 줄 때만 붙인다
function paidManager(f) {
  const m = f && f.manager && f.manager.model;
  return '유료 관리자' + (m ? `(${m})` : '');
}

function renderFleetControl(data) {
  renderFleetChain(data);
  const box = $('fleet-control');
  const pill = $('fleet-mode-pill');
  const f = data.fleet || {};
  const md = f.mode;
  if (pill) {
    pill.textContent = md ? '함대: ' + fleetModeLabel(f) : '';
    pill.className = 'mode-pill' + (md ? ' mode-' + md : '');
    pill.title = f.note ? `${fleetModeLabel(f)} - ${f.note} (${fmtDateTime(f.at)}, ${show(f.by)})` : '';
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
  head.appendChild(badge(fleetModeLabel(f), MODE_BADGE[md] || 'neutral'));
  const meta = document.createElement('span');
  meta.className = 'fc-meta';
  const bits = [];
  if (f.at) bits.push(fmtDateTime(f.at) + ' · ' + show(f.by));
  if (f.default) bits.push('상태 파일 없음(기본값)');
  if (f.running_runs) bits.push(`작업자 ${f.running_runs}개 실행 중`);
  if (Array.isArray(f.graphs) && f.graphs.length) bits.push('미완 그래프 ' + f.graphs.map((g) => {
    // 진척을 첫 화면에서 본다 - 전에는 요청 트리 탭까지 가야 했다
    const full = ((state.data && state.data.graphs) || []).find((x) => x && x.id === g.id);
    const pct = full && full.percent !== null && full.percent !== undefined ? ' ' + fmtGraphPct(full.percent) : '';
    const eta = full && full.eta_seconds ? ' · 남은 ' + fmtGraphEta(full.eta_seconds) : '';
    return g.id + pct + eta + (g.runner ? '' : ' (실행기 없음)');
  }).join(', '));
  meta.textContent = bits.join(' · ');
  head.appendChild(meta);
  box.appendChild(head);
  for (const ln of graphWaitSummary((data && Array.isArray(data.graphs)) ? data.graphs : [])) {
    const p = document.createElement('div');
    p.className = 'fc-note ' + ln.cls;
    p.textContent = ln.text;
    box.appendChild(p);
  }

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
    ? `새 ${paidManager(f)} 라운드를 띄웁니다. 브리프: ${briefName}`
      + (can.round ? (f.idle ? ' - 준비 점검을 먼저 돌린 뒤 띄웁니다' : '') : (md === 'running' ? ' - 지금 라운드가 끝난 뒤에' : ' - 먼저 준비를 누르십시오'))
    : '확정된 다음 라운드 브리프가 없습니다' + (brief.drafts && brief.drafts.length ? ` (초안: ${brief.drafts.join(', ')})` : '');
  rb.addEventListener('click', () => {
    // 화면에 다 보이는 것을 되묻지 않는다 - 할 일이 없을 때만 확인
    const reqs = (data && Array.isArray(data.requests)) ? data.requests : [];
    const nNew = reqs.filter((q) => String(q.status || '').toUpperCase() === 'NEW').length;
    const pk = polSeg ? polSeg.get() : null;
    fleetAction('round', brief.standard && !nNew ? "할 일이 없습니다 - 관리자는 점검만 하고 끝냅니다. 그래도 띄울까요?" : null, pk ? { policy: pk } : undefined);
  });
  row.appendChild(rb);
  box.appendChild(row);
  const pol = fleetPolicy(data);
  let polSeg = null;
  if (pol) {
    polSeg = policySegment(pol, policySelected(pol, state.policyChoice), 'fleet-round-policy', (k) => { state.policyChoice = k; renderFleetChain(state.data); });
    box.appendChild(polSeg.el);
  }

  const hint = document.createElement('div');
  hint.className = 'fc-hint';
  if (brief.file && brief.standard) {
    // 라운드가 할 일 = '작업 요청' 폼으로 넣은 NEW 요청. 폼은 넓은 화면에선 오른쪽, 좁은 화면에선 맨 아래라
    // 잘 안 보인다(2026-11-10 태석님) - 여기서 바로 가는 버튼과 지금 쌓인 건수를 보인다.
    const reqs = (data && Array.isArray(data.requests)) ? data.requests : [];
    const fresh = reqs.filter((q) => String(q.status || '').toUpperCase() === 'NEW');
    const txt = document.createElement('span');
    // 라운드가 도는 중에는 '지금 도는 라운드' 를 먼저 보인다 - 다음 번호만 보여 R7 이 도는데 R8 로 읽혔다 (2026-11-10 R7 실측)
    const curRound = (md === 'running' && !f.idle && f.manager && f.manager.round && ['launching', 'running'].includes(f.manager.state)) ? f.manager : null;
    if (curRound) {
      const now = document.createElement('div');
      now.className = 'fc-hint-now';
      const cpl = policyLabel(pol, curRound.policy);
      now.textContent = `지금 R${curRound.round} 실행 중` + (cpl ? ` · ${cpl}` : '') + (curRound.workspace ? ` · 라운드 보고 ${curRound.workspace}/` : '');
      hint.appendChild(now);
    } else if (f.idle) {
      // 라운드가 끝났다 - 다음 요청은 '라운드 실행' 한 번이면 된다 (준비 점검은 그 안에서 돈다)
      const now = document.createElement('div');
      now.className = 'fc-hint-now';
      now.textContent = (f.manager && f.manager.round ? `R${f.manager.round} 은 끝났습니다` : '도는 라운드가 없습니다')
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

  const mg = f.manager;
  if (mg && mg.round) {
    const r = document.createElement('div');
    r.className = 'fc-hint';
    if (mg.state === 'launching') {
      r.textContent = `R${mg.round} 관리자를 띄우는 중입니다`;
    } else if (mg.state === 'running') {
      const ago = agoText(mg.last_event_at);
      r.textContent = `관리자 R${mg.round} 실행 중` + (ago ? ` · 마지막 사건 ${ago}` : ' · 아직 사건 없음');
    } else {
      r.textContent = `R${mg.round} 관리자: ${MGR_STATE_TEXT[mg.state] || show(mg.state)}` + (mg.ended ? ` (${fmtDateTime(mg.ended)})` : '');
    }
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
    const ageMin = (Date.now() - parseTime(prep.at)) / 60000;
    const old = Number.isFinite(ageMin) && ageMin > 30;      // 오래된 결과는 흐리게 (지금 상태가 아니다)
    const ago = !Number.isFinite(ageMin) ? '' : (ageMin < 90 ? `${Math.round(ageMin)}분 전` : (ageMin < 48 * 60 ? `${Math.round(ageMin / 60)}시간 전` : `${Math.round(ageMin / 1440)}일 전`));
    sum.textContent = `준비 점검 ${ageMin < 720 ? fmtTime(prep.at, { date: false }) : fmtDateTime(prep.at)}` + (ago ? ` (${ago})` : '')
      + ` - ${prep.ok ? '통과' : '막힘'}` + (failed.length ? ` (${failed.length}건 미통과)` : '');
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
  const running = runs.filter((r) => r && r.state === 'running' && r.role !== 'manager');
  const graphs = Array.isArray(data.graphs) ? data.graphs : [];
  const live = graphs.filter((g) => !graphFinished(g) && g.runner);
  if (live.length) {
    return `그래프 ${live.map((g) => g.id).join(', ')} 실행 중 · 작업자 ${running.length}개 가동`;
  }
  if (running.length) return `작업자 ${running.length}개 가동 중 (그래프 밖 단건 실행)`;
  return '직접 작업 중 (계획·검증·보고 작성) - 이 동안 작업자는 0개입니다';
}

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
  notePanel('mgr:' + cur.id, '관리자 ' + show(cur.label, ''), () => openManagerDetail(cur, all));
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
    const r = await api('/api/managers/' + encodeURIComponent(cur.id) + (all ? '?all=1' : ''));
    d = r.body;
    if (!r.res.ok || !d.ok) throw new Error(d.error || ('HTTP ' + r.res.status));
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
  const st = parseTime(s.started);
  const la = parseTime(d.last_activity);
  const isRun = s.status === 'running';
  meta.appendChild(detailMetaItem('상태', MGR_STATE_TEXT[s.session_state] || (isRun ? '실행 중' : show(s.status)) + (s.orphaned ? ' (감독 없이 도는 중)' : '')));
  meta.appendChild(detailMetaItem('시작', fmtDateTime(s.started)));
  meta.appendChild(detailMetaItem(isRun ? '경과' : '소요', Number.isFinite(st) ? fmtElapsed(((isRun ? Date.now() : (Number.isFinite(la) ? la : Date.now())) - st) / 1000) : '-'));
  meta.appendChild(detailMetaItem('마지막 사건', Number.isFinite(la) ? fmtDateTime(d.last_activity) + ` (${fmtElapsed((Date.now() - la) / 1000)} 전)` : '-'));
  meta.appendChild(detailMetaItem('단계', show(d.steps_total)));
  meta.appendChild(detailMetaItem('사건 기록', d.record_kb != null ? (d.record_kb >= 1024 ? (d.record_kb / 1024).toFixed(1) + 'MB' : d.record_kb + 'KB') : '-'));
  body.appendChild(meta);

  if (d.round) {
    const r = d.round;
    const rows = [{ head: '브리프', body: show(r.brief) }];
    if (r.at) rows.push({ head: '띄운 때', body: fmtDateTime(r.at) });
    if ((r.requests || []).length) rows.push({ head: '요청', body: r.requests.join(', ') });
    if ((r.projects || []).length) rows.push({ head: '프로젝트', body: r.projects.join(', ') });
    detailRows(body, `라운드 R${r.round} 기록 (rounds/R${r.round}/round.json)`, rows);
  }
  if (d.report) {
    const rsec = document.createElement('section');
    rsec.className = 'detail-section';
    const rh = document.createElement('h3');
    rh.textContent = '마지막 보고';
    rsec.appendChild(rh);
    rsec.appendChild(renderMarkdown(d.report));
    body.appendChild(rsec);
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

function appendPolicyChip(head, data) {
  const pol = fleetPolicy(data);
  const mg = (data.fleet || {}).manager;
  const t = pol && mg ? policyLabel(pol, mg.policy) : '';
  if (!t) return;
  const c = badge(t, 'neutral');
  c.classList.add('manager-policy');
  c.title = '이 라운드의 운영 방식';
  head.appendChild(c);
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
  const mg = (data.fleet || {}).manager;
  // 엔진이 관리자를 띄우는 중인데 세션 폴더가 아직 안 보이는 짧은 틈
  if (mg && mg.state === 'launching' && !(cur && cur.status === 'running')) {
    head.appendChild(mgrStateBadge('launching'));
    appendPolicyChip(head, data);
    const l = document.createElement('span');
    l.className = 'manager-label';
    l.textContent = show(mg.label || ('관리자 R' + mg.round));
    head.appendChild(l);
    box.appendChild(head);
    const w = document.createElement('div');
    w.className = 'manager-what';
    w.textContent = `R${mg.round} 관리자를 띄우는 중입니다`;
    box.appendChild(w);
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
  head.appendChild(mgrStateBadge(cur.session_state, cur.status));
  appendPolicyChip(head, data);
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
  what.textContent = isRun ? managerActivity(data)
    : '실행 중인 관리자 없음' + ((data.fleet || {}).idle ? ' - 라운드가 끝났습니다' : ' - 함대는 다음 라운드 대기(정지) 상태입니다');
  box.appendChild(what);

  if (isRun) {
    const act = document.createElement('div');
    act.className = 'manager-step';
    const la = parseTime(cur.last_activity);
    const idle = Number.isFinite(la) ? (Date.now() - la) / 1000 : null;
    const parts = [];
    if (idle !== null) parts.push('마지막 사건 ' + fmtElapsed(idle) + ' 전');
    if (cur.orphaned) parts.push('감독 없이 도는 중');
    if (cur.steps) parts.push(`${cur.steps}단계`);
    if (cur.last_step) parts.push('최근: ' + cur.last_step);
    act.textContent = parts.join(' · ');
    box.appendChild(act);
  }

  const meta = document.createElement('div');
  meta.className = 'manager-meta';
  const st = parseTime(cur.started);
  const up = parseTime(cur.updated);
  const parts = ['시작 ' + fmtDateTime(cur.started)];
  if (Number.isFinite(st)) {
    const end = isRun ? Date.now() : (Number.isFinite(up) ? up : Date.now());
    parts.push((isRun ? '경과 ' : '소요 ') + fmtElapsed((end - st) / 1000));
  }
  if (cur.record_kb !== null && cur.record_kb !== undefined) {
    parts.push('사건 기록 ' + (cur.record_kb >= 1024 ? (cur.record_kb / 1024).toFixed(1) + 'MB' : cur.record_kb + 'KB'));
  }
  const others = sessions.length - 1;
  if (others > 0) parts.push(`지난 세션 ${others}개`);
  if (m.error) parts.push('세션 조회 실패');
  meta.textContent = parts.join(' · ');
  meta.title = sessions.map((s) => `${s.label} - ${MGR_STATE_TEXT[s.session_state] || s.status} - ${fmtDateTime(s.started)}`).join('\n');
  if (sessions.length > 1) {
    meta.appendChild(document.createTextNode(' · '));
    meta.appendChild(linkButton('세션 목록', () => openManagerList(sessions)));
  }
  box.appendChild(meta);
}

// ---- 슬롯 관리 (2026-11-10, 태석님 지시) - 추가/변경/삭제, 모델은 fleet.toml 목록에서
async function loadModels(force = false) {
  if (state.models && !force) return state.models;
  try {
    state.models = (await api('/api/models')).body;
  } catch (err) {
    state.models = { ok: false, models: [], error: err && err.message ? err.message : String(err) };
  }
  return state.models;
}

async function slotRequest(url, payload) {
  const { res, body } = await api(url, payload);
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
      if (list.some((m) => m.key === alias)) continue;   // fleet.toml 이 이미 준 별칭은 아래 목록에서
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

function openSlotForm(existing, runId, isRunning) {
  const isNew = !existing;
  openPanel(isNew ? '슬롯 추가' : `슬롯 ${existing.slot}`, (body) => {
    if (runId) {
      const act = document.createElement('div');
      act.className = 'detail-actions';
      act.appendChild(linkButton(isRunning ? '지금 도는 실행 보기 →' : '마지막 실행 보기 →', () => openDetail(runId)));
      body.appendChild(act);
    }
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
    field('모델 (fleet.toml)', modelWrap);
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
      const removeSlot = async (force) => {
        del.disabled = true;
        const r = await slotRequest(`/api/slots/${existing.slot}/remove`, force ? { force: true } : {});
        if (r.ok) { closeDetail(); state.slotMsg = { ok: true, text: `${existing.slot} 삭제됨` + (r.body.notice ? ` · 관리자 통지 요청 ${r.body.notice} 생성` : '') }; await refresh(); return; }
        del.disabled = false;
        msg.textContent = r.body.error || '실패';
        msg.classList.add('is-error');
        // 미완 태스크가 있어 엔진이 거절하면 그 말 그대로 보이고, 그래도 지우려면 이 단추 하나 (확인창 없음)
        if (/끝나지 않은 태스크/.test(r.body.error || '') && !actions.querySelector('.slot-force')) {
          const fb = document.createElement('button'); fb.type = 'button'; fb.className = 'btn-danger slot-force'; fb.textContent = '강제로 지움';
          fb.addEventListener('click', () => { fb.remove(); removeSlot(true); });
          actions.appendChild(fb);
        }
      };
      del.addEventListener('click', () => {
        if (window.confirm(`${existing.slot} 을(를) 명부에서 지웁니다. 계속할까요?`)) removeSlot(false);
      });
      actions.appendChild(del);
    }
    form.appendChild(actions); form.appendChild(msg);
    let modelSel = null;
    const rebuildModels = (models, keepCurrent = true) => {
      modelWrap.textContent = '';
      const cur = !keepCurrent ? '' : (modelSel ? modelSel.value : (existing ? show(existing.model, '') : ''));
      modelSel = modelOptions(models, harnessSel.value, cur);
      modelWrap.appendChild(modelSel);
      if (models && models.ok === false) { const e = document.createElement('div'); e.className = 'hint is-error'; e.textContent = '모델 목록 실패: ' + show(models.error, ''); modelWrap.appendChild(e); }
      const src = document.createElement('div'); src.className = 'hint'; src.textContent = '출처: fleet.toml 의 공급자·모델. 하네스마다 받을 수 있는 공급자가 정해져 있습니다 (claude 는 Anthropic).'; modelWrap.appendChild(src);
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
    now.appendChild(r ? badge('실행 중', 'running') : badge('쉬는 중', 'idle'));
    if (r) {
      const sub = document.createElement('span');
      sub.className = 'sub';
      sub.textContent = show(r.label) + ' · ' + fmtElapsed(r.elapsed_sec);
      sub.title = show(r.label, '');
      now.appendChild(sub);
      const liveLine = lastEventText(r);
      if (liveLine) {
        const le = document.createElement('span');
        le.className = 'sub slot-last-event';
        le.textContent = liveLine;
        le.title = liveLine;
        now.appendChild(le);
      }
    }
    // 관리자가 라운드 중에 더한 슬롯 - 사람이 둔 것과 구분해 작은 칩 하나 (지우는 것은 관리자·사람 몫)
    let slotCell = mono(s.slot);
    if (s.origin === 'manager') {
      slotCell = document.createElement('div');
      slotCell.appendChild(mono(s.slot));
      const chip = badge('관리자 추가' + (s.round != null ? ' R' + s.round : ''), 'neutral');
      chip.className += ' slot-origin';
      chip.title = '라운드 관리자가 운영 방식의 한도 안에서 더한 슬롯';
      slotCell.appendChild(chip);
    }
    return [slotCell, now, show(s.harness), modelCell, show(s.role), plainText(s.note) || '-'];
  });
  const rowClasses = slots.map((s) => (running.has(s.slot) ? 'row-running' : ''));   // 색은 지금 도는 슬롯에만 (전에는 마지막 실행이 있으면 전부 칠했다)
  // 행을 누르면 그 슬롯의 패널(실행으로 가는 길 + 하네스·모델·역할 변경·삭제). 전에는 행은 마지막 실행을, 맨 끝 '변경' 단추는 슬롯을 열었다
  wrap.appendChild(newTable(['슬롯', '지금', '하네스', '모델', '역할', '비고'], rows, rowClasses, {
    className: 'slots-table',
    widths: ['52px', '160px', '92px', '230px', '200px', null],
    ellipsis: [3, 4, 5],
    rowOpen: slots.map((s, i) => ({ fn: () => openSlotForm(s, runIds[i], running.has(s.slot)), title: `슬롯 ${s.slot} - 실행 보기 · 변경` })),
  }));
  const bar = document.createElement('div');
  bar.className = 'slot-bar';
  bar.appendChild(linkButton('+ 슬롯 추가', () => openSlotForm(null)));
  if (state.slotMsg) {
    const m = document.createElement('span'); m.className = 'slot-msg' + (state.slotMsg.ok ? '' : ' is-error'); m.textContent = state.slotMsg.text; bar.appendChild(m);
    setTimeout(() => { if (state.slotMsg && state.slotMsg.text === m.textContent) { state.slotMsg = null; } }, 8000);
  }
  wrap.appendChild(bar);
}

const RUNS_PAGE = window.matchMedia('(max-width: 720px)').matches ? 8 : 20;   // 폰에서는 행이 카드라 20건이면 화면 열 장이다

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
    const liveLine = lastEventText(r);
    if (liveLine) {
      const le = document.createElement('span');
      le.className = 'sub run-last-event';
      le.textContent = liveLine;
      what.appendChild(le);
    }
    what.title = `${show(r.label, '')}\n${show(r.id, '')}` + (liveLine ? '\n' + liveLine : '');
    return [
      r.role === 'manager' ? '관리자' : mono(r.slot),
      runStatusBadge(r),
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
    widths: ['52px', '80px', '116px', '130px', '250px', '96px', '40px', null],
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

// 보드 칸은 엔진이 그래프 노드 상태를 따라 직접 고친다(running→IN-PROGRESS, done→REVIEW, failed·blocked→BLOCKED).
// DONE·REJECTED 만 관리자의 판정 - 그 둘만 '닫힘'. REVIEW 는 끝났고 관리자 판정을 기다리는 상태다.
const boardClosed = (b) => ['DONE', 'REJECTED'].includes(String(b.status || '').toUpperCase());
const BOARD_FILTERS = [
  { key: 'open', label: '미완료', test: (b) => !boardClosed(b) },
  { key: 'done', label: '완료', test: (b) => String(b.status || '').toUpperCase() === 'DONE' },
  { key: 'all', label: '전체', test: () => true },
];

// ---- 끝난 것 정리 (아카이브, 2026-11-10) - 8.0 보관·폐기를 웹에서. 미리보기(dry_run) → 실행 (미리보기가 곧 확인)
async function archiveRequest(days, dryRun) {
  const { res, body } = await api('/api/archive', { days, dry_run: dryRun });
  return { ok: res.ok && body.ok !== false, body };
}

function openArchivePanel() {
  openPanel('끝난 것 정리 (아카이브)', (body) => {
    const intro = document.createElement('p');
    intro.className = 'hint archive-intro';
    intro.textContent = '끝난 일을 .aimem/archive/ 로 옮깁니다 (지우지 않음). 미리보기로 목록을 먼저 확인합니다.';
    body.appendChild(intro);
    const row = document.createElement('div'); row.className = 'slot-actions archive-actions';
    const sel = document.createElement('select');
    for (const [v, t] of [[0, '지금 끝난 것 전부'], [7, '7일 지난 것'], [14, '14일 지난 것 (관리자 자동 정리와 같음)']]) { const o = document.createElement('option'); o.value = String(v); o.textContent = t; sel.appendChild(o); }
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
        line.textContent = `이벤트 ${counts.events || 0}건 · 핸드오프 ${counts.handoff || 0}건 · 로그 ${counts.log_lines || 0}줄`;
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
      chip.textContent = `${f.label} ${all.filter((b) => f.test(b, data)).length}`;
      chip.addEventListener('click', () => {
        state.boardFilter = f.key;
        if (state.data) renderBoard(state.data);
      });
      filterBox.appendChild(chip);
    }
  }
  const filter = BOARD_FILTERS.find((f) => f.key === state.boardFilter) || BOARD_FILTERS[0];
  const board = all.filter((b) => filter.test(b, data)).slice().reverse();   // 최신 태스크가 위
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
      const verdictOnly = String(run.state || '').toLowerCase() === 'done' && reportStatus(run.report_head);   // 끝난 실행은 보고 판정만 (done · DONE 이 겹쳐 보였다)
      // 상태 칸이 이미 같은 말('진행 중')을 하고 있으면 여기서는 되풀이하지 않는다 - 칩 둘이 나란히 찍혔다 (2026-11-12 태석님)
      const sameAsStatus = statusLabel(run.state) === statusLabel(b.status, BOARD_LABEL);
      if (!verdictOnly && !sameAsStatus) { line.appendChild(statusBadge(run.state)); line.appendChild(document.createTextNode(' ')); }
      if (reportStatus(run.report_head)) line.appendChild(reportBadge(run.report_head));
      if (line.childNodes.length) last.appendChild(line);
      const sub = document.createElement('span');
      sub.className = 'sub';
      sub.textContent = fmtDateTime(run.started).slice(5) + ' · ' + fmtElapsed(run.elapsed_sec);
      last.appendChild(sub);
    }
    return [
      mono(b.id),
      plainText(b.task) || '-',
      show(b.slot),
      boardBadge(b.status),
      last,
      plainText(b.artifact) || '-',
    ];
  });
  const table = newTable(['ID', '작업', '슬롯', '상태', '최근 실행', '산출물'], rows, null, {
    widths: ['76px', null, '64px', '124px', '190px', '200px'],   // 제목 칸이 남는 폭을 다 쓴다 (전에는 빈 '산출물' 칸이 넓고 제목이 잘렸다)
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
    wrap.appendChild(emptyP('대기 큐 비어 있음 - 남은 후속 일이 없습니다'));
    return;
  }
  const rows = queue.map((q) => [
    show(q.order),
    plainText(q.task) || '-',
    show(q.slots),
    show(q.handoff),
    plainText(q.note) || '-',
  ]);
  // 칸 이름 (2026-11-12 태석님: 설명·명칭을 명확하게) - '핸드오프' 칸은 실제로는 이 일이 나온 태스크였다
  wrap.appendChild(newTable(['순서', '할 일', '추천 슬롯', '출처 태스크', '비고'], rows, null, {
    widths: ['56px', null, '110px', '110px', '240px'],
    num: [0],
    ellipsis: [1, 4],
    rowOpen: queue.map((q) => ({ fn: () => openQueueDetail(q, state.data), title: '대기 큐 항목 전문 보기' })),
  }));
}

function fmtGraphPct(value) {
  if (value === null || value === undefined) return '-';
  return fmtPct(value);
}

function fmtGraphEta(value) {
  if (value === null || value === undefined || value === '') return '-';
  const n = Number(value);
  return Number.isFinite(n) ? fmtElapsed(n) : show(value);
}

function graphFinished(g) {
  const nodes = Array.isArray(g.nodes) ? g.nodes : [];
  if (!nodes.length) return Number(g.percent) >= 100;
  return nodes.every((n) => ['done', 'failed', 'blocked'].includes(String(n.status || '').toLowerCase()));
}

function graphArchivable(g) {
  const nodes = Array.isArray(g.nodes) ? g.nodes : [];
  if (!nodes.length) return false;
  return nodes.every((n) => ['done', 'failed', 'blocked'].includes(String(n.status || '').toLowerCase()));
}

// 생략(...)된 글을 눌러서 그 자리에 펼친다 - 폰에는 호버가 없어 title 을 볼 길이 없다 (요청 Q-261111-2e0f).
// 표의 칸뿐 아니라 태스크 그래프 제목처럼 표 밖의 생략된 글에도 쓴다 (2026-11-12: 그래프 제목이 빠져 있었다).
function makeElidable(el, full) {
  el.classList.add('elide');
  el.title = full || '';
  if (!full || full === '-') return;
  el.tabIndex = 0;
  el.setAttribute('role', 'button');
  el.setAttribute('aria-expanded', 'false');
  el.setAttribute('aria-label', '전문 보기: ' + full);
  const toggleFull = (event) => {
    // 잘리지 않은 글은 펼칠 것이 없다 - 누름을 행(상세 보기)에 넘긴다 (좁은 화면 카드에서는 제목이 다 보인다)
    if (!el.classList.contains('elide-open') && el.scrollWidth <= el.clientWidth + 1 && el.scrollHeight <= el.clientHeight + 1) return;
    event.preventDefault();
    event.stopPropagation();          // 행 전체의 '상세 보기' 가 같이 열리지 않게
    const open = el.classList.toggle('elide-open');
    el.setAttribute('aria-expanded', open ? 'true' : 'false');
  };
  el.addEventListener('click', toggleFull);
  el.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' || event.key === ' ') toggleFull(event);
  });
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

// ---- 그래프 노드의 새 상태 (공급자 대기·기반 장애, 2026-11-13) ----
const INFRA_HINT = '태스크 잘못이 아닙니다 - 공급자가 돌아오면 unblock';
const FAIL_KIND_LABEL = { work: '작업 실패', infra: '공급자 장애', limit: '사용 한도', timeout: '시간 초과' };
// "provider:kisti" -> {kind, name}. 모르는 꼴이면 null (조용히 안 보여 준다)
function parseWaiting(raw) {
  const m = /^(provider|probe|slot):(.+)$/.exec(String(raw || ''));
  return m ? { kind: m[1], name: m[2] } : null;
}
function waitingNote(n) {
  const w = parseWaiting(n && n.waiting);
  if (!w) return '';
  const label = { provider: '공급자 대기', probe: '공급자 응답 대기', slot: '슬롯 대기' }[w.kind];
  return `${label} (${w.name})`;
}
function nodeIsInfra(n) { return !!(n && n.infra && String(n.status || '').toLowerCase() === 'blocked'); }
function nodeStatusBadge(n) {
  if (nodeIsInfra(n)) {
    const b = statusBadge('infra');
    b.title = INFRA_HINT;
    return b;
  }
  return statusBadge(n.status);
}
// 노드 옆 조용한 메모들 (대기 까닭 · 장애 안내 · 장애 재시도 횟수). 없으면 빈 배열
function nodeNotes(n) {
  const out = [];
  const w = String(n.status || 'todo').toLowerCase() === 'todo' ? waitingNote(n) : '';
  if (w) out.push({ text: w, cls: 'is-waiting' });
  if (nodeIsInfra(n)) out.push({ text: INFRA_HINT, cls: 'is-infra' });
  if (n.infra_attempts > 0) out.push({ text: `장애 재시도 ${n.infra_attempts}`, cls: 'is-infra-count' });
  return out;
}
function graphNotes(nodes) {
  const items = [];
  for (const n of nodes) for (const note of nodeNotes(n)) items.push([n, note]);
  if (!items.length) return null;
  const box = document.createElement('ul');
  box.className = 'graph-notes';
  for (const [n, note] of items) {
    const li = document.createElement('li');
    li.className = 'graph-note ' + note.cls;
    li.dataset.node = show(n.id, '');
    const id = document.createElement('span');
    id.className = 'mono';
    id.textContent = show(n.id, '');
    li.appendChild(id);
    li.appendChild(document.createTextNode(' ' + note.text));
    box.appendChild(li);
  }
  return box;
}
// 도는 그래프들의 한 줄 요약: 공급자별 자리 대기, 공급자 장애로 멈춘 노드
function graphWaitSummary(graphs) {
  const byProv = new Map();
  let infra = 0;
  for (const g of graphs) {
    if (graphFinished(g) || !g.runner) continue;   // 실행기가 잡고 있는 그래프만 '대기' 를 말한다
    for (const n of (Array.isArray(g.nodes) ? g.nodes : [])) {
      if (!n) continue;
      const w = parseWaiting(n.waiting);
      if (w && w.kind === 'provider' && String(n.status || 'todo').toLowerCase() === 'todo') byProv.set(w.name, (byProv.get(w.name) || 0) + 1);
      if (nodeIsInfra(n)) infra += 1;
    }
  }
  const lines = [];
  for (const [name, k] of byProv) lines.push({ text: `공급자 ${name} 자리 대기 ${k}건`, cls: 'is-waiting' });
  if (infra) lines.push({ text: `공급자 장애로 멈춘 노드 ${infra}건`, cls: 'is-infra' });
  return lines;
}
function attemptList(n) {
  const log = Array.isArray(n.attempt_log) ? n.attempt_log : [];
  if (!log.length) return null;
  const ol = document.createElement('ol');
  ol.className = 'attempt-list';
  for (const a of log) {
    const li = document.createElement('li');
    li.className = 'attempt-item';
    const bits = [];
    bits.push(FAIL_KIND_LABEL[a.fail_kind] || (a.fail_kind ? String(a.fail_kind) : '성공 또는 실행 중'));
    if (a.session_state) bits.push(`세션 ${a.session_state}`);
    if (a.provider) bits.push(a.provider);
    const head = document.createElement('span');
    head.className = 'attempt-kind' + (a.fail_kind ? ' is-' + a.fail_kind : '');
    head.textContent = bits.join(' · ');
    li.appendChild(mono(a.run_id));
    li.appendChild(document.createTextNode(' '));
    li.appendChild(head);
    if (a.why) {
      const why = document.createElement('div');
      why.className = 'attempt-why';
      why.textContent = plainText(a.why);
      li.appendChild(why);
    }
    ol.appendChild(li);
  }
  return ol;
}

// 그래프가 도는지는 엔진이 안다 - 실행기 프로세스가 그래프를 잡고 있나(runner). 시각으로 짐작하지 않는다.
// runner 가 없거나(null=모름 포함) 못 읽었으면 '실행기 없음'
function graphRunning(g) {
  return !!(g && g.runner === true);
}

function graphStateBadge(g, finished) {
  const counts = g.counts || {};
  if (finished) {
    if (!(counts.failed || counts.blocked)) return badge('완료', 'done');
    return counts.done ? badge('일부 실패', 'partial') : badge('실패', 'failed');   // 끝난 것이 0 인데 '부분 완료' 라고 적혀 실패를 놓쳤다
  }
  if (graphRunning(g)) return badge('실행 중', 'running');
  const span = badge('실행기 없음', 'stale');
  span.title = '끝나지 않았는데 그래프를 돌리는 실행기가 없습니다 - 함대의 재개로 이어 돌립니다';
  return span;
}

function graphBlock(g) {
  const key = show(g.id, '');
  const finished = graphFinished(g);
  if (!state.graphKnown.has(key)) {
    state.graphKnown.add(key);
    if (!finished) state.graphOpen.add(key);   // 끝나지 않은 그래프만 펼친 채로 시작
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
  req.className = 'graph-title';
  req.textContent = plainText(g.request) || '-';
  makeElidable(req, plainText(g.request) || '');
  if (state.graphTitleOpen && state.graphTitleOpen.has(key)) { req.classList.add('elide-open'); req.setAttribute('aria-expanded', 'true'); }
  req.addEventListener('click', () => {            // 5초마다 다시 그려도 펼친 제목이 접히지 않게 기억한다
    if (!state.graphTitleOpen) state.graphTitleOpen = new Set();
    if (req.classList.contains('elide-open')) state.graphTitleOpen.add(key); else state.graphTitleOpen.delete(key);
  });
  head.appendChild(req);
  const pct = document.createElement('span');
  pct.className = 'graph-meta';
  pct.textContent = fmtGraphPct(g.percent) + (finished || !graphRunning(g) ? '' : ' · 남은 ' + fmtGraphEta(g.eta_seconds));
  head.appendChild(pct);
  head.appendChild(graphStateBadge(g, finished));
  block.appendChild(head);

  const counts = g.counts || {};
  const meta = document.createElement('div');
  meta.className = 'graph-counts';
  const parts = [];
  const infraN = (Array.isArray(g.nodes) ? g.nodes : []).filter(nodeIsInfra).length;   // 공급자 장애는 '막힘' 과 따로 센다
  const shown = Object.assign({}, counts, { blocked: (counts.blocked || 0) - infraN, infra: infraN });
  for (const [k, label] of [['done', '완료'], ['running', '실행 중'], ['todo', '할 일'], ['failed', '실패'], ['blocked', '막힘'], ['infra', '공급자 장애']]) {
    if (shown[k] > 0) parts.push(`${label} ${shown[k]}`);
  }
  if (g.updated) parts.push('갱신 ' + fmtDateTime(g.updated));
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
        nodeStatusBadge(n),
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
        widths: ['76px', null, '64px', '90px', '170px', '60px', '200px'],
        num: [5],
        center: [3],
        ellipsis: [1, 4, 6],
        rowRunIds: runIds,
        rowOpen: openers,
      });
      markUnopenableRows(table, runIds.map((id, i) => id || (openers[i] ? 'task' : null)));
      tw.appendChild(table);
      block.appendChild(tw);
      const notes = graphNotes(nodes);
      if (notes) block.appendChild(notes);
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
    if (state.showClosedGraphs) {
      for (const g of closed) list.appendChild(graphBlock(g));
      // 펼친 목록은 수천 px 다 - 끝에서도 접을 수 있게 한다
      if (closed.length > 3) list.appendChild(closedFoldButton(true, closed.length, () => {
        state.showClosedGraphs = false;
        if (state.data) renderGraphs(state.data);
        const sec = $('graphs-section'); if (sec) sec.scrollIntoView({ block: 'start' });
      }));
    }
  }
}

function progressOf(req) {
  const subs = Array.isArray(req.subtasks) ? req.subtasks : [];
  if (!subs.length) return null;
  const n = Number(req.progress_pct);
  return req.progress_pct !== null && req.progress_pct !== undefined && Number.isFinite(n) ? n : null;
}

// 남은 시간 한 줄 - 없으면 '-'
function etaText(req) {
  const n = Number(req.eta_sec);
  return req.eta_sec === null || req.eta_sec === undefined || req.eta_sec === '' || !Number.isFinite(n) ? '-' : '남은 ' + fmtElapsed(n);
}

const REQ_CLOSED = new Set(['DONE', 'REJECTED']);

// 끝난 요청·정리할 수 있는 그래프 - 요청 탭 머리글과 '정리' 단추 숫자가 같이 쓴다
function closedItems(data) {
  return {
    requests: (Array.isArray(data.requests) ? data.requests : []).filter((r) => REQ_CLOSED.has(String(r.status || '').toUpperCase())),
    graphs: (Array.isArray(data.graphs) ? data.graphs : []).filter(graphArchivable),
  };
}

function canEditRequest(req) {
  return String(req.status || '').toUpperCase() === 'NEW'
    && !(Array.isArray(req.subtasks) && req.subtasks.length);
}

async function saveRequestEdit(req, form) {
  const msg = form.querySelector('.form-msg');
  const title = form.querySelector('input').value.trim();
  const detail = form.querySelector('textarea').value;
  const pickEl = form.querySelector('.req-edit-project-pick');
  const newEl = form.querySelector('.req-edit-project');
  const project = (pickEl && pickEl.value === '__new__')
    ? (newEl ? newEl.value.trim() : '')
    : ((pickEl && pickEl.value) || '').trim();
  if (!title) { msg.textContent = '제목은 비워 둘 수 없습니다'; msg.className = 'form-msg error'; return; }
  const buttons = form.querySelectorAll('button');
  buttons.forEach((b) => { b.disabled = true; });
  msg.textContent = '저장 중…'; msg.className = 'form-msg';
  try {
    const { res, body } = await api('/api/requests/' + encodeURIComponent(req.id) + '/edit', pickEl ? { title, detail, project } : { title, detail });
    if (!res.ok || !body.ok) throw new Error(body.error || ('HTTP ' + res.status));
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
  const ps = document.createElement('select');
  ps.className = 'req-edit-project-pick';
  const pi = document.createElement('input');
  pi.type = 'text'; pi.className = 'req-edit-project'; pi.maxLength = 40;
  pi.placeholder = '새 프로젝트 이름'; pi.hidden = true;
  fillProjectPicker(ps, pi, projectNameList(state.data), req.project || '');
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
  form.append(tl, ti, pl, ps, pi, dl, ta, row);
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
    const { requests: closedRequests, graphs: closedGraphs } = closedItems(data);
    const label = document.createElement('span');
    if (!closedRequests.length && !closedGraphs.length) {
      label.textContent = '끝난 요청 없음';
    } else {
      label.textContent = (closedRequests.length ? `끝난 요청 ${closedRequests.length}건` : '끝난 요청 없음')
        + ` · 끝난 그래프 ${closedGraphs.length}개`;
    }
    tools.appendChild(label);
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
        : '아직 분담 전 - 관리자가 서브태스크로 나누면 진행률과 남은 시간이 나옵니다';
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
      etaLabel.textContent = eta === '-' ? '남은 시간 미정' : eta;
      progressRow.appendChild(bar);
      progressRow.appendChild(pctLabel);
      progressRow.appendChild(etaLabel);
      article.appendChild(progressRow);

      const basis = document.createElement('div');
      basis.className = 'req-basis';
      basis.textContent = '남은 시간 근거: ' + show(req.eta_basis, '근거 없음');
      article.appendChild(basis);
    }

    const body = document.createElement('div');
    body.className = 'req-body';
    body.hidden = !open;
    if (!subtasks.length) {
      // 진행 중이면 위의 안내 줄(req-wait-line)이 같은 말을 한다 - 펼쳤을 때 두 번 적지 않는다 (2026-11-12)
      const emptyText = String(req.status || '').toUpperCase() === 'IN-PROGRESS' ? '' : subtaskEmptyText(req);
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
          if (statusLabel(run.state) !== statusLabel(st.status, BOARD_LABEL)) {   // 상태 칸과 같은 말이면 되풀이하지 않는다
            link.appendChild(document.createTextNode(' '));
            link.appendChild(statusBadge(run.state));
          }
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
          boardBadge(st.status),
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
          widths: ['76px', null, '64px', '90px', '100px', '90px', '200px'],
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
    if (state.showClosedRequests) {
      closedRequests.forEach(drawRequest);
      if (closedRequests.length > 3) list.appendChild(closedFoldButton(true, closedRequests.length, () => {
        state.showClosedRequests = false;
        if (state.data) renderRequests(state.data);
        const sec = $('requests-section'); if (sec) sec.scrollIntoView({ block: 'start' });
      }));
    }
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
    wrap.appendChild(emptyP('라운드 핸드오프 로그 없음'));
    return;
  }
  const log = state.logShowAll ? all : all.slice(0, LOG_PAGE);
  const rows = log.map((e) => [show(e.when), plainText(e.text) || '-']);
  wrap.appendChild(newTable(['시각', '내용'], rows, null, {
    widths: ['158px', null],      // 'YYYY-MM-DD HH:MM' 이 잘리지 않게 (2026-11-12 데스크톱 검수)
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
  const running = runs.filter((r) => r && r.state === 'running' && r.role !== 'manager').length;   // 작업자만 (관리자는 따로 카드)
  setTabCount('tab-count-fleet', running, true);
  const projects = Array.isArray(data.projects) ? data.projects : [];
  const unfinished = projects.filter((p) => !projectDone(p)).length;
  // 네 탭 모두 같은 규칙: 숫자 = 그 탭에서 지금 살아 있는 것(도는 작업자 / 진행 중 프로젝트 / 미완료 태스크+큐 / 열린 요청), 0 이면 숨김.
  // 전에는 프로젝트만 전체 수라 다 끝나도 늘 1 이 떠 있었다 (2026-11-12 저녁 태석님: 직접 처리)
  setTabCount('tab-count-projects', unfinished, true);
  // 보드·큐 탭의 숫자 = 미완료 태스크만 (대기 큐 건수는 큐 머리글에 따로)
  const queue = Array.isArray(data.queue) ? data.queue.length : 0;
  const openTasks = (Array.isArray(data.board) ? data.board : []).filter((t) => !boardClosed(t)).length;
  setTabCount('tab-count-board', openTasks, true);
  const qc = $('queue-count');
  if (qc) qc.textContent = queue ? String(queue) : '';
  const reqs = Array.isArray(data.requests) ? data.requests : [];
  const active = reqs.filter((r) => !REQ_CLOSED.has(String(r.status || '').toUpperCase())).length;
  setTabCount('tab-count-requests', active, true);
  const f = $('tab-count-fleet');
  if (f) f.title = '실행 중인 작업자';
  const pj = $('tab-count-projects');
  if (pj) pj.title = `진행 중인 프로젝트 ${unfinished}개 (전체 ${projects.length}개)`;
  const b = $('tab-count-board');
  if (b) b.title = `미완료 태스크 ${openTasks}건`;
  const q = $('tab-count-requests');
  if (q) q.title = '끝나지 않은 요청';
  const { requests: closedRequests, graphs: closedGraphs } = closedItems(data);
  setTabCount('archive-count', closedRequests.length + closedGraphs.length, false);
  const archBtn = $('archive-open');
  if (archBtn) archBtn.title = `끝난 요청 ${closedRequests.length}건 · 끝난 그래프 ${closedGraphs.length}개를 아카이브로 옮깁니다 (지우지 않음)`;
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
  const { res, body } = await api('/api/projects/' + encodeURIComponent(name) + tail);
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
        const d = await projectApi(name, '/files');
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
    tab.textContent = '새 탭에서 열기 ↗';
    tab.className = 'btn-link link-btn';
    tab.title = '더 큰 화면으로 봅니다. 여기서도 격리되어 새 탭에서는 기록이 남지 않습니다';
    body.appendChild(tab);

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

// 프로젝트가 끝났나 - 탭 숫자와 필터가 같은 기준을 쓴다 (목표가 있으면 목표, 없으면 요청 진행률)
function projectDone(p) {
  const g = p && p.goals;
  if (g && g.total) return g.done >= g.total;
  return Number(p && p.percent) >= 100;
}

const PROJECT_FILTERS = [
  { key: 'active', label: '진행 중', test: (p) => !projectDone(p) },
  { key: 'done', label: '끝남', test: (p) => projectDone(p) },
  { key: 'all', label: '전체', test: () => true },
];
const PROJECT_SEARCH_MIN = 7;     // 이보다 많으면 이름 찾기 칸을 보인다

function renderProjects(data) {
  const box = document.getElementById('projects-list');
  if (!box) return;
  const all = Array.isArray(data.projects) ? data.projects : [];
  box.replaceChildren();
  const chips = document.getElementById('projects-filter-chips');
  const search = document.getElementById('projects-search');
  if (chips) chips.replaceChildren();
  if (search) {
    search.hidden = all.length < PROJECT_SEARCH_MIN;
    if (!search.dataset.bound) {
      search.dataset.bound = '1';
      search.addEventListener('input', () => { if (state.data) renderProjects(state.data); });
    }
  }
  if (!all.length) {
    const p = document.createElement('p');
    p.className = 'empty';
    p.textContent = "아직 프로젝트가 없습니다. '작업 요청' 의 프로젝트 칸에 이름을 적어 보내면 생깁니다.";
    box.appendChild(p);
    return;
  }
  // 필터 칩 (작업 보드의 미완료/완료/전체와 같은 꼴). 처음에는 진행 중이 있으면 진행 중을 보인다
  const fkey = state.projectFilter || (all.some((p) => !projectDone(p)) ? 'active' : 'all');
  if (chips) {
    for (const f of PROJECT_FILTERS) {
      const chip = document.createElement('button');
      chip.type = 'button';
      chip.className = 'chip';
      chip.setAttribute('aria-pressed', String(fkey === f.key));
      chip.textContent = `${f.label} ${all.filter(f.test).length}`;
      chip.addEventListener('click', () => { state.projectFilter = f.key; if (state.data) renderProjects(state.data); });
      chips.appendChild(chip);
    }
  }
  const filter = PROJECT_FILTERS.find((f) => f.key === fkey) || PROJECT_FILTERS[2];
  const q = search && !search.hidden ? search.value.trim().toLowerCase() : '';
  // 진행 중 먼저, 그 안에서는 최근에 움직인 것 먼저
  const recent = (p) => Math.max(Number(p.last_round) || 0, 0) * 1e12 + (parseTime(p.updated) || 0) / 1000;
  const list = all.filter(filter.test)
    .filter((p) => !q || String(p.name || '').toLowerCase().includes(q))
    .sort((a, b) => (projectDone(a) - projectDone(b)) || (recent(b) - recent(a)));
  if (!list.length) {
    box.appendChild(emptyP(q ? `'${q}' 에 맞는 프로젝트가 없습니다` : '이 필터에 해당하는 프로젝트가 없습니다'));
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
    name.title = show(pr.path, '');
    head.appendChild(name);
    if (projectDone(pr)) {
      const done = document.createElement('span');
      done.className = 'badge badge-done';
      done.textContent = '끝남';
      head.appendChild(done);
    }
    const actions = document.createElement('div');
    actions.className = 'proj-actions';
    head.appendChild(actions);
    const rq = pr.requests || {};
    const meta = document.createElement('div');
    meta.className = 'proj-meta proj-sub';
    const bits = [];
    bits.push(rq.total ? `요청 ${rq.done || 0}/${rq.total} 완료` : '요청 없음');
    if (rq.active) bits.push(`처리 중 ${rq.active}`);
    if (rq.new) bits.push(`대기 ${rq.new}`);
    const rounds = Array.isArray(pr.rounds) ? pr.rounds : [];
    bits.push(rounds.length
      ? `라운드 ${rounds.length}회 (${rounds.length > 6 ? 'R' + rounds[0] + ' … R' + rounds[rounds.length - 1] : rounds.map((n) => 'R' + n).join(' · ')})`
      : '아직 라운드 없음');
    meta.textContent = bits.join(' · ');
    // '실행' 은 함대 모드 '실행' 과 헷갈려 '앱 열기' 로 (2026-11-12)
    if (pr.app && pr.app.runnable) {
      const run = linkButton('앱 열기 ▶', () => openProjectApp(pr));
      run.classList.add('proj-run');
      run.title = `${pr.app.title} 을(를) 모니터 안에서 바로 돌려 봅니다 (projects/${pr.name}/${pr.app.root}/)`;
      actions.appendChild(run);
    }
    if (pr.exists) {
      const view = linkButton('결과물 보기', () => openProjectFiles(pr));
      view.classList.add('proj-view');
      view.title = `projects/${show(pr.name, '')}/ 의 파일 목록과 본문`;
      actions.appendChild(view);
    }
    item.appendChild(head);
    item.appendChild(meta);
    if (pr.app && !pr.app.runnable) {
      const bad = document.createElement('div');
      bad.className = 'proj-meta warn-text';
      bad.textContent = '앱 실행 선언(app.json)에 문제가 있습니다: ' + show(pr.app.reason, '이유 없음');
      item.appendChild(bad);
    }
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
      label.textContent = typeof pr.percent === 'number' ? `요청 기준 ${Math.round(pct)}%` : '목표·요청 없음';
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

// 옆으로 밀어야 보이는 표에 표시 (2026-11-12 모바일 검수) - 폰에서는 칸 절반이 화면 밖인데 단서가 없었다
function markScrollableTables() {
  for (const w of document.querySelectorAll('.tablewrap')) {
    const update = () => {
      const more = w.scrollWidth - w.clientWidth > 4;
      w.classList.toggle('is-scrollable', more);
      w.classList.toggle('at-end', !more || w.scrollLeft + w.clientWidth >= w.scrollWidth - 4);
    };
    if (!w.dataset.scrollHint) {
      w.dataset.scrollHint = '1';
      w.addEventListener('scroll', update, { passive: true });
    }
    update();
  }
}
window.addEventListener('resize', () => markScrollableTables());

function renderAll(data) {
  setTimeZone(data && data.tz);
  renderErrors(data);
  renderTabCounts(data);
  renderFleetControl(data);
  renderClaudeUsage(data);
  renderProjectPicker(data);
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
  markScrollableTables();
}

async function fetchState() {
  const { res, body } = await api('/api/state');
  if (res.status === 401) {
    // 세션 만료·토큰 교체 - 로그인 화면으로 (인증이 켜진 서버에서만 생긴다)
    location.href = '/login';
    throw new Error('로그인이 필요합니다');
  }
  if (!res.ok) {
    throw new Error(`GET /api/state ${res.status} ${res.statusText || ''}`.trim());
  }
  return body;
}

function updateLastRefresh() {
  const el = $('refresh-status');
  if (!el) return;
  if (state.error) {
    el.classList.add('is-error');
    el.textContent = '갱신 실패';
    el.title = '갱신 실패: ' + state.error;
    return;
  }
  el.classList.remove('is-error');
  if (!state.fetchedAt) {
    el.textContent = '마지막 갱신 -';
    return;
  }
  const seconds = Math.max(0, Math.floor((Date.now() - state.fetchedAt) / 1000));
  // '마지막 갱신' 은 좁은 화면에서 숨긴다 (2026-11-12 모바일 검수: 세 줄로 꺾여 상단 바를 키웠다)
  const lab = document.createElement('span');
  lab.className = 'rs-label';
  lab.textContent = '마지막 갱신 ';
  el.replaceChildren(lab, document.createTextNode(`${seconds}초 전`));
  el.title = `마지막 갱신 ${seconds}초 전`;
}

// 불러오기 실패를 본문 위에 크게 알린다 - 전에는 상단 바의 작은 영문('Failed to fetch') 한 줄뿐이라 빈 카드만 보였다
function showLoadError() {
  let box = $('load-error');
  if (!state.error) { if (box) box.hidden = true; return; }
  if (!box) {
    box = document.createElement('div');
    box.id = 'load-error';
    box.className = 'banner banner-errors load-error';
    box.setAttribute('role', 'alert');
    const layout = document.querySelector('.layout');
    if (layout && layout.parentNode) layout.parentNode.insertBefore(box, layout); else document.body.appendChild(box);
  }
  const why = /failed to fetch|networkerror|load failed/i.test(state.error) ? '서버에 연결할 수 없습니다' : state.error;
  const when = state.fetchedAt ? `아래 내용은 ${fmtTime(state.fetchedAt, { date: false, seconds: true })} 에 받은 것입니다.` : '아직 받은 자료가 없어 화면이 비어 있습니다.';
  box.textContent = '';
  const msg = document.createElement('div');
  const b = document.createElement('strong'); b.textContent = '자료를 불러오지 못했습니다';
  msg.appendChild(b);
  msg.appendChild(document.createTextNode(`${why}. ${when}`));
  const retry = document.createElement('button');
  retry.type = 'button'; retry.textContent = '다시 시도';
  retry.addEventListener('click', () => { refresh(); });
  box.appendChild(msg); box.appendChild(retry);
  box.hidden = false;
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
    showLoadError();
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
  const pickEl = $('req-project-pick');
  const projectEl = $('req-project');
  const project = (pickEl && pickEl.value === '__new__')
    ? ((projectEl && projectEl.value) || '').trim()
    : ((pickEl && pickEl.value) || '').trim();
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
    const { res, body } = await api('/api/requests', payload);
    if (!res.ok || body.ok === false) throw new Error(body.error || `POST /api/requests ${res.status} ${res.statusText || ''}`.trim());
    const result = body;
    $('request-form').reset();
    if (pickEl) pickEl.value = '';
    if (projectEl) { projectEl.value = ''; projectEl.hidden = true; }
    msg.className = 'form-msg success';
    msg.textContent = '요청 생성됨: ' + show(result.id, '-') +
      (project ? ` · 프로젝트 ${project}` : ' · 함대 자체') + ' ';
    // 다음 일(라운드 실행)은 함대 탭 맨 위에 있다 - 폰에서는 폼에서 수천 px 위라 길을 놓는다
    const go = document.createElement('button');
    go.type = 'button'; go.className = 'btn-link'; go.textContent = '함대 제어로 ↑';
    go.addEventListener('click', () => { selectTab('fleet', false); const fc = $('fleet-control'); if (fc) fc.scrollIntoView({ behavior: 'smooth', block: 'center' }); });
    msg.appendChild(go);
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

// 폰의 ⚙ 설정 메뉴 (2026-11-12) - 어두운 모드 · 로그인한 이름 · 로그아웃. 바깥을 누르거나 Esc 면 닫힌다
function initSettingsMenu() {
  const btn = $('settings-toggle');
  const menu = $('settings-menu');
  if (!btn || !menu) return;
  const set = (open) => {
    menu.classList.toggle('is-open', open);
    btn.setAttribute('aria-expanded', String(open));
  };
  btn.addEventListener('click', (e) => { e.stopPropagation(); set(!menu.classList.contains('is-open')); });
  document.addEventListener('click', (e) => {
    if (menu.classList.contains('is-open') && !menu.contains(e.target)) set(false);
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && menu.classList.contains('is-open')) { set(false); btn.focus(); }
  });
}

async function initAuth() {
  try {
    const info = (await api('/api/authinfo')).body;
    if (!info || !info.auth_required) return;      // 인증이 꺼진 로컬 서버 - 표시하지 않는다
    $('auth-who').textContent = info.who ? info.who : '';
    $('auth-box').hidden = false;
    $('logout').addEventListener('click', async () => {
      try {
        await api('/api/logout', {});
      } finally {
        location.href = '/login';
      }
    });
  } catch (err) {
    /* authinfo 를 못 읽어도 화면은 그대로 */
  }
}

// 상단 바의 실제 높이를 재서 탭 줄·옆 폼의 고정 위치에 쓴다 - 721~900px 에서는 상단 바가 두 줄이라 56px 고정값이면 탭 글자를 가렸다
function trackTopbarHeight() {
  const bar = document.querySelector('.topbar');
  if (!bar || typeof ResizeObserver !== 'function') return;
  const set = () => document.documentElement.style.setProperty('--topbar-h-live', Math.round(bar.getBoundingClientRect().height) + 'px');
  new ResizeObserver(set).observe(bar);
  set();
}

// 옆 폼이 아래로 내려간 화면(1360px 이하)에서 어느 탭·어느 자리에서든 작업 요청 폼으로 가는 단추. 폼이 보이는 동안은 숨는다
function initRequestFab() {
  const sec = $('request-form-section');
  if (!sec || typeof IntersectionObserver !== 'function') return;
  const fab = document.createElement('button');
  fab.type = 'button'; fab.id = 'req-fab'; fab.className = 'req-fab btn-primary';
  fab.textContent = '＋ 요청';
  fab.title = "'작업 요청' 폼으로 갑니다";
  fab.addEventListener('click', focusRequestForm);
  document.body.appendChild(fab);
  new IntersectionObserver((entries) => { fab.classList.toggle('is-hidden', entries[0].isIntersecting); }, { threshold: 0.05 }).observe(sec);
}

function init() {
  trackTopbarHeight();
  initRequestFab();
  initAuth();
  initTheme();
  initSettingsMenu();
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

  const archBtn = $('archive-open');
  if (archBtn) archBtn.addEventListener('click', openArchivePanel);

  $('request-form').addEventListener('submit', onSubmit);

  setInterval(updateLastRefresh, 1000);
  schedule();
  refresh();
}

init();

// --- 탭 전환 (Q-261110-549a) ---------------------------------------------
const TABS = [
  { tab: 'tab-fleet', panel: 'panel-fleet', key: 'fleet' },
  { tab: 'tab-projects', panel: 'panel-projects', key: 'projects' },
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
  markScrollableTables();               // 숨어 있던 패널의 표는 폭이 0 이라 보일 때 다시 잰다
  if (location.hash !== '#tab=' + target) {
    history.replaceState(null, '', '#tab=' + target);
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
if ('serviceWorker' in navigator && location.protocol === 'https:') {
  window.addEventListener('load', () => { navigator.serviceWorker.register('/sw.js').catch(() => null); });
}
