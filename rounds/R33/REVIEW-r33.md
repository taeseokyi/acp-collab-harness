# R33 적대적 검수 - VoxLog 전체 + 앱 서버 정리(R32-N3·N5)

검수: S1 (T-345, G-071), REV 184. 고치지 않고 찾기만 했습니다. 실험은 모두 `/tmp/r33x/` 의 임시 폴더·임시 포트에서 했고,
띄운 프로세스는 거두었습니다(앞뒤로 `/proc` 확인 - 남은 것은 운영 모니터 pid 203976 하나, 건드리지 않음). 운영 모니터에는 curl 하지 않았습니다.

## 1. 판정

**조건부** - 핵심 흐름(녹음→대기열→업로드→받아쓰기→목록→묻기)과 모니터 '앱 열기'(목록·묻기)는 실제로 돌지만,
50MB 를 넘는 녹음(크롬 기본 비트레이트로 약 1시간)이 대기열에 영원히 남고 지울 수도 없으며(N1), 날짜가 UTC 로 매겨져 KST 00~09시 녹음이 전날로 쌓입니다(N2).
앱 서버는 owner pid 를 살아 있는지로만 봐서, pid 가 재사용되면 앱이 영구히 503 이 됩니다(N7). 이 셋은 고친 뒤 닫을 것.

상 1 · 중 7 · 하 9

## 2. 돌린 검사와 결과

| 명령 | 결과 |
| ---- | ---- |
| `python3 -m unittest discover -s projects/VoxLog/tests` | `Ran 62 tests ... OK` |
| `python3 projects/VoxLog/tests/browser_voxlog.py` | `11/11 통과` |
| `python3 -m unittest tests.test_aimem_monitor_app_server` | `Ran 27 tests ... OK`, 돌리기 앞뒤로 `/proc` 를 보니 고아 없음 |
| `claude --help` | `--tools <tools...> ... Use "" to disable all tools` - **내장 도구는** 꺼짐 확인. 단 "from the built-in set" 이라 MCP 서버는 다른 장치(`--strict-mcp-config`)로 끄며, `--bare`/`--safe-mode` 가 없으면 CLAUDE.md·hooks 도 읽음 → N6 |
| `/tmp/r33x/exp.py` (make_server 임시 포트·가짜 STT/LLM) | `Origin: null` + text/plain 의 묻기 → **202**; `Origin: http://evil.example` → 403; `Host: evil.example:<port>` 의 GET 목록 → **200**, 같은 Host·Origin 의 POST 묻기 → **202** (리바인딩); 정적 `/../serve.py`·`/..%2fserve.py`·`/%2e%2e/serve.py`·`/icons/..%2f..%2fserve.py` → 모두 404; id `..%2f..%2fx` → 404; 60MB 본문 → 413 응답 뒤 연결 끊김; 받아쓰는 중 지우기 → 200, 남은 파일 `[]`; 받아쓰는 중 retry → 받아쓰기가 한 번 더 돎; ids 201개 → 400; 재시작 뒤 `running` 답 → **계속 `running`** |
| `/tmp/r33x/big.py` (크롬에서 51MB fetch) | `status 413` (로컬에서는 413 을 받음 → 대기열은 4xx 경로로 감, N1) |
| `/tmp/r33x/tz.py Pacific/Honolulu` (기기 시간대 ≠ UTC 날짜) | `recorded_at 2026-11-16T05:26:16Z`, 파일 `transcripts/2026-11-16/...` (기기는 11-15), `stat-today 0`, '오늘' 묻기 → "그 범위에 녹취가 없습니다" (N2) |
| `/tmp/r33x/mon.py` (임시 루트에 진짜 모니터 `--auth` + VoxLog 복사본, 가짜 STT/LLM) | 로그인 200; `#rec` 꺼짐 + 안내 "녹음은 VoxLog 자체 주소에서 - 여기서는 기록·묻기만" 보임; 목록 2건·"연결됨"; 녹취 글 `<img onerror>` 는 그려지지 않음(img 0개); 3MB 음성 → 토스트 "음성을 불러오지 못했습니다 (502)"; 지우기 → "서버에 연결할 수 없습니다" 이고 디스크에 그대로; 묻기(오늘·요약) → 답 보임; 모니터 내린 뒤 앱 서버 자식 살아 있는 것 `[]` |
| `/tmp/r33x/owner.py` (app_server, 죽은 모니터 기록의 owner 를 살아 있는 무관한 pid 로) | `cleanup_stale killed: [] record still there: True`, `ensure -> 503 다른 모니터가 쓰고 있는 앱입니다` (N7) |
| `/tmp/r33x/mutate.py` (복사본에 결함을 넣고 검사 실행, 원본은 안 건드림·복사본 지움) | 서버 중복 막기 끔 → 단위 검사 2건 실패 ✔; 프롬프트 감쌈 줄 지움 → 1건 실패 ✔; `?action=toggle` 무시 → 브라우저 8번 실패 ✔; **`source=launch`+자동 녹음 경로 지움 → 11/11 통과 ✘**; **상세 글을 `innerHTML` 로 → 11/11 통과 ✘** (N8) |

