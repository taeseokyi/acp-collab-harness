# R49 공통 약속 - VoxLog F2 녹취 이름·태그 + AI 자동 태그

요청 `Q-261125-76c8`. 바탕은 `projects/VoxLog/docs/DESIGN-next-features.md` F2 절이고, **이 문서가 그 절과 다르면 이 문서가 맞습니다**
(태석님이 I3 자동 태그 보류를 뒤집었고, 아래가 관리자가 정한 세부입니다). 모든 노드가 이 약속을 그대로 씁니다.
F1(출처)·F3(이어 묻기)는 이번 일이 아닙니다.

## 1. 관리자가 정한 것 (요청이 관리자에게 맡긴 결정)

- **AI 태그와 사람 태그를 구분해 저장한다.** 화면에는 하나의 태그 줄로 보이되, AI 가 단 칩은 점선 테두리(`tag-auto`)와
  `title="AI 가 단 태그"` 로 구분한다. 사람이 그대로 둔 AI 태그는 계속 AI 표시를 유지한다.
- **사람이 태그를 한 번이라도 고치면(PATCH 에 `tags` 가 있으면) 그 녹취의 자동 태그는 끝난다**(`tags_human=true`).
  다시 받아쓰기 등 뒤의 자동 태그는 그 녹취의 태그를 바꾸지 않는다 - 지운 것을 되살리지도, 더한 것을 지우지도 않는다.
  이름(`label`)만 고친 PATCH 는 `tags_human` 을 바꾸지 않는다.
- **이미 있는 녹취에 다는 길을 둔다:** 상세의 `태그 다시 달기` 단추(`POST /api/recordings/<id>/autotag`). 사람이 누른
  것이므로 `tags_human` 이어도 돈다. 이때 사람이 단 태그(= `tags` 에서 `tags_auto` 를 뺀 것)는 그대로 두고, 예전 AI 태그는
  새 AI 태그로 바꾼다(사람 것 먼저, 합쳐 10개까지).
- 자동 태그는 받아쓰기가 **성공해 글이 저장된 뒤에만** 맡긴다(`no-stt`·`failed` 에는 없음). 빈 글이면 맡기지 않는다.
- 서버 재시작 때 `autotag="pending"` 으로 남은 것은 `failed` 로 바꾼다(묻기 답의 `running` 처리와 같은 방식). 다시 달려면 단추.
- 실패는 조용히: 받아쓰기·올리기 결과와 상태(`status`)에는 아무 영향이 없고, 상세에 작게 `자동 태그를 달지 못했습니다` 만.

## 2. 저장 (`meta/<id>.json`)

| 필드 | 꼴 | 기본(옛 meta 를 읽을 때 채움) | 뜻 |
| --- | --- | --- | --- |
| `label` | str | `""` | 사람이 붙인 이름. 화면은 `label || title` |
| `tags` | list[str] | `[]` | 보이는 태그 전부(사람 + AI), 최대 10 |
| `tags_auto` | list[str] | `[]` | `tags` 가운데 AI 가 단 것(대소문자 무시로 `tags` 의 부분집합) |
| `tags_human` | bool | `false` | 사람이 태그를 고친 적이 있음 → 자동(받아쓰기 뒤) 태그 안 함 |
| `autotag` | null 또는 `"pending"`·`"done"`·`"failed"` | `null` | 자동 태그 진행 상태 |

`Store.add_recording_file` 의 새 meta 에 다섯 필드를 기본값으로 넣는다. `Store.get`·`Store.list` 는 옛 meta 에 없으면
위 기본값으로 채워 돌려준다(`location` 선례). `set_transcript` 는 이 다섯 필드를 건드리지 않는다.

## 3. `voxlog/tags.py` (새 파일, 표준 라이브러리만, 다른 voxlog 모듈을 import 하지 않음)

