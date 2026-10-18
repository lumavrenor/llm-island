"""
カメラ

ステート（StateMachine）:
    auto   … ディレクター。出来事にスコアをつけ、いちばん面白い所へ移る（最低保持 hold_min 秒）
    manual … WASD か左ドラッグで平行移動、右ドラッグで回転、ホイールでズーム。しばらく操作がなければ auto へ
    follow … クリックした NPC を追う。WASD か左ドラッグで manual、Esc で auto

左ボタンは「押して drag_threshold 以上動かしたらドラッグ、動かさずに離したらクリック」。
ドラッグは地面をつかむ動き（押したときにカーソルの下にあった地面の点が、カーソルについてくる）。
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from panda3d.core import Point2, Point3
from ursina import Vec3, application, camera, held_keys, mouse, scene, window

import lang
from sim.raid import RAIDER_ID
from core.state import StateMachine

# 悪の魔物の出来事は Hotspot.npc = RAIDER_ID（悪そのものを映す）
SCORES = {"raider_defeated": 7, "raider_appear": 6, "attack": 6, "raider_strike": 6, "raider_froze": 6,
          "raider_counter": 5, "heal": 6, "cast_start": 5, "cheer": 5, "first_talk": 4, "memory_say": 3,
          "affinity": 2, "say": 1}


@dataclass
class Hotspot:
    npc: int
    score: int
    t: float


def smooth(dt: float, tau: float) -> float:
    """時定数 tau の指数追従で、このフレームに進む割合（フレームレートに依存しない）"""
    return 1.0 - math.exp(-dt / tau) if tau > 0 else 1.0


class CameraRig:
    def __init__(self, world, vcfg):
        self.world = world
        self.vcfg = vcfg
        self.state = StateMachine("auto")
        self.focus = Vec3(0, 0, 0)     # 実際に見ている点（なめらかに追従）
        self.goal = Vec3(0, 0, 0)      # 見たい点
        self.yaw, self.pitch, self.dist = 30.0, 45.0, 34.0
        self.hotspots: list[Hotspot] = []
        self.director_npc: int | None = None
        self.director_score = 0
        self.director_since = -1e9
        self.follow_id: int | None = None
        self.idle = 0.0
        self._zoom = 0
        self._press: tuple[float, float] | None = None   # 左ボタンを押した画面位置（離すまで）
        self._grab: Vec3 | None = None                   # ドラッグでつかんでいる地面の点
        camera.fov = 50

    # ---------- 外から ----------

    def on_event(self, ev: dict):
        now = self.world.now
        match ev["kind"]:
            case "cheer":
                self.hotspots.append(Hotspot(ev["dst"], SCORES["cheer"], now))
            case "heal":
                self.hotspots.append(Hotspot(ev["dst"], SCORES["heal"], now))
            case "cast_start":
                self.hotspots.append(Hotspot(ev["npc"], SCORES["cast_start"], now))
            case "talk_start" if ev["first"]:
                self.hotspots.append(Hotspot(ev["a"], SCORES["first_talk"], now))
            case "say":
                self.hotspots.append(Hotspot(ev["npc"], SCORES["memory_say" if ev["memory"] else "say"], now))
            case "affinity":
                self.hotspots.append(Hotspot(ev["npc"], SCORES["affinity"], now))
            case "raider_appear" | "attack" | "raider_strike" | "raider_froze" | "raider_counter" | "raider_defeated":
                self.hotspots.append(Hotspot(RAIDER_ID, SCORES[ev["kind"]], now))

    def on_scroll(self, direction: int):
        self._zoom += direction

    def press(self):
        """左ボタンを押した。ドラッグかクリックかは動かしたかどうかで後から決まる"""
        self._press = (mouse.x, mouse.y)
        self._grab = None

    def release(self) -> bool:
        """左ボタンを離した。ドラッグしていなければ True（＝クリックとして扱う）"""
        was_click = self._press is not None and self._grab is None
        self._press = self._grab = None
        return was_click

    @property
    def dragging(self) -> bool:
        return self._grab is not None

    def follow(self, npc_id: int):
        self.follow_id = npc_id
        self.state.change("follow")

    def back_to_auto(self):
        self.follow_id = None
        self.director_since = -1e9
        self.state.change("auto")

    @property
    def mode_label(self) -> str:
        return lang.data("camera.modes").get(self.state.current, "")

    # ---------- 毎フレーム ----------

    def update(self, dt: float):
        moved = self._manual_input(dt)
        match self.state.update():
            case "auto":
                if moved:
                    self.state.change("manual")
                else:
                    self._director()
            case "manual":
                self.idle = 0.0 if moved else self.idle + dt
                if self.state.entered:
                    self.idle = 0.0
                if self.idle >= self.vcfg.manual_idle_sec:
                    self.back_to_auto()
            case "follow":
                if held_keys["w"] or held_keys["a"] or held_keys["s"] or held_keys["d"] or self.dragging:
                    self.follow_id = None
                    self.state.change("manual")
                else:
                    npc = self.world.npcs[self.follow_id]
                    self.goal = Vec3(npc.x, 0, npc.z)
        self._apply(dt)

    def _manual_input(self, dt: float) -> bool:
        moved = False
        fwd = Vec3(math.sin(math.radians(self.yaw)), 0, math.cos(math.radians(self.yaw)))
        right = Vec3(fwd.z, 0, -fwd.x)
        pan = fwd * (held_keys["w"] - held_keys["s"]) + right * (held_keys["d"] - held_keys["a"])
        if pan.length() > 0:
            self.goal += pan.normalized() * self.dist * 0.9 * dt
            moved = True
        if self._drag_input():
            moved = True
        if mouse.right:
            self.yaw += mouse.velocity[0] * 220
            self.pitch = max(15.0, min(85.0, self.pitch - mouse.velocity[1] * 120))
            moved = moved or mouse.velocity.length() > 0
        if self._zoom:
            self.dist = max(8.0, min(160.0, self.dist * (0.88 ** self._zoom)))
            self._zoom = 0
            moved = True
        half = self.world.half
        self.goal = Vec3(max(-half, min(half, self.goal.x)), 0, max(-half, min(half, self.goal.z)))
        self.focus = Vec3(max(-half, min(half, self.focus.x)), 0, max(-half, min(half, self.focus.z)))
        return moved

    def _drag_input(self) -> bool:
        """左ドラッグの平行移動。動かしたら True"""
        if self._press is None or not mouse.left:
            return False
        if self._grab is None:
            px, py = self._press
            if math.hypot(mouse.x - px, mouse.y - py) < self.vcfg.drag_threshold:
                return False
            self._grab = self.ground_at(px, py)   # 押した位置の地面をつかむ
            if self._grab is None:
                return False
            self.goal = Vec3(self.focus)   # 追従の遅れを止めて、つかんだ点がずれないようにする
        now = self._ground_under_mouse()
        if now is None:   # 地平線より上を指している
            return False
        delta = self._grab - now
        # 遅れなしで動かす（なめらか追従をはさむと、つかんだ点がカーソルから離れる）
        self.goal += delta
        self.focus += delta
        self._apply(0.0)
        return delta.length() > 0

    def _ground_under_mouse(self) -> Vec3 | None:
        return self.ground_at(mouse.x, mouse.y)

    @staticmethod
    def ground_at(sx: float, sy: float) -> Vec3 | None:
        """画面の点（mouse と同じ座標）の下にある地面（y=0）の点。地面に当たらなければ None"""
        near, far = Point3(), Point3()
        film = Point2(sx / (window.aspect_ratio / 2), sy * 2)   # 画面は縦 -0.5〜0.5、レンズは -1〜1
        if not camera.lens.extrude(film, near, far):
            return None
        cam = application.base.cam
        a, b = scene.getRelativePoint(cam, near), scene.getRelativePoint(cam, far)
        if a.y - b.y <= 1e-6:
            return None
        t = a.y / (a.y - b.y)
        return Vec3(a.x + (b.x - a.x) * t, 0, a.z + (b.z - a.z) * t)

    def _director(self):
        now = self.world.now
        raider_here = self.world.raider.present
        self.hotspots = [h for h in self.hotspots
                         if now - h.t < 20.0 and (h.npc != RAIDER_ID or raider_here)][-200:]
        if self.director_npc == RAIDER_ID and not raider_here:
            self.director_npc, self.director_score = None, 0   # 悪が消えた
        held = now - self.director_since
        best = max(self.hotspots, key=lambda h: (h.score, h.t), default=None)
        switch = self.director_npc is None or held >= self.vcfg.director_hold_max \
            or (held >= self.vcfg.director_hold_min and best is not None and best.score > self.director_score)
        if switch and best is not None and best.npc != self.director_npc:
            self.director_npc, self.director_score, self.director_since = best.npc, best.score, now
            self.hotspots = [h for h in self.hotspots if h.npc != best.npc]
        elif switch and best is None and self.director_npc is None:
            self.director_npc, self.director_since = 0, now
        if self.director_npc is not None:
            who = self.world.raider if self.director_npc == RAIDER_ID else self.world.npcs[self.director_npc]
            self.goal = Vec3(who.x, 0, who.z)
        if self.state.entered:
            self.dist = 34.0

    def _apply(self, dt: float):
        self.focus = self.focus + (self.goal - self.focus) * smooth(dt, 0.6)
        yaw, pitch = math.radians(self.yaw), math.radians(self.pitch)
        back = Vec3(-math.sin(yaw) * math.cos(pitch), math.sin(pitch), -math.cos(yaw) * math.cos(pitch))
        camera.position = self.focus + back * self.dist
        camera.look_at(self.focus)
