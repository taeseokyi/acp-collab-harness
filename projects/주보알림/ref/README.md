# ref/ - 원본 스킬 사본 (R45 관리자가 옮겨 둠, 2026-11-24)

원본: `~/.openclaw/workspace/skills/church-bulletin-monitor/`, `~/.openclaw/workspace/skills/bulletin-pdf-downloader/`.
원본은 고치지 않는다. 이 폴더도 **고치지 않는다** - 앱이 그대로 불러 쓴다(`scripts/` 아래 파일).

- `church-bulletin-monitor/scripts/check_bulletin.py` - 원본과 같음(표준 라이브러리만). 상태 파일은 `BULLETIN_STATE` 로 바꿀 수 있다
- `bulletin-pdf-downloader/scripts/download.py` - 원본과 같음. `requests`·`bs4`·`lxml`(maria 는 `scrapling` 이 있으면 씀)이 필요해
  오픈클로 conda 파이썬 `/home/tsyi/miniconda3/envs/openclaw/bin/python3` 으로 돌린다
- `bulletin-pdf-downloader/scripts/pipeline.py` - 원본과 같음. 받기(bstsd+maria) → pdftoppm → 윈도우 Pictures 비움·복사 →
  AutoHotkey `send_kakao.ahk` 로 카톡 전송. `--skip-send` 면 전송만 뺀다(그래도 Pictures 는 비우고 채운다)
- `*/SKILL.md` - 원본 설명서 요지는 원본 폴더에 있다. 여기에는 두지 않았다(위 설명과 스크립트 머리 주석으로 충분)

원본 상태 파일 `~/.openclaw/workspace/memory/church-bulletin-last.json` 은 오픈클로 크론이 쓴다. 앱은 그것을 **쓰지 않는다**
(앱 자기 상태는 `projects/주보알림/data/`). R45 시작 때 그 파일의 값: 최신 2026-11-22, 직전 알림 2026-11-22.
