# R30 검수 (T-309, S1) - R29-N1·N2 재검수 + 변이 V19

검수자 S1 (claude opus), 2026-11-14. 프로젝트 파일은 고치지 않았고, 변이는 `/tmp/s1-r30/` 사본에서만 넣었다가 지웠다.

## 1 네 벌

| 벌 | 명령 | 출력 | rc | README 의 수 |
|---|---|---|---|---|
| 로직·저장 | `node --test projects/자모맞히기/tests/*.mjs` | `ℹ pass 66`, `ℹ fail 0` | 0 | 66 - 맞음 |
| 낱말 목록 | `python3 -m unittest discover -s projects/자모맞히기/tests -p 'test_*.py'` | `Ran 13 tests`, `OK` | 0 | 13 - 맞음 |
| 화면 | `python3 projects/자모맞히기/tests/browser_game.py` | `통과 121 / 전체 121` | 0 | 121 - 맞음 |
| 모드 | `python3 projects/자모맞히기/tests/browser_modes.py` | `통과 100 / 전체 100` | 0 | 100 - 맞음(표·본문·증명 표 세 곳 모두 100) |

`tests/README.md` 의 세 자리(명령 표, "네 벌이 초록" 문장, 증명 표 마지막 줄)가 모두 `100` 으로 고쳐졌고 실제 수와 같다.
`browser_modes.py` 의 `scenario_hard_locked_after_play` 에는 잠금 시도 직후와 새로 고친 뒤 두 번 `localStorage['jamo.settings'].hardMode` 가 참이 아닌지 묻는 검사가 들어 있다(R29-N1 의 요구).

## 2 변이

모두 `web/js/ui.js` 의 `set-hard` change 처리기 잠금 분기(토스트 다음, `return` 앞)에 한 줄을 넣었다. 돌린 것은 사본의 `tests/browser_modes.py`.

| 번호 | 변이 | 잡은 곳 | 판정 |
|---|---|---|---|
| V19 | `settings.hardMode = !game.hardMode; saveSettings(settings);` | `T-304 잠금 시도 뒤 저장된 설정의 하드가 참이 아님`, `T-304 새로 고친 뒤에도 저장된 설정의 하드가 참이 아님`, `T-304 잠금 시도 뒤 빈 연습 판의 하드 체크박스가 꺼짐` (통과 97 / 전체 100) | 잡힘 |
| V20 | `settings.hardMode = true; saveSettings(settings);` (체크는 되돌린 채 참을 저장) | 위와 같은 3건 (97 / 100) | 잡힘 |
| V21 | `saveSettings({ ...settings, hardMode: true });` (메모리 설정은 그대로, 저장소만 오염) | 위와 같은 3건 (97 / 100) - 새 저장소 검사가 아니면 화면상 첫 체크(되돌림·토스트)는 통과하므로 새 검사가 실제로 일함 | 잡힘 |

## 3 R29-N2

- `python3 -c "...test_words.read_arrays()..."` → `배우다` ALLOWED 에 있음 `True`, ANSWERS 에는 없음 `False`, ANSWERS `380`, ALLOWED `2182`(중복 없음, R29 의 2181 + 1).
- `풀이씨.txt` 의 `git diff`(HEAD 대비 - R28·R29 미커밋분이 함께 보임): `-우다` 줄 `키우다` 다음에 `+배우다`. 같은 diff 의 다른 줄(`데리다 빠지다 따지다 싸우다 비추다 다투다 쪼개다 비싸다` 보탬, `채이다` 지움)은 T-305 몫으로 R29 검수 3절이 이미 본 것이다. 지움은 `채이다` 하나뿐이고 이는 R28-N3 의 의도된 지움 - 다른 낱말이 빠지지 않았다.
- `web/js/words.js` diff 는 2줄(ALLOWED 배열 한 줄 교체) - 낱말 목록 13건 OK 가 파일과 `words.js` 가 같음을 보장한다.

R29-N2: **닫힘**.

## 4 새 결함

| 번호 | 심각도 | 무엇 | 어디 | 재현 | 고칠 방향 |
|---|---|---|---|---|---|
| R30-N1 | 하 | 잠금 저장소 검사가 한 방향(하드 꺼진 판에서 켜기 시도)만 본다. 하드 **켜진** 판에서 끄기를 시도할 때 `settings.hardMode = false` 를 저장하는 변이는 이 시나리오로는 보이지 않는다(검사는 "참이 아님"만 보므로) | `tests/browser_modes.py:scenario_hard_locked_after_play` | 읽기로 확인 - 시나리오가 하드 꺼진 상태에서만 시작함 | 필요하면 하드 켠 판에서 줄을 낸 뒤 끄기를 시도하고 저장된 값이 `True` 로 남는지 보는 짝 시나리오. 목표 닫힘에는 영향 없음 |

'상'·'중' 없음.

## 5 판정

- R29-N1: **닫힘** - 네 벌 초록, README 수 일치, V19 와 새 변이 V20·V21 모두 저장소 검사로 잡힘.
- R29-N2: **닫힘** - `배우다` ALLOWED 에 있음, ANSWERS 380 그대로, 의도 밖 지움 없음.

판정: R29-N1·N2 닫음 - 네 벌 모두 초록(66·13·121·100, rc 0), V19 잡힘, 배우다 들어감, 새 결함은 '하' 1건뿐.
