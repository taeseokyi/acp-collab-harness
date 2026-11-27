DONE

## 한 일

T-277 낱말 목록을 손으로 고른 원본에서 생성하는 파이프라인을 만들었습니다. 6칸 규칙(쌍자음·ㅐㅔㅒㅖ 한 칸, 겹모음·겹받침 두 칸)에 맞는 일상 한국어 낱말을 직접 골랐고, 빌드가 완성형 한글 6칸만 남기도록 했습니다.

- `data/answers.txt` — 정답 후보 416줄(빌드 후 **398개**)
- `data/allowed.txt` — 추측 허용 1340줄. `answers ∪ allowed` = **1032개**
- `tools/build_words.py` — 주석·빈 줄·비6칸·중복 제거, ANSWERS는 `random.Random(20261113).shuffle`, ALLOWED는 정렬, `json.dumps(ensure_ascii=False)`로 `web/js/words.js` 생성. 걸러 낸 수를 표준출력에 찍음
- `data/README.md` — 고른 기준·출처(함대 작업자 직접 고름, 외부 목록 복사 없음)·이용 조건·재생성 명령
- `tests/test_words.py` — unittest 8개: 6칸 검사, 중복 없음, 부분집합, 개수 하한, ALLOWED 정렬, ANSWERS 고정 씨앗 섞임, 재생성 바이트 동일, 칸 풀기 예시

## 실제로 돌린 검증

```
$ python3 projects/자모맞히기/tools/build_words.py
answers: 398개 (걸러 냄 18줄)
allowed: 1032개 (원본 1020개, 걸러 냄 320줄)

$ python3 .aimem/graph/inputs/r24/v_words.py
ANSWERS 398 ALLOWED 1032
words: 모두 통과

$ python3 -m unittest discover -s projects/자모맞히기/tests -p 'test_words.py'
Ran 8 tests in 0.046s
OK
```

## 다음 담당자가 알아야 할 것

- `web/js/words.js`는 생성물이므로 손으로 고치지 말고 `python3 projects/자모맞히기/tools/build_words.py`로 다시 만드십시오. 같은 입력이면 바이트 단위로 같습니다.
- 빌드 걸러 냄 수는 `answers` 18줄, `allowed` 320줄입니다(대부분 5칸이거나 7칸인 후보). 원본에 후보를 더 넣어도 빌드가 알아서 거릅니다.
- 쓰기 범위 밖 파일은 건드리지 않았고, git commit/push/삭제/의존성 설치/네트워크는 하지 않았습니다.