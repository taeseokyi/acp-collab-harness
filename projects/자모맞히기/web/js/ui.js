// 자모맞히기 화면: DOM · 입력 · 애니메이션. 진입점.
import {
  WORD_LENGTH, MAX_GUESSES, dailyIndex, answerForDate, keyboardState, createGame, fromJSON,
} from './game.js';
import { ANSWERS, ALLOWED, TREND } from './words.js';
import { KEY_ROWS, KEYMAP, SHIFTED, toUnits, composeUnits } from './jamo.js';
import {
  loadStats, recordResult, loadDaily, saveDaily, loadSettings, saveSettings,
  loadSeenHelp, saveSeenHelp, init, loadDict, saveDict, loadExtraWords, addExtraWord,
} from './storage.js';
import { sinceText, mergeTrend } from './trend.js';
import { SOURCES, DEFAULT_SOURCE, isLookupWord, fetchServerSources, lookupWord } from './dict.js';

const $ = (id) => document.getElementById(id);
const FLIP_STEP = 100;   // 칸 사이 간격(ms)
const FLIP_TIME = 500;   // 칸 하나가 뒤집히는 시간(ms)
const STATE_LABEL = { correct: '맞음', present: '자리 틀림', absent: '없음' };
const ALLOWED_SET = new Set(ALLOWED.map(toUnits));
const WORD_OF = new Map(ALLOWED.map((word) => [toUnits(word), word]));

let settings;
let mode = 'daily';
let dailyGame = null;
let practiceGame = null;
let game = null;
let dayKey = '';
let puzzleNumber = 0;
let busy = false;          // 뒤집는 애니메이션 중
let looking = false;       // 외부 사전 조회 중(입력을 받지 않음)
let dictCfg;               // {on, source, keys, customs}
let serverSources;         // fetchServerSources 결과(undefined = 아직, null = 서버 없음)
let shiftOn = false;
let endTimer = 0;
let answerToast = null;    // 진 판의 정답 토스트(시간 0 = 직접 지울 때까지 남음)
const tiles = [];          // tiles[row][col]
const rowEls = [];
const keyEls = new Map();

/* ---------- 날짜 ---------- */