## 3. 결함

| 번호 | 심각도 | 무엇 | 어디(파일:줄) | 재현 | 고칠 안 |
| ---- | ------ | ---- | ------------- | ---- | ------- |
| R33-N1 | 상 | 50MB 를 넘는 녹음은 서버가 영원히 413 인데, 대기열은 4xx 에서 `tries+1` 만 하고 줄을 남겨, 앱이 보일 때마다(visibilitychange) 50MB 를 통째로 다시 올림. 화면엔 개수만 있고 까닭(`lastError`)도, 꺼내거나 지울 길도 없어 녹음은 서버에도 못 가고 기기에서 꺼낼 수도 없음. 녹음기는 `audioBitsPerSecond` 를 정하지 않아 크롬 기본값(약 128kbps 로 알려짐)이면 약 55분에서 넘음 - 회의 녹음이 흔한 쓰임 | `web/queue.js:207-215`, `web/sw.js:153-160`, `voxlog/store.py:17`, `web/app.js:197` | `big.py`: 크롬 51MB POST → 413. 그 줄은 지워지지 않음(코드 경로) | 녹음기에 `audioBitsPerSecond: 32000` 정도(음성엔 충분) + 서버 상한 상향 또는 나눠 올리기; 413·400 같은 영구 4xx 는 '실패' 칸으로 옮겨 다시 올리지 않고, 화면에 까닭·내려받기·지우기를 둠 |
| R33-N2 | 중 | `recordedAt` 이 `toISOString()`(UTC) 인데 서버는 그 앞 10자를 날짜로 씀 → KST 00:00~08:59 녹음이 전날 폴더(`transcripts/<전날>/`)에 쌓이고, 화면의 '오늘'(지역 날짜)·`stat-today`·날짜 거르기가 못 찾음. 요청의 핵심인 "날짜별 텍스트 축적" 이 하루 9시간 어긋남. 브라우저 검사 7번도 KST 00~09시에 돌리면 실패할 것 | `web/app.js:208`, `voxlog/store.py:96-104` | `tz.py Pacific/Honolulu` 위 결과 | 기기에서 지역 시각과 오프셋을 담은 ISO(`2026-11-16T08:00:00+09:00`)를 보내거나, 서버가 오프셋을 읽어 지역 날짜를 쓰기. 검사에 `timezone_id` 를 바꾼 경우 하나 |
| R33-N3 | 중 | 묻기 큐는 메모리에만 있어, 서버 재시작(모니터의 15분 유휴 내림 포함) 때 `running` 답이 영원히 `running`. 화면은 2초마다 끝없이 폴링하고 '묻기' 단추가 꺼진 채로 남음 | `voxlog/ask.py:155-156`, `voxlog/store.py:354-368`, `web/app.js:545-563` | `exp.py` 10번: `answer after restart -> running` | 시작 때 `running` 을 `failed`("서버가 다시 시작되어 끊김")로 바꾸거나 다시 큐에 넣기 + 폴링 상한 |
| R33-N4 | 중 | 녹음 조각(`state.chunks`)을 멈출 때까지 메모리에만 둠 → 녹음 중 페이지가 내려가면(안드로이드가 백그라운드 렌더러를 죽임, 크래시, 바로가기가 기존 창을 새로 불러옴) 그 녹음을 통째로 잃음. "녹음을 쉽게 저장·축적" 과 어긋남 | `web/app.js:209`, `web/app.js:231-249` | 코드 경로 | `ondataavailable` 조각을 IndexedDB 에 이어 붙이고, 다음 열 때 끝나지 않은 녹음을 살려 대기열로 |
| R33-N5 | 중 | Host 머리를 검사하지 않아 기본 실행(루프백·토큰 없음)이 DNS 리바인딩에 열림: Origin 검사는 Origin 과 Host 가 같기만 보면 되므로 공격자 이름으로 둘 다 맞추면 통과 → 녹취 전부 읽기·지우기·묻기 | `serve.py:174-189` | `exp.py` 3번: `Host: evil.example` 의 GET 200, POST 202 | 토큰이 없으면 Host 가 `127.0.0.1`/`localhost`/`[::1]`(:포트)일 때만 받기 |
| R33-N6 | 중 | 묻기의 `claude -p --tools ""` 는 **내장** 도구만 끔. MCP 서버(`~/.claude.json` 에 `mcpServers` 있음)·hooks·CLAUDE.md 는 그대로 읽히고, 작업 폴더가 저장소 안(`projects/VoxLog`)이라 `~/work/ai-fleet/CLAUDE.md` 와 전역 위임문까지 요약기의 맥락에 들어감. 녹취 글(남이 한 말 포함)로 프롬프트 주입 시 허용 목록에 있는 MCP 도구는 쓰일 수 있음 | `voxlog/ask.py:78`, `voxlog/ask.py:87-94` | `claude --help` 의 `--tools`: "from the built-in set" | 기본 명령에 `--strict-mcp-config`(그리고 `--mcp-config` 없이) + `--setting-sources ""` 또는 `--safe-mode`, `cwd` 를 빈 임시 폴더로 |
| R33-N7 | 중 | (앱 서버) 남의 모니터인지를 owner pid 가 살아 있는지로만 봄. 모니터가 죽은 뒤 그 pid 가 무관한 프로세스로 재사용되면(WSL 재시작 뒤엔 pid 가 작게 다시 시작해 흔함) `cleanup_stale` 이 고아 자식을 영영 안 거두고, `ensure` 는 그 앱을 영구히 503 "다른 모니터가 쓰고 있는 앱입니다" 로 거절 | `tools/aimem_monitor/app_server.py:240-249`, `:431-438` | `owner.py` 위 결과 | 기록에 owner 의 시작 시각(`/proc/<pid>/stat` 22번째 칸)을 함께 적고 둘 다 맞을 때만 남의 것, 또는 `/proc/<owner>/cmdline` 에 `aimem_monitor` 가 있는지 확인 |
| R33-N8 | 중 | 브라우저 검사가 요청의 핵심인 측면 버튼 경로(`launchQueue` 소비자·`source=launch`+자동 녹음·첫 신호 중복 거르기)를 전혀 돌지 않음(8번은 새 페이지의 `?action=toggle` 뿐, 끄기는 클릭). 서버 글이 `textContent` 로만 들어가는지도 보지 않음 | `projects/VoxLog/tests/browser_voxlog.py:224-233` | `mutate.py launch`, `mutate.py xss` → 둘 다 11/11 통과 | `window.launchQueue` 를 `add_init_script` 로 흉내 내 소비자에 targetURL 을 넣어 켜고 끄기·처음 3초 중복 무시 확인; 녹취 글에 `<img onerror>` 를 넣은 표본으로 img 0개 확인 |
| R33-N9 | 하 | `Origin: null` 을 남의 출처가 아닌 것으로 침 → 아무 사이트의 sandbox iframe 이 text/plain POST 로 묻기·retry 를 부를 수 있음(id 가 추측 불가라 영향은 작음). 모니터 앱 프록시는 Origin 을 넘기지 않으므로(`app_server.py:320-325`) 이 예외가 필요 없음 | `serve.py:176-177` | `exp.py` 1번: 202 | 토큰이 없을 때 `null` 도 거절 |
| R33-N10 | 하 | '이번 주'·'검색 결과' 범위는 `limit=500` 으로 id 를 모으는데 서버는 1~200개만 받음 → 그 범위에 200건이 넘으면 400 "ids 는 1~200개" | `web/app.js:524`, `voxlog/ask.py:135` | `exp.py` 9번: 201개 → 400 | 화면이 200 으로 자르고 "최근 200건만" 이라 알리기(또는 서버가 앞 200 을 쓰고 알리기) |
| R33-N11 | 하 | 401 뒤 설정에서 토큰을 고쳐도 대기열을 다시 올리지 않음(다음 visibilitychange·online·녹음까지 기다림). 대기열 줄의 `lastError`("인증 실패" 등)는 화면 어디에도 안 보임 | `web/app.js:643`, `web/app.js:119-133` | 코드 경로 | 토큰·주소 저장 뒤 `VoxQueue.flush()`; 대기 수 옆에 마지막 까닭 |
| R33-N12 | 하 | 모니터 '앱 열기' 에서 지우기가 안 됨(모니터에 DELETE 이어 주기가 없음)인데 안내는 "서버에 연결할 수 없습니다" 로 잘못 나감. 2MB 가 넘는 음성(약 2분)은 응답 상한으로 502 | `tools/aimem_monitor/server.py`(do_DELETE 없음), `app_server.py:199`(`max_resp_body`), `README.md:50` | `mon.py`: 지우기 토스트·파일 그대로, 3MB 음성 502 | 모니터 쪽에서는 지우기 단추를 숨기고 음성은 "자체 주소에서" 안내(README 에도 한 줄) |
| R33-N13 | 하 | 받아쓰는 중 '다시 받아쓰기' → 끝난 뒤 같은 녹음을 한 번 더 받아씀(비용·시간). retry 가 `Transcriber` 의 비공개 `_seen`·`_lock` 을 직접 만짐 | `serve.py:317-329` | `exp.py` 8번: 받아쓰기가 한 번 더 돎 | `transcribing` 이면 409, `Transcriber.resubmit()` 공개 메서드 |
| R33-N14 | 하 | (인증 뒤) 업로드는 50MB 를 메모리에 다 읽고 스레드 수 제한이 없으며 저장 총량 상한도 없음. `add_recording` 이 전역 잠금 안에서 50MB 를 쓰고 fsync → 그동안 목록·상세가 멈춤. 목록은 요청마다 모든 글 파일을 읽음(받아쓰는 중엔 5초마다) | `serve.py:239`, `voxlog/store.py:165-198`, `voxlog/store.py:212-246` | 코드 경로 | 본문을 임시 파일로 흘려 쓰고 잠금은 메타 쓰기에만; 동시 업로드 수·디스크 여유 검사 |
| R33-N15 | 하 | ffmpeg 를 `-i` 로만 불러 내용으로 형식을 판별 → 녹음으로 위장한 HLS/concat 재생목록이면 서버의 ffmpeg 가 다른 주소·파일을 읽으러 감(인증 필요) | `voxlog/stt.py:68-71` | 코드 경로 | mime 에 맞춰 입력 형식을 강제(`-f matroska` 등) + `-protocol_whitelist file,pipe` |
| R33-N16 | 하 | 설정의 '서버 주소'(apiBase)를 다른 출처로 두면 서버가 CORS 를 주지 않아(OPTIONS 204 에 ACAO 없음) 어떤 요청도 안 됨 - 쓸 수 없는 설정이 화면에 있음 | `web/api.js:39-44`, `serve.py:135-139` | 코드 경로 | 설정을 빼거나, 토큰이 있을 때 정해진 출처에만 CORS |
| R33-N17 | 하 | (앱 서버) `_kill_heirs` 는 그룹 내리기 **전에** 모은 자손 pid 전부(그룹 안에 있어 이미 죽은 것 포함)에 최대 약 4초 뒤 신호를 보냄. 그사이 pid 가 재사용되면 같은 사용자의 무관한 프로세스가 SIGTERM/SIGKILL 을 받을 수 있음(가능성은 낮음). 자기·조상은 `_self_and_ancestors` 로 잘 빠짐. 내리는 동안 새로 생긴 손자·이중 fork 로 init 에 붙은 것은 못 거둠 | `tools/aimem_monitor/app_server.py:162-183` | 코드 경로 | 모을 때 sid≠앱 pid 인 것만 남기고, 보내기 직전 `/proc/<p>/stat` 시작 시각이 모을 때와 같은지 확인 |

