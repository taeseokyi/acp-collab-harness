# 주보알림 - 진행

## 목표
- [x] 최신 주보(날짜·제목)를 사이트에서 다시 읽고, 못 읽으면 못 읽었다고 보인다
- [x] 보낸 주보와 새것 여부가 한눈에 보인다(첫 기준선은 오픈클로 기록)
- [x] 주보 그림 미리 보기 - 실제 전송과 같은 쪽·순서(maria 1~7쪽, bstsd 내림차순), 카톡 대화방 모양
- [ ] '카톡 보내기' 가 지금 쓰는 pipeline.py 를 그대로 부르고, 성공하면 보낸 주보가 갱신된다 (부르기·실패 기록까지 확인, 성공은 미확인)
- [x] 보낸 기록(언제·어느 주보·성공/실패와 까닭)
- [ ] app.json 으로 모니터 프로젝트 탭에서 열린다 (모니터의 project_app() 이 runnable 로 읽음까지 확인, 실제로 열어 보지는 않음)
- [ ] 실제로 확인·전송을 한 번 해 봤다 (확인은 됨, 전송은 작업자 울타리에서 /mnt/c 가 읽기 전용이라 Pictures 정리 단계에서 멈춤)
- [x] 폰 폭(360px)에서도 화면이 넘치지 않는다

## R45 (2026-11-24)
새 프로젝트. 관리 방식 **속도 우선**(검수 노드 없음, 새 검사 파일 없음, verify 는 "뜬다").

**한 일**
- 관리자: 원본 스킬 두 개의 스크립트를 `ref/` 로 옮겨 적음(원본과 같음, 고치지 않음 - 앱이 그대로 부름), README·.gitignore(data/)
- T-409 (S2 codex·kistillm) `bulletin.py` - check(bstsd 목록, 날짜+제목, 실패는 ok:false 와 까닭)·preview(ref download.py → pdftoppm 60dpi)·
  send(ref pipeline.py 그대로, 로그에서 보낸 날짜·제목·실패 까닭)·history·state(첫 기준선은 오픈클로 `church-bulletin-last.json` 을 읽기만)·잠금 하나
- T-410 (S3 opencode·kistillm) `serve.py`(`--host --port`, 기본 18831, `/api/state|check|preview|send`, `/api/preview/<jpg>`)·`web/`·`app.json`
- INBOX 지시(20:46): 미리 보기 = 실제 전송 그림 → T-411 preview 를 pipeline 의 쪽 고르기·순서로 맞추고 `seq`, T-412 미리 보기를 카톡 대화방 모양(오른쪽 묶음 말풍선)으로
- T-413 실물 시험: check 성공(최신 2026-11-22 그리스도 왕 대축일, is_new false), preview 9장(maria 11-29 1~7쪽 + bstsd 11-22 2쪽 거꾸로),
  send 한 번 → **실패**: 작업자 울타리에서 `/mnt/c` 가 읽기 전용이라 pipeline 이 Pictures 를 못 비우고 멈춤(AutoHotkey 까지 안 감, 카톡 전송 없음).
  앱은 그 실패를 보낸 기록에 까닭과 함께 남겼고 `sent` 는 갱신하지 않음 - 의도대로

**바뀐 파일** `bulletin.py`, `serve.py`, `web/index.html·app.js·style.css`, `app.json`, `ref/**`, `README.md`, `.gitignore`, `PROGRESS.md`. `data/` 는 실행 산출물(git 제외)

**검증한 방법** 각 노드 verify(모듈이 불리고 state 키·함수가 있음 / 빈 포트에 serve.py 가 떠서 `/`·`api/state` 응답), 작업자 손 확인(실사이트 check·preview,
접근 막기 404, 플레이라이트 360px), T-413 실물 순서. 함대 전체 테스트 1118 OK

**메모 (속도 우선 - 큐 대신 여기에)**
- 실제 카톡 전송은 아직 한 번도 성공 확인 못 함. 태석님이 모니터 '앱 열기'(또는 `python3 projects/주보알림/serve.py`)로 띄워 '카톡 보내기' 를 한 번 눌러 보면 됨.
  모니터가 띄운 앱 서버가 `/mnt/c` 에 쓸 수 있는지가 관건(작업자 울타리는 못 씀)
- `data/history.json` 첫 건은 위 시험의 실패 기록(울타리 탓). 지우지 않았음 - 거슬리면 태석님이 data/ 를 지우면 됨
- '새것' 판정은 bstsd 날짜만 본다(원본 check_bulletin 과 같음). 미리 보기·전송은 maria 도 함께 - maria 가 bstsd 보다 먼저 올라오는 주(이번 11-29)엔 화면이 "새 주보 없음" 이어도 미리 보기엔 새 maria 가 보임
- 보낸 주보 제목: 오픈클로 씨앗은 제목이 비어 있음(원본 상태 파일에 제목이 없음)
- 앱 서버의 '카톡 보내기' 는 최대 10분 붙잡는다(pipeline 의 AHK 180초 + 받기). 화면은 그동안 단추를 막음
- `__pycache__/` 가 생김(.gitignore 에 있음)

**남은 일** 실제 전송 성공 확인 · 모니터 프로젝트 탭에서 실제로 열어 보기
