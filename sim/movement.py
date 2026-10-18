"""
移動意図 → 実際の移動

LLM が決めるのは Intent（どこへ・誰を・どの速さで）だけ。毎フレームの歩き方は
ここでプログラムが決める。性格の「移動の癖」もここで反映する。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import lang
from llm.schemas import ALL_INTENTS, PACES

ARRIVE_DIST = 1.0


@dataclass
class Intent:
    kind: str
    target: str = ""
    pace: str = "normal"
    manner: str = ""
    duration: float = 30.0
    started: float = 0.0
    # --- 実行時に決まるもの ---
    target_id: int | None = None
    waypoints: list[tuple[float, float]] = field(default_factory=list)
    patrol: list[str] = field(default_factory=list)
    anchor: tuple[float, float] = (0.0, 0.0)
    refresh_at: float = 0.0


def validate(data: dict, npc, world) -> tuple[Intent, bool]:
    """LLM の出力を検証して Intent にする。不正なら wander にフォールバック（2 つめの値が False）"""
    kind = data.get("intent")
    pace = data.get("pace") if data.get("pace") in PACES else "normal"
    target = str(data.get("target") or "").strip()
    manner = lang.clip(str(data.get("manner") or ""), 40)
    try:
        duration = float(max(10, min(90, int(data.get("duration_sec", 30)))))
    except (TypeError, ValueError):
        duration = 30.0
    ok = kind in ALL_INTENTS
    if kind == "fight" and not npc.warrior:
        ok = False   # 戦えるのは戦士だけ
    if kind == "rescue":
        other = world.npc_by_name.get(target)
        # 癒せるのはヒーラーだけ。相手はフリーズしている住人（返答を待つ間に誰かが癒していたら無効）
        ok = npc.healer and other is not None and other.frozen
    if kind in ("fight", "flee") and not (world.raider.present and world.raider.hp > 0):
        ok = False   # 返答を待つ間に、悪が倒れた・去った
    if kind == "go_spot" and target not in world.spot_by_name:
        ok = False
    if kind in ("seek", "follow", "avoid"):
        other = world.npc_by_name.get(target)
        ok = ok and other is not None and other.id != npc.id
    if not ok:
        return Intent("wander", "", pace, manner, duration), False
    return Intent(kind, target, pace, manner, duration), True


def start(intent: Intent, npc, world):
    """意図の実行を始める（目的地や経路をここで決める）"""
    rng = world.rng
    intent.started = world.now
    intent.anchor = (npc.x, npc.z)
    if intent.kind == "go_spot":
        spot = world.spot_by_name[intent.target]
        r = spot.radius * (0.4 if spot.kind == "solace" else 0.7)
        goal = (spot.x + rng.uniform(-r, r), spot.z + rng.uniform(-r, r))
        intent.waypoints = _habit_detour(npc, world, goal) + [goal]
    elif intent.kind in ("seek", "follow", "avoid", "rescue"):
        intent.target_id = world.npc_by_name[intent.target].id
    elif intent.kind == "patrol":
        fav = npc.seed["favorite_spot"]
        others = [s.name for s in world.spots if s.kind == "place" and s.name != fav]
        intent.patrol = [fav] + rng.sample(others, k=min(2, len(others)))
        intent.waypoints = [_spot_point(world, intent.patrol[0])]
    elif intent.kind == "wander":
        intent.waypoints = [_wander_point(intent.anchor, world)]


def _spot_point(world, name):
    s = world.spot_by_name[name]
    r = s.radius * 0.7
    return (s.x + world.rng.uniform(-r, r), s.z + world.rng.uniform(-r, r))


def _wander_point(anchor, world, radius=10.0):
    a = world.rng.uniform(0, math.tau)
    d = world.rng.uniform(2, radius)
    return world.clamp(anchor[0] + math.cos(a) * d, anchor[1] + math.sin(a) * d)


def _habit_detour(npc, world, goal) -> list[tuple[float, float]]:
    """「寄り道」「外周」の癖：目的地の手前に経由地をはさむ"""
    habit = npc.seed["move_habit"]
    mx, mz = (npc.x + goal[0]) / 2, (npc.z + goal[1]) / 2
    if lang.habit(habit, "detour"):
        a = world.rng.uniform(0, math.tau)
        return [world.clamp(mx + math.cos(a) * 12, mz + math.sin(a) * 12)]
    if lang.habit(habit, "outer"):
        d = math.hypot(mx, mz) or 1.0
        edge = world.half * 0.85
        return [world.clamp(mx / d * edge, mz / d * edge)]
    return []


def step(npc, world, dt: float) -> tuple[float, bool]:
    """1 フレーム分歩く。戻り値は（移動距離, 到着したか）"""
    it = npc.intent
    goal, arrived, stop_dist = None, False, ARRIVE_DIST

    match it.kind:
        case "go_spot" | "wander" | "patrol":
            goal = it.waypoints[0] if it.waypoints else None
        case "seek":
            other = world.npcs[it.target_id]
            # 見えている間は本当の位置、見えないときは 8 秒おきに「噂の位置」を更新する
            if npc.dist_to(other) <= world.cfg.move.sight or world.now >= it.refresh_at:
                it.anchor = (other.x, other.z)
                it.refresh_at = world.now + 8.0
            goal, stop_dist = it.anchor, world.cfg.encounter.radius * 0.8
        case "follow":
            other = world.npcs[it.target_id]
            goal, stop_dist = (other.x, other.z), 3.0
        case "avoid":
            other = world.npcs[it.target_id]
            dx, dz = npc.x - other.x, npc.z - other.z
            d = math.hypot(dx, dz)
            if d > 25.0:
                return 0.0, True
            d = d or 1.0
            goal, stop_dist = world.clamp(npc.x + dx / d * 6, npc.z + dz / d * 6), 0.5
        case "rescue":
            target = world.npcs[it.target_id]
            if not target.frozen:
                return 0.0, True   # 着く前に、ほかのヒーラーが癒していた
            # 救助判断（heal.check_rescues）は rescue_radius に入った時点で始まる
            goal, stop_dist = (target.x, target.z), world.cfg.npc.rescue_radius * 0.7
        case "fight":
            r = world.raider
            if not (r.present and r.hp > 0):
                return 0.0, True   # 悪が倒れた・去った
            npc.face(r)
            # 射程の 7 割まで近づいて踏みとどまる（撃つのは raid.warrior_attacks）
            goal, stop_dist = (r.x, r.z), world.cfg.warrior.attack_range * 0.7
        case "flee":
            r = world.raider
            if not r.present:
                return 0.0, True
            dx, dz = npc.x - r.x, npc.z - r.z
            d = math.hypot(dx, dz)
            if d > world.cfg.raider.safe_distance:
                return 0.0, True   # 十分に離れた
            d = d or 1.0
            goal, stop_dist = world.clamp(npc.x + dx / d * 6, npc.z + dz / d * 6), 0.5
        case "wait":
            return 0.0, False

    if goal is None:
        return 0.0, True

    # 「立ち止まって観察する」癖：12 秒周期で 2 秒止まる
    if lang.habit(npc.seed["move_habit"], "pause") and (world.now + npc.id * 1.7) % 12.0 < 2.0:
        return 0.0, False

    dx, dz = goal[0] - npc.x, goal[1] - npc.z
    dist = math.hypot(dx, dz)
    if dist <= stop_dist:
        if it.kind in ("go_spot", "wander", "patrol") and it.waypoints:
            it.waypoints.pop(0)
            if it.kind == "wander":
                it.waypoints.append(_wander_point(it.anchor, world))
            elif it.kind == "patrol":
                it.patrol.append(it.patrol.pop(0))
                it.waypoints.append(_spot_point(world, it.patrol[0]))
            arrived = it.kind == "go_spot" and not it.waypoints
        elif it.kind in ("seek", "rescue"):
            arrived = True
        return 0.0, arrived

    speed = getattr(world.cfg.move, f"speed_{it.pace}")
    step_len = min(dist, speed * dt)
    ux, uz = dx / dist, dz / dist
    # 「蛇行」の癖：進行方向に直交する揺れを足す
    if lang.habit(npc.seed["move_habit"], "zigzag"):
        wob = math.sin(world.now * 1.3 + npc.id) * 0.6
        ux, uz = ux - uz * wob, uz + ux * wob
        n = math.hypot(ux, uz)
        ux, uz = ux / n, uz / n
    npc.x, npc.z = world.clamp(npc.x + ux * step_len, npc.z + uz * step_len)
    npc.heading = math.degrees(math.atan2(ux, uz))
    return step_len, False