앱 서버(대상 2) 정리: 남의 모니터 자식 건너뛰기는 평소엔 맞게 동작하고 검사(`test_cleanup_stale_spares_record_of_live_other_owner` 등 4건)도 있음. 다만 owner 확인이 pid 만이라 N7. 자손 거두기는 자기·조상을 빼고, 무관한 프로세스에는 pid 재사용 때만 닿음(N17). 검사(27건)와 위 모니터 e2e 는 고아를 남기지 않음.

## 4. 요청 대비 빠진 것

- **측면(전원) 버튼:** README 의 "웹은 전원 버튼을 직접 못 받는다" 는 정직함. 코드를 따라가 보면 대안은 이렇게 동작함 - 처음 열기는 `start_url ./?source=launch` 를 `initOpen` 이 처리하고(자동 녹음이 켜져 있을 때만), 바로 뒤 같은 `launchQueue` 신호는 3초 안 첫 호출이면 버림; 이미 떠 있으면 `focus-existing` 으로 소비자가 `targetURL` 을 받아 켜고 끔; 바로가기 `?action=toggle` 은 설정과 무관하게 켜고 끔. 단 (1) 자동 녹음은 기본이 꺼짐이라 설정을 켜야 측면 버튼이 동작함(README 의 삼성 줄에는 이 조건이 다시 적혀 있지 않음), (2) 안드로이드 크롬이 `launch_handler` 를 지원하지 않으면 다시 열어도 신호가 없거나 기존 창을 새로 불러와 녹음을 잃음(N4), (3) 이 경로는 검사가 전혀 안 돎(N8).
- **긴 녹음:** 약 1시간 넘는 녹음은 올라가지 않음(N1).
- **날짜별 축적:** 하루 9시간이 전날로 쌓임(N2).
- **실제 받아쓰기:** 가짜 명령으로만 검사됨. `whisper-cli` 명령·OpenRouter 오디오 모델은 실제로 돌려 보지 않음(키·모델 필요).
- **iOS:** Background Sync 가 없어 앱을 열 때만 올라감(README 에 적혀 있음). 측면 버튼 대안은 안드로이드 전용.

