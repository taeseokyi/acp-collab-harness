DONE

**한 일**
- `projects/자모맞히기/web/index.html`: `<title>`·`<h1>` → `자모맞히기`. `header` 바로 아래 `<nav id="modes">`(`#mode-daily` aria-pressed=true, `#mode-practice` false, `#btn-new` hidden, 모두 type=button) 추가. `#board` 바로 위 `#preview.preview[aria-live="off"]` 추가. 도움말 전면 교체(6칸·한 칸=자판 1회·쌍자음/ㅐㅔㅒㅖ 한 칸, Shift, 겹모음 ㅘ=ㅗㅏ 등 표, 겹받침 ㄺ=ㄹㄱ 등 표, 6칸 예시 3줄 자리맞음/들어있음/없음, 중복 자모 개수 제한, 날마다/연습). 통계·설정 창 구조 유지, 하드 모드 설명 '글자'→'자모'.
- `web/css/style.css`: 보드 `.row` `repeat(6, 1fr)`. `--board-width`/`--board-height`를 6×6 정사각 기준으로 재계산(세로·가로·dvh). `#modes`(한 줄·가운데·작은 알약 단추, aria-pressed=true 채움, 어두운 테마)와 `#preview`(보드 위, 큰 글자, `min-height:2.2rem`으로 빈 줄에도 높이 유지, 테마 색) 추가. `.spacer` 제거, `.key.wide` flex 1.4, `#keyboard[data-shift="on"] .key[data-key="shift"]` 눌린 모양. 예시 타일 6칸 폭.
- `web/js/storage.js`: `const PREFIX = 'jamo.';` 한 줄만 변경.
- `tests/test_storage.mjs`: `webwordle.` 문자열이 원래 없어(테스트는 접두를 직접 참조하지 않음) 수정 불필요. 변경 없음.

**실제로 돌린 검증**
- `python3 .aimem/graph/inputs/r24/v_static.py` → `static: 모두 통과` (rc=0)
- `node --test projects/자모맞히기/tests/test_storage.mjs` → `tests 12 / pass 12 / fail 0`
- (참고) Playwright 배치 확인 320×568·360×740·430×932·1280×800·900×420: `#modes`·`#preview`·`#board`·`#keyboard` 모두 화면 안, 서로 겹침 없음. 보드 228/348/350/350/230px, 320px에서 타일 33.8px.

**다음 담당자에게**
- 지금 `ui.js`는 아직 웹워들 판(영어 키·완성형 낱말 전달)이라 로드 시 `정답은 자모 6글자여야 합니다: "학력"` 오류가 납니다. 내 파일 문제가 아니며 T-279가 ui.js를 고치면 사라집니다. `v_smoke.py`는 그 전까지 실패하는 게 정상입니다.
- 새 HTML은 `#modes`/`#preview`를 제공하지만 모드 전환·Shift·`data-shift`·미리보기 채우기는 ui.js(T-279) 몫입니다. 자판 키 수는 계약대로 1줄 10 / 2줄 Shift+9 / 3줄 입력+7+지우기이며 `.spacer`는 쓰지 않습니다.
- `--board-width`는 세로 `calc(100vh - 340px)`, 가로(높이≤560·폭≥760) `calc(100vh - 190px)`로 잡았습니다. 화면 높이가 극단적으로 낮으면 이 값을 조정하십시오.
- 소유 경로 밖 파일은 건드리지 않았고 commit/push/삭제/설치도 하지 않았습니다.