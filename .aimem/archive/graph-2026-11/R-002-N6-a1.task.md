## 대상 파일 (이 셋만 고친다)

- `/home/tsyi/work/ai-fleet/tools/aimem_monitor/static/style.css`
- `/home/tsyi/work/ai-fleet/tools/aimem_monitor/static/index.html`
- `/home/tsyi/work/ai-fleet/tools/aimem_monitor/static/app.js`

**직전 작업(R-002/N3)이 같은 파일을 이미 고쳤다.** 밝은 모드 기본, 표 정렬·말줄임, KISTI 상태 카드(`#kisti-card`), 그래프 트리(`#graphs-list`), 테마 토글(`#theme-toggle`) 이 들어가 있다. **그것을 전부 그대로 유지하면서 색·치수만 Strata 토큰으로 갈아끼우는 작업이다.** 기능이나 DOM id 를 하나도 없애지 마라.

## 왜

태석님 요청 `20261109-172326-c5c1` (2026-11-09 17:25): 모니터 화면을 KISTI Strata 모니터(`aida.kisti.re.kr:10430/#monitor`)와 비슷하게. 두 화면을 나란히 띄워 보는 사람이 같은 제품으로 느껴야 한다.

## 참조 파일 (읽어라)

`/home/tsyi/work/ai-fleet/.aimem/briefs/strata-tokens.css` - 원본 토큰 정의다. **이 파일을 고치지 말고 읽기만 해라.** `:root` 와 `[data-theme="dark"]` 의 `--st-*` 값이 정본이다.

## 할 일

1. **`style.css` 의 `:root` 에 `--st-*` 토큰을 참조 파일에서 그대로 옮겨 적는다.**
   - **변수 이름을 바꾸지 마라.** `--st-bg`, `--st-surface`, `--st-surface-2`, `--st-line`, `--st-line-soft`, `--st-ink`, `--st-ink-soft`, `--st-ink-muted`, `--st-accent`, `--st-accent-hover`, `--st-accent-ink`, `--st-accent-tint`, `--st-accent-text`, `--st-focus`, `--st-info`/`--st-info-tint`/`--st-info-text`, `--st-warn`/`--st-warn-tint`/`--st-warn-text`, `--st-danger`/`--st-danger-tint`/`--st-danger-text`, `--st-sh-card`, `--st-sh-bar`, `--st-sh-pop`, 글자 크기 `--st-fs-*`, 굵기 `--st-fw-*`, 행간 `--st-lh-*`, 간격 `--st-s-*`, 반경 `--st-r-*`, 모션 `--st-ease`/`--st-dur` - 참조와 1:1 로 대응해야 나중에 원본이 바뀔 때 대조할 수 있다.
   - 참조 파일의 `[data-theme="dark"]` 블록도 그대로 옮긴다. **어두운 모드는 토글로만** 들어간다(기본은 밝은 모드). `@media (prefers-color-scheme: dark)` 를 쓰지 마라.
   - `:root` 에 `color-scheme: light;`, `[data-theme="dark"]` 에 `color-scheme: dark;` 를 둔다.
2. **글꼴: `@font-face` 와 Outfit 파일 참조를 가져오지 마라.** 그 폰트 파일은 우리 저장소에 없고 외부 로드는 금지다. `--st-font` 를 `system-ui, -apple-system, "Segoe UI", Roboto, "Noto Sans KR", sans-serif` 로 정의하고 `body` 가 그것을 쓰게 한다. `--st-font-mono` 는 참조대로 둔다.
3. **기존 `--bg`/`--card`/`--text`/`--muted`/`--accent`/`--warn`/`--danger`/`--border` 같은 옛 이름은 `--st-*` 의 별칭으로만 남긴다.** 예: `--bg: var(--st-bg); --card: var(--st-surface); --text: var(--st-ink);` - 이렇게 두면 규칙 본문을 전부 고치지 않아도 색이 바뀐다. 별칭을 쓰지 않고 본문을 직접 고쳐도 되지만, **규칙 본문에 하드코딩된 hex 가 하나도 남아서는 안 된다.**
4. **치수를 Strata 스케일에 맞춘다.**
   - 글자: 본문 `--st-fs-md`(14px), 보조·주석 `--st-fs-xs`(12px)~`--st-fs-sm`(13px), `h3` `--st-fs-base`(16px), `h2` `--st-fs-lg`(18px), 페이지 제목/브랜드 `--st-fs-xl`(24px). **큰 수치 한 개짜리 통계가 있으면** `--st-fs-stat`(32px).
   - 여백·간격은 `--st-s-*`(4pt 스케일)만 쓴다. 임의의 `13px`, `7px` 같은 값을 남기지 마라.
   - 카드: `border-radius: var(--st-r-md)`(14px), `background: var(--st-surface)`, `border: 1px solid var(--st-line)`, `box-shadow: var(--st-sh-card)`. 상단바는 `var(--st-sh-bar)`.
   - 작은 요소(버튼·입력·배지가 아닌 것): `--st-r-sm`(8px). 큰 패널: `--st-r-lg`(20px).