## 5. 사람이 실물로 확인해야 할 것

1. 폰(안드로이드 크롬)에 HTTPS 주소로 설치 - 설치 안내가 뜨는지, 홈 아이콘·길게 눌러 '녹음' 바로가기가 보이는지.
2. 설정에서 '앱을 열면 바로 녹음' 켜고: 삼성 측면 버튼 두 번 누르기 → 앱 열기 목록에 VoxLog(WebAPK)가 있는지, 두 번 = 시작·다시 두 번 = 멈춤이 되는지. **앱이 이미 앞에 있을 때와 뒤에 있을 때, 화면이 잠겨 있을 때** 각각.
3. 이미 떠 있을 때 바로가기 '녹음' 을 누르면 창이 새로 불러와지지 않고(녹음이 끊기지 않고) 멈추는지 - `focus-existing` 실제 지원 여부.
4. 녹음 중 전원 버튼 한 번(화면 끔) - 녹음이 계속되는지(Wake Lock 은 자동 꺼짐만 막음), 다시 켰을 때 시간 표시·멈춤이 맞는지.
5. 비행기 모드로 녹음 → 앱을 닫고 → 온라인으로: 앱을 열지 않아도 올라가는지(Background Sync).
6. 30분·70분 녹음 크기 - 50MB 상한과 비교(N1).
7. 오전 9시 전에 녹음해 '오늘' 에 보이는지(N2 고친 뒤).
8. 실제 STT 백엔드(whisper 명령 또는 OpenRouter)로 한국어 받아쓰기 품질·시간, ffmpeg 설치 여부.
9. 실제 `claude` 로 요약·할 일 답이 나오는지, 녹취에 "도구를 써서 ~ 하라" 를 넣어도 도구를 쓰지 않는지(N6 고친 뒤).

