# 상세 패널 - 2차 시도 (1차 `20261109-175553-S3` 는 파일을 하나도 못 고치고 끝났다)

**1차 시도에서 너는 `style.css` 를 출력만 하고 70초 만에 보고 없이 끝났다.** `index.html` 과
`app.js` 는 한 줄도 바뀌지 않았다. 이번에는 **파일을 실제로 편집**하고 **보고를 응답 본문에 써라.**

고칠 파일은 셋뿐이다: `static/index.html`, `static/app.js`, `static/style.css`.

## 1. 상세 패널 (요청 8d8d - 태석님: "작업이나 라벨을 클릭하면 상세내용이 나오면 좋겠다")
API 는 이미 떠 있다. 먼저 쳐 보라:
`curl -s localhost:18799/api/runs/20261109-172618-S3`
키 16개: `id found slot harness model label status rc elapsed_s started ended brief report stderr_tail paths errors`.
없는 id → 404, 잘못된 id → 400.

- 실행 표의 행, 보드 표의 행, 요청 트리의 서브태스크 중 **`run_id` 를 가진 것**을 클릭하면 패널이 열린다
- 패널 내용 순서: 라벨 / id / 슬롯·하네스·모델·상태·rc·경과 / **보고 본문**(기본 펼침) /
  **지시 본문**(`<details>` 접힘) / 산출물 경로 / **stderr 꼬리**(lost 실행 진단용)
- **본문은 `textContent` + `white-space: pre-wrap` 으로 넣어라. `innerHTML` 금지** (작업자가 쓴 문자열이다)
- 닫기는 ESC·바깥 클릭·X 버튼 셋 다. 열려 있는 동안 5초 폴링이 패널을 덮지 않게 하라
- 가져오는 중 / 404 / 400 을 패널 안에 보여라. 조용히 실패하지 마라

## 2. id 중심 표시 (요청 `cf63` - 태석님: "작업자 실행 상태에 id 가 있어야 작업을 식별할 수 있다")
실행 표에 **run id 열을 추가**하라(모노스페이스, 전체 id, 말줄임 금지 - 식별이 목적이다).
보드·요청 트리의 행에도 연결된 run id 를 작게 보여라.

## 3. lost 배지 (요청 `c87c` 2항)
`status == "lost"` 행은 **회색 배지 + `title` 툴팁 "작업자가 보고/종료코드 없이 사라짐"** 으로 표시하라.
(경과 시간이 멈추는 것은 `reader.py` 쪽에서 따로 고치는 중이다 - 네 일이 아니다.)

## 4. 요청 폼 요청자 칸
기본값을 **`태석`** 으로 **채워라**(`placeholder` 가 아니라 `value`). `required` 도 걸어라.
서버가 이제 빈 요청자를 **400** 으로 거절한다 - 그 `error` 문자열을 폼 아래에 보여라.

## 지키기
- `--st-*` 토큰만 쓴다. 하드코딩 hex·외부 폰트·CDN 금지. 밝은 모드 기본, 대비 4.5:1
- **기존 DOM id 를 지우지 마라** (`kisti-card`, `graphs-list`, `theme-toggle`, `requests-list` …)
- **`--st-accent-ink`(#fff) 를 `--st-accent` 배경 위에 쓰지 마라 - 대비 2.54:1 이다**(S4 검수 실측).
  채운 버튼이 필요하면 `--st-accent-text` 를 쓰거나 테두리 버튼으로 하라
- `pkill` 류 금지. 서버는 관리자가 18799 에 띄워 두었다

## 검증 (출력을 보고에 붙여라)
```
curl -s -o /dev/null -w "index %{http_code} css %{http_code}\n" localhost:18799/
grep -c "api/runs" tools/aimem_monitor/static/app.js
grep -n "innerHTML" tools/aimem_monitor/static/app.js | head
git diff --stat tools/aimem_monitor/static/ 2>/dev/null; ls -l tools/aimem_monitor/static/
python3 -m unittest discover -s tests 2>&1 | grep -E "^Ran|^OK|^FAILED"
```
**보고는 이 응답 본문에 반드시 써라.** 무엇을 어느 파일 몇 행에 넣었는지, `innerHTML` 을
상세 본문에 쓰지 않았음을, 검증 출력을 그대로 적어라.