function dayKeyOf(d) {
  const p = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

/* ---------- 토스트 ---------- */

function toast(message, ms = 1500) {
  const el = document.createElement('div');
  el.className = 'toast';
  el.textContent = message;
  $('toasts').prepend(el);
  if (ms > 0) {
    setTimeout(() => {
      el.classList.add('out');
      setTimeout(() => el.remove(), 300);
    }, ms);
  }
  return el;
}

function clearAnswerToast() {
  if (answerToast) {
    answerToast.remove();
    answerToast = null;
  }
}

function showAnswerToast() {
  clearAnswerToast();
  if (game && game.status === 'lost') {
    answerToast = toast(`정답: ${WORD_OF.get(game.answer) ?? composeUnits(game.answer)}`, 0);
  }
}

/* ---------- 테마 ---------- */

function hasStoredSettings() {
  try {
    return globalThis.localStorage.getItem('jamo.settings') !== null;
  } catch {
    return false;
  }
}

function applySettings() {
  const root = document.documentElement;
  root.dataset.theme = settings.dark ? 'dark' : 'light';
  root.dataset.colorblind = settings.colorblind ? 'on' : 'off';
}

/* ---------- 보드 ---------- */

function buildBoard() {
  const board = $('board');
  board.textContent = '';
  tiles.length = 0;
  rowEls.length = 0;
  for (let r = 0; r < MAX_GUESSES; r++) {
    const row = document.createElement('div');
    row.className = 'row';
    row.setAttribute('role', 'row');
    const cols = [];
    for (let c = 0; c < WORD_LENGTH; c++) {
      const t = document.createElement('div');
      t.className = 'tile';
      t.setAttribute('role', 'gridcell');
      const dropAnim = () => t.classList.remove('pop', 'bounce');
      t.addEventListener('animationend', dropAnim);
      t.addEventListener('animationcancel', dropAnim);
      row.appendChild(t);
      cols.push(t);
    }
    board.appendChild(row);
    tiles.push(cols);
    rowEls.push(row);
  }
}

function setTile(r, c, letter, state) {
  const t = tiles[r][c];
  const L = letter || '';
  t.textContent = L;
  t.dataset.state = state;
  const pos = `${r + 1}번째 줄 ${c + 1}번째 칸`;
  if (state === 'empty') t.setAttribute('aria-label', `${pos}, 비어 있음`);
  else if (state === 'filled') t.setAttribute('aria-label', `${pos}, ${L}`);
  else t.setAttribute('aria-label', `${pos}, ${L}, ${STATE_LABEL[state]}`);
}

function renderAll() {
  for (let r = 0; r < MAX_GUESSES; r++) {
    for (let c = 0; c < WORD_LENGTH; c++) {
      const row = game.rows[r];
      if (row) setTile(r, c, row.guess[c], row.scores[c]);
      else if (r === game.rows.length && game.status === 'playing' && game.current[c]) {
        setTile(r, c, game.current[c], 'filled');
      } else setTile(r, c, '', 'empty');
    }
  }
  renderPreview();
  renderKeyboard();
}

function renderCurrentRow() {
  const r = game.rows.length;
  if (r >= MAX_GUESSES) return;
  for (let c = 0; c < WORD_LENGTH; c++) {
    const ch = game.current[c];
    setTile(r, c, ch || '', ch ? 'filled' : 'empty');
  }
  renderPreview();
}

function renderPreview() {
  $('preview').textContent = game && game.status === 'playing'
    ? composeUnits(game.current)
    : '';
}

function popTile(r, c) {
  const t = tiles[r][c];
  t.classList.remove('pop');
  void t.offsetWidth;
  t.classList.add('pop');
}

function shakeRow(r) {
  const el = rowEls[r];
  el.classList.remove('shake');
  void el.offsetWidth;
  el.classList.add('shake');
  setTimeout(() => el.classList.remove('shake'), 600);
}

/* ---------- 키보드 ---------- */

function buildKeyboard() {
  const kb = $('keyboard');
  kb.textContent = '';
  kb.removeAttribute('data-shift');
  keyEls.clear();
  const rows = [
    KEY_ROWS[0].map((ch) => makeKey(ch, ch, ch, false)),
    [makeKey('shift', '⇧', '쌍자음', false), ...KEY_ROWS[1].map((ch) => makeKey(ch, ch, ch, false))],
    [makeKey('enter', '입력', '입력', true), ...KEY_ROWS[2].map((ch) => makeKey(ch, ch, ch, false)), makeKey('back', '⌫', '지우기', true)],
  ];
  for (const keys of rows) {
    const row = document.createElement('div');
    row.className = 'krow';
    row.append(...keys);
    kb.appendChild(row);
  }
  keyEls.get('shift').setAttribute('aria-pressed', 'false');
}

function makeKey(id, text, label, wide) {
  const b = document.createElement('button');
  b.type = 'button';
  b.className = wide ? 'key wide' : 'key';
  b.textContent = text;
  b.dataset.key = id;
  b.setAttribute('aria-label', label);
  // 마우스로 누르면 포커스가 남아 스페이스바가 다시 누르므로 막는다 (Tab 포커스는 그대로)
  b.addEventListener('mousedown', (e) => e.preventDefault());
  b.addEventListener('click', () => handleKey(id));
  keyEls.set(id, b);
  return b;
}

function renderKeyboard(rows = game.rows) {
  applyShiftDisplay();
  const st = keyboardState(rows);
  for (const [id, el] of keyEls) {
    if (id.length !== 1) continue;
    const shown = shiftOn ? (SHIFTED[id] ?? id) : id;
    const s = st[shown];
    if (s) {
      el.dataset.state = s;
      el.setAttribute('aria-label', `${shown}, ${STATE_LABEL[s]}`);
    } else {
      delete el.dataset.state;
      el.setAttribute('aria-label', shown);
    }
  }
}

function applyShiftDisplay() {
  const kb = $('keyboard');
  if (shiftOn) kb.dataset.shift = 'on';
  else kb.removeAttribute('data-shift');
  const shiftKey = keyEls.get('shift');
  if (shiftKey) shiftKey.setAttribute('aria-pressed', shiftOn ? 'true' : 'false');
  for (const id of Object.keys(SHIFTED)) {
    const el = keyEls.get(id);
    if (el) el.textContent = shiftOn ? SHIFTED[id] : id;
  }
}

/* ---------- 입력 ---------- */

function modalOpen() {
  return !!document.querySelector('.modal:not([hidden])');
}

function handleKey(id) {
  if (busy || looking || modalOpen() || !game || game.status !== 'playing') return;
  const r = game.rows.length;
  if (id === 'enter') return submit();
  if (id === 'back') {
    if (game.removeLetter()) {
      renderCurrentRow();
      renderKeyboard();
    }
    return;
  }
  if (id === 'shift') {
    shiftOn = !shiftOn;
    renderKeyboard();
    return;
  }
  const unit = shiftOn ? (SHIFTED[id] ?? id) : id;
  const c = game.current.length;
  shiftOn = false;
  if (game.addLetter(unit)) {
    renderCurrentRow();
    popTile(r, c);
  }
  renderKeyboard();
}

function sourceLabel(id) {
  const c = dictCfg.customs.find((x) => x.id === id);
  if (c) return c.label;
  return SOURCES.find((x) => x.id === id)?.label ?? id;
}

// 없는 낱말이면 외부 사전에 물어본다. 찾으면 true(다시 제출), 아니면 거절 토스트를 띄우고 false, 판이 바뀌었으면 null.
function lookupTarget(g) {
  const word = composeUnits(g.current);
  return dictCfg.on && isLookupWord(word) && toUnits(word) === g.current;
}

async function askDictionary(g, r, res) {
  const guess = g.current;
  const word = composeUnits(guess);
  looking = true;
  const wait = toast('사전 확인 중…', 0);
  let found = null;
  let result;
  try {
    result = await lookupWord(word, dictCfg, { fetch: globalThis.fetch.bind(globalThis) });
  } catch (e) {
    result = { ok: false, error: String((e && e.message) || e) };
  }
  wait.remove();
  looking = false;
  if (g !== game || g.current !== guess || g.status !== 'playing') return null; // 그 사이 판이 바뀜
  const name = sourceLabel(result.source || dictCfg.source);
  if (result.ok && result.found) {
    ALLOWED_SET.add(guess);
    g.allowWord(guess);
    WORD_OF.set(guess, word);
    addExtraWord(word);
    toast(`${name}에서 찾았습니다`);
    found = true;
  } else if (result.ok) {
    shakeRow(r);
    toast(`${res.message} (${name}에도 없음)`);
    found = false;
  } else {
    shakeRow(r);
    toast(`사전 조회 실패: ${result.error || '알 수 없는 오류'}`, 2500);
    found = false;
  }
  return found;
}

function submit(afterLookup = false) {
  const r = game.rows.length;
  const res = game.submit();
  if (!res.ok) {
    // 한 추측에 조회는 최대 한 번 - 조회 뒤 다시 제출해도 unknown 이면 오류만 내고 멈춘다.
    if (res.reason === 'unknown' && !afterLookup && !looking && lookupTarget(game)) {
      const g = game;
      askDictionary(g, r, res).then((found) => { if (found === true && g === game) submit(true); });
      return;
    }
    shakeRow(r);
    toast(res.message);
    return;
  }
  const finished = res.status !== 'playing';
  if (mode === 'daily') {
    saveDaily(dayKey, game.toJSON());
    if (finished) recordResult(res.status === 'won', game.rows.length, dayKey);
  }
  if (finished) clearAnswerToast();
  renderPreview();
  busy = true;
  const { guess, scores } = res.row;
  for (let c = 0; c < WORD_LENGTH; c++) {
    const t = tiles[r][c];
    setTimeout(() => {
      t.classList.remove('pop', 'bounce');
      t.classList.add('flip');
      setTimeout(() => setTile(r, c, guess[c], scores[c]), FLIP_TIME / 2);
      setTimeout(() => t.classList.remove('flip', 'pop'), FLIP_TIME);
    }, c * FLIP_STEP);
  }
  setTimeout(() => {
    busy = false;
    renderKeyboard();
    if (finished) onFinish(res.status, r);
  }, (WORD_LENGTH - 1) * FLIP_STEP + FLIP_TIME + 50);
}

function onFinish(status, r) {
  if (status === 'won') {
    const cheers = ['천재!', '대단해요!', '훌륭해요!', '멋져요!', '좋아요!', '아슬아슬!'];
    toast(cheers[Math.min(r, cheers.length - 1)], 2000);
    tiles[r].forEach((t, c) => setTimeout(() => {
      t.classList.remove('bounce');
      void t.offsetWidth;
      t.classList.add('bounce');
    }, c * 100));
  } else {
    showAnswerToast();
  }
  clearTimeout(endTimer);
  endTimer = setTimeout(() => openModal('stats'), status === 'won' ? 2000 : 1500);
}

document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    if (modalOpen()) closeModal();
    return;
  }
  if (e.ctrlKey || e.metaKey || e.altKey || modalOpen()) return;
  const t = e.target;
  if (e.key === 'Enter') {
    // 포커스가 단추에 있으면 Enter 는 그 단추의 눌림(click)에 맡긴다
    const a = document.activeElement;
    if (a instanceof Element && a.closest('button')) return;
    // 머리글·모드 줄의 Enter 도 그 안의 단추가 처리한다
    if (t instanceof Element && t.closest('.header, #modes')) return;
    e.preventDefault();
    handleKey('enter');
  } else if (e.key === 'Backspace') {
    e.preventDefault();
    handleKey('back');
  } else {
    if (busy || looking) return;
    const pair = KEYMAP[e.code];
    if (!pair || !game || game.status !== 'playing') return;
    // 실물 자판으로 글자를 치면 머리글·모드 단추의 포커스를 풀어, 이어지는 Enter 가 제출로 가게 한다
    const focused = document.activeElement;
    if (focused instanceof Element && focused.closest('.header, #modes')) focused.blur();
    e.preventDefault();
    const unit = e.shiftKey ? pair[1] : pair[0];
    const r = game.rows.length;
    const c = game.current.length;
    shiftOn = false;
    if (game.addLetter(unit)) {
      renderCurrentRow();
      renderKeyboard();
      popTile(r, c);
    } else {
      renderKeyboard();
    }
  }
});

