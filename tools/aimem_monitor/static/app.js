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
    if (runId) makeRowOpenable(trb, runId);
  });
  table.appendChild(tbody);
  return table;
}

function makeRowOpenable(tr, runId) {
  tr.classList.add('clickable-row');
  tr.tabIndex = 0;
  tr.title = '실행 상세 보기: ' + runId;
  tr.addEventListener('click', () => openDetail(runId));
  tr.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      openDetail(runId);
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
  const wrap = document.createElement('div');
  wrap.className = 'req-detail';
  wrap.textContent = show(req.detail, '본문 없음');   // 텍스트 그대로 둔다 (마크업 해석 없음)
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

function addDetailSection(parent, title, text) {
  const section = document.createElement('section');
  section.className = 'detail-section';
  const h3 = document.createElement('h3');
  h3.textContent = title;
  section.appendChild(h3);
  const pre = document.createElement('pre');
  pre.className = 'detail-pre';
  pre.textContent = show(text, '없음');
  section.appendChild(pre);
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
  addDetailSection(body, 'stderr 꼬리', detail.stderr_tail);
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

function renderMeta(data) {
  const box = $('aimem-meta');
  box.textContent = '';
  const aimem = data.aimem || {};
  const goal = aimem.goal || {};
  const goalWrap = document.createElement('div');
  goalWrap.className = 'goal-value';
  const goalText = document.createElement('span');
  goalText.textContent = show(goal.text, '-');
  goalWrap.appendChild(goalText);
  const goalStatus = document.createElement('span');
  goalStatus.className = 'goal-status';
  goalStatus.textContent = show(goal.status);
  goalWrap.appendChild(goalStatus);

  box.appendChild(metaItem('AIMEM REV', aimem.rev));
  box.appendChild(metaItem('최종 갱신', aimem.updated));
  box.appendChild(metaItem('줄 수', aimem.lines));
  box.appendChild(metaItem('현재 목표', goalWrap));
}

function renderSlots(data) {
  const wrap = $('slots-table-wrap');
  wrap.textContent = '';
  const slots = Array.isArray(data.slots) ? data.slots : [];
  if (!slots.length) {
    wrap.appendChild(emptyP('슬롯 명부 없음'));
    return;
  }
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
    return [
      mono(s.slot),
      show(s.harness),
      modelCell,
      show(s.role),
      show(s.note),
    ];
  });
  wrap.appendChild(newTable(['슬롯', '하네스', '모델', '역할', '비고'], rows, null, {
    widths: ['60px', '90px', '240px', '180px', '260px'],
    ellipsis: [2, 3, 4],
  }));
}

function renderRuns(data) {
  const wrap = $('runs-table-wrap');
  wrap.textContent = '';
  const runs = Array.isArray(data.runs) ? data.runs.slice() : [];
  runs.sort((a, b) => {
    const byStart = String(b.started || '').localeCompare(String(a.started || ''));
    if (byStart !== 0) return byStart;
    return String(b.id || '').localeCompare(String(a.id || ''));
  });
  if (!runs.length) {
    wrap.appendChild(emptyP('실행 기록 없음'));
    return;
  }
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
    head.textContent = show(r.report_head);
    head.title = show(r.report_head, '');
    const runIdCell = document.createElement('span');
    runIdCell.className = 'mono run-id-cell';
    runIdCell.textContent = show(r.id);
    return [
      mono(r.slot),
      runIdCell,
      show(r.harness),
      show(r.label),
      statusBadge(r.state),
      rc,
      fmtElapsed(r.elapsed_sec),
      head,
    ];
  });
  wrap.appendChild(newTable(['슬롯', 'run id', '하네스', '라벨', '상태', 'rc', '경과', '보고 머리말'], rows, rowClasses, {
    widths: ['60px', '190px', '80px', '180px', '100px', '60px', '100px', '390px'],
    num: [5, 6],
    center: [4],
    ellipsis: [3, 7],
    rowRunIds: runs.map((r) => r.id),
  }));
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

