# R34 종료 보고 (관리자 M-R34-151152, 2026-11-16 15:11~15:45)

상태: DONE

할 일: 새 요청·넘겨받은 요청 없음 → 대기 큐 1건 `[VoxLog] R33-N13·N14·N15·N16` (하). 관리자가 요청 `Q-261116-r34q` 를 만들어 이었습니다.
운영 방식: 빠른 구현. REV 185 → 186.

## (1) 태스크

| 태스크 | 슬롯 | 그래프 | 내용 | 결과 |
| ------ | ---- | ------ | ---- | ---- |
| T-354 | S3 opencode 무료 | G-074 | `voxlog/stt.py` Transcriber.busy/resubmit (N13) + ffmpeg `-protocol_whitelist file,pipe -f <형식>` (N15) | done · 시도 2(첫 verify 에서 검사 1개 실패) · 약 5분 |
| T-355 | S4 sonnet | G-074 | `voxlog/store.py` incoming_path·add_recording_file·잠금은 메타에만·목록 글 캐시 (N14) | done · 1 · 72s |
| T-356 | S5 sonnet | G-074 | 화면: '서버 주소' 설정 삭제·늘 같은 출처 (N16) + 503/507 은 영구 실패 아님, 검사 20·21번 | done · 1 · 290s |
| T-357 | S5 sonnet | G-074 | `serve.py` retry 409 (N13) + 업로드 흘려 쓰기·동시 2개 503·디스크 여유 507 (N14) | done · 1 · 285s |
| T-358 | S1 opus | G-074 | 적대적 검수 → 조건부(상0 중0 하7), 네 결함 모두 닫힘 | done · 1 · 418s |
| T-359 | S5 sonnet | G-075(후속) | R34-N1(회귀: 전사 예외 뒤 영구 409)·N2(retry 경쟁) | done · 1 · 99s |
| T-360 | S4 sonnet | G-075(후속) | R34-N3(검사 21번 거짓 실패)·N5(Retry-After)·N7(INTERFACE.md) | done · 1 · 359s · 21/21 ×3 |

요청 `Q-261116-r34q` DONE. 쌓인 곳: **`projects/VoxLog/`** - `voxlog/stt.py`, `voxlog/store.py`, `serve.py`, `web/{index.html,app.js,api.js,queue.js,sw.js}`,
`docs/INTERFACE.md`, `tests/{test_stt,test_store,test_serve}.py`, `tests/browser_voxlog.py`, `PROGRESS.md`(목표 '보안' 체크·R34 항목).
기록: `rounds/R34/REVIEW-r34.md`(검수), 이 파일. 함대 코드(`tools/`, `tests/`)는 바꾸지 않았습니다 - 모니터 재시작 불필요.

## (2) 재현한 검증

- `python3 -m unittest discover -s tests` → `Ran 1047 tests ... OK (skipped=1)` (관리자)
- `python3 -m unittest discover -s projects/VoxLog/tests` → `Ran 104 tests ... OK` (관리자)
- `python3 projects/VoxLog/tests/browser_voxlog.py` → `21/21 통과` - T-360 엔진 verify 와 작업자의 세 번 연속 실행. 관리자 셸에서는 이 명령에 승인이 필요해 직접 돌리지 못했습니다(R33 과 같음)
- `python3 tools/aimem_lint.py AIMEM.md` → `OK: 위반 없음`
- 검수(S1)가 `/tmp/s1r34/` 복사본에서 경쟁 실험 6가지(받아쓰는 중 retry, 동시 client_id 5개, 느린 업로드 중 목록 0.002초, 503/507, 메타 쓰기 실패 뒤 고아 없음, 캐시)와
  실제 ffmpeg 로 concat/HLS 위장 10종(예전 명령은 HLS 5종 모두 다른 파일을 읽음 → 새 명령은 10종 모두 SttError)을 재현해 N13~N16 닫힘 확인

## (3) 기다린 시간

그래프 실행 15:15:19 ~ 15:38:31 (약 23분). G-074 만들기 단계 약 10분(15:15~15:25) → 검수 7분 → 후속 G-075 6분.
가장 긴 사슬은 S3(무료) stt → S5 serve → S1 검수. T-354 재시도로 약 2분 늦어졌습니다.

## (4) 큐 진행

- 내림: `[VoxLog] R33-N13·N14·N15·N16` (닫힘)
- 올림: `[VoxLog] R34-N4·N6` (하) - 503/507 을 본문 읽기 전에 보내고 닫아 큰 녹음 쪽엔 연결 오류로 보임(실제 서버로 503 받는 브라우저 검사), 느린 연결이 업로드 자리를 오래 쥠(업로드 전체 마감), 메타 쓰기·os.replace 의 OSError 를 500/507 로 답하기
- 남은 큐 1건

## (5) 다음 라운드 계획

넘기는 PLANNED 요청 없음. 다음 라운드는 큐 `[VoxLog] R34-N4·N6` 한 건(작은 serve.py 일 하나 + 검사)입니다.
VoxLog 목표 중 남은 셋 가운데 'PWA 오프라인 열림 검사' 는 작업자가 할 수 있으나 요청이 없으면 하지 않습니다. 나머지 둘(실물 폰, 실제 STT·claude)은 태석님 몫입니다.

## (6) 운영 지표

- 슬롯 가동(15:15~15:38, 약 23분 중): S5 약 11분(T-356·T-357·T-359), S4 약 8분(T-355·T-360), S1 7분(검수), S3 5분(T-354). S2 는 일시 중지(장애) - 안 씀.
- 관리자만 돈 구간: 시작·그래프 짜기 15:11~15:15(4분), 검수 뒤 후속 짜기 15:31:56~15:32:32(36초), 마감 15:38~15:45.
- 재시도: T-354 1회(첫 시도의 verify 에서 test_stt 1개 실패 → 재시도에서 통과).
- 슬롯 추가: S6(claude sonnet) 을 더하려 했으나 엔진이 거절(anthropic 공급자 동시 3 - S1·S4·S5 로 이미 참). 태석님이 R33 에 opencode·deepseek 유료 슬롯 대신 claude 를 쓰라고 해서 다른 공급자는 더하지 않음.
  그래서 S5 에 화면 → serve 두 노드를 이어 주고, 검수 뒤 후속에서 쓰기 경로를 옮김(stt.py·test_stt.py → S5, web/**·browser_voxlog.py·INTERFACE.md → S4). 노드 move 는 없음.
- 유료 슬롯이 만들기를 맡은 까닭: 운영 방식이 '빠른 구현'(비용보다 속도)이고 무료 슬롯은 S3 하나만 쓸 수 있었음.
- 그래프 2개·태스크 7개(후속 G-075 는 `--followup`). 재검수는 하 결함만 고쳐 하지 않음(운영 방식대로).

## (7) 개선안 하나

관리자 셸에서 `python3 projects/<P>/tests/browser_*.py` 가 두 라운드 연속 승인 요구로 막혔습니다(작업자 verify 로는 돔). 브리프와 `8.0-8` 은 이 명령을 관리자가 마감 때 돌리는
것으로 적고 있으니, 관리자 세션의 허용 목록에 `python3 projects/*/tests/browser_*.py` 꼴을 넣거나, 아니면 `8.0-8` 마감에 "브라우저 검사는 엔진 verify 결과를 인용" 이라고
적어 둘 중 하나로 맞추면 보고 (2)가 매번 단서를 달지 않아도 됩니다.
