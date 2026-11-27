DONE

- 새 파일: `projects/자모맞히기/web/js/jamo.js` (185줄)
- 구현: `UNITS`, `SHIFTED`, `KEY_ROWS`, `KEYMAP`, `toUnits`, `composeUnits`
- 검증 1: `node .aimem/graph/inputs/r24/v_jamo.mjs` → 마지막 줄 `jamo: 모두 통과` (exit 0)
- 검증 2: 전체 11172개 완성형 음절 `composeUnits(toUnits(ch)) === ch` 왕복 확인 → `roundtrip all syllables: OK`
- 변경 파일은 위 하나뿐이며 다른 파일·테스트 파일은 건드리지 않았습니다.
- 다음 담당자는 계약서에 적힌 이름 그대로 import하면 됩니다. `toUnits`는 빈 문자열·비음절 입력에서 `null`을 반환합니다.