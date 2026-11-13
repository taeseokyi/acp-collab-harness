import { test } from "node:test";
import assert from "node:assert/strict";
import {
  UNITS, SHIFTED, KEY_ROWS, KEYMAP, toUnits, composeUnits
} from "../web/js/jamo.js";
import { ANSWERS, ALLOWED } from "../web/js/words.js";

const ROUNDTRIP_WORDS = [
  "까닭", "꼬끼리", "아가씨", "얘기", "예", "해", "세",
  "과", "괘", "괴", "궈", "궤", "귀", "의",
  "넋", "앉", "않", "닭", "삶", "넓", "곬", "핥", "읊", "앓", "값",
  "한국", "과자", "의사"
];

test("UNITS: 계약의 33글자 그대로", () => {
  assert.equal(UNITS, "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎㅏㅐㅑㅒㅓㅔㅕㅖㅗㅛㅜㅠㅡㅣ");
  assert.equal(UNITS.length, 33);
  assert.equal(new Set(UNITS).size, 33);
});

test("SHIFTED: 정확히 일곱 쌍", () => {
  assert.deepEqual(SHIFTED, {
    "ㅂ": "ㅃ", "ㅈ": "ㅉ", "ㄷ": "ㄸ", "ㄱ": "ㄲ",
    "ㅅ": "ㅆ", "ㅐ": "ㅒ", "ㅔ": "ㅖ"
  });
  assert.equal(Object.keys(SHIFTED).length, 7);
});

test("KEYMAP: KeyA..KeyZ 26키", () => {
  const keys = Object.keys(KEYMAP);
  assert.equal(keys.length, 26);
  for (const key of keys) {
    assert.match(key, /^Key[A-Z]$/);
    assert.ok(Array.isArray(KEYMAP[key]));
    assert.equal(KEYMAP[key].length, 2);
  }
});

test("KEYMAP: 두 칸 모두 UNITS 안이고 Shift 꼴이 SHIFTED 와 맞음", () => {
  for (const [key, [plain, shift]] of Object.entries(KEYMAP)) {
    assert.ok(UNITS.includes(plain), `${key} 보통 글자`);
    assert.ok(UNITS.includes(shift), `${key} Shift 글자`);
    if (SHIFTED[plain]) assert.equal(shift, SHIFTED[plain], `${key} Shift 꼴`);
    else assert.equal(shift, plain, `${key} Shift 없음`);
  }
});

test("KEY_ROWS: 모든 글자가 UNITS 안이고 KEYMAP 보통 글자 집합과 같음", () => {
  const rowChars = KEY_ROWS.flat();
  for (const ch of rowChars) assert.ok(UNITS.includes(ch), `KEY_ROWS 의 ${ch}`);
  const mapPlain = new Set(Object.values(KEYMAP).map(([plain]) => plain));
  assert.deepEqual(new Set(rowChars), mapPlain);
  assert.equal(rowChars.length, 26);
});

test("toUnits: 쌍자음은 한 칸", () => {
  assert.equal(toUnits("까닭"), "ㄲㅏㄷㅏㄹㄱ");
  assert.equal(toUnits("꼬끼리"), "ㄲㅗㄲㅣㄹㅣ");
  assert.equal(toUnits("아가씨"), "ㅇㅏㄱㅏㅆㅣ");
});

test("toUnits: ㅐㅔㅒㅖ 는 한 칸", () => {
  assert.equal(toUnits("얘기"), "ㅇㅒㄱㅣ");
  assert.equal(toUnits("예"), "ㅇㅖ");
  assert.equal(toUnits("해"), "ㅎㅐ");
  assert.equal(toUnits("세"), "ㅅㅔ");
});

test("toUnits: 겹모음 일곱은 각각 두 칸", () => {
  const cases = [
    ["과", "ㄱㅗㅏ"], ["괘", "ㄱㅗㅐ"], ["괴", "ㄱㅗㅣ"],
    ["궈", "ㄱㅜㅓ"], ["궤", "ㄱㅜㅔ"], ["귀", "ㄱㅜㅣ"], ["의", "ㅇㅡㅣ"]
  ];
  for (const [word, units] of cases) assert.equal(toUnits(word), units, word);
});

