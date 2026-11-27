SLOT=S4 엔진 v2 손 검사
확인토큰: 6cd650
AIMEM REV: 162
너는 S4 슬롯이다. 작업 폴더는 /home/tsyi/work/ai-fleet 다.
쓰기 없음(읽기 전용). 파일 생성/수정/삭제 금지.
금지: git commit / push / 삭제 / 의존성 설치. 보고는 응답 본문에 직접 쓴다.
보고 첫 줄은 상태(DONE / PARTIAL / BLOCKED / NEEDS-LOCK / NEEDS-APPROVAL), 이어서 한 일·고친 파일·실제로 돌린 검증 명령과 출력·다음 담당자가 알아야 할 것.
검증 명령은 승인 없이 실행되는 형태로 쓴다: `python3 ...`, `PYTHONPATH=tools python3 ...`, `pytest ...`, `ls/cat/grep/sed -n/wc/diff/git status/git diff/curl ...`. 셸 변수 대입이나 다른 접두사를 앞에 붙이면 승인 요구로 막힌다. py_compile 이 만드는 __pycache__ 는 쓰기로 치지 않는다.

읽기 전용 점검이다. ls tools 를 한 번 실행하고 보고 첫 줄에 DONE, 둘째 줄에 파일 개수를 적어라.