## 6. 재검수 (T-351)

검수: S1 (T-351, G-072), REV 184. 고치지 않고 확인만 했습니다. 실험은 모두 `/tmp/r33y/` 의 임시 폴더·임시 포트에서 했고
띄운 프로세스는 거두었습니다(끝난 뒤 `/proc` 확인 - 남은 것은 운영 모니터 pid 205794 와 그 자식 자모맞히기 225784 뿐, 둘 다 건드리지 않음).
운영 모니터에는 curl 하지 않았고 실제 `claude` 는 부르지 않았습니다(`claude --help` 만 읽음).

### 6.1 돌린 검사와 결과

| 명령 | 결과 |
| ---- | ---- |
| `python3 -m unittest discover -s projects/VoxLog/tests` | `Ran 77 tests ... OK` |
| `python3 projects/VoxLog/tests/browser_voxlog.py` | `17/17 통과` (12 launchQueue·13 XSS·14 Honolulu·15 413·16 새로고침·17 위치 새로 생김) |
| `python3 -m unittest tests.test_aimem_monitor_app_server` | `Ran 29 tests ... OK` |
| `claude --help` | `--tools`·`--strict-mcp-config`·`--setting-sources`·`--no-session-persistence`·`--output-format` 모두 있음. `--tools <tools...>` 는 가변 인자지만 다음 칸이 `--` 로 시작해 거기서 끊김 |
| `/tmp/r33y/exp.py` (make_server 임시 포트·가짜 STT/LLM) | Host `127.0.0.1:p`·`localhost:p`·`[::1]:p`·`127.0.0.1`·`LOCALHOST:p` → 200; `evil.example(:p)`·`127.0.0.1.evil.example:p`·`localhost.evil.example`·`127.0.0.2:p`·빈 Host·`localhost:p:1` → **403**; 리바인딩 POST 묻기·DELETE → 403; `Origin: null`/`NULL` POST → **403**; 같은 출처·Origin 없음(모니터 경유) 묻기 → 202. X-Location 21가지(범위 밖·nan·inf·1e309·칸 수 틀림·`abc`·`;javascript:`·`<img>`·5000자·라틴1 밖 원 바이트) → **모두 201 + 녹음 저장**, 틀린 것은 `location None`, 옳은 것은 float. 옛 메타(location 없음) get/list → `None` 채움. store 에 문자열 lat `javascript:1` → None. `recorded_at 2026-11-16T07:30+09:00` → 날짜 `2026-11-16`, from=to=11-15 에는 없음. `running` 답 뒤 재시작 → `failed` "서버가 다시 시작되어 끊겼습니다". 프롬프트 머리 `<녹취 id=x 시각=t 위치=37.5,127.0>` |
| `/tmp/r33y/br.py` (실제 크롬·가짜 마이크·가짜 위치) | **N1:** 진짜 서버에 51MB 줄(서비스 워커 켬) → 실패 칸 1줄 "서버가 받지 않았습니다: 본문이 너무 큽니다 (최대 52428800 바이트)"·내려받기·다시 올리기·지우기, 대기 수 숨김; 그 뒤 `flush()`·visibilitychange·online·SW `flush` 메시지·오프라인→온라인·새로고침을 다 불러도 **서버 POST 1 → 1** (다시 안 올라감), 줄은 `failed tries 1`, blob 53477376 바이트 꺼내짐. **N4:** 녹음 7초 중 새로고침 → 토스트 "끝나지 않은 녹음 1건을 살렸습니다", 서버에 올라옴(`duration_ms None`). **단 위치 `None`** - 같은 맥락의 보통 녹음은 `{37.5665,126.978,20}` (→ N18). **오프라인:** 대기열 줄에 위치 저장 → 온라인 뒤 서버 메타에 위치. 서비스 워커 경로(`postMessage flush`)로 올린 줄도 서버 메타에 위치 |
| `/tmp/r33y/map.py` (상세 응답의 location 을 바꿔 침) | `javascript:alert(1)//`·`1" onclick=x`·`127#x` → 위치 칸 숨김; `[37]`·`"1e2"`·`"0x10"`·`1e-7` → `Number()` 를 거친 숫자만 href 에(`mlat=37`, `mlat=100&mlon=16`, `mlat=1e-7`); 위치 칸은 글자 노드 + `<a>` 뿐, `target=_blank rel=noopener` |
| `/tmp/r33y/mon.py` (임시 루트에 진짜 모니터 `--auth` + VoxLog 복사본) | 로그인 200; `#rec` 꺼짐; 실패 칸 숨김; 목록 2건 "연결됨"(= `Host: 127.0.0.1:<port>` 경유 GET 통과); 📍 1개·지도 링크 숫자; 상세 img 0개; 3MB 음성 → 안내 "음성은 VoxLog 자체 주소에서 들으십시오." + 토스트 502; **지우기 단추 보임 → 확인창 → 토스트 "서버에 연결할 수 없습니다", 디스크에 그대로** (N12); 묻기(오늘·요약, 경유 POST) → 답 보임; 앱 서버 기록 키 `owner, owner_start, pid, port, script, started`; 모니터 내린 뒤 살아 있는 자식 `[]` |
| `/tmp/r33y/owner.py` (app_server, pid 재사용 흉내) | owner = 살아 있는 무관한 `sleep` pid: 시작 시각 다름 → 고아 거둠·기록 지움·`ensure` 정상(기록 owner = 이 프로세스); owner_start 없는 옛 기록(cmdline 에 aimem_monitor 없음) → 거둠·정상; owner = pid 1 + 틀린 시작 시각 → 거둠·정상; **대조** 시작 시각 같음(문자열·정수 둘 다) → 건드리지 않음·`ensure` 503. `_kill_heirs`: 틀린 시작 시각·None → 피해 프로세스 살아 있음, 맞는 시작 시각 → 내림. setsid 손자는 `_kill_group` 뒤 남지 않음; 자기·부모는 보호 목록에 있음 |
| `/tmp/r33y/mutate.py` (복사본 9개에 결함 넣고 브라우저 검사, 복사본 모두 지움 `copy removed: True`) | `source=launch` 경로 지움 → 12번 실패 ✔; 소비자 `handleOpen` 지움 → 12번 실패 ✔; 상세 `innerHTML` → 13번 실패 ✔; 목록 `innerHTML` → 13번 실패 ✔; 413 을 영구 실패로 안 봄(queue·sw) → 15번 실패 ✔; 초안 조각 저장 끔 → 11건 실패 ✔; 서버가 X-Location 무시 → 17번 실패 ✔; **처음 3초 같은 신호 거르기 지움 → 17/17 통과 ✘**; **지도 링크에 `Number()` 안 거친 원래 값 → 17/17 통과 ✘** (N20) |

