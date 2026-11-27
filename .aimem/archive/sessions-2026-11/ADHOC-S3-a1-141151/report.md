DONE

1. `tools/fleet_rt/env.py`의 `session_key_name(root, provider)`는 세션이 `.env`에서 받을 **단 하나의** 변수 이름, 곧 그 공급자의 `env_key`를 돌려준다(없거나 꼴이 아니면 `None`). `SESSION_KEY_RE = \A[A-Z][A-Z0-9_]*_API_KEY\Z` 에 맞지 않는 이름은 거절한다 — 즉 `BASH_ENV`, `LD_PRELOAD`, `ANTHROPIC_BASE_URL` 처럼 실행을 바꾸는 변수는 `_API_KEY` 꼴이 아니므로 넘어가지 않는다. `root`나 `provider`가 없거나 `config.load`가 실패해도 `None`을 돌려준다.

2. `python3 -m unittest discover -s tests -p test_rt_config.py` 마지막 줄:
```
OK
```
(그 위: `Ran 21 tests in 3.099s`, 구분선 `-----`)

3. `tools/fleet_rt/config.py`의 `provider_of`는 claude 별칭(`opus`, `sonnet`, `haiku`, `fable`)을 **anthropic** 공급자로 보낸다. `claude-`, `anthropic/`, `claude-cli/` 접두 이름도 anthropic이다 (config.py:38-39, 84-86).

다음 담당자 참고: 읽기 전용 점검이었고 파일 생성/수정/삭제 없음. 쓰기 권한 경로는 확인만 하고 사용하지 않았다.