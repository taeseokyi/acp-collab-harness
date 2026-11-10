// 통합 연기 테스트: words.js 와 game.js 를 실제로 불러 맞물려 도는지 본다.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { scoreGuess, answerForDate, createGame, fromJSON } from "../web/js/game.js";
import { ANSWERS, ALLOWED } from "../web/js/words.js";

const ALLOWED_SET = new Set(ALLOWED);

test("ANSWERS 의 모든 낱말이 ALLOWED 안에 있다", () => {
  const missing = ANSWERS.filter((w) => !ALLOWED_SET.has(w));
  assert.deepEqual(missing, []);
});

test("ANSWERS·ALLOWED 의 모든 낱말이 a-z 다섯 글자", () => {
  assert.ok(ANSWERS.length > 0 && ALLOWED.length > 0);
  const bad = [...ANSWERS, ...ALLOWED].filter((w) => !/^[a-z]{5}$/.test(w));
  assert.deepEqual(bad, []);
});

test("answerForDate(오늘) 은 ANSWERS 안의 낱말", () => {
  assert.ok(ANSWERS.includes(answerForDate(new Date(), ANSWERS)));
});

// 독립 구현: 글자별로 따로 센다.
// 글자 ch 의 노랑 개수 = min(초록이 아닌 추측 속 ch 수, 초록이 아닌 정답 속 ch 수),
// 그 개수만큼 초록이 아닌 추측 자리 중 앞쪽부터 노랑을 준다.
function referenceScore(guess, answer) {
  const out = ["absent", "absent", "absent", "absent", "absent"];
  const green = [0, 1, 2, 3, 4].map((i) => guess[i] === answer[i]);
  green.forEach((g, i) => { if (g) out[i] = "correct"; });
  for (const ch of new Set(guess)) {
    const guessSlots = [0, 1, 2, 3, 4].filter((i) => !green[i] && guess[i] === ch);
    const spare = [0, 1, 2, 3, 4].filter((i) => !green[i] && answer[i] === ch).length;
    guessSlots.slice(0, spare).forEach((i) => { out[i] = "present"; });
  }
  return out;
}

// 고정 시드 선형 합동 생성기 (Numerical Recipes 상수, 32비트)
function lcg(seed) {
  let s = seed >>> 0;
  return () => {
    s = (Math.imul(s, 1664525) + 1013904223) >>> 0;
    return s;
  };
}

test("독립 대조: 고정 시드 1,000쌍에서 scoreGuess 와 참조 구현이 같다", () => {
  // 참조 구현 자체가 맞는지 손으로 푼 겹친 글자 사례로 먼저 본다
  assert.deepEqual(referenceScore("stars", "sassy"),
    ["correct", "absent", "present", "absent", "present"]);
  assert.deepEqual(referenceScore("eerie", "abide"),
    ["absent", "absent", "absent", "present", "correct"]);

  const next = lcg(20261110);
  const pairs = [];
  for (let k = 0; k < 1000; k++) {
    pairs.push([ANSWERS[next() % ANSWERS.length], ANSWERS[next() % ANSWERS.length]]);
  }
  // 같은 시드면 같은 쌍이 나와야 한다
  const again = lcg(20261110);
  assert.deepEqual(pairs[0], [ANSWERS[again() % ANSWERS.length], ANSWERS[again() % ANSWERS.length]]);

  const diffs = [];
  let withDup = 0;
  for (const [answer, guess] of pairs) {
    if (new Set(guess).size < 5 || new Set(answer).size < 5) withDup++;
    const got = scoreGuess(guess, answer);
    const want = referenceScore(guess, answer);
    if (JSON.stringify(got) !== JSON.stringify(want)) diffs.push({ guess, answer, got, want });
  }
  assert.deepEqual(diffs.slice(0, 5), []);
  assert.ok(withDup > 0, "겹친 글자 쌍이 하나도 뽑히지 않았다");
});

function wrongGuesses(answer, n) {
  return ANSWERS.filter((w) => w !== answer).slice(0, n);
}

