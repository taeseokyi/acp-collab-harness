import { test } from "node:test";
import assert from "node:assert/strict";
import {
  scoreGuess, keyboardState, hardModeViolation, createGame, fromJSON,
  dailyIndex, answerForDate, WORD_LENGTH, MAX_GUESSES
} from "../web/js/game.js";

const HANGUK = "ㅎㅏㄴㄱㅜㄱ";
const KKADAK = "ㄲㅏㄷㅏㄹㄱ";
const KOKKIRI = "ㅋㅗㄲㅣㄹㅣ";
const GAROSU = "ㄱㅏㄹㅗㅅㅜ";
const BANANA = "ㅂㅏㄴㅏㄴㅏ";
const GONGHANG = "ㄱㅗㅇㅎㅏㅇ";

const CORRECT = "correct";
const PRESENT = "present";
const ABSENT = "absent";

test("상수: WORD_LENGTH === 6, MAX_GUESSES === 6", () => {
  assert.equal(WORD_LENGTH, 6);
  assert.equal(MAX_GUESSES, 6);
});

test("scoreGuess: 같은 판은 모두 초록", () => {
  assert.deepEqual(scoreGuess(HANGUK, HANGUK), Array(6).fill(CORRECT));
});

test("scoreGuess: 자리 맞은 자모가 먼저 가져간다", () => {
  assert.deepEqual(
    scoreGuess("ㄱㄱㄱㄴㄴㄴ", "ㄱㄱㅏㅏㄴㄴ"),
    [CORRECT, CORRECT, ABSENT, ABSENT, CORRECT, CORRECT]
  );
});

test("scoreGuess: 겹치는 자모는 정답에 남은 개수만큼만 present", () => {
  assert.deepEqual(
    scoreGuess("ㄴㄴㄴㄱㄱㄱ", "ㄱㅏㄴㄱㅏㄴ"),
    [PRESENT, ABSENT, CORRECT, CORRECT, PRESENT, ABSENT]
  );
});

test("scoreGuess: 길이가 다르면 예외", () => {
  assert.throws(() => scoreGuess("ㄱㄱㄱ", HANGUK));
  assert.throws(() => scoreGuess(HANGUK, KKADAK.slice(0, 5)));
});

test("keyboardState: 줄에서 자모 상태를 모은다", () => {
  const state = keyboardState([
    { guess: KKADAK, scores: [PRESENT, ABSENT, ABSENT, ABSENT, ABSENT, ABSENT] }
  ]);
  assert.equal(state["ㄲ"], PRESENT);
  assert.equal(state["ㅋ"], undefined);
});

test("keyboardState: 줄이 늘어도 높은 상태만 남는다", () => {
  const state = keyboardState([
    { guess: KKADAK, scores: [PRESENT, ABSENT, ABSENT, ABSENT, ABSENT, ABSENT] },
    { guess: KKADAK, scores: [CORRECT, ABSENT, ABSENT, ABSENT, ABSENT, ABSENT] }
  ]);
  assert.equal(state["ㄲ"], CORRECT);
  const reversed = keyboardState([
    { guess: KKADAK, scores: [CORRECT, ABSENT, ABSENT, ABSENT, ABSENT, ABSENT] },
    { guess: KKADAK, scores: [PRESENT, ABSENT, ABSENT, ABSENT, ABSENT, ABSENT] }
  ]);
  assert.equal(reversed["ㄲ"], CORRECT);
});

test("hardModeViolation: 초록 자리를 어기면 잡힌다", () => {
  const rows = [{ guess: KKADAK, scores: [CORRECT, ABSENT, ABSENT, ABSENT, ABSENT, ABSENT] }];
  const msg = hardModeViolation("ㅋㅏㄷㅏㄹㄱ", rows);
  assert.ok(msg && msg.includes("1번째 칸은 ㄲ 이어야 합니다"));
});

test("hardModeViolation: 노랑 자모가 아예 빠지면 잡힌다", () => {
  const rows = [{ guess: KKADAK, scores: [ABSENT, ABSENT, ABSENT, ABSENT, ABSENT, PRESENT] }];
  const msg = hardModeViolation("ㅁㅁㅁㅁㅁㅁ", rows);
  assert.ok(msg && msg.includes("ㄱ 가 들어가야 합니다"));
});

