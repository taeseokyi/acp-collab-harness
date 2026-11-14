// 자모맞히기 순수 로직. DOM·window·localStorage·네트워크를 모르게 두어 node 에서 그대로 시험할 수 있게 한다.

export const WORD_LENGTH = 6;
export const MAX_GUESSES = 6;

const CORRECT = "correct";
const PRESENT = "present";
const ABSENT = "absent";
const RANK = { [ABSENT]: 1, [PRESENT]: 2, [CORRECT]: 3 };
const EMOJI = { [CORRECT]: "🟩", [PRESENT]: "🟨", [ABSENT]: "⬛" };
// 한 칸 = 두벌식 자판 한 번 누름 = 호환 자모 한 글자. 칸으로 쓰는 글자는 정확히 33개다.
const UNITS = 'ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎㅏㅐㅑㅒㅓㅔㅕㅖㅗㅛㅜㅠㅡㅣ';
const LETTER = new RegExp(`^[${UNITS}]$`);
const WORD = new RegExp(`^[${UNITS}]+$`);
const CURRENT = new RegExp(`^[${UNITS}]*$`);
const MS_PER_DAY = 86400000;
// 2026-11-13 을 0 번으로 센다. UTC 로 잡는 까닭은 dailyIndex 주석 참고.
const EPOCH_UTC = Date.UTC(2026, 10, 13);

// 대문자가 섞여 들어와도 판정이 갈리지 않게 소문자로 맞춘다.
// 길이가 다르면 조용히 잘라 판정하는 대신 예외를 던진다 - 호출하는 쪽 버그를 숨기지 않으려는 것.
export function scoreGuess(guess, answer) {
  const g = String(guess).toLowerCase();
  const a = String(answer).toLowerCase();
  if (g.length !== a.length) {
    throw new Error(`길이가 다릅니다: "${g}"(${g.length}) / "${a}"(${a.length})`);
  }
  const scores = new Array(g.length).fill(ABSENT);
  const left = {};
  // 1단계: 자리 맞은 글자가 먼저 가져간다. 가져가지 않은 정답 글자만 남은 개수로 센다.
  for (let i = 0; i < g.length; i++) {
    if (g[i] === a[i]) scores[i] = CORRECT;
    else left[a[i]] = (left[a[i]] || 0) + 1;
  }
  // 2단계: 왼쪽부터 남은 개수만큼만 노랑. 그래서 겹친 글자가 정답보다 많으면 뒤쪽은 회색이 된다.
  for (let i = 0; i < g.length; i++) {
    if (scores[i] === CORRECT) continue;
    if (left[g[i]] > 0) {
      scores[i] = PRESENT;
      left[g[i]]--;
    }
  }
  return scores;
}

// getTime() 차이를 그냥 나누면 서머타임이 있는 지역에서 하루가 23/25시간이 되어 번호가 어긋난다.
// 로컬 연·월·일만 뽑아 UTC 로 다시 세우면 "로컬 자정 기준 날짜" 끼리의 차이가 정확히 하루 단위가 된다.
export function dailyIndex(date = new Date()) {
  const d = date instanceof Date ? date : new Date(date);
  if (Number.isNaN(d.getTime())) throw new Error("날짜가 올바르지 않습니다");
  const local = Date.UTC(d.getFullYear(), d.getMonth(), d.getDate());
  return Math.round((local - EPOCH_UTC) / MS_PER_DAY);
}

