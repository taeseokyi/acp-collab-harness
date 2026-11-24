#!/bin/sh
# R43 관리자: 쓰기 경로 소유와 슬롯 역할
set -e
cd /home/tsyi/work/ai-fleet
A="python3 tools/aimem_db.py"
$A ownership set --path projects/VoxLog/docs/RESEARCH-draft-owner.md --owner S2 --note R43
$A ownership set --path projects/VoxLog/voxlog/store.py --owner S3 --note R43
$A ownership set --path projects/VoxLog/tests/test_store.py --owner S3 --note R43
$A ownership set --path projects/VoxLog/tests/test_serve_ask_body.py --owner S3 --note R43
$A slot set --slot S2 --role "R43 VoxLog 조사 문서: 초안 주인 판정의 표준 방식 (무료, 웹 문서 읽기)"
$A slot set --slot S3 --role "R43 VoxLog 대기 큐 R42-N2·N3 수정 (무료)"
$A slot set --slot S4 --role "R43 적대적 검수: 조사 문서 근거 대조 + 큐 수정 (유료, 판단)"
$A slot set --slot S1 --role "R43 대기 (무료 중심 라운드)"
$A slot set --slot S5 --role "R43 대기 (무료 중심 라운드)"
$A slot set --slot S6 --role "R43 대기 (맡길 독립 일 없음)"
$A ownership list | grep R43
$A slot list
