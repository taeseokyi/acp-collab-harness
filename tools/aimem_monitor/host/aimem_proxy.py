"""AIMEM 함대 모니터 - 윈도우 쪽 TCP 통과 프록시.

PC IP(0.0.0.0):18800 으로 들어온 연결을 127.0.0.1:18799 로 넘깁니다.
윈도우의 127.0.0.1:18799 는 WSL2 localhost 포워딩이 WSL 서버로 이어 주므로
WSL IP 가 재부팅마다 바뀌어도 이 프록시는 아무것도 몰라도 됩니다.
TLS 는 건드리지 않습니다(바이트만 통과) - 인증서·인증은 WSL 서버가 처리합니다.

표준 라이브러리만. 실행: pythonw.exe aimem_proxy.py [--listen 18800] [--target 18799]
로그: 같은 폴더 aimem_proxy.log (1MB 넘으면 .1 로 밀어냄)
"""
import argparse
import asyncio
import logging
import logging.handlers
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
TARGET_HOST = "127.0.0.1"


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


async def handle(client_r, client_w, target_port):
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
    try:
        ip, port = str(peer[0]), int(peer[1])
        fam = "TCP6" if ":" in ip else "TCP4"
        dst = "::1" if fam == "TCP6" else TARGET_HOST
        up_w.write(f"PROXY {fam} {ip} {dst} {port} {target_port}\r\n".encode("ascii"))
        await up_w.drain()
    except (TypeError, ValueError, IndexError, OSError) as e:
        logging.warning("PROXY 줄을 못 보냄 (%s) - 주소 없이 잇습니다", e)
    await asyncio.gather(pipe(client_r, up_w), pipe(up_r, client_w))


async def main(listen_port, target_port):
    server = await asyncio.start_server(lambda r, w: handle(r, w, target_port),
                                        host="0.0.0.0", port=listen_port)
    logging.info("듣는 중 0.0.0.0:%s -> %s:%s", listen_port, TARGET_HOST, target_port)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--listen", type=int, default=18800)
    ap.add_argument("--target", type=int, default=18799)
    a = ap.parse_args()
    setup_log()
    try:
        asyncio.run(main(a.listen, a.target))
    except KeyboardInterrupt:
        pass
    except Exception as e:  # noqa: BLE001 - 창 없이 돌므로 로그에 남기고 종료
        logging.exception("프록시 종료: %s", e)
        sys.exit(1)
