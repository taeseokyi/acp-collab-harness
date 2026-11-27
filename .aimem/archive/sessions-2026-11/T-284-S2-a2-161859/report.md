DONE
ANSWERS 383 / ALLOWED 900. `allowed.txt`는 주석 3줄 포함 903줄이며, 빌드 후 `words.js`의 ALLOWED는 900개입니다.

**고친 파일**
- `projects/자모맞히기/data/allowed.txt`: 기계 생성 `정*`·`염*`·`역*` 조합과 지어낸 말을 걷어 내고, N2 흔한 낱말·동사/형용사 기본형·받침 있는 두 음절·받침 없는 세 음절을 넣었습니다. 첫 음절 최대 40개.
- `projects/자모맞히기/data/answers.txt`: N3의 민감어·고유명사·비속어·신조어·낱말 아님·희귀어를 제거하고, 흔한 일상어 383개만 남겼습니다.
- `projects/자모맞히기/data/README.md`: 실제 기준(900/383, 금칙어 시험, 임시 빌드, 첫 음절 제한)을 사실대로 다시 썼습니다.
- `projects/자모맞히기/tools/build_words.py`: `--out PATH` 인자를 추가했고 기본값은 기존 `web/js/words.js`입니다.
- `projects/자모맞히기/tests/test_words.py`: `BANNED` 금칙어 검사, `MUST` 흔한 낱말 검사, 첫 음절 40 이하 검사, `tempfile` 임시 출력으로 다시 빌드 비교를 넣었습니다.
- `projects/자모맞히기/web/js/words.js`: `build_words.py`로 다시 생성했습니다.

**실제 검증**
```bash
python3 projects/자모맞히기/tools/build_words.py
```
```text
answers: 383개 (걸러 냄 2줄)
allowed: 900개 (원본 900개, 걸러 냄 3줄)
wrote /home/tsyi/work/ai-fleet/projects/자모맞히기/web/js/words.js
```

```bash
python3 .aimem/graph/inputs/r24/v_words2.py
```
```text
ANSWERS 383 ALLOWED 900
첫 음절 상위 [('정', 40), ('전', 39), ('공', 27)]
OK
words2: 모두 통과
```

```bash
python3 -m unittest discover -s projects/자모맞히기/tests -p 'test_words.py'
```
```text
Ran 11 tests in 0.050s
OK
```

```bash
node --test projects/자모맞히기/tests/test_jamo.mjs
```
```text
tests 19
pass 19
fail 0
```

**다음 담당자에게**
`test_words.py`의 다시 빌드 시험은 이제 임시 폴더만 사용하고 실제 `web/js/words.js`를 건드리지 않습니다. `git commit`/`push`/삭제/의존성 설치는 하지 않았고, 변경 파일은 작업 트리에 남아 있습니다.