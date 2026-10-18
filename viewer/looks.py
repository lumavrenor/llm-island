"""
住人の見た目（髪型・色・装飾品）を決める（ursina 非依存）

100 体ぶんを手で書くのは大変なので、既定は乱数で決める。種は world.seed と NPC の id なので、
何度起動しても同じ住人は同じ見た目になる。色は llm-radio-daemon の出演者と同じく
OKLCH（L=明度・C=彩度・H=色相）の「トーン段」に載せ、色相だけを個性にする。

個別に決めたい住人は config.toml の [[look.npc]] に id か name で書く（キーは
llm-radio-daemon の [[cast]] と同じ。書いた項目だけ上書きされる）。
"""

from __future__ import annotations

import logging
import math
import random
import re
from dataclasses import dataclass, field

from viewer.models import ACCESSORY_SIDES, ACCESSORY_TYPES, BODY_STYLES, HAIR_STYLES, MODEL_PRESETS

logger = logging.getLogger(__name__)

OVERRIDE_KEYS = {"id", "name", "model", "hair_style", "body_style", "hair_color", "eye_color",
                 "clothing_color", "accessory"}
HEX = re.compile(r"#[0-9a-fA-F]{6}")


@dataclass
class Look:
    hair_style: str
    body_style: str
    hair_color: str        # "#rrggbb"
    eye_color: str
    clothing_color: str
    accessories: list[tuple[str, str | None, str | None]] = field(default_factory=list)  # (type, 色, side)


# ---------- 色 ----------

def oklch_to_hex(lightness: float, chroma: float, hue: float) -> str:
    """OKLCH → "#rrggbb"。sRGB に収まらない色は彩度だけ落として収める"""
    for _ in range(40):
        rgb = _oklch_to_srgb(lightness, chroma, hue)
        if all(-1e-4 <= v <= 1 + 1e-4 for v in rgb):
            break
        chroma *= 0.92
    return "#" + "".join(f"{round(min(1.0, max(0.0, v)) * 255):02x}" for v in rgb)


def _oklch_to_srgb(lightness: float, chroma: float, hue: float) -> tuple[float, float, float]:
    a, b = chroma * math.cos(math.radians(hue)), chroma * math.sin(math.radians(hue))
    l_ = (lightness + 0.3963377774 * a + 0.2158037573 * b) ** 3
    m_ = (lightness - 0.1055613458 * a - 0.0638541728 * b) ** 3
    s_ = (lightness - 0.0894841775 * a - 1.2914855480 * b) ** 3
    lin = (4.0767416621 * l_ - 3.3077115913 * m_ + 0.2309699292 * s_,
           -1.2684380046 * l_ + 2.6097574011 * m_ - 0.3413193965 * s_,
           -0.0041960863 * l_ - 0.7034186147 * m_ + 1.7076147010 * s_)
    return tuple(12.92 * v if v <= 0.0031308 else 1.055 * max(v, 0.0) ** (1 / 2.4) - 0.055 for v in lin)


def hex_to_rgb(value: str) -> tuple[float, float, float]:
    return tuple(int(value[i:i + 2], 16) / 255 for i in (1, 3, 5))


# ---------- 既定（乱数） ----------

def _random_look(lc, world_seed: int, npc_id: int) -> Look:
    rng = random.Random(f"look-{world_seed}-{npc_id}")
    hue = rng.uniform(0, 360)
    hair_c = lc.gray_chroma if rng.random() < lc.hair_gray_chance else lc.hair_chroma
    eye_c = lc.gray_chroma if hair_c == lc.gray_chroma else lc.eye_chroma
    cloth = oklch_to_hex(rng.choice(lc.clothing_lightness), rng.choice(lc.clothing_chroma), rng.uniform(0, 360))
    accessories = []
    if rng.random() < lc.accessory_chance:
        kind = rng.choice(lc.accessories)
        # 色は服と揃えるか、髪色（None = poly_character 側の既定）か
        tint = rng.choice([cloth, None])
        side = rng.choice(["left", "right", "both"]) if kind == "pin" else None
        accessories.append((kind, tint, side))
    return Look(
        hair_style=rng.choice(lc.hair_styles),
        body_style=rng.choice(lc.body_styles),
        hair_color=oklch_to_hex(rng.choice(lc.hair_lightness), hair_c, hue),
        eye_color=oklch_to_hex(lc.eye_lightness, eye_c, hue),   # 目の色相は髪と同じ
        clothing_color=cloth,
        accessories=accessories,
    )


