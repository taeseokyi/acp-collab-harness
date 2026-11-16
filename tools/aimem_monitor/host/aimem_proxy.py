"""AIMEM 함대 모니터 - 윈도우 쪽 TCP 통과 프록시.

PC IP(0.0.0.0):18800 으로 들어온 연결을 127.0.0.1:18799 로 넘깁니다.
윈도우의 127.0.0.1:18799 는 WSL2 localhost 포워딩이 WSL 서버로 이어 주므로
WSL IP 가 재부팅마다 바뀌어도 이 프록시는 아무것도 몰라도 됩니다.
TLS 는 건드리지 않습니다(바이트만 통과) - 인증서·인증은 WSL 서버가 처리합니다.

**배포한 앱** (2026-11-16): 같은 폴더의 `ports.json` (`{"ports": [18810, ...]}`)에 적힌 공개 포트도 같이 듣습니다.
WSL 의 모니터가 배포를 켜고 끌 때 이 파일을 고쳐 쓰고(`tools/aimem_monitor/deploy.py`), 이 프록시는 몇 초마다 다시 읽어
포트를 열고 닫습니다 - 프로세스도 작업 스케줄러 항목도 하나 그대로입니다. 여기서 정하는 것은 **어느 포트를 여느냐뿐**입니다:
포트는 18810~18899 만 받고, 잇는 곳은 늘 127.0.0.1 의 `포트 + 100` 입니다(파일을 고칠 수 있어도 다른 포트·다른 곳은 못 엽니다).
앱 서버에는 PROXY 줄을 보내지 않습니다(모니터만 그 줄을 압니다).

표준 라이브러리만. 실행: pythonw.exe aimem_proxy.py [--listen 18800] [--target 18799] [--config ports.json]
로그: 같은 폴더 aimem_proxy.log (1MB 넘으면 .1 로 밀어냄)
"""
import argparse
import asyncio
import json
import logging
import logging.handlers
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
TARGET_HOST = "127.0.0.1"
APP_PORT_FIRST = 18810        # 배포 공개 포트 범위와 안쪽 포트 간격 - WSL 쪽 tools/aimem_monitor/deploy.py 와 같은 값
APP_PORT_COUNT = 90           # 18810~18899
APP_INNER_OFFSET = 100
CONFIG_POLL_SEC = 3


def setup_log():
    h = logging.handlers.RotatingFileHandler(HERE / "aimem_proxy.log", maxBytes=1_000_000,
                                             backupCount=1, encoding="utf-8")
    logging.basicConfig(level=logging.INFO, handlers=[h],
                        format="%(asctime)s %(levelname)s %(message)s")


async def pipe(reader, writer):
    try:
        while True:
            data = await reader.read(65536)
            if not data:
                break
            writer.write(data)
            await writer.drain()
    except (ConnectionError, asyncio.IncompleteReadError, OSError):
        pass
    finally:
        try:
            writer.close()
        except OSError:
            pass


async def handle(client_r, client_w, target_port, proxy_line=True):
    peer = client_w.get_extra_info("peername")
    try:
        up_r, up_w = await asyncio.wait_for(
            asyncio.open_connection(TARGET_HOST, target_port), timeout=5)
    except (OSError, asyncio.TimeoutError) as e:
        logging.warning("backend %s:%s 연결 실패 (%s) - %s 끊음", TARGET_HOST, target_port, e, peer)
        client_w.close()
        return
    logging.info("연결 %s -> %s:%s", peer, TARGET_HOST, target_port)
    # PROXY protocol v1 한 줄로 **진짜 접속자 주소**를 넘깁니다 (2026-11-11). 이 줄이 없으면 WSL 서버에는 모든 접속이
    # 127.0.0.1 로 보여 접속 기록과 주소별 제한이 한 바구니가 됩니다. 서버는 loopback 에서 온 이 줄만 믿습니다
    # (`tools/aimem_monitor/server.py` 의 `read_proxy_header`). 서버가 이 줄을 모르는 옛 판이면 TLS 가 깨지니
    # **서버를 먼저 올린 뒤** 이 프록시를 바꿉니다.
    if not proxy_line:
        await asyncio.gather(pipe(client_r, up_w), pipe(up_r, client_w))
        return
    try:
        ip, port = str(peer[0]), int(peer[1])
        fam = "TCP6" if ":" in ip else "TCP4"
        dst = "::1" if fam == "TCP6" else TARGET_HOST
        up_w.write(f"PROXY {fam} {ip} {dst} {port} {target_port}\r\n".encode("ascii"))
        await up_w.drain()
    except (TypeError, ValueError, IndexError, OSError) as e:
        logging.warning("PROXY 줄을 못 보냄 (%s) - 주소 없이 잇습니다", e)
    await asyncio.gather(pipe(client_r, up_w), pipe(up_r, client_w))


