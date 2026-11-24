#!/bin/sh
# R42 관리자: 쓰기 경로 소유와 슬롯 역할
set -e
cd /home/tsyi/work/ai-fleet
A="python3 tools/aimem_db.py"
$A ownership set --path projects/VoxLog/web/app.js --owner S6 --note R42
$A ownership set --path projects/VoxLog/web/queue.js --owner S6 --note R42
$A ownership set --path projects/VoxLog/web/sw.js --owner S6 --note R42
$A ownership set --path projects/VoxLog/tests/browser_voxlog.py --owner S6 --note R42
$A ownership set --path projects/VoxLog/voxlog/stt.py --owner S6 --note R42
$A ownership set --path projects/VoxLog/serve.py --owner S6 --note R42
$A ownership set --path projects/VoxLog/tests/test_stt.py --owner S6 --note R42
$A ownership set --path projects/VoxLog/tests/test_serve_ask_body.py --owner S6 --note R42
$A ownership set --path projects/VoxLog/tests/test_store.py --owner S6 --note R42
$A ownership set --path projects/VoxLog/tests/test_serve.py --owner S6 --note R42
$A ownership set --path projects/VoxLog/tests/test_ask.py --owner S6 --note R42
$A ownership set --path projects/VoxLog/docs/INTERFACE.md --owner S6 --note R42
$A ownership set --path projects/자모맞히기/tests/README.md --owner S6 --note R42
$A slot set --slot S6 --role "R42 VoxLog 큐 4건·자모맞히기 문서 1건 (종류별 기본 1차 지시 첫 실물 시험)"
$A slot set --slot S3 --role "R42 VoxLog 적대적 검수 (/tmp 사본 변이 시험 - R41-P1 확인)"
$A slot set --slot S2 --role "R42 검수 결함 수정 (무료)"
$A slot set --slot S1 --role "R42 대기 (무료 중심 라운드)"
$A slot set --slot S4 --role "R42 대기 (무료 중심 라운드)"
$A slot set --slot S5 --role "R42 대기 (무료 중심 라운드)"
$A ownership list | grep R42
$A slot list
