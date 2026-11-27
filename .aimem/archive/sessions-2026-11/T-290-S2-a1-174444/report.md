DONE

**결과**
- `ANSWERS` 380개, `ALLOWED` 1033개.
- `allowed.txt` 원본 1033개(1000개 이상), 빌드 뒤 합친 ALLOWED도 1033개.
- `v_words3` 마지막 줄: `words3: 모두 통과`.

**고친 파일**
- `projects/자모맞히기/data/allowed.txt` — 흔한 6칸 낱말 139개 추가, `쇄약·갑작·학종·국공·과감·과중` 삭제.
- `projects/자모맞히기/data/answers.txt` — `과감·과중·냉장` 삭제.
- `projects/자모맞히기/data/README.md` — 900 → 1000개 이상, `한국` 예시 제거, 정답 후보 383 → 380.
- `projects/자모맞히기/tests/test_words.py` — ALLOWED 하한 1000, `BANNED`에 여섯 낱말 추가, `MUST`에 29개 추가.
- `projects/자모맞히기/web/js/words.js` — `build_words.py`로 재생성.

**검증**
- `python3 .aimem/graph/inputs/r24/v_words3.py` → `ANSWERS 380 ALLOWED 1033`, 첫 음절 상위 `[('정', 40), ('전', 39), ('공', 28)]`, `words3: 모두 통과`.
- `node --test projects/자모맞히기/tests/test_jamo.mjs` → `pass 19`, `fail 0`.
- `python3 -m unittest discover -s projects/자모맞히기/tests -p 'test_words.py'` → `Ran 11 tests`, `OK`.
- 빌드 출력: `answers: 380개`, `allowed: 1033개`, `wrote .../web/js/words.js`.

**다음 담당자에게**
- `냉장`은 ANSWERS에서만 빠졌고 ALLOWED에는 남아 있습니다.
- 첫 음절 최대값은 `정` 40으로 제한을 넘지 않습니다.
- `words.js`는 생성물이므로 직접 수정하지 말고 `build_words.py`로 다시 만드십시오.
- 금지 행위(commit/push/삭제/의존성 설치)는 하지 않았습니다.