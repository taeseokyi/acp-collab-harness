// 뉴스로 고른 정답 보조 - 순수 함수(DOM 없음). 정본은 서버의 data/trend.txt, 화면은 받아 쓰기만 한다.
import { toUnits } from './jamo.js';

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
const WORD_UNITS = 6;
const MIN = 60 * 1000;
const HOUR = 60 * MIN;
const DAY = 24 * HOUR;

// 정답으로 쓸 낱말인가: 자모로 풀었을 때 꼭 6칸이어야 한다(R37-N2). 아니면 그 날짜는 목록 정답으로 돌아간다.
function isAnswer(word) {
  if (typeof word !== 'string' || word === '') return false;
  const units = toUnits(word);
  return units !== null && units.length === WORD_UNITS;
}

// 마지막으로 정한 시각(ISO)이 지금으로부터 얼마나 지났는지 한 줄로
export function sinceText(lastRunIso, now = new Date()) {
  if (lastRunIso === null || lastRunIso === undefined || lastRunIso === '') return '아직 정한 적 없음';
  const t = Date.parse(lastRunIso);
  const n = now instanceof Date ? now.getTime() : Number(now);
  if (!Number.isFinite(t) || !Number.isFinite(n)) return '방금 정함';
  const diff = n - t;
  if (diff < MIN) return '방금 정함'; // 앞날짜(시계 어긋남) 포함
  if (diff < HOUR) return `${Math.floor(diff / MIN)}분 전에 정함`;
  if (diff < DAY) return `${Math.floor(diff / HOUR)}시간 전에 정함`;
  return `${Math.floor(diff / DAY)}일 전에 정함`;
}

// {...정적, ...서버} 중 날짜(YYYY-MM-DD)와 6칸 낱말 꼴이 맞는 것만. 서버 것이 정적 것을 덮는다.
export function mergeTrend(staticTrend, serverTrend) {
  const out = {};
  for (const src of [staticTrend, serverTrend]) {
    if (!src || typeof src !== 'object' || Array.isArray(src)) continue;
    for (const [date, word] of Object.entries(src)) {
      if (DATE_RE.test(date) && isAnswer(word)) out[date] = word;
    }
  }
  return out;
}