test("진짜 한 판: 틀린 추측 다섯 번 + 정답 → won, 공유 마지막 줄 🟩🟩🟩🟩🟩", () => {
  const answer = ANSWERS[0];
  const game = createGame({ answer, allowed: ALLOWED });
  const typeAndSubmit = (word) => {
    for (const ch of word) assert.equal(game.addLetter(ch), true);
    return game.submit();
  };
  for (const w of wrongGuesses(answer, 5)) {
    const res = typeAndSubmit(w);
    assert.equal(res.ok, true, `${w}: ${res.message}`);
    assert.equal(game.status, "playing");
  }
  const res = typeAndSubmit(answer);
  assert.equal(res.ok, true);
  assert.equal(game.status, "won");
  assert.equal(game.rows.length, 6);
  const lines = game.shareText().split("\n");
  assert.equal(lines.at(-1), "🟩🟩🟩🟩🟩");
  // 끝난 판은 입력을 더 받지 않는다
  assert.equal(game.addLetter("a"), false);
  assert.equal(game.submit().ok, false);
});

test("저장·복원: 두 줄 둔 판을 toJSON → fromJSON 하면 이어서 둘 수 있다", () => {
  const answer = ANSWERS[0];
  const game = createGame({ answer, allowed: ALLOWED });
  const [w1, w2] = wrongGuesses(answer, 2);
  for (const w of [w1, w2]) {
    for (const ch of w) game.addLetter(ch);
    assert.equal(game.submit().ok, true);
  }
  // 실제 저장 경로처럼 문자열을 한 번 거친다
  const data = JSON.parse(JSON.stringify(game.toJSON()));
  const restored = fromJSON(data, { allowed: ALLOWED });
  assert.equal(restored.status, "playing");
  assert.deepEqual(restored.rows, game.rows);
  for (const ch of answer) restored.addLetter(ch);
  const res = restored.submit();
  assert.equal(res.ok, true);
  assert.equal(restored.status, "won");
  assert.equal(restored.rows.length, 3);
});

// ---------- T-103 회귀: fromJSON 이 손상된 저장값을 막는다 ----------

// 정상 저장값 하나를 만들어 두고 필드만 바꿔 손상을 흉내 낸다.
function savedGame(words) {
  const answer = ANSWERS[0];
  const g = createGame({ answer, allowed: ALLOWED });
  for (const w of words) {
    for (const ch of w) g.addLetter(ch);
    assert.equal(g.submit().ok, true, w);
  }
  return JSON.parse(JSON.stringify(g.toJSON()));
}

test("fromJSON: maxGuesses 99 는 6 으로 잡힌다", () => {
  const data = { ...savedGame([]), maxGuesses: 99 };
  assert.equal(fromJSON(data, { allowed: ALLOWED }).maxGuesses, 6);
  // 0·음수·소수·문자열도 같은 기본값
  for (const mg of [0, -1, 2.5, "x", null]) {
    assert.equal(fromJSON({ ...savedGame([]), maxGuesses: mg }).maxGuesses, 6, String(mg));
  }
});

test("fromJSON: answer 가 다섯 글자가 아니면 예외", () => {
  for (const answer of ["abcd", "abcdef", "", 12345, null, undefined, "ab1de", "가나다라마"]) {
    assert.throws(() => fromJSON({ ...savedGame([]), answer }), Error, String(answer));
  }
});

test("fromJSON: rows 의 한 줄이 모양에 안 맞으면 예외", () => {
  const base = savedGame(wrongGuesses(ANSWERS[0], 2));
  const good = base.rows[0];
  const broken = [
    null,
    "crane",
    { guess: "abc", scores: good.scores },
    { guess: "ab1de", scores: good.scores },
    { scores: good.scores },
    { guess: good.guess },
    { guess: good.guess, scores: good.scores.slice(0, 4) },
    { guess: good.guess, scores: ["correct", "present", "absent", "absent", "green"] },
  ];
  for (const row of broken) {
    assert.throws(() => fromJSON({ ...base, rows: [row, base.rows[1]] }), Error, JSON.stringify(row));
  }
  // 이긴 줄 뒤에 줄이 더 있어도 예외
  const won = savedGame([ANSWERS[0]]);
  assert.throws(() => fromJSON({ ...won, rows: [won.rows[0], base.rows[0]] }), Error);
});

test("fromJSON: rows.length 가 maxGuesses 를 넘으면 예외", () => {
  const base = savedGame(wrongGuesses(ANSWERS[0], 3));
  assert.throws(() => fromJSON({ ...base, maxGuesses: 2 }), Error);
  const seven = [...base.rows, ...base.rows, base.rows[0]];
  assert.equal(seven.length, 7);
  assert.throws(() => fromJSON({ ...base, rows: seven }), Error);
  // 경계: 줄 수 == maxGuesses 는 받는다 (진 판)
  assert.equal(fromJSON({ ...base, maxGuesses: 3 }).status, "lost");
});