```python
LABEL_MAX = 40; TAG_MAX = 20; TAGS_MAX = 10; AUTO_TAGS_MAX = 5
def clean(s: str) -> str            # " ".join(s.split()) - 앞뒤 자르고 안쪽 공백(줄바꿈 포함)을 한 칸으로
def normalize_label(v) -> str       # str 아니면 ValueError("label 은 문자열이어야 합니다"); clean; 40자 넘으면 ValueError("이름은 40자 이하여야 합니다")
def normalize_tags(v) -> list[str]  # list 이고 원소가 모두 str 아니면 ValueError("tags 는 문자열 목록이어야 합니다");
                                    # 각각 clean, 빈 것 버림, 20자 넘으면 ValueError("태그는 하나당 20자 이하여야 합니다"),
                                    # casefold 기준 중복은 첫 표기만, 그 뒤 10개 넘으면 ValueError("태그는 최대 10개입니다")
def tag_key(t: str) -> str          # t.casefold() - 비교는 언제나 이것으로
def merge_tags(human, auto) -> list[str]  # human 먼저, auto 에서 key 가 겹치지 않는 것을 이어 붙여 10개까지
def parse_tag_output(text: str, limit=AUTO_TAGS_MAX) -> list[str]
    # 모델 출력에서 태그만 관대하게 뽑는다(예외 없음): 줄마다, 그리고 쉼표(,·、)로 나눔 → 앞의 글머리(-*•·#)·번호(1. 1) ①)
    # 와 감싼 따옴표·백틱·끝 구두점(.。) 떼기 → clean → 빈 것·20자 넘는 것·'<' 또는 '>' 가 든 것 버림 → key 중복 버림 → 앞에서 limit 개
```

## 4. `voxlog/store.py` (바뀌는 것)

```python
def set_label_tags(self, rid, patch) -> None
    # patch 는 서버가 이미 정규화한 {"label": str} / {"tags": [str]} 중 온 키만. 잠금 안 read-modify-write(set_status 와 같음).
    # "tags" 가 있으면: tags = patch["tags"]; tags_auto = 옛 tags_auto 가운데 key 가 새 tags 에 남은 것(새 tags 의 표기로);
    #                   tags_human = True.  없는 id 는 ValueError(기존 _load_meta).
def set_auto_tags(self, rid, tags, manual=False) -> bool
    # tags 는 parse_tag_output 결과. 잠금 안에서:
    #  manual=False 이고 tags_human 이면 태그는 그대로 두고 autotag="done", False 를 돌려줌.
    #  manual=False 이고 사람 손 안 탐: tags = tags_auto = tags[:10].
    #  manual=True: human = [t for t in 옛 tags if key 가 옛 tags_auto 에 없음]; tags = merge_tags(human, tags);
    #               tags_auto = [t for t in tags if key 가 새 AI tags 에 있고 human 에 없음]. tags_human 은 그대로.
    #  끝에 autotag="done", True. 없는 id 는 ValueError.
def set_autotag(self, rid, state) -> None   # state ∈ {None,"pending","done","failed"} 아니면 ValueError. 없는 id 는 ValueError
def autotag_pending_ids(self) -> list[str]  # meta 만 훑어(글 안 읽음) autotag=="pending" 인 id
def list(self, q=None, date_from=None, date_to=None, status=None, limit=200, tag=None)
    # tag: tag_key 가 같은 태그가 있는 것만, 다른 거르기와 AND.
    # q 가 있으면 글·title·label·tags 를 대소문자 무시로 찾고 항목에 match 를 넣는다:
    #   글 또는 title 에 맞음 → "text"(스니펫은 지금 규칙), 아니고 label → "label", 아니고 태그 → "tag"(스니펫 text[:80]).
    #   q 가 없으면 match 키를 넣지 않는다.
```

## 5. `voxlog/ask.py`·`voxlog/stt.py` (바뀌는 것)

