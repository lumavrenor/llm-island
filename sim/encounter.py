"""
遭遇と会話セッション

- 毎フレーム、近くにいる「手の空いた」2 体を探す（空間グリッドで近傍だけ見る）
- 初めて距離 R 以内に入ったときに 1 回だけ会話開始の抽選（社交性で確率が上がる）
  外れたら miss_cooldown_sec のあいだ同じペアは抽選しない
- セッションは 2 体のみ。交互に発話し、1 発話＝1 リクエスト
"""

from __future__ import annotations

import math
from collections import defaultdict


class Session:
    def __init__(self, sid: int, a: int, b: int, first: int, spot: str, max_turns: int):
        self.id = sid
        self.a, self.b = a, b
        self.next_speaker = first
        self.spot = spot
        self.max_turns = max_turns
        self.lines: list[tuple[int, str]] = []         # (speaker_id, text)
        self.cheers: list[tuple[int, int]] = []        # (励ました, 励まされた)
        self.ended = False

    def partner_of(self, npc_id: int) -> int:
        return self.b if npc_id == self.a else self.a


class Grid:
    """一様グリッドの空間ハッシュ（毎フレーム作り直す。100 体なら十分軽い）"""

    def __init__(self, npcs, cell: float):
        self.cell = cell
        self.cells: dict[tuple[int, int], list] = defaultdict(list)
        for n in npcs:
            self.cells[(int(n.x // cell), int(n.z // cell))].append(n)

    def pairs_within(self, radius: float):
        """距離 radius 以内のペアを重複なく列挙（radius <= cell であること）"""
        r2 = radius * radius
        for (cx, cz), members in self.cells.items():
            for dx, dz in ((0, 0), (1, 0), (0, 1), (1, 1), (1, -1)):
                other = members if (dx, dz) == (0, 0) else self.cells.get((cx + dx, cz + dz))
                if not other:
                    continue
                for i, a in enumerate(members):
                    for b in (other[i + 1:] if other is members else other):
                        if (a.x - b.x) ** 2 + (a.z - b.z) ** 2 <= r2:
                            yield a, b


def separate(world, grid: Grid):
    """重なった NPC を押し離す（フリーズ中・詠唱中の NPC は動かさない）"""
    sep = world.cfg.move.separation
    for a, b in grid.pairs_within(sep):
        dx, dz = b.x - a.x, b.z - a.z
        d = math.hypot(dx, dz) or 0.01
        push = (sep - d) * 0.5
        ux, uz = dx / d, dz / d
        if not a.frozen and a.casting is None:
            a.x, a.z = world.clamp(a.x - ux * push, a.z - uz * push)
        if not b.frozen and b.casting is None:
            b.x, b.z = world.clamp(b.x + ux * push, b.z + uz * push)


def check_encounters(world, grid: Grid):
    ecfg = world.cfg.encounter
    for a, b in grid.pairs_within(ecfg.radius):
        if not (a.free and b.free):
            continue
        key = (min(a.id, b.id), max(a.id, b.id))
        if world.now < world.pair_cooldown.get(key, 0.0):
            continue
        social = (a.seed["sociability"] + b.seed["sociability"]) / 2
        if world.rng.random() > ecfg.base_chance + ecfg.social_chance * social:
            world.pair_cooldown[key] = world.now + ecfg.miss_cooldown_sec
            continue
        world.start_session(a, b)
