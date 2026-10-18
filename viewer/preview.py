"""
住人の見た目を近くで確かめる（llm-radio-daemon の display/test_character.py を移植）

    python -m viewer.preview                 # 住人 0〜9 を並べる（config.toml の [look] と [[look.npc]] を反映）
    python -m viewer.preview --ids 3,10-14   # 指定した住人を並べる（戦士は剣、ヒーラーは杖を持つ）
    python -m viewer.preview --catalog       # 選べる髪型・装飾品の一覧（最後に剣を持った戦士・杖を持ったヒーラー）
    python -m viewer.preview --weapons       # 剣と杖だけを大きく並べる（形の確認用）
    python -m viewer.preview --roles         # 戦士とヒーラー全員を並べる
    python -m viewer.preview --ids 0-4 --raider   # 悪の魔物も並べる（大きさ比べ）
    python -m viewer.preview --pose walk,talk                # 歩く・話すを入れた状態で始める
    python -m viewer.preview --seconds 3 --shot out.png   # 3 秒で閉じ、直前に画面を保存

マウス: 右ドラッグ 回転 / ホイール ズーム / 中ドラッグ 移動。
キー: W 歩く / T 話す / A 剣を振る・杖を掲げる / S フリーズ / C solace で回復中（それぞれ切り替え）
"""

from __future__ import annotations

import argparse
import math
import time
from types import SimpleNamespace

from ursina import EditorCamera, Entity, Text, Ursina, Vec3, application, camera, color, scene, window

from core.config import ROOT, load_config
from memory.db import DB
from sim.world import pick_roles
from viewer.app import ICE, _rgb, setup_japanese_font, setup_lights
from viewer.looks import Look, build_looks
from viewer.models import ACCESSORY_TYPES, HAIR_STYLES
from viewer.poly_character import Character
from viewer.raider_figure import RaiderModel
from viewer.weapons import Staff, Sword

STEP = 2.4   # 並べる間隔


def parse_ids(text: str) -> list[int]:
    ids = []
    for part in text.split(","):
        a, _, b = part.partition("-")
        ids += range(int(a), int(b or a) + 1)
    return ids