test("hardModeViolation: 노랑이 둘인데 하나만 넣으면 잡힌다", () => {
  const rows = [{ guess: "ㄱㄱㄴㄴㄷㄷ", scores: [PRESENT, PRESENT, ABSENT, ABSENT, ABSENT, ABSENT] }];
  const msg = hardModeViolation("ㄱㄴㄴㄴㄷㄷ", rows);
  assert.ok(msg && msg.includes("ㄱ 가 2개 들어가야 합니다"));
});

test("hardModeViolation: 노랑 둘을 다 넣으면 null", () => {
  const rows = [{ guess: "ㄱㄱㄴㄴㄷㄷ", scores: [PRESENT, PRESENT, ABSENT, ABSENT, ABSENT, ABSENT] }];
  assert.equal(hardModeViolation("ㄴㄴㄱㄱㄷㄷ", rows), null);
});

test("hardModeViolation: 노랑이었던 자리에 같은 자모를 되놓으면 잡힌다", () => {
  const rows = [{ guess: "ㄱㅏㄴㄴㄷㄷ", scores: [PRESENT, ABSENT, ABSENT, ABSENT, ABSENT, ABSENT] }];
  const msg = hardModeViolation("ㄱㅁㅁㅁㅁㅁ", rows);
  assert.ok(msg && msg.includes("ㄱ 는 1번째 자리가 아닙니다"));
});

test("hardModeViolation: 규칙을 다 지킨 추측은 null", () => {
  const rows = [{ guess: KKADAK, scores: [CORRECT, ABSENT, ABSENT, ABSENT, ABSENT, PRESENT] }];
  assert.equal(hardModeViolation("ㄲㅗㄱㅣㄹㅁ", rows), null);
});

test("hardModeViolation: rows 가 비었거나 null 이면 null", () => {
  assert.equal(hardModeViolation(KKADAK, []), null);
  assert.equal(hardModeViolation(KKADAK, null), null);
});

test("addLetter: 자모 한 글자만 받고 6칸을 넘기지 않는다", () => {
  const g = createGame({ answer: HANGUK, allowed: [HANGUK] });
  assert.equal(g.addLetter("a"), false);
  assert.equal(g.addLetter("ㅘ"), false);
  assert.equal(g.addLetter("ㄳ"), false);
  assert.equal(g.addLetter("가"), false);
  assert.equal(g.addLetter("ㄲ"), true);
  assert.equal(g.current, "ㄲ");
  g.removeLetter();
  for (const ch of HANGUK) assert.equal(g.addLetter(ch), true);
  assert.equal(g.current, HANGUK);
  assert.equal(g.addLetter("ㅎ"), false);
  assert.equal(g.current.length, 6);
});

test("submit: 모자라면 실패 문구가 자모 6개", () => {
  const g = createGame({ answer: HANGUK, allowed: [HANGUK] });
  for (const ch of "ㅎㅏㄴ") g.addLetter(ch);
  const res = g.submit();
  assert.equal(res.ok, false);
  assert.equal(res.reason, "short");
  assert.equal(res.message, "자모 6개를 채워 주세요");
  assert.equal(g.rows.length, 0);
  assert.equal(g.current, "ㅎㅏㄴ");
});

test("submit: 목록에 없으면 실패하고 판이 그대로", () => {
  const g = createGame({ answer: HANGUK, allowed: [HANGUK] });
  for (const ch of KKADAK) g.addLetter(ch);
  const res = g.submit();
  assert.equal(res.ok, false);
  assert.equal(res.reason, "unknown");
  assert.equal(res.message, "낱말 목록에 없는 낱말입니다");
  assert.equal(g.rows.length, 0);
  assert.equal(g.current, KKADAK);
});