test("fromJSON: 저장 status 를 믿지 않는다 - 이긴 rows + status:playing → won", () => {
  const data = { ...savedGame([...wrongGuesses(ANSWERS[0], 2), ANSWERS[0]]), status: "playing" };
  const g = fromJSON(data, { allowed: ALLOWED });
  assert.equal(g.status, "won");
  assert.equal(g.addLetter("a"), false);
  // 반대로 진행 중 rows + status:won 은 playing 으로 돌아온다
  const mid = { ...savedGame(wrongGuesses(ANSWERS[0], 1)), status: "won" };
  assert.equal(fromJSON(mid).status, "playing");
  // 저장된 scores 를 조작해도 다시 판정한다
  const fake = savedGame(wrongGuesses(ANSWERS[0], 1));
  fake.rows[0].scores = ["correct", "correct", "correct", "correct", "correct"];
  assert.deepEqual(fromJSON(fake).rows[0].scores, scoreGuess(fake.rows[0].guess, ANSWERS[0]));
});

test("fromJSON: current 에 이상한 글자가 있으면 빈 문자열", () => {
  for (const current of ["ab1", "a b", "AB", "é", "<b>", 123, null, ["a"]]) {
    assert.equal(fromJSON({ ...savedGame([]), current }).current, "", JSON.stringify(current));
  }
  assert.equal(fromJSON({ ...savedGame([]), current: "abcdefgh" }).current, "abcde");
  assert.equal(fromJSON({ ...savedGame([]), current: "abc" }).current, "abc");
});

// ---------- T-103 회귀: storage.recordResult 의 연승 ----------

test("recordResult: lastDay 로 끊긴 연승을 다시 시작하고, lastDay 없는 예전 값은 깎지 않는다", async () => {
  const mem = new Map();
  const prev = Object.getOwnPropertyDescriptor(globalThis, "localStorage");
  Object.defineProperty(globalThis, "localStorage", {
    configurable: true,
    value: {
      getItem: (k) => (mem.has(k) ? mem.get(k) : null),
      setItem: (k, v) => mem.set(k, String(v)),
      removeItem: (k) => mem.delete(k),
    },
  });
  try {
    const { recordResult, loadStats } = await import("../web/js/storage.js");
    const put = (o) => mem.set("webwordle.stats", JSON.stringify(o));
    // 예전 저장값: lastDay 없음, 연승 4 → 깎이지 않고 5
    put({ played: 4, wins: 4, streak: 4, maxStreak: 4, dist: [0, 0, 4, 0, 0, 0] });
    assert.equal(recordResult(true, 3, "2026-11-01").streak, 5);
    assert.equal(loadStats().lastDay, "2026-11-01");
    // 바로 다음 날 → 이어짐
    assert.equal(recordResult(true, 2, "2026-11-02").streak, 6);
    // 하루 건너뜀 → 1 부터, 최대 연승은 남음
    const s = recordResult(true, 2, "2026-11-04");
    assert.equal(s.streak, 1);
    assert.equal(s.maxStreak, 6);
    // 월·연 경계
    put({ ...loadStats(), streak: 3, lastDay: "2026-11-30" });
    assert.equal(recordResult(true, 1, "2026-12-01").streak, 4);
    put({ ...loadStats(), streak: 3, lastDay: "2026-12-31" });
    assert.equal(recordResult(true, 1, "2027-01-01").streak, 4);
    // 진 판은 0
    assert.equal(recordResult(false, 6, "2027-01-02").streak, 0);
  } finally {
    if (prev) Object.defineProperty(globalThis, "localStorage", prev);
    else delete globalThis.localStorage;
  }
});

// ---------- T-103 회귀: ui.js·style.css 고친 자리 (정적 검사) ----------

const read = (p) => readFileSync(new URL(p, import.meta.url), "utf8");

function importedNames(src, from) {
  const re = new RegExp(`import\\s*\\{([^}]*)\\}\\s*from\\s*['"]${from.replace(/\./g, "\\.")}['"]`);
  const m = re.exec(src);
  assert.ok(m, `ui.js 에 ${from} import 가 없다`);
  return m[1].split(",").map((s) => s.trim()).filter(Boolean);
}