function renderBoard(data) {
  const wrap = $('board-table-wrap');
  wrap.textContent = '';
  const board = Array.isArray(data.board) ? data.board : [];
  if (!board.length) {
    wrap.appendChild(emptyP('보드 없음'));
    return;
  }
  const rows = board.map((b) => [
    mono(b.id),
    show(b.task),
    show(b.slot),
    statusBadge(b.status),
    show(b.handoff),
    show(String(b.artifact || '-').replace(/`/g, '')),
  ]);
  const rowRunIds = board.map((b) => resolveBoardRunId(b.id, data));
  const table = newTable(['ID', '작업', '슬롯', '상태', '핸드오프', '산출물'], rows, null, {
    widths: ['80px', '220px', '80px', '100px', '100px', '260px'],
    center: [3],
    ellipsis: [1, 5],
    rowRunIds,
  });
  markUnopenableRows(table, rowRunIds);
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
    show(q.task),
    show(q.slots),
    show(q.handoff),
    show(q.note),
  ]);
  wrap.appendChild(newTable(['순서', '작업', '슬롯', '핸드오프', '비고'], rows, null, {
    widths: ['60px', '240px', '100px', '100px', '400px'],
    num: [0],
    ellipsis: [1, 4],
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

function renderGraphs(data) {
  const list = $('graphs-list');
  list.textContent = '';
  const graphs = Array.isArray(data.graphs) ? data.graphs : [];
  if (!graphs.length) {
    list.appendChild(emptyP('진행 중인 태스크 그래프가 없습니다'));
    return;
  }

  for (const g of graphs) {
    const block = document.createElement('div');
    block.className = 'graph-block';

    const head = document.createElement('div');
    head.className = 'graph-head';
    const id = document.createElement('span');
    id.className = 'graph-id';
    id.textContent = show(g.id);
    head.appendChild(id);
    head.appendChild(document.createTextNode(' · '));
    const req = document.createElement('span');
    req.className = 'graph-title';
    req.textContent = show(g.request);
    req.title = show(g.request, '');
    head.appendChild(req);
    head.appendChild(document.createTextNode(' · '));
    const pct = document.createElement('span');
    pct.className = 'graph-meta';
    pct.textContent = fmtGraphPct(g.percent);
    head.appendChild(pct);
    head.appendChild(document.createTextNode(' · '));
    const eta = document.createElement('span');
    eta.className = 'graph-meta';
    eta.textContent = 'ETA ' + fmtGraphEta(g.eta_seconds);
    head.appendChild(eta);
    block.appendChild(head);

    const counts = g.counts || {};
    const meta = document.createElement('div');
    meta.className = 'graph-counts';
    meta.textContent = '완료 ' + show(counts.done, '-') +
      ' · 진행 ' + show(counts.running, '-') +
      ' · 대기 ' + show(counts.todo, '-') +
      (g.eta_at ? ' · 도착 ' + fmtDateTime(g.eta_at) : '');
    block.appendChild(meta);

    const nodes = Array.isArray(g.nodes) ? g.nodes : [];
    if (!nodes.length) {
      block.appendChild(emptyP('그래프 노드 없음'));
    } else {
      const rows = nodes.map((n) => [
        mono(n.id),
        show(n.title),
        show(n.slot),
        show(n.harness),
        statusBadge(n.status),
        Array.isArray(n.deps) && n.deps.length ? n.deps.join(', ') : '-',
        show(n.attempts) + '/' + show(n.max_attempts),
        show(n.last_run),
      ]);
      block.appendChild(newTable(
        ['노드ID', '제목', '슬롯', '하네스', '상태', '의존', '시도', 'run'],
        rows,
        null,
        {
          widths: ['70px', '260px', '70px', '90px', '100px', '120px', '80px', '220px'],
          num: [6],
          center: [4],
          ellipsis: [1, 5, 7],
        },
      ));
    }
    list.appendChild(block);
  }
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

function renderRequests(data) {
  const list = $('requests-list');
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

  requests.forEach((req, index) => {
    const key = show(req.id, '') || ('request-' + index);
    if (!state.known.has(key)) {
      state.known.add(key);
      state.expanded.add(key);
    }
    const open = state.expanded.has(key);

    const article = document.createElement('article');
    article.className = 'req-block';

    const top = document.createElement('div');
    top.className = 'req-top';

    const toggle = document.createElement('button');
    toggle.type = 'button';
    toggle.className = 'req-toggle';
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
    if (req.detail) {
      const detail = document.createElement('div');
      detail.className = 'req-detail';
      detail.textContent = show(req.detail);
      detail.title = show(req.detail, '');
      titleWrap.appendChild(detail);
      const fullLabel = requestFullViewLabel(req);
      if (fullLabel !== null) {
        const full = document.createElement('button');
        full.type = 'button';
        full.className = 'req-full';
        full.textContent = fullLabel;
        full.addEventListener('click', () => openRequestDetail(req));
        titleWrap.appendChild(full);
      }
    }

    const badges = document.createElement('div');
    badges.className = 'req-badges';
    badges.appendChild(statusBadge(req.status));

    top.appendChild(toggle);
    top.appendChild(titleWrap);
    top.appendChild(badges);
    article.appendChild(top);

    const pct = progressOf(req);
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
    etaLabel.textContent = 'ETA ' + etaText(req);
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
          widths: ['80px', '240px', '70px', '90px', '100px', '100px', '260px'],
          num: [5],
          center: [4],
          ellipsis: [1, 6],
          rowRunIds: subRunIds,
        },
      );
      markUnopenableRows(subTable, subRunIds);
      body.appendChild(subTable);
    }
    article.appendChild(body);
    list.appendChild(article);
  });
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

function renderAll(data) {
  renderErrors(data);
  renderMeta(data);
  renderSlots(data);
  renderKisti(data);
  renderRuns(data);
  renderBoard(data);
  renderQueue(data);
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

function init() {
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