### 6.2 결함별 판정

| 번호 | 판정 | 근거 |
| ---- | ---- | ---- |
| R33-N1 (상) | 닫음 | 413·400·415 는 `state:'failed'` 로 옮기고 `waiting` 만 올림(`web/queue.js:216,240-245`, `web/sw.js:149,174-178` 같은 규칙). 실제 51MB 로 413 → 실패 칸·까닭·내려받기·지우기, 다시 부르는 길 6가지에도 POST 1회. 녹음기 `audioBitsPerSecond: 32000`(`web/app.js:297-298`) → 50MB 는 약 3.6시간. 변이 `perm` 을 15번이 잡음 |
| R33-N2 (중) | 닫음 | `localIso` 가 지역 시각 + 오프셋을 보냄(`web/app.js:54-62,309`). 서버 날짜 = 앞 10자 = 지역 날짜. 검사 14번(Honolulu)·exp KST 07:30 → 11-16 |
| R33-N3 (중) | 닫음 | `Asker.start` 가 `running` 을 `failed` 로(`voxlog/ask.py:123-139`), exp 재시작 결과 `failed`. 화면 폴링은 상한 없이 2초마다지만 `failed` 를 받으면 멈추므로 끝없이 돌지 않음 |
| R33-N4 (중) | 닫음 (위치는 N18) | 조각을 5초마다 IndexedDB `drafts/chunks` 에 이어 쓰고 다음 열 때 `draftRecover` 가 대기열로(`web/queue.js:296-374`, `web/app.js:862`). 크롬 실측·검사 16번·변이 `draft` 로 확인. 마지막 5초 미만과 길이(`duration_ms None`)는 잃음 - 하 수준 |
| R33-N5 (중) | 닫음 | 토큰 없으면 Host 가 `127.0.0.1`/`localhost`/`::1` 일 때만(`serve.py:146-148,196-202`). 리바인딩 이름 전부 403, 모니터 경유(`app_server.py` `_request` 의 `Host: 127.0.0.1:<port>`) 목록·묻기 정상. `[::1]evil` 같은 Host 는 통과하지만 브라우저가 공격자 이름으로 그런 Host 를 보낼 수 없어 결함 아님 |
| R33-N6 (중) | 닫음 (실물 확인 남음) | 기본 명령 `claude -p --tools "" --strict-mcp-config --setting-sources "" --no-session-persistence --output-format text`, `cwd` 는 빈 임시 폴더(`voxlog/ask.py:75-100`). 플래그 다섯 개 모두 `claude --help` 에 있음. 실제로 MCP·CLAUDE.md·hooks 가 안 읽히는지는 claude 를 부르지 않아 못 봄 → 5절 9번 그대로 |
| R33-N7 (중) | 닫음 | 기록에 `owner_start`(`/proc/<pid>/stat` 22번째 칸)를 적고 둘 다 맞을 때만 남의 것, 옛 기록은 cmdline `aimem_monitor` 확인(`app_server.py:63-89,262-286,465-475`). owner.py 5가지 모두 기대대로 |
| R33-N8 (중) | 닫음 (남은 틈은 N20) | 12번(launchQueue 흉내 켜고 끄기)·13번(XSS, 목록·상세) 이 생김. 변이 `launch`·`consumer`·`xss`·`xsslist` 를 모두 잡음 |
| R33-N9 (하) | 닫음 | 토큰 없을 때 `Origin: null` 은 남의 출처(`serve.py:208-209,220`). exp: 403 |
| R33-N10 (하) | 닫음 | `newest()` 가 200 으로 자르고 "최근 200건만 묻습니다" 토스트(`web/app.js:684-691`). 검사는 없음(코드 경로) |
| R33-N11 (하) | 닫음 | 토큰·주소 입력 뒤 `flushSoon`(`web/app.js:805-812`), 실패 칸이 `lastError` 있는 대기 줄도 "아직 올리지 못했습니다: …" 로 보임(`web/app.js:150,190-192`). 코드 경로 |
| R33-N12 (하) | **안 닫힘** (음성은 닫음) | 음성 안내 `#audio-note` 는 생겼으나, 모니터에서 지우기 단추가 그대로 보이고 누르면 "서버에 연결할 수 없습니다"·디스크에 그대로(mon.py). `detail-delete` 를 숨기는 코드가 없음(`web/index.html:115`, `web/app.js:651-662`), README 48~52행에도 지우기 말이 없음. 고칠 안은 처음과 같음 - `isolated()` 이면 지우기 단추를 숨기고 "자체 주소에서" 안내 |
| R33-N13~N16 (하) | 범위 밖·그대로 | 이번 후속 노드 대상이 아님. `serve.py:351-363` retry 는 여전히 `_seen` 을 직접 만짐, CORS 없음(`serve.py:157-161`) 등 처음 그대로 |
| R33-N17 (하) | 닫음 | `_descendants` 가 (pid, 시작 시각)을 모으고 `_kill_heirs` 는 시작 시각이 같을 때만 SIGTERM/SIGKILL(`app_server.py:106-169`). owner.py 로 확인. 내리는 도중 새로 생긴 손자·이중 fork 는 여전히 못 거둠(처음에 적은 한계, 가능성 낮음) |

