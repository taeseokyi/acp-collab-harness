"""R45 관리자: 주보알림이 쓸 실행 환경 확인 (읽기만)."""
import importlib.util
import os
import sys

print("python", sys.executable, sys.version.split()[0])
for m in ("requests", "bs4", "lxml", "scrapling"):
    print(m, bool(importlib.util.find_spec(m)))
for p in ("/home/tsyi/miniconda3/envs/openclaw/bin/python3",
          "/mnt/c/Program Files/AutoHotkey/v2/AutoHotkey64.exe",
          "/mnt/c/Users/이태석/Documents/send_kakao.ahk",
          "/mnt/c/Users/이태석/Pictures"):
    print(p, os.path.exists(p))
