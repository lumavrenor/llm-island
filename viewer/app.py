"""
ビューア（Ursina）

World と同じメインスレッドで動く。IslandView.update() が毎フレーム:
    1. world.update(dt)        … 世界を 1 フレーム進める
    2. world.drain_feed()      … このフレームの出来事を受け取って、ふきだし・演出・カメラへ
    3. 表示物を順番に update   … キャラ → 悪 → solace の塔 → ふきだし → 励まし・癒しの粒 → 攻撃の弾と火花 → カメラ → 音 → HUD
キューもスレッドも使わない（World のデータをそのまま読む）。
音は viewer/sound.py。出来事を受け取ったところで、その位置といっしょに鳴らす（カメラから近いものだけ聞こえる）。

■ 住人の見た目（2026-10-13：電力を HP・心・状態異常に置き換え）
    戦士       … 名前が金色、頭上に金の菱形、右手に剣（viewer/weapons.py）。撃つたびに剣を振り下ろす
    ヒーラー   … 名前が若葉色、頭上に若葉色の十字、右手に魔法の杖。詠唱中は杖を頭上に掲げ、足元に光の輪
    フリーズ   … 青白く色が抜けて、半透明の氷のかたまりに閉じこめられる（名前の上に「フリーズ」）
    ノイズ     … 紫がかってチカチカ明滅する
    おびえ     … 青みがかって小刻みに震える
    solace で休んでいる … ピンクに明るく脈打つ
    攻撃を受けた … 一瞬赤く光る
    HP・心のバー … 減っているときだけ、近くの住人の名前の上に出る（赤＝HP、ピンク＝心）
"""

from __future__ import annotations

import atexit
import logging
import math
import random
import time
from pathlib import Path

from ursina import (AmbientLight, BoxCollider, Circle, DirectionalLight, Entity, Text, Ursina,
                    Vec3, application, camera, color, mouse, scene, window)
from ursina.shaders import lit_with_shadows_shader

import lang
from core.config import ROOT
from sim.raid import RAIDER_ID
from viewer.bubbles import BubblePool, LogPanel
from viewer.camera import CameraRig, smooth
from viewer.hud import HUD, InfoPanel
from viewer.looks import Look, build_looks, hex_to_rgb
from viewer.poly_character import Character, _low_poly_sphere_mesh, _tube_mesh
from viewer.raider_figure import RaiderFigure
from viewer.sound import SoundBoard
from viewer.weapons import Staff
from viewer.window_geometry import load_geometry, start_tracking

logger = logging.getLogger(__name__)

LABEL_DIST = 70.0  # 名前を表示するカメラからの距離
ANIM_DIST = 80.0   # 顔・手足を動かすカメラからの距離（遠くの住人は省略）
BAR_W = 1.1        # HP・心のバーの幅

ICE = color.rgba(0.62, 0.9, 1.0, 0.32)      # フリーズの氷
HEART_PINK = color.rgb(1.0, 0.55, 0.75)     # 心（バー・励ましの粒・solace の塔）
HEAL_GREEN = color.rgb(0.55, 1.0, 0.65)     # 癒し（weapons.GEM_GLOW とそろえる）

# 攻撃の弾の色（弾, 尾, 撃った瞬間, 当たった火花, 外れた火花）
BOLT_WARRIOR = (color.rgb(0.8, 0.97, 1), (0.35, 0.8, 1), color.rgb(0.6, 0.95, 1),
                color.rgb(1, 0.95, 0.6), color.rgb(0.5, 0.6, 0.8))
BOLT_RAIDER = (color.rgb(0.35, 0.05, 0.4), (0.55, 0.0, 0.25), color.rgb(0.8, 0.1, 0.3),
               color.rgb(1, 0.2, 0.25), color.rgb(0.3, 0.1, 0.35))


def setup_japanese_font():
    """Windows のシステムフォントから日本語フォントを探す"""
    fonts_dir = Path("C:/Windows/Fonts")
    for name in ("meiryo.ttc", "msgothic.ttc", "YuGothM.ttc"):
        if (fonts_dir / name).exists():
            application.fonts_folder = fonts_dir
            Text.default_font = name
            return
    logger.warning("日本語フォントが見つかりません（文字化けする可能性）")