def catalog(lc) -> list[tuple[str, Look, str | None]]:
    """髪型 6 種と装飾品 4 種を、同じ色で並べる。最後に剣の戦士・杖のヒーラー"""
    base = dict(body_style="dress", hair_color="#5a3a2c", eye_color="#2c1f3f", clothing_color="#8a6bb0")
    items = [(hs, Look(hair_style=hs, **base), None) for hs in HAIR_STYLES]
    for kind in ACCESSORY_TYPES:
        acc = [(kind, "#7cb0d9", "both" if kind == "pin" else None)]
        items.append((kind, Look(hair_style="bob", accessories=acc, **base), None))
    items.append(("box", Look(hair_style="cap", **{**base, "body_style": "box"}), None))
    items.append(("戦士（剣）", Look(hair_style="cap", **{**base, "body_style": "box"}), "sword"))
    items.append(("ヒーラー（杖）", Look(hair_style="medium", **base), "staff"))
    return items


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", default="0-9", help="並べる住人の id（例: 0-9 / 3,7,12-14）")
    ap.add_argument("--catalog", action="store_true", help="選べる髪型・装飾品の一覧を並べる")
    ap.add_argument("--raider", action="store_true", help="悪の魔物も並べる（住人との大きさ比べ）")
    ap.add_argument("--roles", action="store_true", help="戦士とヒーラー全員を並べる（--ids の代わり）")
    ap.add_argument("--weapons", action="store_true", help="剣と杖だけを大きく並べる")
    ap.add_argument("--pose", default="",
                    help="最初から入れておく動き（walk / talk / action / freeze / solace をカンマ区切り）")
    ap.add_argument("--seconds", type=float, default=0, help="この秒数で閉じる")
    ap.add_argument("--shot", default=None, help="閉じる直前に画面を保存するパス（--seconds と併用）")
    ap.add_argument("--db", default=None, help="既定は config.toml の [world] db_file")
    ap.add_argument("--config", default=str(ROOT / "config.toml"))
    args = ap.parse_args()

    cfg = load_config(args.config)
    lc = cfg.look
    if args.weapons:
        show_weapons(cfg, args)
        return
    if args.catalog:
        items = catalog(lc)
    else:
        db = DB(args.db or str(ROOT / cfg.world.db_file))
        names = {r["id"]: r["name"] for r in db.load_npcs()}
        db.close()
        warriors, healers = pick_roles(cfg, cfg.world.npc_count)
        ids = sorted(warriors + healers) if args.roles else parse_ids(args.ids)
        npcs = [SimpleNamespace(id=i, name=names.get(i, f"住人{i}")) for i in ids]
        looks = build_looks(lc, cfg.world.seed, npcs)

        def held(i):
            return "sword" if i in warriors else "staff" if i in healers else None

        role = {"sword": " 戦士", "staff": " ヒーラー", None: ""}
        items = [(f"{n.id} {n.name}{role[held(n.id)]}\n{looks[n.id].hair_style}", looks[n.id], held(n.id))
                 for n in npcs]

    app = Ursina(title="住人の見た目", borderless=False, size=(1600, 900), development_mode=False)
    setup_japanese_font()
    window.color = color.rgb(0.03, 0.05, 0.1)
    Entity(model="plane", scale=60, color=color.rgb(0.07, 0.13, 0.15), texture="white_cube",
           texture_scale=(30, 30), unlit=True)
    setup_lights()

    per_row = 7
    chars = []
    ices = []
    for i, (label, look, weapon) in enumerate(items):
        row, col = divmod(i, per_row)
        n_in_row = min(per_row, len(items) - row * per_row)
        x = (col - (n_in_row - 1) / 2) * STEP
        root = Entity(position=(x, 0, row * STEP * 1.6))
        ch = Character(
            parent=root,   # 正面は -Z（カメラ側）
            hair_style=look.hair_style, body_style=look.body_style,
            hair_color=_rgb(look.hair_color), eye_color=_rgb(look.eye_color),
            dress_color=_rgb(look.clothing_color), skin_color=_rgb(lc.skin_color),
            accessories=[(k, _rgb(c) if c else None, s) for k, c, s in look.accessories],
        )
        if weapon:
            ch.hold(weapon)
        ices.append(Entity(parent=root, model="cube", color=ICE, unlit=True, enabled=False,
                           scale=(1.25, 2.5, 1.0), y=1.2))
        Text(label, parent=root, y=2.75, scale=9, billboard=True, origin=(0, 0), color=color.rgba(1, 1, 1, 0.9))
        chars.append(ch)
    raider = None
    if args.raider:
        # 住人の列の左端に、住人の size_ratio 倍で置く（T で腕を前へ＝吸い取るポーズ）
        n_in_row = min(per_row, len(items))
        raider = RaiderModel(position=(-(n_in_row + 1.2) / 2 * STEP, 0.25, 0), scale=cfg.raider.size_ratio)
        Text(cfg.raider.name, parent=scene, position=(raider.x, 2.75 * cfg.raider.size_ratio + 0.3, 0), scale=9,
             billboard=True, origin=(0, 0), color=color.rgb(1, 0.4, 0.35))

    # EditorCamera はカメラを自分の子にして回転を 0 に戻す。見下ろしの角度と回転の中心は
    # EditorCamera 側に、引きの距離だけをカメラ（ローカル z）に持たせる
    rows = math.ceil(len(items) / per_row)
    camera.fov = 50
    camera.position = (0, 0, -19 - 3.0 * rows)
    ed = EditorCamera(rotation_speed=200, panning_speed=6)
    ed.position = (0, 1.0, (rows - 1) * STEP * 0.8)
    ed.rotation_x = ed.smoothing_helper.rotation_x = 24

    mode = {"walk": False, "talk": False, "action": False, "freeze": False, "solace": False}
    for name in filter(None, args.pose.split(",")):
        if name not in mode:
            raise SystemExit(f"--pose に使えるのは {', '.join(mode)}")
        mode[name] = True
    help_text = Text("", position=window.top_left + Vec3(0.02, -0.02, 0), scale=0.9)
    started = time.time()

    def refresh_help():
        on = [k for k, v in mode.items() if v]
        help_text.text = (f"W 歩く / T 話す / A 剣を振る・杖を掲げる / S フリーズ / C 回復中　"
                          f"いま: {'・'.join(on) or 'なし'}")

    refresh_help()

    def update():
        t = time.time()
        for i, ch in enumerate(chars):
            ices[i].enabled = mode["freeze"]
            if mode["freeze"]:
                ch.set_tint(0.85, 0.75, (0.8, 0.95, 1.25))
            elif mode["solace"]:
                ch.set_tint(1.0 + 0.25 * (0.5 + 0.5 * math.sin(t * 3 + i)), 0.0, (1.0, 0.92, 0.97))
            else:
                ch.set_tint(1.0)
            pose = None
            if mode["action"] and isinstance(ch.weapon, Sword):
                k = (t * 1.2 + i * 0.3) % 1.0   # 振り上げて振り下ろすをくり返す
                pose = 160 - 120 * min(1.0, k * 3.0) if k < 0.6 else 40 + 120 * (k - 0.6) / 0.4
            elif mode["action"] and isinstance(ch.weapon, Staff):
                pose = 150 + 6 * math.sin(t * 5)
            ch.set_arm_pose(pose)
            if isinstance(ch.weapon, Staff):
                ch.weapon.spin(t, 1.0 if mode["action"] else 0.0)
            rms = 0.1 + 0.1 * abs(math.sin(t * 14 + i))
            ch.animate(t, mode["talk"], rms, walk=t * 7 + i if mode["walk"] else None, asleep=mode["freeze"])
        if raider is not None:
            raider.y = 0.25 + math.sin(t * 2.2) * 0.1
            raider.set_arms(70 if mode["talk"] else 12)
        if args.seconds and t - started > args.seconds:
            if args.shot:
                from panda3d.core import Filename
                application.base.win.saveScreenshot(Filename.from_os_specific(args.shot))
            application.quit()

    def input(key):
        keymap = {"w": "walk", "t": "talk", "a": "action", "s": "freeze", "c": "solace"}
        if key in keymap:
            mode[keymap[key]] = not mode[keymap[key]]
            refresh_help()

    Entity(update=update, input=input)
    app.run()


