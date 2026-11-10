# 상세 패널 - 3차 (짧게 간다. 한 가지만 해라)

1차는 파일을 못 고치고 끝났고, 2차는 모델 API 연결이 끊겨(`Cannot connect to API`) 중간에 죽었다.
2차가 남긴 것: `index.html` 의 요청자 칸은 **이미 `value="태석" required` 로 고쳐졌다 - 건드리지 마라.**
`app.js` 는 문법은 멀쩡하나 상세 패널이 없다.

**이번에 할 것은 상세 패널 하나뿐이다.** 다른 것은 하지 마라.

## API (이미 떠 있다)
`curl -s localhost:18799/api/runs/20261109-172618-S3`
→ 키 16개: `id found slot harness model label status rc elapsed_s started ended brief report stderr_tail paths errors`
없는 id = 404, 잘못된 id = 400.

## 구현
`static/app.js` 와 `static/style.css` 만 고친다 (`index.html` 은 건드리지 마라 - 패널 요소는 JS 로 만들어 붙여라).

1. 실행 표(`runs`)의 **행을 클릭**하면 패널이 열린다. 행의 `id` 를 `/api/runs/<id>` 로 가져온다
2. 패널 내용: 라벨 / id / 슬롯·하네스·모델·상태·rc·경과 / **보고 본문** / **지시 본문** / **stderr 꼬리**
3. 본문은 **`textContent` + `white-space: pre-wrap`**. **`innerHTML` 을 쓰지 마라**
4. 닫기: X 버튼 + ESC. 열려 있는 동안 자동 새로고침이 패널을 덮지 않게 하라
5. 가져오는 중 / 404 / 400 을 패널 안에 글자로 보여라
6. 색은 `--st-*` 변수만 쓴다. **`--st-accent-ink` 는 쓰지 마라**(대비 2.54:1)

## 검증 (이 두 줄을 돌리고 출력을 보고에 붙여라)
```
grep -c "api/runs" tools/aimem_monitor/static/app.js
node --check tools/aimem_monitor/static/app.js && echo "문법 OK"
```
첫 줄이 **1 이상**이어야 한다. 그리고 **보고를 이 응답 본문에 써라** - 무엇을 app.js 몇 행에 넣었는지.
