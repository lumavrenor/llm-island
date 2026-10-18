"""
小さなステートマシン

    sm = StateMachine("idle")
    match sm.update():       # 毎フレーム 1 回呼ぶ。今のステート名を返す
        case "idle":
            if sm.entered:   # 切り替わった最初のフレームだけ True
                ...
            if sm.elapsed > 3.0:   # このステートに入ってからの秒数（実時計）
                sm.change("walk")  # 次の update() から切り替わる
"""

import time


class StateMachine:
    def __init__(self, initial: str | None = None):
        self.current: str | None = None
        self.entered = False
        self._next = initial
        self._since = time.perf_counter()

    def change(self, name: str):
        self._next = name

    def update(self) -> str | None:
        self.entered = self._next is not None
        if self.entered:
            self.current, self._next = self._next, None
            self._since = time.perf_counter()
        return self.current

    @property
    def elapsed(self) -> float:
        return time.perf_counter() - self._since
