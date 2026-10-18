#!/usr/bin/env bash
# データの削除。次の ./start.sh は新しい世界で始まる
#   ./reset.sh         記憶と世界の状態（時刻・位置・HP・心・フリーズ）を消す。住人の性格は残す
#   ./reset.sh --all   world.db ごと消す（次の ./start.sh で住人の性格から作り直す）
cd "$(dirname "$0")" || exit 1

if [ -x .venv/Scripts/python.exe ]; then
  PY=.venv/Scripts/python.exe        # Windows の venv
elif [ -x .venv/bin/python ]; then
  PY=.venv/bin/python                # Linux / macOS の venv
elif python3 -c "" >/dev/null 2>&1; then   # Windows の Store 用の偽 python3 は起動に失敗するので外れる
  PY=python3
else
  PY=python
fi

exec "$PY" tools/reset.py "$@"