5. **상태 배지를 pill 로.** `border-radius: var(--st-r-pill)`, 배경은 틴트, 글자는 텍스트색:
   - 정상/완료(`DONE`, `done`, `대기`) -> `--st-accent-tint` + `--st-accent-text`
   - 진행(`IN-PROGRESS`, `running`, `REVIEW`) -> `--st-info-tint` + `--st-info-text`
   - 주의(`ASSIGNED`, `TODO`, `NEW`, `바쁨`, `lost`) -> `--st-warn-tint` + `--st-warn-text`
   - 위험(`BLOCKED`, `REJECTED`, 오류) -> `--st-danger-tint` + `--st-danger-text`
   - 배지 글자는 `--st-fs-xs`, `--st-fw-medium`, `padding: var(--st-s-1) var(--st-s-3)`.
6. **표:** 머리글 배경 `--st-surface-2`, 구분선 `--st-line-soft`, 본문 글자 `--st-fs-md`, 행간 `--st-lh-body`. **N3 이 넣은 `table-layout: fixed`·숫자 열 우측정렬·`tabular-nums`·말줄임+툴팁은 그대로 유지한다.**
7. **포커스 링:** 키보드 포커스에 `outline: 2px solid var(--st-focus); outline-offset: 2px;` 를 준다. `outline: none` 만 주고 끝내지 마라.
8. 전환 효과를 쓰면 `transition: ... var(--st-dur) var(--st-ease)` 형태로만 쓴다.

## 하지 말 것

- **외부 폰트·CDN·프레임워크를 불러오지 마라.** 이 화면의 제약은 의존성 0 이다.
- `tools/aimem_monitor/server.py` / `reader.py` / `__init__.py` / `.aimem/briefs/strata-tokens.css` 를 고치지 마라. **네 소유가 아니다.**
- N3 이 만든 DOM id 를 지우지 마라: `kisti-card`, `kisti-section`, `graphs-list`, `theme-toggle`, `autoRefresh`, `refresh-status`, `refresh-now`, `demo-banner`, `errors`, `aimem-meta`, `slots-table-wrap`, `runs-table-wrap`, `board-table-wrap`, `queue-table-wrap`, `request-form`, `req-title`, `req-detail`, `req-requester`, `request-submit`, `form-msg`, `requests-list`.
- `npm` / `pip` 로 아무것도 설치하지 마라.
- 어두운 모드를 기본으로 만들지 마라. **저장값이 없으면 밝은 모드다.**

## 검증 (직접 돌리고 출력을 보고에 붙여라)

```
cd /home/tsyi/work/ai-fleet && curl -s -o /dev/null -w "index=%{http_code}\n" http://127.0.0.1:18799/
cd /home/tsyi/work/ai-fleet && curl -s -o /dev/null -w "css=%{http_code}\n" http://127.0.0.1:18799/static/style.css
cd /home/tsyi/work/ai-fleet && python3 -c "import re,pathlib; c=pathlib.Path('tools/aimem_monitor/static/style.css').read_text(); body=re.sub(r':root\{.*?\}|\[data-theme=\"dark\"\]\{.*?\}','',c,flags=re.S); print('규칙 본문에 남은 하드코딩 hex:', sorted(set(re.findall(r'#[0-9a-fA-F]{3,8}', body))))"
cd /home/tsyi/work/ai-fleet && python3 -c "import re,pathlib; h=pathlib.Path('tools/aimem_monitor/static/index.html').read_text(); ids=['kisti-card','graphs-list','theme-toggle','requests-list','runs-table-wrap']; print([(i, ('id=\"%s\"'%i) in h) for i in ids])"
```

**대비비를 숫자로 보고해라.** `--st-ink` on `--st-surface`, `--st-ink-muted` on `--st-surface`, 그리고 배지 4종(틴트 배경 + 텍스트색)에 대해 WCAG 대비비를 `python3 -c` 로 계산해 붙여라. **4.5 미만이면 그 쌍의 텍스트색을 어둡게 조정하고 조정한 값을 보고에 적어라.** (참조 토큰이 이미 4.5:1 을 겨냥했지만 실제로 재서 확인해라.)

브라우저 자동화(Playwright)가 이 환경에 없으면 스크린샷은 생략하고 **"브라우저 없음 - 스크린샷 미수행"** 이라고 보고에 분명히 적어라. 없는 검증을 했다고 쓰지 마라.
