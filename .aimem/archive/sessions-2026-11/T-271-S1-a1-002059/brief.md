SLOT=S1 T-271 재검수: R22-R1·R2 가 닫혔는가 (전체 discover·변이 V08·V21·W01) (G-054)
확인토큰: a41f0c
AIMEM REV: 164
너는 S1 슬롯이다. 작업 폴더는 /home/tsyi/work/ai-fleet 다.
쓰기는 다음 경로에만 한다: rounds/R22/REVIEW-r22-3.md
금지: git commit / push / 삭제 / 의존성 설치. 보고는 응답 본문에 직접 쓴다.
보고 첫 줄은 상태(DONE / PARTIAL / BLOCKED / NEEDS-LOCK / NEEDS-APPROVAL), 이어서 한 일·고친 파일·실제로 돌린 검증 명령과 출력·다음 담당자가 알아야 할 것.
검증 명령은 승인 없이 실행되는 형태로 쓴다: `python3 ...`, `PYTHONPATH=tools python3 ...`, `pytest ...`, `ls/cat/grep/sed -n/wc/diff/git status/git diff/curl ...`. 셸 변수 대입이나 다른 접두사를 앞에 붙이면 승인 요구로 막힌다. py_compile 이 만드는 __pycache__ 는 쓰기로 치지 않는다.

# T-271 **재검수** - R22 2차 재검수의 R1·R2 가 닫혔는가

쓸 파일은 **하나**입니다: `rounds/R22/REVIEW-r22-3.md` (새 파일). 저장소의 다른 파일은 고치지 마십시오. 변이는 저장소 사본에만.
먼저 `rounds/R22/REVIEW-r22-2.md` (당신이 쓴 보고서)의 R1·R2 행과 변이표를 읽으십시오. 고친 곳은 `tests/test_fleet_graph.py` 하나입니다(T-270): Q2 시험이 `fleet_rt.harness.get` 을 claude 어댑터로 패치, Q1 시험이 디딤 폴더를 실제로 만듦.

## 방법

1. 저장소를 `/tmp` 로 복사(`.aimem/tls/` 제외, `.git`·`.aimem/runs`·`__pycache__` 도 빼도 됨). 끝나면 그 `/tmp` 폴더를 `rm -rf`
2. 사본에서 **전체** `python3 -m unittest discover -s tests` 가 초록인지
3. **전체 discover 아래에서** 변이 V08(`_RUN_ID_RE` 몸에 `/` 허용)·V21(세션 갈래 끄기)·W01(어댑터 끝 `return None`→`False`) 이 빨개지는지. 모듈 단독 실행이 아니라 전체 discover(또는 `_fleet_env` 를 먼저 들인 상태)로 재십시오
4. 패치가 fake 안전 장치를 풀어 진짜 하네스가 뜰 길이 생기지 않았는지(패치 범위가 시험 안으로 한정되는지)

## 보고서

1. 닫힘표 `| 번호 | 닫혔나 | 근거 |` 2. 새 결함표(없으면 "없음") 3. 변이표, 마지막 줄 `합계 <n>개: 잡힘 <a>, 생존 <b>` 4. 한 문단 총평

## 하지 말 것

제품·시험 고치기, `git commit`/`push`, 저장소 파일 삭제, 운영 모니터 부르기.