/* ---------- 모달 ---------- */

let openEl = null;
let opener = null;

function openModal(name) {
  closeModal(true);
  const el = $('modal-' + name);
  if (name === 'stats') renderStats();
  if (name === 'settings') { syncSettingsForm(); renderTrendSince(); }
  opener = document.activeElement;
  openEl = el;
  el.hidden = false;
  $('app').inert = true;
  el.querySelector('.modal-box').focus();
}

function closeModal(quiet) {
  if (!openEl) return;
  openEl.hidden = true;
  openEl = null;
  $('app').inert = false;
  if (!quiet && opener && opener.focus && document.contains(opener)) opener.focus();
}

for (const el of document.querySelectorAll('.modal')) {
  el.addEventListener('mousedown', (e) => { if (e.target === el) closeModal(); });
  el.querySelector('.modal-close').addEventListener('click', () => closeModal());
}

/* ---------- 통계 ---------- */

function renderStats() {
  const s = loadStats();
  const pct = s.played ? Math.round((s.wins / s.played) * 100) : 0;
  const row = $('stat-row');
  row.textContent = '';
  for (const [n, label] of [[s.played, '판수'], [pct, '승률 %'], [s.streak, '연승'], [s.maxStreak, '최대 연승']]) {
    const d = document.createElement('div');
    d.className = 'stat';
    const b = document.createElement('b');
    b.textContent = String(n);
    const sp = document.createElement('span');
    sp.textContent = label;
    d.append(b, sp);
    row.appendChild(d);
  }
  const dist = $('dist');
  dist.textContent = '';
  const max = Math.max(1, ...s.dist);
  const hl = game && game.status === 'won' && mode === 'daily' ? game.rows.length : 0;
  s.dist.forEach((n, i) => {
    const r = document.createElement('div');
    r.className = 'dist-row';
    const lab = document.createElement('span');
    lab.className = 'n';
    lab.textContent = String(i + 1);
    const wrap = document.createElement('div');
    wrap.className = 'bar-wrap';
    const bar = document.createElement('div');
    bar.className = 'bar' + (hl === i + 1 ? ' hl' : '');
    bar.style.width = Math.max(8, (n / max) * 100) + '%';
    bar.textContent = String(n);
    wrap.appendChild(bar);
    r.append(lab, wrap);
    r.setAttribute('aria-label', `${i + 1}번 만에 맞힘 ${n}회`);
    dist.appendChild(r);
  });
  $('btn-share').hidden = !(game && game.status !== 'playing');
}