test("계약: ui.js 가 import 하는 game.js·storage.js 이름이 모두 export 되어 있다", async () => {
  const ui = read("../web/js/ui.js");
  const game = await import("../web/js/game.js");
  const storage = await import("../web/js/storage.js");
  const missing = [
    ...importedNames(ui, "./game.js").filter((n) => !(n in game)),
    ...importedNames(ui, "./storage.js").filter((n) => !(n in storage)),
  ];
  assert.deepEqual(missing, []);
  // recordResult 는 dayKey 를 세 번째 인자로 받는다
  assert.match(ui, /recordResult\([^)]*,[^)]*,\s*dayKey\s*\)/);
});

test("ui.js: 새 판에 알림을 비우고 하드 모드를 맞추며, 화면 키는 mousedown 으로만 포커스를 막는다", () => {
  const ui = read("../web/js/ui.js");
  const start = ui.slice(ui.indexOf("function startToday"), ui.indexOf("function checkNewDay"));
  assert.match(start, /\$\('toasts'\)\.textContent\s*=\s*''/);
  assert.match(start, /game\.hardMode\s*!==\s*settings\.hardMode/);
  assert.match(ui, /addEventListener\('mousedown',\s*\(e\)\s*=>\s*e\.preventDefault\(\)\)/);
  // tabindex=-1 로 Tab 포커스를 없애지 않았고, focus-visible 테두리가 남아 있다
  assert.doesNotMatch(ui, /tabIndex|tabindex/);
  assert.match(read("../web/css/style.css"), /:focus-visible\s*\{[^}]*outline:\s*3px/);
});

test("style.css: 칸·키 글자색 열 조합과 dvh 대비 선언", () => {
  const css = read("../web/css/style.css").toLowerCase();
  const block = (sel) => {
    const i = css.indexOf(sel + " {");
    assert.ok(i >= 0, sel);
    return css.slice(i, css.indexOf("}", i));
  };
  const vars = (b) => Object.fromEntries([...b.matchAll(/(--[\w-]+):\s*([^;]+);/g)].map((m) => [m[1], m[2].trim()]));
  const light = vars(block(":root"));
  const dark = { ...light, ...vars(block('html[data-theme="dark"]')) };
  const cb = vars(block('html[data-colorblind="on"]'));
  const pairs = [
    [light["--correct"], light["--on-correct"]], [light["--present"], light["--on-present"]],
    [light["--absent"], light["--on-absent"]],
    [dark["--correct"], dark["--on-correct"]], [dark["--present"], dark["--on-present"]],
    [dark["--absent"], dark["--on-absent"]],
    [cb["--correct"], cb["--on-correct"]], [cb["--present"], cb["--on-present"]],
    [light["--key-bg"], light["--key-fg"]], [dark["--key-bg"], dark["--key-fg"]],
  ];
  assert.deepEqual(pairs, [
    ["#6aaa64", "#121213"], ["#c9b458", "#121213"], ["#6b6f71", "#ffffff"],
    ["#538d4e", "#121213"], ["#b59f3b", "#121213"], ["#3a3a3c", "#ffffff"],
    ["#f5793a", "#121213"], ["#85c0f9", "#121213"],
    ["#d3d6da", "#121213"], ["#565758", "#ffffff"],
  ]);
  // 칸·키가 고정 색이 아니라 변수를 써야 테마를 갈아끼울 때 함께 바뀐다
  for (const s of ["correct", "present", "absent"]) {
    assert.match(css, new RegExp(`\\.tile\\[data-state="${s}"\\]\\s*\\{[^}]*color:\\s*var\\(--on-${s}\\)`));
    assert.match(css, new RegExp(`\\.key\\[data-state="${s}"\\]\\s*\\{[^}]*color:\\s*var\\(--on-${s}\\)`));
  }
  assert.match(block(".key"), /color:\s*var\(--key-fg\)/);
  // dvh 를 쓰는 속성에는 반드시 vh 대비가 있어야 한다 (dvh 를 모르는 브라우저)
  const dvhProps = new Set(
    [...css.matchAll(/([\w-]+)\s*:\s*[^;]*dvh\b/g)].map((m) => m[1])
  );
  assert.ok(dvhProps.size >= 2, `dvh 를 쓰는 속성이 ${dvhProps.size} 개뿐이다`);
  for (const prop of dvhProps) {
    assert.ok(
      new RegExp(`${prop}\\s*:\\s*[^;]*(?<!d)vh\\b`).test(css),
      `${prop} 의 dvh 선언에 vh 대비가 없다`
    );
  }
});