### 6.3 새 결함

| 번호 | 심각도 | 무엇 | 어디(파일:줄) | 재현 | 고칠 안 |
| ---- | ------ | ---- | ------------- | ---- | ------- |
| R33-N18 | 중 | **살린 녹음은 위치를 잃음.** 초안은 `location: null` 로 만들어지고(`draftStart`) 위치를 얻은 뒤에도 초안에 적지 않음. 위치는 멈출 때 `draftFinish(…, loc)` 로만 건너가므로, 녹음 중 페이지가 내려가 `draftRecover → draftFinish(id, null)` 로 살아난 녹음은 서버 메타 `location: null`. 요청 수정의 '음성파일과 위치정보를 서버로' 가 N4 경로(긴 녹음·안드로이드가 렌더러를 죽이는 경우 - 바로 N4 를 고친 까닭)에서 빠짐. 검사 16번은 위치 권한 없이 돌아 못 잡음 | `web/app.js:311,316`, `web/queue.js:297-308,356,370` | `br.py`: 위치 허용·녹음 7초 중 새로고침 → 서버 `location None`, 같은 맥락 보통 녹음은 `{37.5665,126.978,20}` (두 번 돌려 같음) | `locPromise` 가 풀리면 초안 줄에 위치를 덧쓰기(`draftSetLocation(draftId, loc)` 또는 `draftStart` 를 다시 put); 검사 16번에 `geolocation` 을 주고 서버 `location` 확인 |
| R33-N19 | 하 | 멈춘 녹음의 저장이 위치를 최대 12초 기다린 뒤 **전역** `state.draftOk` 를 읽음. 그사이 다음 녹음을 시작하면(측면 버튼으로 끊고 다시 - 흔한 쓰임) `startRec` 이 `draftOk=false` 로 바꿔, 앞 녹음은 `enqueue` 로 가고 초안은 지워지지 않음 → 다음 열 때 `draftRecover` 가 같은 clientId 로 한 번 더 올림(서버 중복 막기로 보통은 무해, 그사이 사용자가 서버에서 지웠다면 되살아남). 같은 원리로 조각 저장이 중간에 실패하면 남은 부분 초안이 나중에 대기열의 온전한 줄을 덮을 수 있음 | `web/app.js:312,368-374`, `web/queue.js:353-357` | 코드 경로 | 녹음마다 `draftOk` 를 지역 변수(또는 draftId 별 표)로 잡기; `draftRecover` 는 같은 clientId 줄이 대기열에 있으면 그 초안을 지우기만 |
| R33-N20 | 하 | 검사 틈: (1) 측면 버튼 '처음 3초 같은 신호 거르기'(N8 고칠 안에 있던 것)를 지워도 17/17 - 12번은 `?source=launch` 로 연 페이지에서 첫 신호를 보내지 않음; (2) 지도 링크의 `Number()` 거르기를 빼도 17/17 - 17번은 정상 숫자만 씀. (3) 16번은 위치를 보지 않음(N18) | `projects/VoxLog/tests/browser_voxlog.py:349-368,438-452,454-483` | `mutate.py dedup3s`·`loc-num` → 17/17 | 12번에 `goto(b+"/?source=launch")` 직후 같은 targetURL 로 소비자를 한 번 불러 꺼지지 않음 확인; 17번에 `page.route` 로 `lat:"javascript:…"` 를 넣어 위치 칸 숨김 확인 |