def read_ports(config, first=APP_PORT_FIRST):
    """`ports.json` 의 공개 포트 집합. 없거나 깨졌으면 None(= 지금 열어 둔 것을 그대로 둔다), 범위 밖 값은 버린다."""
    try:
        data = json.loads(config.read_text(encoding="utf-8"))
        ports = data["ports"]
        if not isinstance(ports, list):
            return None
    except FileNotFoundError:
        return set()
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return {p for p in ports if isinstance(p, int) and not isinstance(p, bool)
            and first <= p < first + APP_PORT_COUNT}


async def watch_apps(config, base_listen, first=APP_PORT_FIRST):
    """설정 파일을 몇 초마다 읽어 배포 포트를 열고 닫는다. 못 연 포트는 다음 바퀴에 다시 해 본다(같은 까닭은 한 번만 적는다)."""
    open_now, complained = {}, {}
    while True:
        want = read_ports(config, first)
        if want is not None:
            want.discard(base_listen)
            for port in sorted(set(open_now) - want):
                open_now.pop(port).close()            # 듣기만 닫는다 - 이어져 있던 연결은 끝날 때까지 간다
                logging.info("배포 포트 닫음 0.0.0.0:%s", port)
            for port in sorted(want - set(open_now)):
                target = port + APP_INNER_OFFSET
                try:
                    open_now[port] = await asyncio.start_server(
                        lambda r, w, t=target: handle(r, w, t, proxy_line=False), host="0.0.0.0", port=port)
                    complained.pop(port, None)
                    logging.info("배포 포트 듣는 중 0.0.0.0:%s -> %s:%s", port, TARGET_HOST, target)
                except OSError as e:
                    if complained.get(port) != str(e):
                        complained[port] = str(e)
                        logging.warning("배포 포트 %s 를 열지 못함 (%s) - 다시 해 봅니다", port, e)
        await asyncio.sleep(CONFIG_POLL_SEC)


async def main(listen_port, target_port, config, first=APP_PORT_FIRST):
    server = await asyncio.start_server(lambda r, w: handle(r, w, target_port),
                                        host="0.0.0.0", port=listen_port)
    logging.info("듣는 중 0.0.0.0:%s -> %s:%s (배포 설정 %s)", listen_port, TARGET_HOST, target_port, config)
    async with server:
        await asyncio.gather(server.serve_forever(), watch_apps(config, listen_port, first))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--listen", type=int, default=18800)
    ap.add_argument("--target", type=int, default=18799)
    ap.add_argument("--config", default=str(HERE / "ports.json"))
    ap.add_argument("--app-first", type=int, default=APP_PORT_FIRST, help="배포 포트 구간의 첫 포트 (검사용 - 운영은 기본값)")
    a = ap.parse_args()
    setup_log()
    try:
        asyncio.run(main(a.listen, a.target, pathlib.Path(a.config), a.app_first))
    except KeyboardInterrupt:
        pass
    except Exception as e:  # noqa: BLE001 - 창 없이 돌므로 로그에 남기고 종료
        logging.exception("프록시 종료: %s", e)
        sys.exit(1)
