"""
戦士の剣・ヒーラーの魔法の杖（Ursina プリミティブ + カスタム Mesh。外部モデルファイルは使わない）

poly_character.py の住人と同じ作り方にそろえる:
- 低ポリ・フラットシェーディング（面ごとに頂点を分けて generate_normals(smooth=False)）
- 単色の塗り分け。光る部分（剣の芯・杖の宝石）だけ unlit
- 全パーツは作るときに 1 回だけ生成し、毎フレームは回転・色だけを書き換える

座標: 持ち手（握る所）が原点。剣は +Y が切っ先、杖は +Y が頭（宝石）。正面は -Z（住人と同じ）。
Character.hold() が右手のピボットの子として付け、腕の振りに合わせて動かす。
大きさは住人の scale 1（身長およそ 2.2）に合わせてある。

    python -m viewer.preview --catalog      # 一覧の最後に「戦士」「ヒーラー」が並ぶ
"""

from __future__ import annotations

import math

from ursina import Entity, Mesh, Vec3, color
from ursina.shaders import lit_with_shadows_shader

from viewer.poly_character import _cached, _low_poly_sphere_mesh, _tube_mesh

# --- 色 ---------------------------------------------------------------------------
STEEL = color.rgb(0.80, 0.85, 0.92)      # 刃
STEEL_DARK = color.rgb(0.55, 0.60, 0.70)  # 刃の付け根の金具
GOLD = color.rgb(0.95, 0.76, 0.30)       # 鍔・柄頭・杖の金の輪
LEATHER = color.rgb(0.30, 0.18, 0.12)    # 柄の革巻き
EDGE_GLOW = color.rgb(0.55, 0.95, 1.00)  # 刃の芯（超能力の電撃の色。app.py の AttackFx とそろえる）
WOOD = color.rgb(0.52, 0.34, 0.20)       # 杖の柄
WOOD_DARK = color.rgb(0.38, 0.24, 0.14)
LEAF = color.rgb(0.45, 0.80, 0.42)       # 杖の頭の若葉（ヒーラーの名前の色とそろえる）
GEM_GLOW = color.rgb(0.55, 1.00, 0.65)   # 杖の宝石（癒しの粒の色とそろえる）


# --- メッシュ ---------------------------------------------------------------------


def _faceted(tris: list[tuple[Vec3, Vec3, Vec3]], center_of) -> Mesh:
    """三角形の列からフラットシェーディングの Mesh を作る。

    center_of(重心) が返す点から外へ向く面を表にする（巻き順を自動でそろえる）。
    このプロジェクトの Mesh は「標準の外積 (q-p)×(r-p) が外向き法線と逆を向く」巻き順が表
    （poly_character._tube_mesh の蓋と同じ。ursina は左手系のため）。
    """
    verts: list[Vec3] = []
    out: list[tuple[int, int, int]] = []
    for p, q, r in tris:
        ux, uy, uz = q.x - p.x, q.y - p.y, q.z - p.z
        vx, vy, vz = r.x - p.x, r.y - p.y, r.z - p.z
        nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
        g = Vec3((p.x + q.x + r.x) / 3, (p.y + q.y + r.y) / 3, (p.z + q.z + r.z) / 3)
        c = center_of(g)
        if nx * (g.x - c.x) + ny * (g.y - c.y) + nz * (g.z - c.z) > 0:
            q, r = r, q
        base = len(verts)
        verts += [p, q, r]
        out.append((base, base + 1, base + 2))
    m = Mesh(vertices=verts, triangles=out, mode="triangle")
    m.generate_normals(smooth=False)
    return m


def _on_y_axis(g: Vec3) -> Vec3:
    return Vec3(0, g.y, 0)


