SLOT=S3 T-286 storage.js: 저장값 없으면 시스템 어두운 모드 따름 + test_storage 접두어·기본값 시험 (R24-N9·N12 일부) (G-057)
확인토큰: 5b8c1e
AIMEM REV: 170
너는 S3 슬롯이다. 작업 폴더는 /home/tsyi/work/ai-fleet 다.
쓰기는 다음 경로에만 한다: projects/자모맞히기/web/js/storage.js, projects/자모맞히기/tests/test_storage.mjs
금지: git commit / push / 삭제 / 의존성 설치. 보고는 응답 본문에 직접 쓴다.
보고 첫 줄은 상태(DONE / PARTIAL / BLOCKED / NEEDS-LOCK / NEEDS-APPROVAL), 이어서 한 일·고친 파일·실제로 돌린 검증 명령과 출력·다음 담당자가 알아야 할 것.

# T-286 시스템 어두운 모드 (R24-N9) + 저장 접두어 시험 (R24-N12 일부)

쓸 파일: `projects/자모맞히기/web/js/storage.js`, `tests/test_storage.mjs`. 다른 파일은 읽기만. **바로 파일을 고치십시오.**

근거: `rounds/R24/REVIEW-r24.md` 2절 N9·N12 행.

## 할 일

1. `storage.js` `loadSettings()`: 저장된 설정에 `dark` 가 **불리언으로 없을 때만** 기본값을 `globalThis.matchMedia?.('(prefers-color-scheme: dark)')?.matches === true` 로(예외는 잡아 `false`). 저장된 `dark` 가 있으면 지금처럼 그것을 씀. 다른 동작·`PREFIX = 'jamo.'` 는 그대로.
2. `tests/test_storage.mjs` 에 시험 더하기(4개 이상): `localStorage` 에 쓰는 키가 모두 `jamo.` 로 시작(웹워들과 같은 출처에서 통계가 섞이지 않게 - N12), 저장값 없음 + `matchMedia` 가 dark → `dark:true`, 저장값 없음 + `matchMedia` 없음 → `false`, 저장값 `dark:false` + 시스템 dark → `false`. 이 파일이 이미 쓰는 가짜 `localStorage`·전역 갈아끼우기 방식을 따르십시오.

## 스스로 확인

`node --test projects/자모맞히기/tests/test_storage.mjs` 전부 통과, 시험 수가 지금보다 4개 이상 늘어야 합니다(지금 12개 - 엔진은 16개 이상·전부 통과를 봅니다).

## 하지 말 것

다른 파일 쓰기, `git commit`/`push`, 파일 삭제, 의존성 설치, 운영 모니터 부르기.

보고 첫 줄은 `DONE` / `PARTIAL` / `BLOCKED`, 그다음 tests·pass 수.
