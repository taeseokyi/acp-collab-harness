SLOT=S3 T-265 browser_monitor_ui.py: 고정 자료가 아직 진짜 저장소를 읽는다 (검수 N1·N2·M11) (G-052)
확인토큰: 5b8c1e
AIMEM REV: 164
너는 S3 슬롯이다. 작업 폴더는 /home/tsyi/work/ai-fleet 다.
쓰기는 다음 경로에만 한다: tests/browser_monitor_ui.py
금지: git commit / push / 삭제 / 의존성 설치. 보고는 응답 본문에 직접 쓴다.
보고 첫 줄은 상태(DONE / PARTIAL / BLOCKED / NEEDS-LOCK / NEEDS-APPROVAL), 이어서 한 일·고친 파일·실제로 돌린 검증 명령과 출력·다음 담당자가 알아야 할 것.
검증 명령은 승인 없이 실행되는 형태로 쓴다: `python3 ...`, `PYTHONPATH=tools python3 ...`, `pytest ...`, `ls/cat/grep/sed -n/wc/diff/git status/git diff/curl ...`. 셸 변수 대입이나 다른 접두사를 앞에 붙이면 승인 요구로 막힌다. py_compile 이 만드는 __pycache__ 는 쓰기로 치지 않는다.

# T-265 `browser_monitor_ui.py`: **아직 남은** 저장소 의존 (검수 N1 높음 · N2 높음 · M11)

쓸 파일은 **하나**입니다: `tests/browser_monitor_ui.py` (지금 **27건 전부 통과**).
**다른 `tests/**` 와 `tools/**` 는 읽기만 하고 절대 고치지 마십시오.** 바로 고치십시오.

지난 노드가 시나리오 넷을 임시 저장소로 옮겼지만 적대적 검수가 **두 군데가 여전히 진짜
저장소를 읽는다**고 실측했습니다. 이 노드가 그것을 닫습니다.

## N1 (높음) - `write_fixed_project` 가 진짜 `projects/웹워들` 을 복사합니다

`:415` 근처:

```python
src = ROOT / "projects" / "웹워들"
shutil.copytree(src, dst)
```

검수 실측: 사본의 `projects/` 를 비우면 `FileNotFoundError` 로 **검사 전체가 무너집니다**
(`통과 3 / 전체 4`). 웹워들이 다른 라운드에 바뀌거나 사라지면 이 검사가 깨집니다.

**고칠 것:** 시험이 **스스로 만드는 최소 프로젝트**로 바꾸십시오. 진짜 `projects/` 를
읽지 마십시오.

- `root/projects/<이름>/app.json` - 지금 웹워들의 `app.json` 을 **읽어 꼴만 본보기로 삼아**
  같은 꼴을 시험 안에 **글자로** 쓰십시오 (복사하지 말고 손으로 쓴 최소값)
- `root/projects/<이름>/web/index.html` - `#board` 안에 `.tile` **30개**를 가진 최소 HTML.
  `scenario` 의 `"안쪽 보드가 진짜로 그려졌다"` 가 타일 30개를 셉니다. 자바스크립트 없이
  HTML 에 타일 30칸을 그대로 써 넣으면 됩니다
- `narrow_scenario`·`short_scenario` 는 미리보기 칸의 **높이**만 보므로 같은 자료로 됩니다
- 프로젝트 **둘**을 만드십시오 - 하나는 **진행 중**, 하나는 **끝남**.
  그래야 `'전체'` 칩이 **반드시** 나타납니다 (아래 M11)

## N2 (높음) - `changed_ui_scenario` 가 아직 진짜 저장소로 돕니다

`main()` 의 첫 `with monitor_server() as base:` 에 남아 있습니다. 검수 실측: 사본의
`.aimem/aimem.db` 를 치우면 `'생략된 제목을 눌러 펼칠 수 있다'` 가 빨개집니다(26/27).
`'이번 라운드'` 검사가 읽는 값도 진짜 DB 의 것입니다.

**고칠 것:** `changed_ui_scenario` 도 `temporary_aimem_root(temp_root)` +
`monitor_server(root=temp_root)` 블록으로 옮기십시오. **`main()` 에 `monitor_server()` 를
`root` 없이 부르는 자리가 하나도 남으면 안 됩니다.**
그 시나리오가 보는 값(`.meta-goal`·`'이번 라운드'`·긴 제목)이 고정 자료에서 나오도록
`write_fixed_*` 에 필요한 것을 보태십시오 - **단언을 느슨하게 바꾸지 말고 자료를 맞추십시오.**

## M11 (낮음) - `'전체'` 칩 누르기가 "있으면 누르기" 로 느슨해졌습니다

`:83` 근처. 칩이 버그로 사라져도 조용히 통과합니다.
N1 에서 **진행 중 프로젝트**를 넣었으니 칩은 반드시 있습니다 - **무조건 누르게** 되돌리고,
칩이 없으면 그 검사가 **빨개지게** 하십시오.

## 지켜야 할 것

- **검사 27건이 전부 그대로 있어야 하고 전부 통과해야 합니다.** 지우거나 느슨하게 바꾸지 마십시오
- 검사는 그려진 것을 묻습니다 - `is_visible()`·`getComputedStyle`·`bounding_box()`
- 제품(`tools/**`)이 틀려 빨개지면 고치지 말고 보고 첫 줄을 `NEEDS-FIX: <무엇이 어디서>` 로

## 검증

검증 명령이 봅니다: (1) `main()` 소스에 `root` 없는 `monitor_server()` 호출이 **없고**
`write_fixed_project` 가 `ROOT` 를 **읽지 않으며**, (2) `projects/` 와 `.aimem` 을 통째로
치운 저장소 사본에서도 `python3 tests/browser_monitor_ui.py` 가 **통과 27 / 전체 27** 인 것.

[재시도 2/2] 직전 시도(run T-265-S3-a1-193012) 는 rc=1 / 검증 rc=-1 로 실패했다. 산출물이 남아 있을 수 있으니 먼저 확인하고 이어서 하라. 직전 검증 출력 꼬리:
실행 rc != 0

직전 작업자의 보고(참고만 하라 - 틀렸을 수 있으니 그대로 믿지 말고 직접 확인하라):
(최종 보고문 없음 - 작업자가 보고 전에 끝남. stderr 꼬리:)
Error: Provider response headers timed out after 300000ms