def _rgb(hex_str: str) -> color.Color:
    return color.rgb(*hex_to_rgb(hex_str))


class Figure:
    """NPC 1 体の見た目（llm-radio-daemon から移植したクレイ風キャラ＋名前＋武器）"""

    def __init__(self, npc, look: Look, lcfg, ncfg):
        self.npc = npc
        self.ncfg = ncfg
        self.s = lcfg.scale
        self.root = Entity(position=(npc.x, 0, npc.z))
        self.root.collider = BoxCollider(self.root, center=Vec3(0, 1, 0), size=Vec3(1.4, 2.2, 1.4))
        # キャラの正面は -Z、npc.heading = 0 は +Z 向きなので、半回転させて載せる
        self.body = Character(
            parent=self.root, rotation_y=180, scale=lcfg.scale,
            hair_style=look.hair_style, body_style=look.body_style,
            hair_color=_rgb(look.hair_color), eye_color=_rgb(look.eye_color),
            dress_color=_rgb(look.clothing_color), skin_color=_rgb(lcfg.skin_color),
            accessories=[(kind, _rgb(c) if c else None, side) for kind, c, side in look.accessories],
        )
        top = self.body.label_local_y * lcfg.scale
        self.label = Text(npc.name, parent=self.root, y=top, scale=11, billboard=True, origin=(0, 0),
                          color=color.rgba(1, 1, 1, 0.9))
        self.frozen_label = Text(lang.t("app.frozen_label"), parent=self.root, y=top + 0.55, scale=12, billboard=True, origin=(0, 0),
                                 color=color.rgb(0.6, 0.92, 1), enabled=False)
        self.anchor_y = top + 0.3       # ふきだしを出す高さ
        # HP（赤）と心（ピンク）のバー。減っているときだけ出す
        self.bars = Entity(parent=self.root, y=top + 0.32, billboard=True, enabled=False)
        Entity(parent=self.bars, model="quad", color=color.rgba(0, 0, 0, 0.7), scale=(BAR_W + 0.05, 0.19))
        self.hp_bar = Entity(parent=self.bars, model="quad", color=color.rgb(0.95, 0.3, 0.25),
                             scale=(BAR_W, 0.07), origin=(-0.5, 0), x=-BAR_W / 2, y=0.04, z=-0.01)
        self.heart_bar = Entity(parent=self.bars, model="quad", color=HEART_PINK,
                                scale=(BAR_W, 0.07), origin=(-0.5, 0), x=-BAR_W / 2, y=-0.04, z=-0.01)
        self.shown_bars = (-1, -1)
        for e in (self.bars, *self.bars.children):
            e.ignore = True   # update を持たないので、ursina の毎フレームの処理から外す（Character と同じ）
        # フリーズの氷のかたまり（キャラを包む半透明の箱）
        self.ice = Entity(parent=self.root, model="cube", color=ICE, unlit=True, enabled=False,
                          scale=(1.25 * self.s, 2.5 * self.s, 1.0 * self.s), y=1.2 * self.s, ignore=True)
        # 戦士：名前を金色にして、頭上に回る金の菱形。右手に剣
        self.emblem = None
        if npc.warrior:
            self.label.color = color.rgb(1, 0.85, 0.35)
            self.emblem = Entity(parent=self.root, model=_low_poly_sphere_mesh(2, 4), color=color.rgb(1, 0.82, 0.25),
                                 unlit=True, scale=(0.16, 0.26, 0.16), y=top + 0.42)
            self.body.hold("sword")
        # ヒーラー：名前を若葉色にして、頭上に回る若葉色の十字。右手に魔法の杖。詠唱中は足元に光の輪
        self.cast_ring = None
        if npc.healer:
            self.label.color = color.rgb(0.55, 1, 0.65)
            self.emblem = Entity(parent=self.root, y=top + 0.42)
            for sx, sy in ((0.3, 0.09), (0.09, 0.3)):
                Entity(parent=self.emblem, model="cube", color=color.rgb(0.45, 1, 0.55), unlit=True,
                       scale=(sx, sy, 0.09))
            self.body.hold("staff")
            self.cast_ring = Entity(parent=self.root, model=Circle(6), rotation_x=90, y=0.05, scale=2.6,
                                    color=color.rgba(0.55, 1, 0.65, 0.45), unlit=True, enabled=False, ignore=True)
        self.was_frozen = False
        self.label_str = npc.name
        self.phase = npc.id * 0.7
        self.x, self.z, self.yaw = npc.x, npc.z, 0.0   # 表示上の位置と向き（npc の値へなめらかに寄せる）
        self.bob = 0.0
        self.label_on = True
        self.walk = 0.0                 # 歩行の位相 [rad]（歩いた距離で進める）
        self.talk_until = 0.0           # この時刻（time.time()）まで口パクする
        self.flash_until = 0.0          # この時刻まで赤く光る（攻撃を受けた）
        self.swing_at = -1.0            # 剣を振り下ろし始めた時刻（time.time()）

    def say(self, text: str, life: float):
        self.talk_until = time.time() + min(life, 0.6 + len(text) * 0.1)

    def flash(self):
        """攻撃を受けた（AttackFx・悪の爪から）"""
        self.flash_until = time.time() + 0.18

    def swing(self):
        """戦士が超能力を撃った：剣を振り上げて振り下ろす"""
        self.swing_at = time.time()

    @property
    def chest(self) -> Vec3:
        return Vec3(self.x, 1.2 * self.s, self.z)

    def _arm_pose(self, t: float) -> float | None:
        n = self.npc
        if n.warrior:
            k = (t - self.swing_at) / 0.45
            if 0.0 <= k < 1.0:   # 頭上（160°）から前の下（40°）へ振り下ろす
                return 160 - 120 * min(1.0, k * 1.8)
            if n.intent is not None and n.intent.kind == "fight":
                return 55          # 剣を前に構える
        if n.healer and n.casting is not None:
            return 150 + 6 * math.sin(t * 5)   # 杖を頭上に掲げる
        return None

    def _tint(self, t: float):
        n = self.npc
        if n.frozen:
            self.body.set_tint(0.85, 0.75, (0.8, 0.95, 1.25))
        elif t < self.flash_until:
            self.body.set_tint(1.4, 0.0, (1.3, 0.45, 0.45))
        elif "noise" in n.status and int(t * 14 + self.phase) % 3 == 0:
            self.body.set_tint(0.6, 0.3, (1.0, 0.75, 1.2))      # ノイズ：チカチカ
        elif n.solace is not None and n.heart < self.ncfg.max_heart:
            p = 0.5 + 0.5 * math.sin(t * 3 + self.phase)
            self.body.set_tint(1.0 + 0.25 * p, 0.0, (1.0, 0.92, 0.97))   # solace：ピンクに脈打つ
        elif "fear" in n.status:
            self.body.set_tint(0.9, 0.25, (0.85, 0.9, 1.15))
        else:
            self.body.set_tint(1.0)

    def update(self, dt: float, now: float, cam_pos: Vec3):
        # 100 体ぶん毎フレーム回るので、位置と向きは自前の float で持って NodePath に直接書く
        # （ursina の rotation_y は読むたびに getHpr から Vec3 を組み立て直して重い。rotation_y = -H）
        n = self.npc
        t = time.time()
        k = smooth(dt, 0.12)
        dx, dz = (n.x - self.x) * k, (n.z - self.z) * k
        self.x += dx
        self.z += dz
        shiver = math.sin(t * 47 + self.phase) * 0.035 if "fear" in n.status and not n.frozen else 0.0
        self.root.setPos(self.x + shiver, 0, self.z)
        if not n.frozen:
            diff = (n.heading - self.yaw + 180) % 360 - 180
            if abs(diff) > 0.05:
                self.yaw += diff * smooth(dt, 0.15)
                self.root.setH(-self.yaw)
        # 歩いている間は手足を振って上下に弾む
        walking = n.moving_now and not n.frozen
        if walking:
            self.walk += math.hypot(dx, dz) * 3.2
        bob = abs(math.sin(self.walk)) * 0.08 if walking else 0.0
        if bob != self.bob:
            self.bob = bob
            self.body.setY(bob)

        if n.frozen != self.was_frozen:
            self.was_frozen = n.frozen
            self.ice.enabled = n.frozen
            self.frozen_label.enabled = n.frozen
            if self.emblem is not None:
                self.emblem.enabled = not n.frozen
        if self.emblem is not None and not n.frozen:
            self.emblem.setH(now * 120 % 360)
        self._tint(t)
        if self.cast_ring is not None:
            casting = n.casting is not None
            if self.cast_ring.enabled != casting:
                self.cast_ring.enabled = casting
            if casting:
                self.cast_ring.setH(t * 90 % 360)
        if isinstance(self.body.weapon, Staff):
            self.body.weapon.spin(t, 1.0 if n.casting is not None else 0.0)

        dist = math.sqrt((self.x - cam_pos.x) ** 2 + cam_pos.y ** 2 + (self.z - cam_pos.z) ** 2)
        if dist < ANIM_DIST:
            talking = t < self.talk_until
            rms = 0.1 + 0.1 * abs(math.sin(t * 14 + self.phase)) if talking else 0.0
            self.body.set_arm_pose(None if n.frozen else self._arm_pose(t))
            self.body.animate(t, talking, rms, walk=self.walk if walking else None, asleep=n.frozen)

        label = n.name + (" …" if n.waiting == "say" else "")
        if label != self.label_str:
            self.label_str = label
            self.label.text = label
        near = dist < LABEL_DIST
        if near != self.label_on:
            self.label_on = near
            self.label.enabled = near
        self._update_bars(near)

    def _update_bars(self, near: bool):
        n, nc = self.npc, self.ncfg
        hp, heart = int(n.hp), int(n.heart)
        show = near and not n.frozen and (hp < nc.max_hp or heart < nc.max_heart * 0.6 or "noise" in n.status)
        if self.bars.enabled != show:
            self.bars.enabled = show
        if show and (hp, heart) != self.shown_bars:
            self.shown_bars = (hp, heart)
            self.hp_bar.scale_x = max(0.001, BAR_W * hp / nc.max_hp)
            self.heart_bar.scale_x = max(0.001, BAR_W * heart / nc.max_heart)

    @property
    def anchor(self) -> Vec3:
        return Vec3(self.x, self.anchor_y, self.z)