```python
# ask.py
TAG_HEAD = "이 녹취에 붙일 주제 태그를 3~5개 골라라. 한 줄에 태그 하나, 태그만 쓰고 다른 말은 쓰지 마라. 태그는 20자 이하의 짧은 명사구."
TAG_TEXT_MAX = 20_000
def build_tag_prompt(text) -> str   # TAG_HEAD + "\n" + _GUARD + "\n<녹취>\n" + text[:TAG_TEXT_MAX](</녹취> 이스케이프는 build_prompt 와 같게) + "\n</녹취>"
def llm_status(env=None) -> (bool, str|None)   # serve._health 에 있던 판정을 옮김(설정 오류면 (False, "LLM 명령 설정 오류: …"))
class Asker:
    # 큐를 queue.PriorityQueue 로: 항목 (우선순위, 순번, 일). 사용자 묻기 0, 태그 1, 멈춤(None) 2 - 같은 우선순위는 들어온 순서.
    # 그래서 태그 일이 쌓여 있어도 새 사용자 묻기가 먼저 돈다(지금 도는 태그 하나는 끝까지 감).
    def submit_tag(self, rid, manual=False) -> bool
        # 같은 rid 가 이미 큐에 있으면 False(중복 안 넣음, 단 manual=True 가 오면 그 일을 manual 로 올림).
        # store.set_autotag(rid, "pending") 뒤 넣고 True. 없는 id(ValueError)는 False.
    # 태그 일 처리: rec = store.get(rid); 없거나 글이 비면 set_autotag(rid, None) 하고 끝.
    #   out = self.run(build_tag_prompt(글), self.env); tags = tags.parse_tag_output(out)
    #   tags 가 비면 set_autotag(rid,"failed"), 아니면 store.set_auto_tags(rid, tags, manual).
    #   어떤 예외든 set_autotag(rid,"failed") 를 시도하고 삼킨다(지워진 녹취면 그것도 삼킴). 스레드는 죽지 않는다.
    # start(): 지금처럼 running 답을 failed 로 + store.autotag_pending_ids() 를 set_autotag(rid,"failed").
    # idle(): 태그 일까지 포함해 큐가 비고 도는 것이 없을 때 True.
# stt.py
class Transcriber:
    def __init__(self, store, env=None, transcribe_fn=transcribe, on_done=None)
    # _process 에서 set_transcript 가 성공하고 글이 비지 않았으면 on_done(rid) - 예외는 삼킨다(받아쓰기 결과에 영향 없음).
```

## 6. `serve.py`·HTTP

- `make_server(..., llm_ready=None)`: `server.llm_ready = llm_ready or (lambda: ask_mod.llm_status(env)[0])`. Asker 를 먼저
  만들고 Transcriber 에 `on_done=lambda rid: server.asker.submit_tag(rid) if server.llm_ready() else None` 를 준다.
  `_health` 는 `ask_mod.llm_status(env)` 를 쓴다(응답 꼴은 지금 그대로).
- `recordings/<id>` 갈래: `("GET","PATCH","DELETE")` → `_rec_get`/`_rec_patch`/`_rec_delete`, 405 의 `Allow` 도 같은 셋.
- `PATCH /api/recordings/<id>` - 설계 문서 F2 '인터페이스' 그대로(`PATCH_JSON_MAX = 6 * 1024`, `_read_body` 직접, 오류 문구 그대로,
  정규화는 `tags.normalize_label`/`normalize_tags`, `Store.get` 404, 사이에 지워져 `ValueError` 도 404). 200 은 `Store.get` 꼴.
- `POST /api/recordings/<id>/autotag` (새, 본문 없음): 없는 id 404 `없는 녹음입니다` · `server.llm_ready()` 거짓이면
  503 `{"error":"묻기(LLM)가 준비되지 않았습니다"}` · 글이 비면 409 `{"error":"받아 적은 글이 없습니다"}` ·
  아니면 `asker.submit_tag(rid, manual=True)` 후 202 `{"ok":true,"autotag":"pending"}`. 토큰·출처 검사는 다른 쓰기와 같이.
- `GET /api/recordings?tag=<태그>` - 20자 넘으면 400 `태그는 하나당 20자 이하여야 합니다`, `Store.list(tag=…)` 로.
- `GET /api/recordings`·`/api/recordings/<id>` 응답 항목에 2절의 다섯 필드(+ q 가 있을 때 `match`).

## 7. 화면 (`web/`)

요소 id (index.html 이 만들고 app.js 가 씀 - 이름을 바꾸지 않는다):

| id / class | 자리 | 뜻 |
| --- | --- | --- |
| `#search` placeholder | 목록 | `글·이름·태그에서 찾기` 로 바꿈 |
| `#tag-filter-row`(hidden) 안 `#tag-filter-label`, `#tag-filter-clear`(button) | `#status-filter` 뒤 | 거르는 태그 표시·풀기 |
| `#detail-chips` | 상세 `#detail-meta` 뒤 | 그 녹취의 태그 칩 전부 |
| `#detail-edit`(class `detail-edit`, hidden) 안 `#detail-label`(input, maxlength 40), `#detail-tags`(input, placeholder `쉼표로 나눔`), `#detail-save`(button `저장`), `#detail-retag`(button `태그 다시 달기`, hidden), `#detail-tag-state`(span) | `#detail-chips` 뒤, 오디오·글보다 위 | 편집 |
| `.rec-tags` 안 `.tag-chip`(button), AI 것은 `.tag-chip.tag-auto` | 목록 항목 | 앞 2개 + `+N`(`.tag-chip.tag-more`, 누르면 상세 열림과 같음) |
| `.rec-match` | 목록 항목 | `match` 가 label/tag 일 때 `이름에서 맞음`/`태그에서 맞음` |

