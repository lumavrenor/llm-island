"""
データの削除（次の start.sh を新しい世界で始める）

    python tools/reset.py          # 記憶（出来事・会話・関係・噂）と世界の状態（時刻・位置・HP・心・フリーズ）を消す。住人の性格は残す
    python tools/reset.py --all    # world.db ごと消す（住人の性格も消える。次の起動で作り直す）

消すのは [locale] lang の DB（[world] db_file。英語は world_en.db）。

main.py が動いている間は消さない（同じ world.db を使っているため）。
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # python tools/reset.py で起動しても core/・lang/ などを import できるように

from core import run_lock
from core.config import ROOT, load_config
from memory.db import DB


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="world.db ごと消す（住人の性格も消える）")
    ap.add_argument("--db", default=None, help="既定は config.toml の [world] db_file")
    ap.add_argument("--config", default=str(ROOT / "config.toml"))
    args = ap.parse_args()

    cfg = load_config(args.config)
    args.db = args.db or str(ROOT / cfg.world.db_file)
    lock = run_lock.acquire(ROOT / cfg.log.dir / "running.lock")
    if lock is None:
        print("main.py か gen_personas.py が動いています。終わってから実行してください", file=sys.stderr)
        return 1

    if args.all:
        for suffix in ("", "-wal", "-shm"):
            path = Path(args.db + suffix)
            if path.exists():
                path.unlink()
                print(f"{path} を消しました")
        print("次の起動で住人の性格から作り直します（LLM で 100 体分）")
    else:
        db = DB(args.db)
        db.clear_memory()
        db.close()
        print(f"{args.db} の記憶と世界の状態を消しました（住人の性格は残っています）。次の起動は新しい世界で始まります")


if __name__ == "__main__":
    sys.exit(main())
