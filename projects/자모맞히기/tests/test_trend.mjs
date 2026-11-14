import { test } from "node:test";
import assert from "node:assert/strict";
import { sinceText, mergeTrend } from "../web/js/trend.js";

const NOW = new Date("2026-11-15T12:00:00+09:00");
const SEC = 1000;
const MIN = 60 * SEC;
const HOUR = 60 * MIN;
const DAY = 24 * HOUR;
const ago = (ms) => new Date(NOW.getTime() - ms).toISOString();

test("sinceText: 없음·빈 값은 아직 정한 적 없음", () => {
  assert.equal(sinceText(null, NOW), "아직 정한 적 없음");
  assert.equal(sinceText(undefined, NOW), "아직 정한 적 없음");
  assert.equal(sinceText("", NOW), "아직 정한 적 없음");
});

test("sinceText: 1분 안은 방금 정함 (30초)", () => {
  assert.equal(sinceText(ago(30 * SEC), NOW), "방금 정함");
  assert.equal(sinceText(ago(0), NOW), "방금 정함");
});

test("sinceText: 분 단위 경계 (1분·59분)", () => {
  assert.equal(sinceText(ago(MIN), NOW), "1분 전에 정함");
  assert.equal(sinceText(ago(59 * MIN + 59 * SEC), NOW), "59분 전에 정함");
});

test("sinceText: 시간 단위 경계 (1시간·23시간)", () => {
  assert.equal(sinceText(ago(HOUR), NOW), "1시간 전에 정함");
  assert.equal(sinceText(ago(23 * HOUR + 59 * MIN), NOW), "23시간 전에 정함");
});

test("sinceText: 일 단위는 내림 (1일·3일)", () => {
  assert.equal(sinceText(ago(DAY), NOW), "1일 전에 정함");
  assert.equal(sinceText(ago(3 * DAY + 20 * HOUR), NOW), "3일 전에 정함");
});

test("sinceText: 앞날짜·못 읽음은 방금 정함", () => {
  assert.equal(sinceText(ago(-5 * MIN), NOW), "방금 정함");
  assert.equal(sinceText("어제쯤", NOW), "방금 정함");
});

test("sinceText: 시간대가 붙은 ISO 도 읽음", () => {
  assert.equal(sinceText("2026-11-15T10:00:00+09:00", NOW), "2시간 전에 정함");
});

test("mergeTrend: 서버 것이 정적 것을 덮음", () => {
  const out = mergeTrend(
    { "2026-11-15": "지원", "2026-11-16": "혐의" },
    { "2026-11-16": "진출", "2026-11-17": "중단" },
  );
  assert.deepEqual(out, { "2026-11-15": "지원", "2026-11-16": "진출", "2026-11-17": "중단" });
});

test("mergeTrend: 꼴이 틀린 날짜·낱말은 거름", () => {
  const out = mergeTrend({}, {
    "2026-11-15": "지원",
    "2026/11/16": "혐의",
    "11-17": "진출",
    "2026-11-18": 7,
    "2026-11-19": "abc",
    "2026-11-20": "",
    "2026-11-21": null,
    "2026-11-22": "가나다라마바사아자차카",
  });
  assert.deepEqual(out, { "2026-11-15": "지원" });
});

test("mergeTrend: 객체가 아니면 빈 결과", () => {
  assert.deepEqual(mergeTrend(null, undefined), {});
  assert.deepEqual(mergeTrend(["지원"], "문자열"), {});
  assert.deepEqual(mergeTrend({ "2026-11-15": "지원" }, null), { "2026-11-15": "지원" });
});
