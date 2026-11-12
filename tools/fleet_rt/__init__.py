"""함대 런타임: 하네스 어댑터 + 세션 감독 (설계 `docs/FLEET-ENGINE-V2.md` 3절).

    base.py         규약 (SessionSpec · Command · Event · Harness) - 여기부터 읽는다
    harness/        어댑터: claude · codex · opencode · fake
    sessions.py     세션 띄우기·상태·끊기·고아 청소
    run.py          세션마다 하나 뜨는 감독 프로세스 (`python3 -m fleet_rt.run <세션 폴더>`)
    config.py       fleet.toml 읽기
    providers.py    공급자 동시성·응답 점검

`tools/fleet.py`(CLI·겉면)가 이 패키지를 부른다. 패키지 이름이 `fleet` 이 아닌 까닭: `tools/fleet/`
폴더는 `tools/fleet.py` 를 가려 `import fleet` 을 전부 바꿔 버린다.
"""