class Flow:
    """2 体の間を光の粒が弧を描いて流れる（励まし＝ピンク、癒し＝若葉色）"""

    def __init__(self, size: int, tint: color.Color, scale: float):
        self.pool = [Entity(model="sphere", scale=scale, color=tint, unlit=True, enabled=False, ignore=True)
                     for _ in range(size)]
        self.active: list[tuple[Entity, Figure, Figure, float]] = []

    def start(self, src: Figure, dst: Figure, count: int):
        for i in range(count):
            if not self.pool:
                return
            p = self.pool.pop()
            p.enabled = True
            self.active.append((p, src, dst, -i * 0.08))

    def update(self, dt: float):
        keep = []
        for p, src, dst, t in self.active:
            t += dt / 1.2
            if t >= 1.0:
                p.enabled = False
                self.pool.append(p)
                continue
            tt = max(0.0, t)
            a, b = src.root.position + Vec3(0, 1.2, 0), dst.root.position + Vec3(0, 1.2, 0)
            p.position = a + (b - a) * tt + Vec3(0, math.sin(tt * math.pi) * 1.5, 0)
            keep.append((p, src, dst, t))
        self.active = keep


class AttackFx:
    """攻撃の弾と火花。戦士の超能力（水色の弾 → 悪）と、悪の反撃（黒紫の弾 → 戦士）の両方に使う。
    当たれば弾けて相手が光り（dst.flash()）、外れれば相手の脇へそれて散る。burst() は火花だけ（悪の爪・フリーズ・癒し）"""

    FLY_SEC = 0.35
    SPARK_SEC = 0.45

    def __init__(self, size: int = 140):
        self.pool = [Entity(model="sphere", unlit=True, enabled=False, ignore=True) for _ in range(size)]
        self.bolts: list[list] = []    # [弾, 尾, 撃った位置, 相手, それる向き, 進み 0〜1, 当たったか, 色]
        self.sparks: list[list] = []   # [粒, 速度, 経過, 大きさ]

    def _take(self, tint, scale: float) -> Entity | None:
        if not self.pool:
            return None
        e = self.pool.pop()
        e.enabled = True
        e.color, e.scale = tint, scale
        return e

    def _give(self, e: Entity):
        e.enabled = False
        self.pool.append(e)

    def fire(self, start: Vec3, dst, hit: bool, palette=BOLT_WARRIOR):
        """dst は .chest と .flash() を持つもの（RaiderFigure / Figure）"""
        orb_c, trail_rgb, muzzle, _, _ = palette
        self.burst(start, muzzle, 4, 2.5)   # 撃った瞬間の光
        orb = self._take(orb_c, 0.45)
        if orb is None:
            return
        trail = [e for e in (self._take(color.rgba(*trail_rgb, 0.7 - i * 0.18), 0.32 - i * 0.07)
                             for i in range(3)) if e is not None]
        miss = Vec3(0, 0, 0)
        if not hit:
            miss = Vec3(random.uniform(-1, 1), random.uniform(0.4, 1.2), random.uniform(-1, 1)).normalized() * 2.4
        self.bolts.append([orb, trail, start, dst, miss, 0.0, hit, palette])

    def burst(self, pos: Vec3, tint, n: int, speed: float, size: float = 0.22):
        for _ in range(n):
            e = self._take(tint, size)
            if e is None:
                return
            e.position = pos
            v = Vec3(random.uniform(-1, 1), random.uniform(-0.2, 1), random.uniform(-1, 1)).normalized() * speed
            self.sparks.append([e, v, 0.0, size])

    def update(self, dt: float):
        keep = []
        for b in self.bolts:
            orb, trail, start, dst, miss, t, hit, palette = b
            t += dt / self.FLY_SEC
            end = dst.chest + miss
            if t >= 1.0:
                self._give(orb)
                for e in trail:
                    self._give(e)
                if hit:
                    self.burst(end, palette[3], 10, 5.0)
                    dst.flash()
                else:
                    self.burst(end, palette[4], 3, 2.0)
                continue
            b[5] = t
            for i, e in enumerate([orb, *trail]):
                tt = max(0.0, t - i * 0.07)
                e.position = start + (end - start) * tt + Vec3(0, math.sin(tt * math.pi) * 0.8, 0)
            keep.append(b)
        self.bolts = keep
        alive = []
        for s in self.sparks:
            e, v, age, size = s
            age += dt
            if age >= self.SPARK_SEC:
                self._give(e)
                continue
            v.y -= 6.0 * dt
            e.position += v * dt
            e.scale = size * (1.0 - age / self.SPARK_SEC)
            s[2] = age
            alive.append(s)
        self.sparks = alive