async function share() {
  const text = game.shareText();
  let ok = false;
  try {
    await navigator.clipboard.writeText(text);
    ok = true;
  } catch {
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.setAttribute('readonly', '');
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    try { ok = document.execCommand('copy'); } catch { ok = false; }
    ta.remove();
  }
  toast(ok ? '클립보드에 복사했습니다' : '복사하지 못했습니다');
}

/* ---------- 설정 ---------- */

function syncSettingsForm() {
  // 체크박스는 지금 보고 있는 판의 값을 보여 준다(모드를 바꾸면 그 판 값으로 맞춤)
  $('set-hard').checked = game ? game.hardMode : settings.hardMode;
  $('set-dark').checked = settings.dark;
  $('set-cb').checked = settings.colorblind;
  syncDictForm();
}

function hardModeLocked() {
  return !!game && game.rows.length > 0;
}

$('set-hard').addEventListener('change', (e) => {
  if (hardModeLocked()) {
    e.target.checked = game.hardMode;
    toast('하드 모드는 판이 시작된 뒤에는 바꿀 수 없습니다', 2000);
    return;
  }
  settings.hardMode = e.target.checked;
  saveSettings(settings);
  // 아직 제출한 줄이 없으니 지금 판만 다시 만들어 하드 모드를 적용한다(친 칸 유지)
  if (game.status === 'playing') {
    const typed = game.current;
    const rebuilt = newGame(game.answer, game.puzzleNumber);
    for (const ch of typed) rebuilt.addLetter(ch);
    if (mode === 'daily') {
      dailyGame = rebuilt;
      saveDaily(dayKey, dailyGame.toJSON());
    } else {
      practiceGame = rebuilt;
    }
    game = rebuilt;
    renderAll();
  }
});
$('set-dark').addEventListener('change', (e) => {
  settings.dark = e.target.checked;
  saveSettings(settings);
  applySettings();
});
$('set-cb').addEventListener('change', (e) => {
  settings.colorblind = e.target.checked;
  saveSettings(settings);
  applySettings();
});

