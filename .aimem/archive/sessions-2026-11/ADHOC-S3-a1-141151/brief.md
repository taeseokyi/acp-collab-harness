SLOT=S3 무료 딥시크 확인 (읽기 전용)
확인토큰: 5b8c1e
AIMEM REV: 169
너는 S3 슬롯이다. 작업 폴더는 /home/tsyi/work/ai-fleet 다.
쓰기 없음(읽기 전용). 파일 생성/수정/삭제 금지.
금지: git commit / push / 삭제 / 의존성 설치. 보고는 응답 본문에 직접 쓴다.
보고 첫 줄은 상태(DONE / PARTIAL / BLOCKED / NEEDS-LOCK / NEEDS-APPROVAL), 이어서 한 일·고친 파일·실제로 돌린 검증 명령과 출력·다음 담당자가 알아야 할 것.

읽기 전용 점검이다. 파일을 고치지 마라.
1. tools/fleet_rt/env.py 를 읽고 함수 session_key_name 이 무엇을 돌려주는지, 어떤 이름을 거절하는지 한두 문장으로 설명하라.
2. 다음 명령을 실행하고 마지막 줄을 그대로 옮겨라: python3 -m unittest discover -s tests -p test_rt_config.py
3. tools/fleet_rt/config.py 에서 provider_of 가 claude 별칭(opus 등)을 어느 공급자로 보내는지 적어라.
보고 첫 줄은 DONE, 이어서 1~3 의 답.
