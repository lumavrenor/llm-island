"""
ふきだし

- ワールド空間のビルボード Text。決まった数をプールして使い回す（毎回作って壊さない）
- 全文で背景の大きさを決めてから、1 文字ずつ表示する
- 数秒でフェードアウト
- 画面外の会話は LogPanel（画面右）に流す
"""

from __future__ import annotations

from ursina import Entity, Text, Vec2, Vec3, camera, color, window

import lang
from lang import t

WRAP = 14          # 1 行の文字数（日本語。英語は単語の切れ目で、この 2 倍まで。lang.wrap）
REVEAL_CPS = 18.0  # 1 秒に表示する文字数
FADE_SEC = 1.0

STYLES = {
    #          文字色                          背景色                         大きさ
    "say":    (color.rgb(0.08, 0.08, 0.1),    color.rgba(1, 1, 1, 0.9),      20),
    "rescue": (color.rgb(0.05, 0.2, 0.08),    color.rgba(0.75, 1, 0.75, 0.95), 22),  # ヒーラーが癒すときのひとこと
    "inner":  (color.rgba(0.85, 0.9, 1, 0.9), color.rgba(0.1, 0.15, 0.3, 0.55), 15),
    "raider": (color.rgb(1, 0.3, 0.25),       color.rgba(0.03, 0.0, 0.05, 0.9), 22),   # 悪のひとこと
}


class Bubble:
    def __init__(self):
        self.pivot = Entity(billboard=True, enabled=False)
        self.text = Text(parent=self.pivot, text=" ", origin=(-0.5, 0.5))
        self.npc_id: int | None = None
        self.full = ""
        self.age = 0.0
        self.life = 0.0
        self.shown = -1
        self.fg = color.black
        self.bg = color.white

    def show(self, npc_id: int, text: str, style: str, life: float):
        fg, bg, size = STYLES[style]
        self.npc_id, self.full, self.age, self.life, self.shown = npc_id, lang.wrap(text, WRAP), 0.0, life, -1
        self.fg, self.bg = fg, bg
        self.text.scale = size
        self.text.color = fg
        self.text.text = self.full                      # 全文で大きさを測って背景を作り…
        self.text.create_background(padding=0.6 * Text.size, radius=0.3, color=bg)
        w, h = self.text.width * size, self.text.height * size
        self.text.position = Vec3(-w / 2, h + 0.3, 0)   # ふきだしの下端を頭の上に合わせる
        self.text.text = ""                             # …文字は 1 文字ずつ出す
        self.pivot.enabled = True

    def hide(self):
        self.pivot.enabled = False
        self.npc_id = None

    def update(self, dt: float, anchor: Vec3):
        self.age += dt
        if self.age >= self.life:
            self.hide()
            return
        self.pivot.position = anchor
        n = min(len(self.full), int(self.age * REVEAL_CPS) + 1)
        if n != self.shown:
            self.shown = n
            self.text.text = self.full[:n]
        left = self.life - self.age
        if left < FADE_SEC:
            a = left / FADE_SEC
            self.text.color = color.rgba(self.fg.r, self.fg.g, self.fg.b, self.fg.a * a)
            self.text.background.color = color.rgba(self.bg.r, self.bg.g, self.bg.b, self.bg.a * a)


class BubblePool:
    def __init__(self, size: int = 40):
        self.bubbles = [Bubble() for _ in range(size)]

    def show(self, npc_id: int, text: str, style: str, life: float):
        # 同じ NPC のふきだしがあれば置き換え、なければ空き → いちばん古いもの
        b = next((b for b in self.bubbles if b.npc_id == npc_id), None) \
            or next((b for b in self.bubbles if b.npc_id is None), None) \
            or max(self.bubbles, key=lambda b: b.age)
        b.show(npc_id, text, style, life)

    def update(self, dt: float, anchors: dict[int, Vec3]):
        for b in self.bubbles:
            if b.npc_id is not None:
                b.update(dt, anchors[b.npc_id])


class LogPanel:
    """画面外の会話を流す（画面右上）"""

    def __init__(self, lines: int = 16):
        self.lines: list[str] = []
        self.max_lines = lines
        self.text = Text(parent=camera.ui, text="", origin=(0.5, 0.5), scale=0.72,
                         position=window.top_right + Vec2(-0.02, -0.02), color=color.rgba(1, 1, 1, 0.85))
        self.dirty = False

    def add(self, line: str):
        self.lines.append(lang.fit(line, 34))
        self.lines = self.lines[-self.max_lines:]
        self.dirty = True

    def update(self):
        if self.dirty:
            self.text.text = t("log.title") + "\n" + "\n".join(self.lines)
            self.dirty = False