def show_weapons(cfg, args):
    """剣と杖だけを住人の 2.5 倍で並べ、ゆっくり回す（形の確認用）"""
    app = Ursina(title="剣と杖", borderless=False, size=(1600, 900), development_mode=False)
    setup_japanese_font()
    window.color = color.rgb(0.03, 0.05, 0.1)
    Entity(model="plane", scale=40, color=color.rgb(0.07, 0.13, 0.15), texture="white_cube",
           texture_scale=(20, 20), unlit=True)
    setup_lights()
    sword, staff = Sword(scale=2.5), Staff(scale=2.0)
    sword.position = (-1.6, 1.6, 0)
    staff.position = (1.6, 0.55 * 2.0, 0)
    Text("剣（戦士）", parent=scene, position=(-1.6, 5.2, 0), scale=12, billboard=True, origin=(0, 0))
    Text("魔法の杖（ヒーラー）", parent=scene, position=(1.6, 0.6, -1.0), scale=12, billboard=True, origin=(0, 0))
    camera.fov = 50
    camera.position = (0, 3.2, -13)
    camera.look_at(Vec3(0, 3.0, 0))
    started = time.time()

    def update():
        t = time.time()
        sword.rotation_y = t * 30 % 360
        staff.rotation_y = -t * 30 % 360
        staff.spin(t, 0.5 + 0.5 * math.sin(t))
        if args.seconds and t - started > args.seconds:
            if args.shot:
                from panda3d.core import Filename
                application.base.win.saveScreenshot(Filename.from_os_specific(args.shot))
            application.quit()

    Entity(update=update)
    app.run()


if __name__ == "__main__":
    main()
