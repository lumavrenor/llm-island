#!/usr/bin/env bash
# llm-island. Args go to main.py (e.g. ./start.sh --headless / ./start.sh --stub)
# 前回終了時の世界（時刻・位置・HP・心・フリーズ・記憶）から続ける。新しく始めるなら先に ./reset.sh
# Git Bash (Windows) / Linux 共用。.venv の Python で起動する。
# .venv が無ければ作って requirements.txt を入れてから起動する（初回だけ）
cd "$(dirname "$0")" || exit 1

if [ -x .venv/Scripts/python.exe ]; then
  PY=.venv/Scripts/python.exe        # Windows の venv
elif [ -x .venv/bin/python ]; then
  PY=.venv/bin/python                # Linux / macOS の venv
else
  echo "[first-time setup] .venv not found. Creating it..." >&2

  BOOT=""
  # Windows の Store 用の偽 python3 は起動に失敗するので外れる。3.11 未満（tomllib が無い）も外す
  for cand in python3 python; do
    if command -v "$cand" >/dev/null 2>&1 &&
       "$cand" -c "import sys; sys.exit(sys.version_info < (3, 11))" >/dev/null 2>&1; then
      BOOT="$cand"
      break
    fi
  done
  if [ -z "$BOOT" ]; then
    echo "[error] No python / python3 command of version 3.11 or later found." >&2
    exit 1
  fi
  "$BOOT" -m venv .venv || exit 1

  if [ -x .venv/Scripts/python.exe ]; then
    PY=.venv/Scripts/python.exe
  else
    PY=.venv/bin/python
  fi

  echo "[first-time setup] Installing dependencies (pip install -r requirements.txt)..." >&2
  "$PY" -m pip install -q --upgrade pip || exit 1
  if ! "$PY" -m pip install -q -r requirements.txt; then
    echo "[error] pip install failed. Fix the error above, then delete .venv and run again." >&2
    exit 1
  fi
  echo "[first-time setup] Done." >&2
fi

exec "$PY" main.py "$@"