/* ---------- 외부 사전 설정 ---------- */

const fetchNow = (...a) => globalThis.fetch(...a);

function sourceNote(id) {
  const list = Array.isArray(serverSources) ? serverSources : null;
  const src = SOURCES.find((x) => x.id === id);
  if (!src) return '';
  if (dictCfg.keys[id] && src.browserDirect) return '';
  if (!list) return src.browserDirect && src.kind === 'mediawiki' ? '' : ' (serve.py 필요)';
  const s = list.find((x) => x.id === id);
  if (s && !s.available) return ' (키 없음)';
  return '';
}

function renderDictSelect() {
  const sel = $('dict-source');
  sel.textContent = '';
  const add = (id, label) => {
    const o = document.createElement('option');
    o.value = id;
    o.textContent = label;
    sel.appendChild(o);
  };
  for (const s of SOURCES) add(s.id, s.label + sourceNote(s.id));
  for (const c of dictCfg.customs) add(c.id, c.label);
  sel.value = [...sel.options].some((o) => o.value === dictCfg.source) ? dictCfg.source : DEFAULT_SOURCE;
  dictCfg.source = sel.value;
}

function renderDictCustoms() {
  const ul = $('dict-customs');
  ul.textContent = '';
  for (const c of dictCfg.customs) {
    const li = document.createElement('li');
    const name = document.createElement('span');
    name.textContent = `${c.label} · ${c.model}`;
    const del = document.createElement('button');
    del.type = 'button';
    del.className = 'dict-del';
    del.textContent = '지우기';
    del.setAttribute('aria-label', `${c.label} 지우기`);
    del.addEventListener('click', () => {
      dictCfg.customs = dictCfg.customs.filter((x) => x.id !== c.id);
      if (dictCfg.source === c.id) dictCfg.source = DEFAULT_SOURCE;
      saveDict(dictCfg);
      syncDictForm();
    });
    li.append(name, del);
    ul.appendChild(li);
  }
}

function syncDictKey() {
  const src = SOURCES.find((x) => x.id === dictCfg.source);
  const needKey = !!src && src.kind === 'llm' && src.browserDirect;
  $('dict-key-row').hidden = !needKey;
  $('dict-key').value = needKey ? (dictCfg.keys[src.id] || '') : '';
  $('dict-signup').textContent = needKey && src.signup ? `키 받는 곳: ${src.signup}` : '';
}

