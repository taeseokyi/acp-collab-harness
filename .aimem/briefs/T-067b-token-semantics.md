# T-067 (2차, 좁은 범위) 토큰 파일 의미 하나를 구현에 맞춘다

네가 1차에서 쓴 `tests/test_aimem_monitor_auth.py` 는 **55건 중 54건이 통과했고, 그중 한 건은
관리자 코드의 실제 결함을 잡아냈다** - `POST /api/requests` 의 Origin 검사가 들여쓰기 때문에
**Origin 헤더가 있으면 무조건 403** 이었다(`test_post_requests_guards`). 관리자가 고쳤고 지금
전체 161건 중 160건이 통과한다. 고맙다.

남은 1건은 **계약 불일치**다. 네 테스트가 아니라 관리자가 의미를 바꾼 쪽이다.

## 무엇

`test_malformed_existing_file_is_replaced_not_trusted` (61행 근처) 는 꼴이 깨진 토큰 파일
(`"short\n"`)이 있으면 `ensure_access_token()` 이 **새 토큰으로 바꿔 쓴다**고 단언한다.

**관리자가 그 동작을 바꿨다.** 이제 `SystemExit` 로 멈추고 사람에게 알린다
(`tools/aimem_monitor/server.py` 의 `ensure_access_token`, "접근 토큰 파일이 있는데 꼴이 아닙니다").

**왜 바꿨나:** 사람이 손으로 적어 둔 토큰이 한 글자 틀렸을 때 말없이 새 토큰을 만들면,
그 사람은 접속이 막힌 이유를 알 수 없다. 보안 문(門)은 **닫힌 채로 실패하고 사람을 부르는** 쪽이
맞다. 또 S4 적대적 검수 9번이 "말없이 덮어쓰고 새 토큰을 stderr 에 찍는다"를 위험으로 지목했다.

## 할 일 (이것만)

1. 그 테스트를 **구현에 맞게** 바꿔라 - `assertRaises(SystemExit)` 로, 그리고 **기존 파일 내용이
   그대로 남아 있는지**(덮어쓰지 않았는지)까지 단언해라
2. 같은 자리에 하나 더: **정상 꼴 토큰 파일이 있으면** 그대로 읽고 `created=False` 인지
   (이미 있으면 그 케이스는 그대로 두어도 된다)
3. `O_NOFOLLOW` 가 들어갔으니, 토큰 자리에 **심볼릭 링크**를 놓으면 `ensure_access_token` 이
   `SystemExit` 또는 `OSError` 로 막히는지 한 건 더해라(실제 동작을 보고 맞춰라 -
   지금 구현은 `path.exists()` 가 링크를 따라가므로 어느 쪽으로 떨어지는지 직접 확인할 것)

**쓰기 경로: `tests/test_aimem_monitor_auth.py` 하나.** `tools/` 는 읽기만.

## 검증

```bash
python3 -m unittest discover -s tests 2>&1 | grep -E "^Ran|^OK|^FAILED"
python3 -m unittest discover -s tests -p "test_aimem_monitor_auth.py" 2>&1 | tail -3
ls -l .aimem/tls/access-token   # 실물 토큰을 건드리지 않았는지 (수정 시각 그대로)
```

전체가 **OK** 여야 한다(지금은 `FAILED (errors=1)`).

## 보고

첫 줄 상태. 바꾼 테스트 이름, 더한 테스트 이름, 위 명령의 출력 그대로.