test("toUnits: 겹받침 열하나는 각각 두 칸", () => {
  const cases = [
    ["넋", "ㄴㅓㄱㅅ"], ["앉", "ㅇㅏㄴㅈ"], ["않", "ㅇㅏㄴㅎ"],
    ["닭", "ㄷㅏㄹㄱ"], ["삶", "ㅅㅏㄹㅁ"], ["넓", "ㄴㅓㄹㅂ"],
    ["곬", "ㄱㅗㄹㅅ"], ["핥", "ㅎㅏㄹㅌ"], ["읊", "ㅇㅡㄹㅍ"],
    ["앓", "ㅇㅏㄹㅎ"], ["값", "ㄱㅏㅂㅅ"]
  ];
  for (const [word, units] of cases) assert.equal(toUnits(word), units, word);
});

test("toUnits: 계약의 본보기", () => {
  assert.equal(toUnits("한국"), "ㅎㅏㄴㄱㅜㄱ");
  assert.equal(toUnits("과자"), "ㄱㅗㅏㅈㅏ");
  assert.equal(toUnits("의사"), "ㅇㅡㅣㅅㅏ");
  assert.equal(toUnits("값"), "ㄱㅏㅂㅅ");
});

test("toUnits: 음절이 아닌 입력은 null", () => {
  for (const word of ["", "abc", "ㄱ", "한 국", "한a", "ㅘ"]) {
    assert.equal(toUnits(word), null, JSON.stringify(word));
  }
});

test("composeUnits: 모든 본보기 낱말의 되돌림", () => {
  for (const word of ROUNDTRIP_WORDS) {
    assert.equal(composeUnits(toUnits(word)), word, word);
  }
});

test("composeUnits: 입력 중 꼴", () => {
  assert.equal(composeUnits("ㅎㅏㄴㄱ"), "한ㄱ");
  assert.equal(composeUnits("ㅎㅏㄴ"), "한");
  assert.equal(composeUnits("ㄱㅗㅏ"), "과");
});

test("composeUnits: 받침이 다음 음절 첫소리로 넘어감", () => {
  assert.equal(composeUnits("ㄷㅏㄹㄱㅏ"), "달가");
  assert.equal(composeUnits("ㄱㅏㅂㅅㅣ"), "갑시");
  assert.equal(composeUnits("ㅂㅏㄹㅂㅏ"), "발바");
  assert.equal(composeUnits("ㄱㅏㅂㅅㅇㅣ"), "값이");
});

test("composeUnits: 낱자와 빈 문자열", () => {
  assert.equal(composeUnits(""), "");
  assert.equal(composeUnits("ㄱㄱ"), "ㄱㄱ");
  assert.equal(composeUnits("ㅏ"), "ㅏ");
  assert.equal(composeUnits("ㅎ"), "ㅎ");
  assert.equal(composeUnits("ㅎㅏ"), "하");
});

test("composeUnits: 겹모음·겹받침 합치기", () => {
  assert.equal(composeUnits("ㄲㅏㄷㅏㄹㄱ"), "까닭");
  assert.equal(composeUnits("ㄷㅏㄹㄱ"), "닭");
  assert.equal(composeUnits("ㅂㅏㄹㅂ"), "밟");
});

test("words: ALLOWED 모든 낱말이 6칸", () => {
  assert.ok(ALLOWED.length > 0);
  for (const word of ALLOWED) {
    const units = toUnits(word);
    assert.ok(units !== null, `${word} 는 음절 낱말`);
    assert.equal(units.length, 6, `${word} 의 칸 수`);
  }
});

test("words: ALLOWED 모든 낱말의 되돌림이 같음", () => {
  for (const word of ALLOWED) {
    assert.equal(composeUnits(toUnits(word)), word, word);
  }
});

test("words: ANSWERS 도 6칸이고 ALLOWED 에 들어 있음", () => {
  const allowed = new Set(ALLOWED);
  for (const word of ANSWERS) {
    const units = toUnits(word);
    assert.ok(units !== null, `${word} 는 음절 낱말`);
    assert.equal(units.length, 6, `${word} 의 칸 수`);
    assert.equal(composeUnits(units), word, `${word} 의 되돌림`);
    assert.ok(allowed.has(word), `${word} 가 ALLOWED 에 있음`);
  }
});
