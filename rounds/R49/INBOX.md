# R49 사람이 관리자에게 남긴 말

관리자는 읽고 판단합니다. 요청보다 이 말이 앞섭니다(같은 요청 안에서).

## 2026-11-25T13:45:14 · 태석(클로드 코드)

[태석님 지시 · R49 범위 보탬] 자동 태그는 claude 명령이 아니라 KISTI 의 kistillm 을 씁니다. 지금 구현은 자동 태그도 묻기와 같은 ask.run_llm(claude -p)을 타는데, 이를 바꿉니다. (1) 자동 태그 전용 호출: OpenAI 호환 POST <URL>/chat/completions, 표준 라이브러리(urllib)만. 설정 이름은 STT 와 같은 방식으로 settings.json·환경변수 VOXLOG_TAG_LLM_URL(예: https://aida.kisti.re.kr:10430/v1) · VOXLOG_TAG_LLM_MODEL(kistillm) · VOXLOG_TAG_LLM_API_KEY. (2) 이 설정이 없으면 자동 태그는 '쓸 수 없음'으로 두고(지금의 LLM 없음 경로와 같게) claude 로 넘어가지 않습니다. 묻기(답하기)는 그대로 claude 명령입니다. (3) kistillm 은 동시에 1건만 받으니 자동 태그는 한 번에 하나씩, 응답이 늦어도 사용자 묻기를 막지 않게. 추론 모델이라 답에 생각 글이 섞일 수 있으니 tags.py 의 뽑기가 견디는지 실제 응답으로 확인. (4) 실제 주소와 키는 settings.json(git 제외)에만 두고 settings.example.json·문서·시험에는 예시 주소만. 실제 settings.json 에는 클로드 코드가 세 값을 넣어 둡니다(작업자는 이 파일을 고치지 않음). (5) 시험은 가짜 서버로, 문서(INTERFACE·README·설계 문서 F2 절)도 맞춥니다. 검수(T-441)는 이 변경까지 포함해 봅니다.

## 2026-11-25T13:46:37 · 태석(클로드 코드)

[태석님 지시 · 바로 앞 말 철회] 자동 태그를 kistillm 으로 바꾸라는 앞의 말(VOXLOG_TAG_LLM_* 설정, OpenAI 호환 호출)은 철회합니다. 자동 태그는 지금 구현대로 기존 묻기 방식(ask.run_llm, claude 명령)을 그대로 씁니다. 그 말 때문에 이미 고친 코드·문서·시험·새 노드가 있으면 원래대로 되돌리고, 아직 손대지 않았으면 그대로 마무리(T-439 → T-441)하면 됩니다. 되돌린 것이 있으면 보고에 한 줄.