function syncDictForm() {
  $('dict-on').checked = dictCfg.on;
  renderDictSelect();
  renderDictCustoms();
  syncDictKey();
}

$('dict-on').addEventListener('change', (e) => {
  dictCfg.on = e.target.checked;
  saveDict(dictCfg);
});
$('dict-source').addEventListener('change', (e) => {
  dictCfg.source = e.target.value;
  saveDict(dictCfg);
  syncDictKey();
  $('dict-status').textContent = '';
});
$('dict-key').addEventListener('input', (e) => {
  const v = e.target.value.trim();
  if (v) dictCfg.keys[dictCfg.source] = v;
  else delete dictCfg.keys[dictCfg.source];
  saveDict(dictCfg);
  renderDictSelect();
});
$('dict-test').addEventListener('click', async () => {
  const st = $('dict-status');
  st.textContent = '확인 중…';
  let r;
  try {
    r = await lookupWord('한국', dictCfg, { fetch: fetchNow });
  } catch (e) {
    r = { ok: false, error: String((e && e.message) || e) };
  }
  const name = sourceLabel(r.source || dictCfg.source);
  if (r.ok) st.textContent = `${name}: '한국' ${r.found ? '있음' : '없음'}${r.evidence ? ` (${r.evidence})` : ''}`;
  else st.textContent = `${name}: 실패 - ${r.error}`;
});
$('dict-add').addEventListener('click', () => {
  const st = $('dict-status');
  const label = $('dict-add-name').value.trim();
  const baseUrl = $('dict-add-url').value.trim();
  const model = $('dict-add-model').value.trim();
  const key = $('dict-add-key').value.trim();
  if (!label) { st.textContent = '이름을 적어 주세요'; return; }
  if (!/^https:\/\/[^\s/]+/.test(baseUrl)) { st.textContent = '주소는 https:// 로 시작해야 합니다'; return; }
  if (!model) { st.textContent = '모델 이름을 적어 주세요'; return; }
  let n = 1;
  while (dictCfg.customs.some((c) => c.id === `custom:${n}`)) n++;
  const id = `custom:${n}`;
  dictCfg.customs.push({ id, label, baseUrl, model, key });
  dictCfg.source = id;
  saveDict(dictCfg);
  for (const f of ['name', 'url', 'model', 'key']) $('dict-add-' + f).value = '';
  st.textContent = `${label} 을(를) 더했습니다`;
  syncDictForm();
});

/* ---------- 뉴스로 정답 고르기 (T-325) ---------- */

const TREND_TIMEOUT = 150000;
const TREND_NO_SERVER = '뉴스 정답 고르기는 serve.py 로 열었을 때만 됩니다 - 지금 정답으로 이어 갑니다';

// 서버 출처(SOURCES 의 id)면 그것, 사용자 LLM·키 직접 출처면 wiktionary
function trendSource() {
  const s = SOURCES.find((x) => x.id === dictCfg.source);
  if (!s || (s.kind === 'llm' && s.browserDirect)) return DEFAULT_SOURCE;
  return s.id;
}

function trendStart() {
  const now = new Date();
  const todayPlayed = dayKeyOf(now) === dayKey && dailyGame && dailyGame.rows.length > 0;
  return dayKeyOf(todayPlayed ? new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1) : now);
}

// 서버(data/trend.txt)가 정본. 화면은 받아서 하루 정답에만 쓰고 브라우저에는 저장하지 않는다.
let serverTrend = {};
let trendLastRun = null;
let trendServerKnown = false; // 서버에서 한 번이라도 받았는가

function currentTrend() {
  return mergeTrend(TREND, serverTrend);
}

function renderTrendSince() {
  const el = $('trend-since');
  if (!el) return;
  el.textContent = trendServerKnown ? sinceText(trendLastRun, new Date()) : '서버 없이 열어 정한 때를 모릅니다';
}

