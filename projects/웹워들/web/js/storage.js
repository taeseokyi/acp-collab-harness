// localStorage 래퍼. import 시점에는 localStorage 를 건드리지 않습니다.
const PREFIX = 'webwordle.';
const memory = new Map();
let backend; // undefined = 아직 안 알아봄, null = 못 씀
let parentMode = false;
let initPromise = null;
let parentOriginValue;

function parentOrigin() {
  if (parentOriginValue === undefined) parentOriginValue = new URL(globalThis.location.href).origin;
  return parentOriginValue;
}

function sendToParent(op, key, value) {
  if (!parentMode) return;
  if (!/^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/.test(key)) return;
  if (op === 'put' && value !== null && (typeof value !== 'string' || value.length > 8192)) return;
  try {
    globalThis.parent.postMessage({ aimem: 'store.v1', op, key, value }, parentOrigin());
  } catch { /* 부모가 없거나 거부해도 게임은 계속 */ }
}

function store() {
  if (backend !== undefined) return backend;
  try {
    const ls = globalThis.localStorage;
    const probe = PREFIX + 'probe';
    ls.setItem(probe, '1');
    ls.removeItem(probe);
    backend = ls;
  } catch {
    backend = null;
  }
  return backend;
}

function read(key) {
  const k = PREFIX + key;
  try {
    const s = store();
    if (s) {
      const v = s.getItem(k);
      return v === null ? null : JSON.parse(v);
    }
  } catch { /* 메모리로 대신 */ }
  try {
    return memory.has(k) ? JSON.parse(memory.get(k)) : null;
  } catch {
    return null;
  }
}

function write(key, value) {
  const k = PREFIX + key;
  const text = JSON.stringify(value);
  memory.set(k, text);
  try {
    const s = store();
    if (s) s.setItem(k, text);
  } catch { /* 메모리에는 남음 */ }
  sendToParent('put', key, text);
}

function remove(key) {
  const k = PREFIX + key;
  memory.delete(k);
  try {
    const s = store();
    if (s) s.removeItem(k);
  } catch { /* 무시 */ }
  sendToParent('put', key, null);
}

function todayKey() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

export async function init() {
  if (initPromise) return initPromise;
  initPromise = (async () => {
    if (store()) return;
    if (!globalThis.parent || globalThis.parent === globalThis) return;

    let snapshotTimer = null;
    let receivedSnapshot = false;
    await new Promise((resolve) => {
      let done = false;
      function finish() {
        if (done) return;
        done = true;
        globalThis.removeEventListener('message', onMsg);
        clearTimeout(snapshotTimer);
        resolve();
      }
      function onMsg(ev) {
        if (ev.source !== globalThis.parent) return;
        const data = ev.data;
        if (typeof data !== 'object' || data === null || Array.isArray(data)) return;
        if (data.aimem !== 'store.v1' || data.op !== 'snapshot') return;
        const items = data.items;
        if (typeof items !== 'object' || items === null || Array.isArray(items)) return;
        receivedSnapshot = true;
        for (const [key, value] of Object.entries(items)) {
          if (typeof value === 'string') memory.set(PREFIX + key, value);
        }
        finish();
      }
      globalThis.addEventListener('message', onMsg);
      snapshotTimer = setTimeout(finish, 500);
      try {
        globalThis.parent.postMessage({ aimem: 'store.v1', op: 'ready' }, parentOrigin());
      } catch { /* 메모리 모드로 계속 */ }
    });

    if (!receivedSnapshot) return;
    parentMode = true;
    const today = todayKey();
    const dailyPrefix = PREFIX + 'daily.';
    for (const k of [...memory.keys()]) {
      if (!k.startsWith(dailyPrefix)) continue;
      const day = k.slice(dailyPrefix.length);
      if (day !== today) remove('daily.' + day);
    }
  })();
  return initPromise;
}

const num = (v) => (Number.isFinite(v) && v >= 0 ? Math.floor(v) : 0);

function emptyStats() {
  return { played: 0, wins: 0, streak: 0, maxStreak: 0, dist: [0, 0, 0, 0, 0, 0], lastDay: '' };
}

export function loadStats() {
  const raw = read('stats');
  const s = emptyStats();
  if (!raw || typeof raw !== 'object') return s;
  s.played = num(raw.played);
  s.wins = num(raw.wins);
  s.streak = num(raw.streak);
  s.maxStreak = Math.max(num(raw.maxStreak), s.streak);
  if (typeof raw.lastDay === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(raw.lastDay)) s.lastDay = raw.lastDay;
  if (Array.isArray(raw.dist)) s.dist = s.dist.map((_, i) => num(raw.dist[i]));
  return s;
}

function prevDay(dayKey) {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(dayKey));
  if (!m) return '';
  return new Date(Date.UTC(+m[1], +m[2] - 1, +m[3] - 1)).toISOString().slice(0, 10);
}

export function recordResult(won, guessCount, dayKey) {
  const s = loadStats();
  s.played += 1;
  // 예전 통계(lastDay 없음)는 연승을 건드리지 않는다. 어제도 오늘도 아니면 연승을 새로 시작한다.
  if (s.lastDay && s.lastDay !== dayKey && s.lastDay !== prevDay(dayKey)) s.streak = 0;
  if (won) {
    s.wins += 1;
    s.streak += 1;
    s.maxStreak = Math.max(s.maxStreak, s.streak);
    const i = Math.floor(guessCount) - 1;
    if (i >= 0 && i < s.dist.length) s.dist[i] += 1;
  } else {
    s.streak = 0;
  }
  if (typeof dayKey === 'string' && dayKey) s.lastDay = dayKey;
  write('stats', s);
  return s;
}

export function loadDaily(dayKey) {
  const v = read('daily.' + dayKey);
  return v && typeof v === 'object' ? v : null;
}

export function saveDaily(dayKey, data) {
  write('daily.' + dayKey, data);
}

export function clearDaily(dayKey) {
  remove('daily.' + dayKey);
}

export function loadSettings() {
  const raw = read('settings');
  const o = raw && typeof raw === 'object' ? raw : {};
  return { hardMode: o.hardMode === true, dark: o.dark === true, colorblind: o.colorblind === true };
}

export function saveSettings(settings) {
  write('settings', {
    hardMode: !!settings.hardMode,
    dark: !!settings.dark,
    colorblind: !!settings.colorblind,
  });
}

// 도움말을 이미 봤는지 (ui.js 보조)
export function loadSeenHelp() {
  return read('seenHelp') === true;
}

export function saveSeenHelp() {
  write('seenHelp', true);
}