### 6.4 위치정보(요청 수정) 정리

- 대기열: `normLoc` 로 숫자만 남겨 줄에 저장, 올릴 때 `X-Location: lat(6자리),lon(6자리),정확도(정수)` - 페이지(`queue.js:140-149,226-227`)와 서비스 워커(`sw.js:164`) 같음. 오프라인 → 온라인, 서비스 워커 경로 둘 다 서버 메타까지 감(실측).
- 초안 살리기: **위치가 가지 않음 (N18).**
- 틀린 X-Location: 21가지 모두 녹음은 201 로 저장되고 위치만 None(실측). 머리 원 바이트가 UTF-8 이어도 201.
- 지도 링크: `Number()`·`isFinite` 를 거친 숫자만 href 에 들어가고 아니면 칸을 숨김, 서버도 float 만 저장 - 안전(실측). 화면에는 범위 검사가 없지만 서버가 범위 밖을 None 으로 받으므로 실제로는 닿지 않음.
- 권한 거절·미지원 → None 으로 녹음 계속(검사 17번 뒷부분). 설정 '위치 함께 저장' 끄면 `getLocation` 이 바로 null(`app.js:222`, 코드 경로).
- 묻기 프롬프트에 `위치=lat,lon` 이 붙음 - 녹취 블록 머리 안이고 숫자만이라 주입 경로 아님.

### 6.5 남은 것

상 0 · 중 1(N18) · 하 3(N12 지우기 부분, N19, N20) + 범위 밖 그대로 하 4(N13~N16).
사람 실물 확인(5절)은 그대로이고, 7번(오전 9시 전 '오늘')은 이제 확인해도 됨, 6번(긴 녹음 크기)은 32kbps 라 약 3.6시간까지.

최종 판정: **조건부** - 요청의 핵심(녹음→대기열→업로드→받아쓰기→목록→묻기)과 N1~N11·N17 은 닫혔으나, 요청 수정으로 더해진 위치정보가 '녹음 중 새로고침 살리기' 경로에서 빠짐(N18, 중). N18 을 고치고 16번에 위치 확인을 더하면 통과.