// 서버가 준 trend·last_run 을 받아 쓴다. 오늘 판이 비어 있고 오늘 정답이 달라졌을 때만 오늘 판을 다시 시작한다.
function applyServerTrend(trend, lastRun) {
  serverTrend = mergeTrend({}, trend);
  trendLastRun = typeof lastRun === 'string' && lastRun ? lastRun : null;
  trendServerKnown = true;
  for (const w of Object.values(serverTrend)) {
    const u = toUnits(w);
    if (u && u.length === WORD_LENGTH) {
      ALLOWED_SET.add(u);
      WORD_OF.set(u, w);
    }
  }
  renderTrendSince();
  if (dailyGame && dailyGame.rows.length === 0 && dayKey === dayKeyOf(new Date())) {
    const answer = toUnits(answerForDate(new Date(), ANSWERS, currentTrend()));
    if (answer !== dailyGame.answer) startDaily();
  }
}

async function fetchServerTrend() {
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), 2500);
  try {
    const res = await fetchNow('api/trend', { signal: ctl.signal });
    if (!res.ok) return;
    const data = await res.json();
    if (data && data.ok === true && data.trend && typeof data.trend === 'object') {
      applyServerTrend(data.trend, data.last_run);
    }
  } catch { /* 서버 없이 열었으면 정적 TREND 만 */ } finally {
    clearTimeout(timer);
  }
}

async function pickTrend() {
  const btn = $('trend-pick');
  const st = $('trend-status');
  if (btn.disabled) return;
  btn.disabled = true;
  st.textContent = '고르는 중… (1분쯤)';
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), TREND_TIMEOUT);
  let msg;
  try {
    let res;
    try {
      res = await fetchNow('api/trend/pick', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source: trendSource(), days: 7, start: trendStart(), skip: [] }),
        signal: ctl.signal,
      });
    } catch {
      res = null;
    }
    let data = null;
    if (res && ![404, 405, 501].includes(res.status)) {
      try { data = await res.json(); } catch { data = null; }
    }
    if (!res || [404, 405, 501].includes(res.status) || data === null || typeof data !== 'object') {
      msg = TREND_NO_SERVER;
    } else if (data.ok === true) {
      const added = (Array.isArray(data.added) ? data.added : Array.isArray(data.picks) ? data.picks : [])
        .filter((p) => p && typeof p.date === 'string');
      if (data.trend && typeof data.trend === 'object') applyServerTrend(data.trend, data.last_run);
      msg = added.length
        ? `${added[0].date}부터 ${added.length}일치 정답을 골랐습니다 (뉴스 제목 ${Number(data.titles) || 0}건에서)`
        : '새로 정한 날짜가 없습니다 (이미 정해진 날은 그대로)';
    } else {
      msg = `정답 고르기 실패: ${data.error || `서버 응답 ${res.status}`}`;
    }
  } catch (e) {
    msg = `정답 고르기 실패: ${String((e && e.message) || e)}`;
  } finally {
    clearTimeout(timer);
  }
  st.textContent = msg;
  btn.disabled = false;
}

$('trend-pick').addEventListener('click', pickTrend);

/* ---------- 판 시작 ---------- */

function newGame(answer, number = puzzleNumber) {
  return createGame({
    answer,
    allowed: ALLOWED_SET,
    hardMode: settings.hardMode,
    puzzleNumber: number,
    maxGuesses: MAX_GUESSES,
  });
}

// 이어하는 판의 하드 모드는 저장된 판 값을 지키고, 빈 판은 저장된 설정을 따른다(입력 중인 글자는 옮김)
function alignEmptyHard(g) {
  if (g.rows.length !== 0 || g.hardMode === settings.hardMode) return g;
  const typed = g.current;
  const fresh = newGame(g.answer, g.puzzleNumber);
  for (const ch of typed) fresh.addLetter(ch);
  return fresh;
}