class SolaceTower:
    """solace（spots の kind = "solace"）の塔。上で円盤が回り、♪ が昇って消える"""

    NOTES = 5

    def __init__(self, spot):
        self.spot = spot
        shd = lit_with_shadows_shader
        x, z = spot.x, spot.z
        # ursina の Cylinder は法線を持たず陰影が黒くつぶれるので、住人と同じ _tube_mesh で作る
        Entity(model=_tube_mesh(1.1, 1.0, 0.35, segments=10), position=(x, 0, z), color=color.rgb(0.62, 0.48, 0.58),
               shader=shd)
        bottom_r, top_r, h = 0.55, 0.38, 3.4
        Entity(model=_tube_mesh(bottom_r, top_r, h, segments=8), position=(x, 0.35, z),
               color=color.rgb(0.92, 0.78, 0.86), shader=shd)
        for y in (1.2, 2.6):   # 金の帯（その高さの柱より少し太く）
            r = bottom_r + (top_r - bottom_r) * (y - 0.35) / h + 0.04
            Entity(model=_tube_mesh(r, r, 0.12, segments=8), position=(x, y, z),
                   color=color.rgb(0.95, 0.76, 0.3), shader=shd)
        # 回る円盤とその上のピン、浮かぶハートの結晶
        self.disc = Entity(position=(x, 3.75, z))
        Entity(parent=self.disc, model=_tube_mesh(1.0, 1.0, 0.14, segments=12), color=color.rgb(0.95, 0.76, 0.3),
               shader=shd)
        for i in range(8):
            a = math.tau * i / 8
            Entity(parent=self.disc, model="cube", color=color.rgb(0.98, 0.95, 0.85), shader=shd,
                   scale=(0.08, 0.16, 0.08), position=(math.cos(a) * 0.7, 0.2, math.sin(a) * 0.7))
        self.crystal = Entity(model=_low_poly_sphere_mesh(2, 4), position=(x, 4.8, z), scale=(0.35, 0.55, 0.35),
                              color=HEART_PINK, unlit=True)
        self.notes = [Text("♪", parent=scene, scale=26, billboard=True, origin=(0, 0), color=HEART_PINK,
                           enabled=False) for _ in range(self.NOTES)]
        self.note_t = [i / self.NOTES for i in range(self.NOTES)]
        self.note_a = [random.uniform(0, math.tau) for _ in range(self.NOTES)]

    def update(self, dt: float, t: float, cam_pos: Vec3):
        x, z = self.spot.x, self.spot.z
        self.disc.setH(t * 40 % 360)
        self.crystal.setH(t * 70 % 360)
        self.crystal.y = 4.8 + math.sin(t * 2.0 + x) * 0.15
        near = (x - cam_pos.x) ** 2 + (z - cam_pos.z) ** 2 < 90 ** 2
        for i, note in enumerate(self.notes):
            if not near:
                if note.enabled:
                    note.enabled = False
                continue
            self.note_t[i] += dt / 3.2
            if self.note_t[i] >= 1.0:
                self.note_t[i] -= 1.0
                self.note_a[i] = random.uniform(0, math.tau)
            p = self.note_t[i]
            a = self.note_a[i] + p * 1.5
            note.enabled = True
            note.position = (x + math.cos(a) * (1.2 + p * 1.5), 4.2 + p * 3.0, z + math.sin(a) * (1.2 + p * 1.5))
            note.color = color.rgba(1.0, 0.55, 0.75, math.sin(p * math.pi))


