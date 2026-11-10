import { test } from "node:test";
import assert from "node:assert/strict";
import { scoreGuess, keyboardState, hardModeViolation, createGame, fromJSON,
         dailyIndex, answerForDate, WORD_LENGTH, MAX_GUESSES } from "../web/js/game.js";

test("상수: WORD_LENGTH === 5, MAX_GUESSES === 6", () => {
  assert.equal(WORD_LENGTH, 5);
  assert.equal(MAX_GUESSES, 6);
});

test("scoreGuess 표", () => {
  const cases = [
    ["crane", "crane", ["correct", "correct", "correct", "correct", "correct"]],
    ["nanny", "crane", ["absent", "present", "absent", "correct", "absent"]],
    ["bebop", "abbey", ["present", "present", "correct", "absent", "absent"]],
    ["eerie", "abide", ["absent", "absent", "absent", "present", "correct"]],
    ["stars", "sassy", ["correct", "absent", "present", "absent", "present"]],
  ];
  for (const [guess, answer, expected] of cases) {
    assert.deepEqual(scoreGuess(guess, answer), expected);
  }
});

test("keyboardState", () => {
  let state = keyboardState([{ guess: "abbey", scores: ["present", "absent", "absent", "absent", "absent"] }]);
  assert.equal(state.a, "present");
  state = keyboardState([
    { guess: "abbey", scores: ["present", "absent", "absent", "absent", "absent"] },
    { guess: "about", scores: ["correct", "absent", "absent", "absent", "absent"] },
  ]);
  assert.equal(state.a, "correct");
  state = keyboardState([
    { guess: "about", scores: ["correct", "absent", "absent", "absent", "absent"] },
    { guess: "abbey", scores: ["present", "absent", "absent", "absent", "absent"] },
  ]);
  assert.equal(state.a, "correct");
  assert.equal(state.z, undefined);
});

test("hardModeViolation", () => {
  const rows = [{ guess: "crane", scores: ["correct", "absent", "absent", "absent", "present"] }];
  assert.equal(hardModeViolation("chess", rows), null);
  assert.match(hardModeViolation("blown", rows), /C/);
  assert.match(hardModeViolation("crank", rows), /E/);
});

test("판 진행", () => {
  const g = createGame({ answer: "crane", allowed: ["crane", "slate", "audio", "ghost"] });
  for (const ch of "cra") g.addLetter(ch);
  let res = g.submit();
  assert.equal(res.ok, false);
  assert.equal(res.reason, "short");
  for (let i = 0; i < 3; i++) g.removeLetter();
  for (const ch of "zzzzz") g.addLetter(ch);
  res = g.submit();
  assert.equal(res.ok, false);
  assert.equal(res.reason, "unknown");
  for (let i = 0; i < 5; i++) g.removeLetter();
  for (const ch of "slate") g.addLetter(ch);
  res = g.submit();
  assert.equal(res.ok, true);
  assert.equal(res.status, "playing");
  assert.equal(g.rows.length, 1);
  assert.equal(g.current, "");
  for (const ch of "crane") g.addLetter(ch);
  res = g.submit();
  assert.equal(res.ok, true);
  assert.equal(res.status, "won");
  res = g.submit();
  assert.equal(res.ok, false);
  assert.equal(res.reason, "over");
});

test("지는 판", () => {
  const g = createGame({ answer: "crane", allowed: ["ghost"] });
  for (let i = 0; i < 6; i++) {
    for (const ch of "ghost") g.addLetter(ch);
    assert.equal(g.submit().ok, true);
  }
  assert.equal(g.status, "lost");
  assert.equal(g.rows.length, 6);
});

test("shareText", () => {
  const g = createGame({ answer: "crane", allowed: ["crane", "slate", "audio", "ghost"] });
  for (const ch of "slate") g.addLetter(ch);
  g.submit();
  for (const ch of "crane") g.addLetter(ch);
  g.submit();
  const lines = g.shareText().split("\n");
  assert.ok(lines[0].startsWith("웹워들"));
  assert.ok(lines[0].includes("2/6"));
  assert.equal(lines.length, 2 + g.rows.length);
  assert.equal(lines[lines.length - 1], "🟩🟩🟩🟩🟩");
});

test("저장과 복원", () => {
  const g = createGame({ answer: "crane", allowed: ["crane", "slate", "audio", "ghost"] });
  for (const ch of "slate") g.addLetter(ch);
  g.submit();
  for (const ch of "crane") g.addLetter(ch);
  g.submit();
  const back = fromJSON(g.toJSON(), { allowed: ["crane", "slate", "audio", "ghost"] });
  assert.equal(back.rows.length, g.rows.length);
  assert.equal(back.status, g.status);
  assert.equal(back.answer, g.answer);
});

test("날짜", () => {
  const d = new Date(2026, 5, 1);
  const idx = dailyIndex(d);
  assert.ok(Number.isInteger(idx));
  assert.equal(dailyIndex(new Date(2026, 5, 2)), idx + 1);
  const ANS = ["crane", "slate", "audio", "ghost", "pound"];
  const a = answerForDate(d, ANS);
  assert.equal(answerForDate(d, ANS), a);
  assert.ok(ANS.includes(a));
});