test("판 진행: 제출·이김·끝난 판", () => {
  const g = createGame({ answer: HANGUK, allowed: [HANGUK, KKADAK, KOKKIRI] });
  for (const ch of KKADAK) g.addLetter(ch);
  let res = g.submit();
  assert.equal(res.ok, true);
  assert.equal(res.status, "playing");
  assert.equal(g.rows.length, 1);
  assert.equal(g.current, "");
  for (const ch of HANGUK) g.addLetter(ch);
  res = g.submit();
  assert.equal(res.ok, true);
  assert.equal(res.status, "won");
  assert.equal(g.rows.length, 2);
  res = g.submit();
  assert.equal(res.ok, false);
  assert.equal(res.reason, "over");
  assert.equal(res.message, "이미 끝난 판입니다");
});

test("지는 판: 여섯 번 틀리면 lost", () => {
  const g = createGame({ answer: HANGUK, allowed: [KKADAK] });
  for (let i = 0; i < 6; i++) {
    for (const ch of KKADAK) g.addLetter(ch);
    assert.equal(g.submit().ok, true);
  }
  assert.equal(g.status, "lost");
  assert.equal(g.rows.length, 6);
  assert.equal(g.submit().reason, "over");
});

test("shareText: 날마다 판", () => {
  const g = createGame({ answer: HANGUK, allowed: [HANGUK, KKADAK], puzzleNumber: 3 });
  for (const ch of KKADAK) g.addLetter(ch);
  g.submit();
  for (const ch of HANGUK) g.addLetter(ch);
  g.submit();
  const lines = g.shareText().split("\n");
  assert.equal(lines[0], "자모맞히기 3 2/6");
  assert.equal(lines[1], "");
  assert.deepEqual(lines.slice(2), ["⬛🟩⬛⬛⬛🟩", "🟩🟩🟩🟩🟩🟩"]);
  assert.equal(lines.length, 4);
});

test("shareText: 연습 판", () => {
  const g = createGame({ answer: HANGUK, allowed: [HANGUK], puzzleNumber: 0 });
  for (const ch of HANGUK) g.addLetter(ch);
  g.submit();
  assert.equal(g.shareText().split("\n")[0], "자모맞히기 연습 1/6");
});

test("shareText: 진 판은 X/6", () => {
  const g = createGame({ answer: HANGUK, allowed: [KKADAK], puzzleNumber: 5 });
  for (let i = 0; i < 6; i++) {
    for (const ch of KKADAK) g.addLetter(ch);
    g.submit();
  }
  const lines = g.shareText().split("\n");
  assert.equal(lines[0], "자모맞히기 5 X/6");
  assert.equal(lines.length, 8);
  assert.equal(lines[2], "⬛🟩⬛⬛⬛🟩");
});

test("shareText: 하드 모드는 별표", () => {
  const g = createGame({ answer: HANGUK, allowed: [HANGUK], hardMode: true, puzzleNumber: 1 });
  for (const ch of HANGUK) g.addLetter(ch);
  g.submit();
  assert.equal(g.shareText().split("\n")[0], "자모맞히기 1 1/6*");
});

test("하드 모드: 규칙을 어긴 추측은 제출 전에 거절", () => {
  const g = createGame({
    answer: HANGUK, allowed: [HANGUK, KKADAK, KOKKIRI],
    hardMode: true, puzzleNumber: 1
  });
  for (const ch of KKADAK) g.addLetter(ch);
  assert.equal(g.submit().ok, true);
  for (const ch of KOKKIRI) g.addLetter(ch);
  const res = g.submit();
  assert.equal(res.ok, false);
  assert.equal(res.reason, "hard");
  assert.ok(res.message.includes("ㅏ"));
  assert.equal(g.rows.length, 1);
  assert.equal(g.status, "playing");
});