def build_scene(world) -> list[SolaceTower]:
    size = world.cfg.world.size
    Entity(model="plane", scale=(size, 1, size), color=color.rgb(0.07, 0.13, 0.15),
           texture="white_cube", texture_scale=(size / 8, size / 8), unlit=True)
    towers = []
    for s in world.spots:
        tint = color.rgba(1.0, 0.55, 0.75, 0.3) if s.kind == "solace" else color.rgba(0.6, 0.9, 0.5, 0.25)
        Entity(model=Circle(48), rotation_x=90, y=0.03, scale=s.radius * 2, color=tint, unlit=True)
        Text(s.name, parent=scene, position=(s.x, 6.2 if s.kind == "solace" else 4, s.z), scale=28,
             billboard=True, origin=(0, 0), color=color.rgba(0.85, 1, 0.9, 0.9))
        if s.kind == "solace":
            towers.append(SolaceTower(s))
    window.color = color.rgb(0.03, 0.05, 0.1)
    setup_lights()
    return towers


def setup_lights():
    """キャラはフラットシェーディングなので、斜めの光＋控えめの環境光で面ごとの陰影を出す"""
    sun = DirectionalLight(shadows=False)
    sun.look_at(Vec3(1, -2, 1.5))
    AmbientLight(color=color.rgba(0.4, 0.4, 0.5, 1))