app.js 동작:
- `renderList`: 제목은 `it.label || it.title`, 칩은 `textContent` 로만. 칩 클릭은 `stopPropagation()` 뒤 `applyTagFilter(tag)`
  (`state.tagFilter` 를 세우고 `#tag-filter-row` 를 보이고 `loadList()`). `#tag-filter-clear` 가 풀고 다시 읽음.
- `filterParams(limit)` 에 `if (state.tagFilter) p.set('tag', state.tagFilter);`. 묻기 범위 `search` 는 따라오고 `today`·`week` 는 무시.
- 상세: `#detail-title` 은 `label || title`. `#detail-chips` 는 매번(폴링 포함) 다시 그림. 입력칸은 상세를 처음 열 때와 저장
  성공 뒤에 채우고, 폴링 때는 **입력칸 값이 마지막으로 채운 값과 같고 포커스가 없을 때만** 다시 채운다(쓰던 것을 지우지 않음,
  AI 태그가 늦게 와도 입력칸에 들어감). `#detail-tags` 는 `tags.join(', ')`, 저장 때 쉼표(`,`)로 나눠 보냄(정규화는 서버).
- `saveLabels(id)`: `PATCH` 본문 `{label, tags}`(둘 다 보냄), 실패면 서버의 `error` 를 토스트. 성공하면 상세·목록 다시 읽기.
- `#detail-retag`: `state.llm`(health 의 `llm`)이 참이고 글이 있고 격리 출처가 아닐 때만 보임. 누르면 POST autotag, 상세 폴링.
- 상세 폴링은 받아쓰는 중에 더해 `autotag === "pending"` 일 때도 돈다. `#detail-tag-state`: pending → `AI 가 태그를 다는 중…`,
  failed → `자동 태그를 달지 못했습니다`, 그 밖에는 빈 글.
- `isolated()` 가 참이면 `#detail-edit` 을 숨긴다(기존 `#detail-delete` 와 같은 경계 - 모니터는 PATCH 를 이어 주지 않고, IndexedDB
  없는 브라우저에서도 숨는 것은 그 선례를 따른 의도, R48-N20).
- `web/sw.js` 의 `VERSION` 을 하나 올린다(셸 캐시 갱신).
- 폰 320~430px: 칩 줄 `flex-wrap:wrap`, 칩 `max-width:100%`·`overflow-wrap:anywhere`, 편집 블록 입력은 `width:100%`, 단추는 줄바꿈.
  가로 넘침 없음(`scrollWidth <= innerWidth`), `#detail-edit` 이 `#detail-audio`·`#transcript` 와 겹치지 않음. 어두운 모드에서 칩이 보임.

## 8. 가짜 LLM

`tests/fake_llm.py`: 표준 입력이 `TAG_HEAD` 의 앞부분 `이 녹취에 붙일 주제 태그` 로 시작하면 `FAKE_LLM_TAGS` 환경 변수(없으면
`회의\n가짜 태그\n- 세번째`)를 그대로 내고 끝(실패 변수 `FAKE_LLM_FAIL=1` 은 지금처럼 먼저 봄). 그 밖은 지금 그대로.
`tests/test_serve.py` 의 `fake_llm` 도 태그 프롬프트면 태그 줄을 돌려주게 한다.

## 9. 13:45 태석님 보탬(자동 태그를 kistillm 으로) - 13:46 철회됨

`rounds/R49/INBOX.md` 의 13:45 말은 13:46 에 철회됐습니다. 자동 태그는 위 1~8절대로 묻기와 같은 `ask.run_llm`(claude 명령)을 씁니다.
그 사이 관리자가 이 절에 적었던 안(별도 Tagger·OpenAI 호환 호출)은 지웠고, 노드·코드 변경은 없었습니다.