test("저장과 복원: 판이 그대로 돌아온다", () => {
  const allowed = [HANGUK, KKADAK, KOKKIRI];
  const g = createGame({ answer: HANGUK, allowed, puzzleNumber: 4 });
  for (const ch of KKADAK) g.addLetter(ch);
  g.submit();
  for (const ch of "ㅋㅗ") g.addLetter(ch);
  const back = fromJSON(JSON.parse(JSON.stringify(g.toJSON())), { allowed });
  assert.equal(back.answer, HANGUK);
  assert.equal(back.status, "playing");
  assert.equal(back.rows.length, 1);
  assert.deepEqual(back.rows[0].scores, g.rows[0].scores);
  assert.equal(back.current, "ㅋㅗ");
  assert.equal(back.puzzleNumber, 4);
  for (const ch of "ㄴㄱㅜㄱ") back.addLetter(ch);
  assert.equal(back.current.length, 6);
});

test("저장과 복원: 저장된 scores 를 믿지 않고 다시 판정", () => {
  const back = fromJSON({
    answer: HANGUK,
    rows: [{ guess: KKADAK, scores: Array(6).fill(CORRECT) }],
    current: ""
  }, { allowed: [HANGUK, KKADAK] });
  assert.deepEqual(back.rows[0].scores, [ABSENT, CORRECT, ABSENT, ABSENT, ABSENT, CORRECT]);
});

test("저장과 복원: 손상된 저장값은 거절", () => {
  const good = { answer: HANGUK, rows: [], current: "" };
  assert.throws(() => fromJSON(null), /저장된 판이/);
  assert.throws(() => fromJSON({}), /저장된 정답/);
  assert.throws(() => fromJSON({ ...good, answer: "ㄱㄱㄱㄱㄱ" }), /저장된 정답/);
  assert.throws(() => fromJSON({ ...good, answer: "abcdef" }), /저장된 정답/);
  const sevenRows = Array.from({ length: 7 }, () => ({
    guess: KKADAK, scores: Array(6).fill(ABSENT)
  }));
  assert.throws(() => fromJSON({ ...good, rows: sevenRows }), /줄 수/);
  assert.throws(() => fromJSON({
    ...good, rows: [{ guess: "ㄱㄱㄱㄱㄱ", scores: Array(5).fill(ABSENT) }]
  }), /추측/);
  assert.throws(() => fromJSON({
    ...good, rows: [{ guess: KKADAK, scores: Array(5).fill(ABSENT) }]
  }), /판정/);
  assert.throws(() => fromJSON({
    ...good, rows: [{ guess: KKADAK, scores: [...Array(5).fill(ABSENT), "green"] }]
  }), /판정/);
  assert.throws(() => fromJSON({
    ...good,
    rows: [
      { guess: HANGUK, scores: Array(6).fill(CORRECT) },
      { guess: KKADAK, scores: Array(6).fill(ABSENT) }
    ]
  }), /이미 맞혔는데/);
});

test("저장과 복원: current 의 자모가 아닌 글자는 버린다", () => {
  const good = { answer: HANGUK, rows: [] };
  assert.equal(fromJSON({ ...good, current: "ㄱaㅏ" }).current, "");
  assert.equal(fromJSON({ ...good, current: "ㅘ" }).current, "");
  assert.equal(fromJSON({ ...good, current: "ㄱㅏㄴㄱㅜㄱㅎ" }).current, "ㄱㅏㄴㄱㅜㄱ");
  assert.equal(fromJSON({ ...good, current: "ㄱㅏ" }).current, "ㄱㅏ");
});

test("날짜: 2026-11-13 이 0, 다음 날이 1", () => {
  assert.equal(dailyIndex(new Date(2026, 10, 13, 0, 1)), 0);
  assert.equal(dailyIndex(new Date(2026, 10, 13, 23, 59)), 0);
  assert.equal(dailyIndex(new Date(2026, 10, 14, 9)), 1);
  assert.equal(dailyIndex(new Date(2026, 10, 12, 12)), -1);
  assert.throws(() => dailyIndex(new Date("아무 날")));
});

test("날짜: answerForDate 는 날짜마다 같은 정답", () => {
  const answers = [GAROSU, BANANA, GONGHANG];
  const day = new Date(2026, 10, 13);
  const a = answerForDate(day, answers);
  assert.ok(answers.includes(a));
  assert.equal(answerForDate(new Date(2026, 10, 13, 22), answers), a);
  assert.equal(answerForDate(new Date(2026, 10, 14), answers), answers[1]);
});
