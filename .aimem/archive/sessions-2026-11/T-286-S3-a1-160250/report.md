DONE — tests 17, pass 17

한 일
- `loadSettings()`: 저장된 `dark`가 불리언이 아닐 때만 시스템 설정(`matchMedia('(prefers-color-scheme: dark)')`)을 따르게 하고, `matchMedia` 부재·예외는 `false`로 처리. 저장된 불리언 `dark`는 종전대로 우선. `PREFIX = 'jamo.'` 등 다른 동작 불변.
- `test_storage.mjs`에 시험 5개 추가(총 12→17): `jamo.` 접두 검사(N12), 저장값 없음+시스템 dark→`true`, 저장값 없음+`matchMedia` 없음→`false`, 저장된 `dark:false`+시스템 dark→`false`, `matchMedia` 예외→`false`. 기존 가짜 `localStorage`/전역 교체 방식을 따름.

고친 파일
- `projects/자모맞히기/web/js/storage.js`
- `projects/자모맞히기/tests/test_storage.mjs`

검증 명령·출력
- `node --test projects/자모맞히기/tests/test_storage.mjs` → `tests 17 / pass 17 / fail 0` (기준: 16개 이상 전부 통과 충족)

다음 담당자 참고
- `matchMedia` 조회는 `loadSettings()` 호출 시점마다 수행(모듈 로드 시 캐시 아님). 저장된 `dark`가 불리언이면 시스템 조회를 하지 않음.
- `store()`가 `jamo.probe`를 set/remove하므로 접두 시험은 쓰기·삭제 키를 모두 검사함.