class IslandView(Entity):
    def __init__(self, world, cfg, minutes: float | None, screenshot: str | None, tracker=None):
        super().__init__()
        self.world = world
        self.tracker = tracker          # window_geometry.GeometryTracker（位置・サイズを控えるだけ）
        self.vcfg = cfg.viewer
        self.minutes = minutes
        self.screenshot = screenshot
        self.towers = build_scene(world)
        looks = build_looks(cfg.look, cfg.world.seed, world.npcs)
        self.figures = [Figure(n, looks[n.id], cfg.look, cfg.npc) for n in world.npcs]
        self.by_entity = {f.root: f.npc.id for f in self.figures}
        self.bubbles = BubblePool(40)
        self.log_panel = LogPanel()
        self.raider_fig = RaiderFigure(world.raider, cfg.look, cfg.raider)
        self.cheer_flow = Flow(60, HEART_PINK, 0.22)     # 励まし
        self.heal_flow = Flow(60, HEAL_GREEN, 0.3)       # 癒し（杖の宝石からフリーズした住人へ）
        self.attack_fx = AttackFx()
        self.rig = CameraRig(world, self.vcfg)
        self.sound = SoundBoard(cfg.audio, application.base.loader)
        lo, hi = cfg.audio.say_pitch
        self.say_rate = [lo + (hi - lo) * ((n.id * 0.618) % 1.0) for n in world.npcs]   # 住人ごとの声の高さ
        self.hud = HUD(world, self.rig)
        self.hud.inner_voice = self.vcfg.show_inner_voice
        self.info = InfoPanel(world)
        self.frames = 0
        self.started = time.perf_counter()

    # ---------- 毎フレーム ----------

    def update(self):
        dt = min(getattr(time, "dt", 1 / 60), 0.25)   # ursina が標準 time モジュールに dt を入れる
        w = self.world
        self.frames += 1
        w.update(dt)
        for ev in w.drain_feed():
            self.on_event(ev)
        cam = camera.world_position
        for f in self.figures:
            f.update(dt, w.now, cam)
        self.raider_fig.update(dt, w)
        t = time.time()
        for tower in self.towers:
            tower.update(dt, t, cam)
        anchors = {f.npc.id: f.anchor for f in self.figures}
        anchors[RAIDER_ID] = self.raider_fig.anchor
        self.bubbles.update(dt, anchors)
        self.cheer_flow.update(dt)
        self.heal_flow.update(dt)
        self.attack_fx.update(dt)
        self.rig.update(dt)
        self.sound.update(camera.world_position, camera.right)
        self.hud.update(dt)
        self.info.update(dt)
        self.log_panel.update()
        if self.tracker is not None:
            self.tracker.tick()   # 位置・サイズを控えるだけ（書き出しは終了時の atexit）
        if self.minutes is not None and w.now - w.start_now >= self.minutes * 60:
            self.quit()

    def on_event(self, ev: dict):
        self.rig.on_event(ev)
        w, life = self.world, self.vcfg.bubble_sec
        fx, snd = self.attack_fx, self.sound
        match ev["kind"]:
            case "say":
                f = self.figures[ev["npc"]]
                style = "rescue" if ev.get("session") is None else "say"
                f.say(ev["text"], life)
                snd.play("say", f.chest, self.say_rate[f.npc.id])
                if self.visible(f):
                    self.bubbles.show(f.npc.id, ev["text"], style, life)
                else:
                    self.log_panel.add(f"{w.npcs[ev['npc']].name}→{w.npcs[ev['partner']].name}: {ev['text']}")
            case "inner":
                f = self.figures[ev["npc"]]
                if self.hud.inner_voice and self.visible(f):
                    self.bubbles.show(f.npc.id, ev["text"], "inner", life * 0.7)
            case "cheer":
                self.cheer_flow.start(self.figures[ev["src"]], self.figures[ev["dst"]], 8)
                snd.play("cheer", self.figures[ev["dst"]].chest)
            case "cast_start":
                f = self.figures[ev["npc"]]
                fx.burst(f.root.position + Vec3(0, 2.4 * f.s, 0), HEAL_GREEN, 6, 2.0)
                snd.play("cast_start", f.chest)
            case "heal":
                src, dst = self.figures[ev["src"]], self.figures[ev["dst"]]
                self.heal_flow.start(src, dst, 14)
                fx.burst(dst.chest, color.rgb(0.7, 0.95, 1), 16, 4.5, 0.3)   # 氷が砕ける
                snd.play("heal", dst.chest)
                self.log_panel.add(lang.t("log.heal", a=w.npcs[ev["src"]].name, b=w.npcs[ev["dst"]].name))
            case "frozen":
                f = self.figures[ev["npc"]]
                fx.burst(f.chest, color.rgb(0.6, 0.92, 1), 12, 3.0)
                snd.play("frozen", f.chest)
            case "attack":
                f = self.figures[ev["npc"]]
                f.swing()
                fx.fire(f.chest + Vec3(0, 0.3, 0), self.raider_fig, ev["hit"], BOLT_WARRIOR)
                snd.play("attack", f.chest)
            case "raider_counter":
                fx.fire(self.raider_fig.chest, self.figures[ev["npc"]], ev["hit"], BOLT_RAIDER)
                snd.play("raider_counter", self.raider_fig.chest)
                self.raider_fig.flash_core()
            case "raider_strike":
                f = self.figures[ev["npc"]]
                fx.burst(f.chest, BOLT_RAIDER[3], 8, 4.0)
                f.flash()
                snd.play("raider_strike", f.chest)
            case "raider_think":
                # セリフがあればセリフ、なければ心の声（V キーで切替）
                shown = self.raider_fig.root.enabled and self.visible(self.raider_fig)
                if ev["say"] and shown:
                    self.bubbles.show(RAIDER_ID, ev["say"], "raider", life)
                elif ev["text"] and shown and self.hud.inner_voice:
                    self.bubbles.show(RAIDER_ID, ev["text"], "inner", life * 0.8)
                if ev["text"]:
                    self.log_panel.add(lang.t("log.raider_thought", name=w.raider.name, x=ev["text"]))
            case "raider_say":
                if self.raider_fig.root.enabled and self.visible(self.raider_fig):
                    self.bubbles.show(RAIDER_ID, ev["text"], "raider", life)
            case "raider_appear":
                self.log_panel.add(lang.t("log.raider_appear", name=w.raider.name, spot=ev["spot"]))
                snd.play("raider_appear", Vec3(w.raider.x, 1, w.raider.z))
            case "raider_froze":
                self.log_panel.add(lang.t("log.froze", name=w.npcs[ev["npc"]].name, n=ev["victims"]))
            case "raider_escaped_hit":
                self.log_panel.add(lang.t("log.escaped_hit", name=w.npcs[ev["npc"]].name, dmg=ev["damage"]))
            case "raider_defeated":
                self.log_panel.add(lang.t("log.defeated", name=w.raider.name,
                                          names=lang.sep().join(w.npcs[i].name for i in ev["fighters"])))
                snd.play("raider_defeated", self.raider_fig.chest)
            case "raider_gone":
                self.log_panel.add(lang.t("log.gone", name=w.raider.name, n=ev["victims"]))
                snd.play("raider_gone", self.raider_fig.chest)
            case "system":
                self.log_panel.add(ev["text"])

    def visible(self, f) -> bool:
        """カメラの視野内かつ一定距離以内"""
        to = f.root.position - camera.world_position
        if to.length() > self.vcfg.bubble_distance or to.dot(camera.forward) <= 0:
            return False
        sp = f.root.screen_position
        return abs(sp.x) < window.aspect_ratio / 2 and abs(sp.y) < 0.5

    def input(self, key):
        match key:
            case "scroll up":
                self.rig.on_scroll(1)
            case "scroll down":
                self.rig.on_scroll(-1)
            case "left mouse down":
                self.rig.press()
            case "left mouse up":
                # 動かさずに離したときだけクリック（ドラッグは平行移動）
                npc_id = self.by_entity.get(mouse.hovered_entity) if self.rig.release() else None
                if npc_id is not None:
                    self.rig.follow(npc_id)
                    self.info.show(npc_id)
            case "escape":
                self.rig.back_to_auto()
                self.info.show(None)
            case "v":
                self.hud.inner_voice = not self.hud.inner_voice
                self.hud.timer = 0
            case "m":
                self.hud.muted = self.sound.toggle_mute()
                self.hud.timer = 0

    def quit(self):
        logger.info("ビューア終了: 平均 %.1f FPS", self.frames / max(1e-6, time.perf_counter() - self.started))
        if self.screenshot:
            from panda3d.core import Filename
            application.base.win.saveScreenshot(Filename.from_os_specific(self.screenshot))
        application.quit()


def run_viewer(world, cfg, minutes: float | None = None, screenshot: str | None = None):
    vc = cfg.viewer
    # 前回終了時のウィンドウ位置・サイズを復元する（無ければ既定サイズで中央）
    state_path = ROOT / vc.window_state_path
    restored = load_geometry(state_path) if vc.remember_window else None
    size = (restored.width, restored.height) if restored else tuple(vc.window_size)
    app = Ursina(title="llm-island", borderless=False, size=size, development_mode=False)
    # 位置の復元は Ursina() の後（ursina 8.3 は初期化の最後に必ず中央配置するため）
    tracker = None
    if vc.remember_window:
        tracker = start_tracking(state_path, restored)
        # Panda3D はウィンドウを閉じると sys.exit() するので、保存は atexit に置く
        atexit.register(tracker.save)
    setup_japanese_font()
    IslandView(world, cfg, minutes, screenshot, tracker)
    app.run()