@_cached
def _blade_mesh(length: float, width: float, thick: float, tip: float) -> Mesh:
    """両刃の刃。断面はひし形（左右が刃、前後が鎬）。y=0 が付け根、y=length が切っ先。
    tip は切っ先の三角の長さ。付け根から切っ先の手前までは、わずかに細くなる"""
    shoulder = length - tip

    def section(y: float, k: float) -> list[Vec3]:
        # +X の刃 → -Z の鎬 → -X の刃 → +Z の鎬（ひし形）
        return [Vec3(width / 2 * k, y, 0), Vec3(0, y, -thick / 2 * k),
                Vec3(-width / 2 * k, y, 0), Vec3(0, y, thick / 2 * k)]

    lo, hi = section(0.0, 1.0), section(shoulder, 0.86)
    point = Vec3(0, length, 0)
    tris = []
    for i in range(4):
        j = (i + 1) % 4
        tris += [(lo[i], lo[j], hi[j]), (lo[i], hi[j], hi[i]), (hi[i], hi[j], point)]
    base = Vec3(0, 0, 0)
    tris += [(base, lo[i], lo[(i + 1) % 4]) for i in range(4)]
    return _faceted(tris, _on_y_axis)


@_cached
def _gem_mesh(height: float, radius: float, sides: int) -> Mesh:
    """上下に尖った宝石（双角錐）。中心が原点"""
    top, bottom = Vec3(0, height / 2, 0), Vec3(0, -height / 2, 0)
    ring = [Vec3(math.cos(math.tau * i / sides) * radius, 0, math.sin(math.tau * i / sides) * radius)
            for i in range(sides)]
    tris = []
    for i in range(sides):
        a, b = ring[i], ring[(i + 1) % sides]
        tris += [(top, a, b), (bottom, b, a)]
    return _faceted(tris, lambda g: Vec3(0, 0, 0))


@_cached
def _ring_mesh(radius: float, tube: float, segments: int, sides: int) -> Mesh:
    """XY 面に立つ輪（低ポリのトーラス）。正面（-Z）から見て丸く見える"""
    tris = []

    def pt(i: int, k: int) -> Vec3:
        a, b = math.tau * i / segments, math.tau * k / sides
        r = radius + math.cos(b) * tube
        return Vec3(math.cos(a) * r, math.sin(a) * r, math.sin(b) * tube)

    for i in range(segments):
        for k in range(sides):
            p, q = pt(i, k), pt(i + 1, k)
            r, s = pt(i + 1, k + 1), pt(i, k + 1)
            tris += [(p, q, r), (p, r, s)]

    def core(g: Vec3) -> Vec3:   # 管の中心線（輪の円周上でいちばん近い点）
        d = math.hypot(g.x, g.y) or 1.0
        return Vec3(g.x / d * radius, g.y / d * radius, 0)

    return _faceted(tris, core)


@_cached
def _leaf_mesh(length: float, width: float, thick: float) -> Mesh:
    """細長い葉（ひし形の板に少し厚み）。付け根が原点、+Y へ伸びる"""
    tip, base = Vec3(0, length, 0), Vec3(0, 0, 0)
    side = [Vec3(width / 2, length * 0.45, 0), Vec3(-width / 2, length * 0.45, 0)]
    front, back = Vec3(0, length * 0.45, -thick / 2), Vec3(0, length * 0.45, thick / 2)
    tris = []
    for s in side:
        for f in (front, back):
            tris += [(base, s, f), (s, tip, f)]
    return _faceted(tris, lambda g: Vec3(0, length * 0.45, 0))


# --- 組み立て ---------------------------------------------------------------------


