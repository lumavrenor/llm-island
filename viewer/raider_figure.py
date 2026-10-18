"""
悪の魔物の見た目（sim/raid.py の Raider を毎フレーム直接読んで描く）

住人（poly_character.py のクレイ風キャラ）とは別の形にする:
- 黒い多面体の胴と頭（分割を粗くして角ばらせる）、吊り上がった赤く光る目、胸の赤いコア
- 紫がかった角・肩と背中のトゲ、長い腕の先に爪。脚はなく、先細りの影の尾で浮いている
- 大きさは住人（[look] scale）の [raider] size_ratio 倍

演出（Raider のフィールドとステートを見るだけ。こちらから世界は書き換えない）:
    appear   … 地面からせり上がる
    hunt     … 浮いて揺れる。獲物に爪が届いている間は両腕を前に構え、一撃ごとに振り抜く
    defeated … 傾いて沈み、暗くなる
    戦士の攻撃が当たったら一瞬白く光る（flash()。app.py の AttackFx から呼ぶ）
    反撃の弾を撃つときは胸のコアが一瞬ふくらむ（flash_core()）
"""

from __future__ import annotations

import math
import time

from ursina import Circle, Entity, Text, Vec3, color
from ursina.shaders import lit_with_shadows_shader

from viewer.camera import smooth
from viewer.poly_character import _low_poly_sphere_mesh, _tube_mesh

BODY = color.rgb(0.07, 0.06, 0.09)
SPIKE = color.rgb(0.22, 0.07, 0.27)
GLOW = color.rgb(1.0, 0.13, 0.08)
HEIGHT = 2.2     # scale 1 のときの身長（住人と同じ。角の先まではもう少し高い）
BAR_W = 1.6      # HP バーの幅