// 날짜를 로컬 기준 `YYYY-MM-DD` 로 적는다. dailyIndex 와 같은 로컬 날짜 경계를 쓴다.
export function dayKey(date = new Date()) {
  const d = date instanceof Date ? date : new Date(date);
  if (Number.isNaN(d.getTime())) throw new Error("날짜가 올바르지 않습니다");
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

export function answerForDate(date, answers, trend = {}) {
  if (!answers || answers.length === 0) throw new Error("정답 목록이 비었습니다");
  // 트렌드에 그 날짜 키가 있으면 그 낱말이 정답이다. 없으면 기존처럼 날짜 번호로 고른다.
  const key = dayKey(date);
  if (trend && Object.prototype.hasOwnProperty.call(trend, key)) return trend[key];
  const n = answers.length;
  // JS 의 % 는 음수를 그대로 돌려주므로 2026 년 이전 날짜도 목록 안에 들어오게 한 번 더 맞춘다.
  return answers[((dailyIndex(date) % n) + n) % n];
}

export function keyboardState(rows) {
  const state = {};
  for (const row of rows || []) {
    const guess = String(row.guess).toLowerCase();
    for (let i = 0; i < guess.length; i++) {
      const ch = guess[i];
      const s = row.scores[i];
      // 같은 글자가 한 줄에서 초록·회색으로 동시에 나올 수 있으므로 높은 쪽만 남긴다.
      if (!state[ch] || RANK[s] > RANK[state[ch]]) state[ch] = s;
    }
  }
  return state;
}

// 초록 자리 -> 노랑 개수 -> 노랑 자리 되놓기 순으로 봅니다 - 안내가 더 구체적인 쪽이 먼저 나오게.
export function hardModeViolation(guess, rows) {
  const g = String(guess).toLowerCase();
  const prevRows = (rows || []).map((row) => ({
    word: String(row.guess).toLowerCase(),
    scores: row.scores,
  }));

  // 1. 초록 자리는 그대로 두어야 합니다.
  for (const { word, scores } of prevRows) {
    for (let i = 0; i < word.length; i++) {
      if (scores[i] === CORRECT && g[i] !== word[i]) {
        return `${i + 1}번째 칸은 ${word[i]} 이어야 합니다`;
      }
    }
  }

  // 2. 글자마다 "최소 몇 개" 가 드러났는지 - 한 줄에서 초록+노랑을 세고 줄 사이에서는 큰 쪽을 남깁니다.
  const need = {};
  for (const { word, scores } of prevRows) {
    const seen = {};
    for (let i = 0; i < word.length; i++) {
      if (scores[i] === CORRECT || scores[i] === PRESENT) {
        seen[word[i]] = (seen[word[i]] || 0) + 1;
      }
    }
    for (const ch of Object.keys(seen)) {
      if (!need[ch] || seen[ch] > need[ch]) need[ch] = seen[ch];
    }
  }
  for (const ch of Object.keys(need)) {
    let have = 0;
    for (const c of g) if (c === ch) have++;
    if (have < need[ch]) {
      const n = need[ch];
      return n === 1
        ? `${ch} 가 들어가야 합니다`
        : `${ch} 가 ${n}개 들어가야 합니다 (지금 ${have}개)`;
    }
  }

  // 3. 노랑이었던 자리에 같은 글자를 다시 놓을 수 없습니다 - 그 자리가 아니라는 것을 이미 알았습니다.
  for (const { word, scores } of prevRows) {
    for (let i = 0; i < word.length; i++) {
      if (scores[i] === PRESENT && g[i] === word[i]) {
        return `${word[i]} 는 ${i + 1}번째 자리가 아닙니다`;
      }
    }
  }

  return null;
}

function copyRows(rows) {
  return rows.map((r) => ({ guess: r.guess, scores: r.scores.slice() }));
}

function checkAnswer(answer) {
  const a = String(answer ?? "").toLowerCase();
  if (a.length !== WORD_LENGTH || !WORD.test(a)) {
    throw new Error(`정답은 자모 ${WORD_LENGTH}글자여야 합니다: "${answer}"`);
  }
  return a;
}

function toAllowedSet(allowed) {
  // 목록을 안 주면 null - 모든 자모 낱말을 받는다. 테스트나 자유 연습용으로 남겨 둔 것.
  if (allowed == null) return null;
  const set = new Set();
  for (const w of allowed) set.add(String(w).toLowerCase());
  return set;
}

class Game {
  #answer;
  #allowed;
  #rows = [];
  #current = "";
  #status = "playing";
  #hardMode;
  #puzzleNumber;
  #maxGuesses;

  constructor(options) {
    const o = options || {};
    this.#answer = checkAnswer(o.answer);
    this.#allowed = toAllowedSet(o.allowed);
    this.#hardMode = Boolean(o.hardMode);
    this.#puzzleNumber = Number.isInteger(o.puzzleNumber) ? o.puzzleNumber : 0;
    this.#maxGuesses =
      Number.isInteger(o.maxGuesses) && o.maxGuesses > 0 ? o.maxGuesses : MAX_GUESSES;
  }

  // 내부 상태는 private 로 두고 읽을 때마다 복사본을 준다 - 화면 쪽이 배열을 고쳐도 판이 깨지지 않게.
  get rows() { return copyRows(this.#rows); }
  get current() { return this.#current; }
  get status() { return this.#status; }
  get answer() { return this.#answer; }
  get hardMode() { return this.#hardMode; }
  get puzzleNumber() { return this.#puzzleNumber; }
  get maxGuesses() { return this.#maxGuesses; }

  // 사전에서 찾은 낱말을 지금 판에 보탠다. 목록이 없는 판(모두 허용)은 할 일이 없다. 저장 형식은 그대로.
  allowWord(units) {
    if (!this.#allowed || typeof units !== "string") return false;
    this.#allowed.add(units.toLowerCase());
    return true;
  }

  // 물리 키보드의 Shift/CapsLock 입력도 받도록 소문자로 맞춘 뒤 검사한다.
  addLetter(ch) {
    if (this.#status !== "playing" || typeof ch !== "string") return false;
    const c = ch.toLowerCase();
    if (!LETTER.test(c) || this.#current.length >= WORD_LENGTH) return false;
    this.#current += c;
    return true;
  }

  removeLetter() {
    if (this.#status !== "playing" || this.#current.length === 0) return false;
    this.#current = this.#current.slice(0, -1);
    return true;
  }

  // 검사를 모두 마친 뒤에만 상태를 바꾼다 - 실패하면 아무것도 바뀌지 않는다는 약속을 지키기 위해.
  submit() {
    if (this.#status !== "playing") {
      return { ok: false, reason: "over", message: "이미 끝난 판입니다" };
    }
    const guess = this.#current;
    if (guess.length < WORD_LENGTH) {
      return { ok: false, reason: "short", message: `자모 ${WORD_LENGTH}개를 채워 주세요` };
    }
    if (guess !== this.#answer && this.#allowed && !this.#allowed.has(guess)) {
      return { ok: false, reason: "unknown", message: "낱말 목록에 없는 낱말입니다" };
    }
    if (this.#hardMode) {
      const v = hardModeViolation(guess, this.#rows);
      if (v) return { ok: false, reason: "hard", message: v };
    }
    const row = { guess, scores: scoreGuess(guess, this.#answer) };
    this.#rows.push(row);
    this.#current = "";
    if (guess === this.#answer) this.#status = "won";
    else if (this.#rows.length >= this.#maxGuesses) this.#status = "lost";
    return { ok: true, row: { guess, scores: row.scores.slice() }, status: this.#status };
  }

  shareText() {
    // 진행 중인 판을 공유해도 X 로 찍히지 않게, 진 판일 때만 X 를 쓰고 그 밖엔 지금까지 쓴 횟수를 쓴다.
    const tries = this.#status === "lost" ? "X" : String(this.#rows.length);
    const head = this.#puzzleNumber > 0
      ? `자모맞히기 ${this.#puzzleNumber} ${tries}/${this.#maxGuesses}${this.#hardMode ? "*" : ""}`
      : `자모맞히기 연습 ${tries}/${this.#maxGuesses}`;
    const grid = this.#rows.map((r) => r.scores.map((s) => EMOJI[s]).join(""));
    return [head, "", ...grid].join("\n");
  }

  toJSON() {
    return {
      answer: this.#answer,
      rows: copyRows(this.#rows),
      current: this.#current,
      status: this.#status,
      hardMode: this.#hardMode,
      puzzleNumber: this.#puzzleNumber,
      maxGuesses: this.#maxGuesses,
    };
  }

  // fromJSON 전용. 저장된 scores·status 는 믿지 않고 추측만 다시 판정해 쌓는다 -
  // localStorage 가 손상되거나 손으로 고쳐져도 정답과 어긋난 색이 화면에 나오지 않게.
  _restore(data) {
    for (const r of Array.isArray(data.rows) ? data.rows : []) {
      if (this.#status !== "playing") break;
      const guess = String(r?.guess ?? "").toLowerCase();
      if (guess.length !== WORD_LENGTH || !WORD.test(guess)) continue;
      this.#rows.push({ guess, scores: scoreGuess(guess, this.#answer) });
      if (guess === this.#answer) this.#status = "won";
      else if (this.#rows.length >= this.#maxGuesses) this.#status = "lost";
    }
    if (this.#status === "playing" && typeof data.current === "string") {
      for (const ch of data.current) this.addLetter(ch);
    }
    return this;
  }
}

export function createGame(options) {
  return new Game(options);
}

// localStorage 는 사용자가 손으로 고칠 수 있는 곳이라 여기 들어오는 값은 전부 외부 입력으로 본다.
// 되살릴 수 없는 판은 반쯤 맞춰 살리지 않고 예외를 던진다 - 화면 쪽이 새 판을 주게.
export function fromJSON(data, options) {
  if (!data || typeof data !== "object") throw new Error("저장된 판이 올바르지 않습니다");

  // 보드는 MAX_GUESSES 줄뿐이라 그보다 큰 값을 받으면 화면 쪽에서 없는 줄을 건드린다.
  const mg = Number(data.maxGuesses);
  const maxGuesses = Number.isInteger(mg) && mg >= 1 && mg <= MAX_GUESSES ? mg : MAX_GUESSES;

  if (typeof data.answer !== "string" || data.answer.length !== WORD_LENGTH || !WORD.test(data.answer)) {
    throw new Error(`저장된 정답이 자모 ${WORD_LENGTH}글자가 아니라 판을 되살릴 수 없습니다`);
  }
  const answer = data.answer;

  const rawRows = Array.isArray(data.rows) ? data.rows : [];
  if (rawRows.length > maxGuesses) {
    throw new Error(`저장된 줄 수(${rawRows.length})가 최대 시도 횟수(${maxGuesses})를 넘습니다`);
  }
  const rows = rawRows.map((r, i) => {
    const n = i + 1;
    if (!r || typeof r !== "object") throw new Error(`저장된 ${n}번째 줄이 올바른 모양이 아닙니다`);
    const guess = typeof r.guess === "string" ? r.guess.toLowerCase() : "";
    if (guess.length !== WORD_LENGTH || !WORD.test(guess)) {
      throw new Error(`저장된 ${n}번째 줄의 추측이 자모 ${WORD_LENGTH}글자가 아닙니다`);
    }
    if (
      !Array.isArray(r.scores) ||
      r.scores.length !== WORD_LENGTH ||
      !r.scores.every((s) => s === CORRECT || s === PRESENT || s === ABSENT)
    ) {
      throw new Error(`저장된 ${n}번째 줄의 판정이 correct/present/absent ${WORD_LENGTH}개가 아닙니다`);
    }
    // 이긴 줄 뒤에 줄이 더 있으면 끝난 판에 제출이 이어진 것이라 앞뒤가 맞지 않는다.
    if (i < rawRows.length - 1 && guess === answer) {
      throw new Error(`저장된 ${n}번째 줄에서 이미 맞혔는데 뒤에 줄이 더 있습니다`);
    }
    return { guess, scores: r.scores.slice() };
  });

  let current = typeof data.current === "string" && CURRENT.test(data.current) ? data.current : "";
  if (current.length > WORD_LENGTH) current = current.slice(0, WORD_LENGTH);

  const game = new Game({
    answer,
    allowed: options?.allowed,
    hardMode: data.hardMode === true,
    puzzleNumber: data.puzzleNumber,
    maxGuesses,
  });
  // status 는 저장값을 넘기지 않는다 - _restore 가 rows 와 answer 로 다시 판정해 won/lost/playing 을 정한다.
  return game._restore({ rows, current });
}
