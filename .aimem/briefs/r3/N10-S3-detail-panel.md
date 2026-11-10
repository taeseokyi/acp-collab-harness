# T-053 상세 패널 - 행을 클릭하면 상세가 열린다 (요청 8d8d, 태석님 17:39)

태석님이 웹 폼으로 직접 넣은 요청이다: **"작업이나 라벨을 클릭하면 상세내용이 나오면 좋겠다."**

데이터는 이미 다 있다. **새 API 가 떠 있다. 직접 쳐 보고 시작하라:**
```
curl -s localhost:18799/api/runs/20261109-172618-S3 | head -c 600
```
응답은 최상위 키 16개다(없으면 빈 값/None 으로라도 **항상 있다**):
`id, found, slot, harness, model, label, status, rc, elapsed_s, started, ended, brief, report, stderr_tail, paths, errors`
- `brief` = 그 작업자에게 준 **지시 본문**, `report` = 작업자의 **보고 본문**(마크다운), `paths` = 산출물 경로 dict
- 없는 id → **404**, 잘못된 id → **400**. 둘 다 `{"error": ...}` 이다

## 할 일 (`static/**` 만 쓴다)
1. **클릭 가능한 것 세 가지**: (a) 실행 표(`runs`)의 행, (b) 보드 표의 행, (c) 요청 트리의 서브태스크.
   셋 다 `run_id` 를 들고 있다(요청 서브태스크는 `run_id` 필드, 보드 행은 산출물 칸의 run 표기).
   **`run_id` 가 없는 행은 클릭 대상이 아니다** - 커서도 바뀌지 않게 하라.
2. **상세 패널**: 오른쪽에서 열리는 드로어나 모달 하나. 내용 순서는
   제목(라벨) / 슬롯·하네스·모델·상태·rc·경과·시작·종료 / **보고 본문** / **지시 본문** / 산출물 경로 / stderr 꼬리.
   보고와 지시는 길다 - 접기(`<details>`)로 두고 보고만 기본 펼침으로 하라.
   **마크다운을 HTML 로 렌더링하지 마라.** `textContent` 로 넣고 `white-space: pre-wrap` 으로 보여라
   (보고 본문은 작업자가 쓴 문자열이다 - innerHTML 에 넣으면 주입이다).
3. **닫기**: ESC, 바깥 클릭, X 버튼 셋 다. 열려 있는 동안 5초 폴링이 패널을 덮어쓰지 않게 하라.
4. **로딩·오류 상태**: 가져오는 동안 "불러오는 중", 404/400 이면 그 메시지를 패널 안에 보여라. 조용히 실패하지 마라.
5. **요청 폼의 요청자 칸**: 기본값을 `태석` 으로 채워라. **서버가 이제 빈 요청자를 400 으로 거절한다**
   (17:39 요청이 `(익명)` 으로 저장돼 누가 시킨 일인지 파일만 보고 알 수 없었다). 폼에서도
   `required` 로 막고, 서버가 400 을 주면 그 `error` 문자열을 폼 아래에 보여라.
6. **스타일은 네가 방금 넣은 `--st-*` 토큰만 쓴다.** 하드코딩 hex 금지, 외부 폰트·CDN 금지,
   밝은 모드 기본, `data-theme=dark` 에서도 패널이 읽히는지 확인하라. 대비 4.5:1.

## 지키기
- 기존 DOM id 를 **지우지 마라**(`kisti-card`, `graphs-list`, `theme-toggle`, `requests-list`, `runs-table-wrap` …).
  다른 슬롯의 검수가 이 id 들을 대조한다.
- `style.css`·`index.html`·`app.js` 세 파일만 쓴다. 서버·reader·테스트는 남의 소유다.
- **`pkill` 류를 쓰지 마라.** 서버는 관리자가 18799 에 띄워 두었고 네가 내릴 일이 없다.

## 검증 (출력을 보고에 붙여라)
```
curl -s -o /dev/null -w "index %{http_code}\n" localhost:18799/
curl -s -o /dev/null -w "css %{http_code}\n" localhost:18799/static/style.css
curl -s -o /dev/null -w "js %{http_code}\n" localhost:18799/static/app.js
curl -s localhost:18799/api/runs/20261109-172618-S3 | python3 -c "import json,sys;d=json.load(sys.stdin);print('키',len(d),'보고',len(d['report']),'지시',len(d['brief']))"
grep -c "innerHTML" tools/aimem_monitor/static/app.js
python3 -m unittest discover -s tests 2>&1 | tail -3
```
`innerHTML` 을 상세 본문에 쓰지 않았음을 보고에서 직접 밝혀라. 브라우저 자동화는 이 환경에 없다 -
DOM id 대조와 CSS 값 확인은 `grep`/`python3` 로 하라.