# ---------- 個別の上書き ----------

def _check(cond: bool, where: str, msg: str):
    if not cond:
        raise SystemExit(f"config.toml [[look.npc]] {where}: {msg}")


def _apply_override(look: Look, ov: dict):
    if "model" in ov:
        preset = MODEL_PRESETS[ov["model"]]
        look.hair_style, look.body_style = preset["hair_style"], preset["body_style"]
    for key in ("hair_style", "body_style", "hair_color", "eye_color", "clothing_color"):
        if key in ov:
            setattr(look, key, ov[key])
    if "accessory" in ov:
        look.accessories = [(a["type"], a.get("color"), a.get("side")) for a in ov["accessory"]]


def _validate_override(ov: dict, where: str):
    _check(not (set(ov) - OVERRIDE_KEYS), where, f"未知のキー {sorted(set(ov) - OVERRIDE_KEYS)}"
           f"（使えるのは {', '.join(sorted(OVERRIDE_KEYS))}）")
    _check(("id" in ov) != ("name" in ov), where, "id か name のどちらか一方で住人を指定してください")
    if "model" in ov:
        _check(ov["model"] in MODEL_PRESETS, where, f"model は {', '.join(MODEL_PRESETS)} のいずれか")
    if "hair_style" in ov:
        _check(ov["hair_style"] in HAIR_STYLES, where, f"hair_style は {', '.join(HAIR_STYLES)} のいずれか")
    if "body_style" in ov:
        _check(ov["body_style"] in BODY_STYLES, where, f"body_style は {', '.join(BODY_STYLES)} のいずれか")
    for key in ("hair_color", "eye_color", "clothing_color"):
        if key in ov:
            _check(isinstance(ov[key], str) and HEX.fullmatch(ov[key]), where, f'{key} は "#rrggbb" で')
    for a in ov.get("accessory", []):
        _check(isinstance(a, dict) and a.get("type") in ACCESSORY_TYPES, where,
               f"accessory の type は {', '.join(ACCESSORY_TYPES)} のいずれか（{a!r}）")
        _check(not (set(a) - {"type", "color", "side"}), where, f"accessory に未知のキー（{a!r}）")
        if "color" in a:
            _check(isinstance(a["color"], str) and HEX.fullmatch(a["color"]), where,
                   f'accessory の color は "#rrggbb" で（{a!r}）')
        if "side" in a:
            _check(a["side"] in ACCESSORY_SIDES, where, f"accessory の side は {', '.join(ACCESSORY_SIDES)}")


def _as_dict(value):
    """config.py の SimpleNamespace を dict に戻す"""
    if isinstance(value, list):
        return [_as_dict(v) for v in value]
    if hasattr(value, "__dict__"):
        return {k: _as_dict(v) for k, v in vars(value).items()}
    return value


def validate_config(lc):
    """[look] の乱数側の表を確認する（起動時に 1 回）"""
    for s in lc.hair_styles:
        _check(s in HAIR_STYLES, "hair_styles", f"未知の髪型 {s!r}（{', '.join(HAIR_STYLES)}）")
    for s in lc.body_styles:
        _check(s in BODY_STYLES, "body_styles", f"未知の胴体 {s!r}（{', '.join(BODY_STYLES)}）")
    for s in lc.accessories:
        _check(s in ACCESSORY_TYPES, "accessories", f"未知の装飾品 {s!r}（{', '.join(ACCESSORY_TYPES)}）")


def build_looks(lc, world_seed: int, npcs) -> dict[int, Look]:
    """全住人の見た目を決める。npcs は id と name を持つもの（sim.npc.Npc）"""
    validate_config(lc)
    looks = {n.id: _random_look(lc, world_seed, n.id) for n in npcs}
    by_name = {n.name: n.id for n in npcs}
    for i, ov in enumerate(_as_dict(getattr(lc, "npc", []))):
        where = f"#{i + 1}（{ov.get('id', ov.get('name'))}）"
        _validate_override(ov, where)
        npc_id = ov["id"] if "id" in ov else by_name.get(ov["name"])
        if npc_id not in looks:
            logger.warning("[[look.npc]] %s に当たる住人がいません（無視します）", where)
            continue
        _apply_override(looks[npc_id], ov)
    return looks