class Weapon(Entity):
    """剣・杖の共通部分。glow は光るパーツ（明るさを変えて脈打たせる）"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.glow: list[Entity] = []

    def _solid(self, model, col, **kw) -> Entity:
        return Entity(parent=self, model=model, color=col, shader=lit_with_shadows_shader, **kw)

    def _light(self, model, col, **kw) -> Entity:
        e = Entity(parent=self, model=model, color=col, unlit=True, **kw)
        self.glow.append(e)
        return e

    def finish(self):
        """全パーツを ursina の毎フレームの処理から外す（Character と同じ。描画には影響しない）"""
        self.ignore = True
        stack = list(self.children)
        while stack:
            e = stack.pop()
            stack.extend(e.children)
            e.ignore = True


class Sword(Weapon):
    """戦士の片手剣。原点が柄の真ん中、+Y が切っ先。刃渡りおよそ 0.8"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        grip = 0.22
        # 柄（革巻き）と、巻きの段差を見せる細い輪
        self._solid(_tube_mesh(0.036, 0.034, grip, segments=6), LEATHER, y=-grip / 2)
        for y in (-0.06, 0.02):
            self._solid(_tube_mesh(0.041, 0.041, 0.02, segments=6), WOOD_DARK, y=y)
        # 柄頭（金の小さな宝石形）
        self._solid(_gem_mesh(0.11, 0.055, 6), GOLD, y=-grip / 2 - 0.04)
        # 鍔：横に伸びる金の棒＋両端の小さな宝石
        guard_y = grip / 2 + 0.02
        self._solid("cube", GOLD, scale=(0.34, 0.05, 0.07), y=guard_y)
        for sx in (-1, 1):
            self._solid(_gem_mesh(0.1, 0.04, 4), GOLD, x=sx * 0.19, y=guard_y, rotation_z=90)
        # 刃の付け根の金具
        self._solid(_tube_mesh(0.055, 0.045, 0.06, segments=4), STEEL_DARK, y=guard_y + 0.025, rotation_y=45)
        # 刃（ひし形断面）と、両面に通る光る芯（超能力の電撃が宿っている）
        blade_y = guard_y + 0.08
        self._solid(_blade_mesh(0.82, 0.12, 0.035, 0.16), STEEL, y=blade_y)
        self._light("cube", EDGE_GLOW, scale=(0.022, 0.6, 0.04), y=blade_y + 0.33)
        self.finish()


class Staff(Weapon):
    """ヒーラーの魔法の杖。原点が握る所、+Y が頭。長さおよそ 2.7（下端は y=-0.55。持つと輪が頭より上に来る）"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        bottom, length = -0.55, 2.3
        # 柄：下ほど細い木の棒。石突きと、握りの上下に金の輪
        self._solid(_tube_mesh(0.032, 0.045, length, segments=7), WOOD, y=bottom)
        self._solid(_gem_mesh(0.1, 0.045, 5), WOOD_DARK, y=bottom)
        for y in (-0.1, 0.12, length + bottom - 0.08):
            self._solid(_tube_mesh(0.055, 0.055, 0.04, segments=7), GOLD, y=y)
        top = bottom + length
        # 頭：金の輪（正面から丸く見える）。輪の中に浮かぶ若葉色の宝石
        self.head = Entity(parent=self, y=top + 0.22)
        Entity(parent=self.head, model=_ring_mesh(0.2, 0.03, 14, 5), color=GOLD, shader=lit_with_shadows_shader)
        self.gem = Entity(parent=self.head, model=_gem_mesh(0.24, 0.085, 6), color=GEM_GLOW, unlit=True)
        self.glow.append(self.gem)
        # 宝石のまわりのやわらかい光（詠唱中だけ。spin で大きさを変える）
        self.halo = Entity(parent=self.head, model=_low_poly_sphere_mesh(4, 6), color=color.rgba(0.55, 1, 0.65, 0.3),
                           unlit=True, scale=0.3, enabled=False)
        # 輪の付け根から左右に開く若葉 2 枚と、つる（輪を柄につなぐ 2 本の細い枝）
        for sx in (-1, 1):
            Entity(parent=self, model=_leaf_mesh(0.32, 0.13, 0.03), color=LEAF, shader=lit_with_shadows_shader,
                   y=top - 0.04, x=sx * 0.03, rotation_z=-sx * 62, rotation_x=-12)
            Entity(parent=self, model=_tube_mesh(0.016, 0.012, 0.14, segments=4), color=WOOD_DARK,
                   shader=lit_with_shadows_shader, y=top - 0.03, x=sx * 0.02, rotation_z=-sx * 28)
        self.finish()

    def spin(self, t: float, power: float = 0.0):
        """宝石を回す。power（0〜1）が 0 より大きいと、まわりの光が脈打つ（詠唱中）"""
        self.gem.setH(t * (60 + 240 * power) % 360)
        on = power > 0.0
        if self.halo.enabled != on:
            self.halo.enabled = on
        if on:
            self.halo.setScale(0.24 + 0.14 * power * (0.6 + 0.4 * math.sin(t * 9)))


def make(kind: str) -> Weapon:
    """'sword' / 'staff'"""
    return {"sword": Sword, "staff": Staff}[kind]()