function startDaily() {
  const now = new Date();
  dayKey = dayKeyOf(now);
  puzzleNumber = Math.max(1, dailyIndex(now) + 1);
  const answer = toUnits(answerForDate(now, ANSWERS, currentTrend()));
  const saved = loadDaily(dayKey);
  dailyGame = null;
  // 오늘 판에 줄이 있으면 그 판의 정답은 새로 고쳐도·정답표가 바뀌어도 그대로(R31-N8).
  // 줄이 없는 판만 지금의 오늘 정답을 따른다.
  if (saved && (saved.answer === answer || (Array.isArray(saved.rows) && saved.rows.length > 0))) {
    try { dailyGame = fromJSON(saved, { allowed: ALLOWED_SET }); } catch { dailyGame = null; }
  }
  if (!dailyGame) dailyGame = newGame(answer, puzzleNumber);
  dailyGame = alignEmptyHard(dailyGame);
  if (mode === 'daily') {
    game = dailyGame;
    shiftOn = false;
    renderAll();
  }
  $('toasts').textContent = '';
  answerToast = null;
  // 화면에 남아 있는 판이 진 판이면(연습 중 날이 바뀐 경우) 그 판의 정답 토스트를 다시 띄운다.
  if (mode === 'practice' && game && game.status === 'lost') showAnswerToast();
  clearTimeout(endTimer);
  busy = false;
}

function startPractice() {
  puzzleNumber = 0;
  const answer = toUnits(ANSWERS[Math.floor(Math.random() * ANSWERS.length)]);
  practiceGame = newGame(answer, 0);
  if (mode === 'practice') {
    game = practiceGame;
    shiftOn = false;
    renderAll();
  }
}

function updateModeUI() {
  $('mode-daily').setAttribute('aria-pressed', mode === 'daily' ? 'true' : 'false');
  $('mode-practice').setAttribute('aria-pressed', mode === 'practice' ? 'true' : 'false');
  $('btn-new').hidden = mode !== 'practice';
}

function selectMode(next) {
  if (busy || next === mode) return;
  if (next === 'practice') {
    if (!practiceGame) startPractice();
    practiceGame = alignEmptyHard(practiceGame);
    game = practiceGame;
  } else {
    dailyGame = alignEmptyHard(dailyGame);
    game = dailyGame;
  }
  mode = next;
  shiftOn = false;
  clearTimeout(endTimer);
  updateModeUI();
  renderAll();
  clearAnswerToast();
  showAnswerToast();
}

function checkNewDay() {
  if (!busy && dayKeyOf(new Date()) !== dayKey) {
    closeModal(true);
    startDaily();
    toast('새로운 날, 새로운 낱말!', 2000);
  }
}

/* ---------- 시작 ---------- */

await init();              // 격리된 미리보기면 부모(모니터)에서 보관함을 받아 온다
settings = loadSettings();
dictCfg = loadDict();
for (const w of [...loadExtraWords(), ...Object.values(TREND)]) {
  const u = toUnits(w);
  if (u) { ALLOWED_SET.add(u); WORD_OF.set(u, w); }
}
// 저장된 설정이 없으면 시스템의 어두운 모드를 기본값으로 따른다
if (globalThis.parent === globalThis && !hasStoredSettings()
    && globalThis.matchMedia && globalThis.matchMedia('(prefers-color-scheme: dark)').matches) {
  settings.dark = true;
}
await fetchServerTrend();   // 서버가 정한 오늘 정답을 판 시작 전에 받는다(없으면 곧바로 넘어감)
applySettings();
buildBoard();
buildKeyboard();
startDaily();
updateModeUI();
syncDictForm();
fetchServerSources({ fetch: fetchNow }).then((list) => { serverSources = list; syncDictForm(); }, () => { serverSources = null; });

$('btn-help').addEventListener('click', () => openModal('help'));
$('btn-stats').addEventListener('click', () => openModal('stats'));
$('btn-settings').addEventListener('click', () => openModal('settings'));
$('btn-share').addEventListener('click', share);
$('mode-daily').addEventListener('click', (e) => { selectMode('daily'); e.currentTarget.blur(); });
$('mode-practice').addEventListener('click', (e) => { selectMode('practice'); e.currentTarget.blur(); });
$('btn-new').addEventListener('click', (e) => {
  if (busy || modalOpen()) return;
  clearTimeout(endTimer);
  startPractice();
  game = practiceGame;
  clearAnswerToast();
  renderAll();
  e.currentTarget.blur();
});
document.addEventListener('visibilitychange', () => { if (!document.hidden) checkNewDay(); });
window.addEventListener('focus', checkNewDay);
setInterval(checkNewDay, 30000);

if (game.status !== 'playing') {
  // 이미 끝낸 판이면 통계를 보여 준다
  showAnswerToast();
  setTimeout(() => openModal('stats'), 600);
} else if (!loadSeenHelp()) {
  saveSeenHelp();
  openModal('help');
}