class RaiderModel(Entity):
    """悪の魔物の形。正面は -Z（住人の Character と同じ向き）"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        shd = lit_with_shadows_shader

        def solid(parent, model, col, **kw):
            return Entity(parent=parent, model=model, color=col, shader=shd, **kw)

        def glow(parent, model, **kw):
            return Entity(parent=parent, model=model, color=GLOW, unlit=True, **kw)

        # 尾（脚の代わり）。下ほど細い
        solid(self, _tube_mesh(0.04, 0.5, 0.9, segments=7), BODY, y=0.2)
        # 胴と胸のコア
        solid(self, _low_poly_sphere_mesh(4, 6), BODY, scale=(0.66, 0.62, 0.5), y=1.3)
        self.core = glow(self, _low_poly_sphere_mesh(3, 5), scale=0.13, y=1.38, z=-0.45)

        # 頭・目・口・角
        self.head = Entity(parent=self, y=2.0)
        solid(self.head, _low_poly_sphere_mesh(4, 6), BODY, scale=(0.44, 0.4, 0.42))
        # 目は内側を下げて吊り上げる（rotation_z は正で時計回り。左目 sx=-1 は右端が下がる向き）
        self.eyes = [glow(self.head, "quad", double_sided=True, scale=(0.17, 0.055),
                          x=sx * 0.15, y=0.05, z=-0.43, rotation_z=-sx * 22) for sx in (-1, 1)]
        glow(self.head, "quad", double_sided=True, scale=(0.2, 0.025), y=-0.13, z=-0.42)
        for sx in (-1, 1):
            pivot = Entity(parent=self.head, x=sx * 0.24, y=0.2, rotation_z=sx * 30)
            solid(pivot, _tube_mesh(0.085, 0.006, 0.55, segments=5), SPIKE)

        # 肩のトゲ（外へ）と背中のトゲ（後ろ上へ。rotation_x が負で +Y が +Z＝背中側へ倒れる）
        for sx in (-1, 1):
            pivot = Entity(parent=self, x=sx * 0.52, y=1.55, rotation_z=sx * 62)
            solid(pivot, _tube_mesh(0.1, 0.005, 0.45, segments=5), SPIKE)
        for i, y in enumerate((1.05, 1.35, 1.65)):
            pivot = Entity(parent=self, y=y, z=0.33, rotation_x=-55)
            solid(pivot, _tube_mesh(0.09, 0.005, 0.32 + 0.08 * i, segments=5), SPIKE)

        # 長い腕と 3 本の爪（ピボットは肩。rotation_x が負で前へ振り上げる＝住人の腕と同じ）
        self.arms = []
        for sx in (-1, 1):
            pivot = Entity(parent=self, x=sx * 0.66, y=1.52)
            solid(pivot, _tube_mesh(0.07, 0.1, 1.0, segments=6), BODY, y=-1.0)
            for k in (-1, 0, 1):
                spread = Entity(parent=pivot, y=-0.98, rotation_z=k * 28)
                solid(spread, _tube_mesh(0.045, 0.004, 0.3, segments=4), SPIKE, rotation_x=180)
            self.arms.append(pivot)

        # まわりの暗いもや
        self.aura = Entity(parent=self, model="sphere", color=color.rgba(0.28, 0.0, 0.38, 0.2), unlit=True,
                           scale=(1.9, 2.7, 1.9), y=1.25)

        self._parts = [(e, e.color) for e in self._descendants() if e.model is not None and e is not self.aura]
        # パーツは update を持たないので、ursina の毎フレームの処理から外す（住人の Character と同じ）
        self.ignore = True
        for e in self._descendants():
            e.ignore = True
        self._tint = (1.0, 0.0)
        self._raise = None

    def _descendants(self):
        stack = list(self.children)
        while stack:
            e = stack.pop()
            stack.extend(e.children)
            yield e

    def set_tint(self, brightness: float, whiten: float = 0.0):
        """全パーツの色を作り直す。whiten は 0〜1 で白へ寄せる（攻撃が当たった光）"""
        if (brightness, whiten) == self._tint:
            return
        self._tint = (brightness, whiten)
        for e, c in self._parts:
            rgb = [min(1.0, (c[i] + (1.0 - c[i]) * whiten) * brightness) for i in range(3)]
            e.color = color.rgba(*rgb, c[3])

    def set_arms(self, deg: float):
        """0 で下ろす。正で前へ振り上げる"""
        if deg != self._raise:
            self._raise = deg
            for a in self.arms:
                a.rotation_x = -deg


class RaiderFigure:
    def __init__(self, raider, lcfg, rcfg):
        self.raider = raider
        self.rcfg = rcfg
        self.s = lcfg.scale * rcfg.size_ratio
        self.root = Entity(enabled=False)
        Entity(parent=self.root, model=Circle(20), rotation_x=90, y=0.04, scale=2.2 * self.s,
               color=color.rgba(0, 0, 0, 0.55), unlit=True)
        self.tilt = Entity(parent=self.root)                      # 倒れるときに傾ける
        self.body = RaiderModel(parent=self.tilt, rotation_y=180, scale=self.s)   # 正面 -Z を +Z（heading 0）へ
        top = (HEIGHT + 0.55) * self.s
        self.label = Text(raider.name, parent=self.root, y=top + 0.4, scale=13, billboard=True, origin=(0, 0),
                          color=color.rgb(1, 0.4, 0.35))
        self.bar = Entity(parent=self.root, y=top, billboard=True)
        Entity(parent=self.bar, model="quad", color=color.rgba(0, 0, 0, 0.75), scale=(BAR_W + 0.06, 0.2))
        self.bar_fg = Entity(parent=self.bar, model="quad", color=color.rgb(0.95, 0.2, 0.15),
                             scale=(BAR_W, 0.13), origin=(-0.5, 0), x=-BAR_W / 2, z=-0.01)
        self.anchor_y = top + 0.7
        self.x = self.z = self.yaw = 0.0
        self.flash_until = 0.0
        self.core_until = 0.0
        self.shown_hp = None

    def flash(self):
        self.flash_until = time.time() + 0.15

    def flash_core(self):
        self.core_until = time.time() + 0.25

    @property
    def chest(self) -> Vec3:
        return Vec3(self.x, self.root.y + 1.4 * self.s, self.z)

    @property
    def anchor(self) -> Vec3:
        return Vec3(self.x, self.anchor_y, self.z)

    def update(self, dt: float, world):
        r = self.raider
        if not r.present:
            if self.root.enabled:
                self.root.enabled = False
            return
        if not self.root.enabled:   # 現れた
            self.root.enabled = True
            self.x, self.z, self.yaw = r.x, r.z, r.heading
            self.tilt.rotation_z = 0
            self.body.set_tint(1.0)
        k = smooth(dt, 0.1)
        self.x += (r.x - self.x) * k
        self.z += (r.z - self.z) * k
        diff = (r.heading - self.yaw + 180) % 360 - 180
        self.yaw += diff * smooth(dt, 0.2)
        self.root.rotation_y = self.yaw

        t = time.time()
        since = world.now - r.since
        y = 0.0
        match r.state.current:
            case "appear":
                y = -HEIGHT * 1.2 * self.s * (1.0 - min(1.0, since / self.rcfg.appear_sec))
            case "defeated":
                p = min(1.0, since / self.rcfg.defeated_sec)
                self.tilt.rotation_z = 80 * min(1.0, p * 2.0)
                y = -HEIGHT * self.s * max(0.0, p - 0.5) * 2.0
        self.root.position = Vec3(self.x, y, self.z)
        self.body.y = 0.25 + math.sin(t * 2.2) * 0.1          # 浮いて揺れる
        if world.now < r.strike_pose_until:
            arms = 100                       # 爪を振り抜いた
        elif r.contact is not None:
            arms = 55                        # 獲物の前で爪を構える
        else:
            arms = 12 + math.sin(t * 1.7) * 8
        self.body.set_arms(arms)
        self.body.core.scale = 0.13 * (1.8 if t < self.core_until else 1.0)
        self.body.aura.scale = Vec3(1.9, 2.7, 1.9) * (1.0 + 0.06 * math.sin(t * 3.0))

        if r.hp <= 0:
            self.body.set_tint(max(0.25, 1.0 - min(1.0, since / self.rcfg.defeated_sec)))
        elif t < self.flash_until:
            self.body.set_tint(1.6, 0.75)
        else:
            self.body.set_tint(1.0)

        if r.hp != self.shown_hp:
            self.shown_hp = r.hp
            self.bar_fg.scale_x = max(0.001, BAR_W * r.hp / r.max_hp)
