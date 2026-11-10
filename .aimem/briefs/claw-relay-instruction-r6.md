태석님 지시 (클로드 코드 경유, 2026-11-10 09:20). 너는 전달자다. 판단하지 말고 아래를 그대로 수행하라.

1. 파일 /home/tsyi/work/opencode/.aimem/briefs/manager-round6-2026-11-10.md 를 읽어라. 그 전문이 관리자 브리프다.
2. 아래 호출을 정확히 한 번 실행하라. task 에는 1 의 파일 전문을 한 글자도 바꾸지 말고 넣어라. model 인자는 주지 말라(항목 기본값 opus[1m]).
   sessions_spawn(runtime: "acp", agentId: "claude", mode: "run", context: "isolated", label: "관리자 R6 (Opus) 2026-11-10", task: <파일 전문>)
3. 스폰 직후 돌아온 세션키(agent:claude:acp:...)를 첫 줄에 적어라.
4. 완료 통보가 올 때까지 기다려라. 관리자 6라운드는 30~60분 걸릴 수 있다. 중간에 sessions_send 로 재촉하거나 끼어들지 말라. 작업자(S1/S2/S3)를 네가 띄우지 말라.
5. 완료되면 sessions_history(sessionKey) 로 관리자의 마지막 응답 본문 전체를 읽어, 아래 형식으로 보고하라.

6. 보고를 마친 뒤, 그 관리자 세션이 done 이면 sessions.delete 로 거둬라(일회성 세션의 컨텍스트 정리). 상주(thread) 세션은 거두지 말라.

보고 형식(이 외 문장 금지):
관리자 세션키: <키>
스폰 시각: <KST HH:MM> / 완료 시각: <KST HH:MM>
--- 관리자 응답 원문 시작
<관리자 마지막 응답 본문 그대로>
--- 관리자 응답 원문 끝
