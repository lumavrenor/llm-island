"""
同時起動を防ぐロック

main.py と gen_personas.py は同じ world.db と log/ を使うので、2 つ同時に動くと
ログが混ざり、DB にも両方の実行が書き込んでしまう。起動時にロックを取り、取れなければ起動しない。
ロックは OS のファイルロックなので、プロセスが落ちても OS が外す（消し忘れのロックファイルで起動できなくなることはない）。
"""

import os
from pathlib import Path


def acquire(path: Path):
    """ロックを取る。取れたら開いたファイルを返す（プロセスが終わるまで持っておく）。ほかが持っていたら None"""
    path.parent.mkdir(parents=True, exist_ok=True)
    f = open(path, "a+")
    f.seek(0)
    try:
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        f.close()
        return None
    return f
