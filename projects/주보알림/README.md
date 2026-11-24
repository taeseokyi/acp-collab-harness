# 주보알림

흑석동성당(bstsd.or.kr) 주보가 새로 올라왔는지 보고, 지금 쓰는 절차 그대로 카카오톡(태석님 본인)으로 보내는 웹 앱 - 시제품.
원래는 오픈클로 스킬 두 개(`church-bulletin-monitor`, `bulletin-pdf-downloader`)로 하던 일을 화면 하나로 옮긴 것이다.

## 화면 하나
- 최신 주보·보낸 주보·새것이 있는지
- 지금 확인 · 미리 보기(주보 그림) · 카톡 보내기
- 보낸 기록(언제, 어느 주보, 성공·실패와 까닭)

## 폴더
- `serve.py` - HTTP 서버 (`--host --port`, 기본 18831). 함대 모니터 프로젝트 탭의 '앱 열기'로도 뜬다(`app.json`)
- `bulletin.py` - 확인·미리 보기·전송·기록 논리
- `web/` - 화면
- `ref/` - 원본 스킬 사본(고치지 않음, 앱이 그대로 부름). `ref/README.md`
- `data/` - 실행 중 생기는 상태·기록·그림 (git 제외)

## 지키는 것
- 전송은 `ref/bulletin-pdf-downloader/scripts/pipeline.py` 를 그대로 부른다 - 받는 대화방·AutoHotkey 스크립트는 바꾸지 않는다.
  윈도우가 잠겼거나 카톡이 로그인돼 있지 않으면 실패하고, 그 실패를 화면에 그대로 보인다
- 오픈클로 쪽 파일은 읽기만(보낸 주보의 첫 기준선을 `church-bulletin-last.json` 에서 읽어 옴)
- 새 의존성 없음: 표준 라이브러리, `pdftoppm`, ref 스크립트가 쓰는 오픈클로 conda 파이썬

## 손으로 띄우기
```
python3 projects/주보알림/serve.py --port 18831
```
