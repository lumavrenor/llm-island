"""
プロンプト組み立て

並び順は固定（同じ NPC のリクエストが同じ前置きを共有するように）:
  1. 世界ルール（全員共通）       … system
  2. 自分の性格                    … system
  3. 相手とのペア記憶              … user
  4. 現在の状況                    … user
  5. この会話の直近の数往復         … user
  6. 指示（返す JSON の説明）       … user

悪の魔物（raider_messages）だけは住人と別の system を使う（世界を悪の視点で書く）。
数値（HP の最大・詠唱の秒数など）は cfg から取る（コード側に値を持たない）。
文そのものは言語ごとの表（lang/ja.py・lang/en.py）にある。
"""

from __future__ import annotations

import lang
from lang import t
from llm import schemas


def world_rules(cfg) -> str:
    spots, nc = cfg.world.spots, cfg.npc
    return t("rules", max_hp=nc.max_hp, max_heart=nc.max_heart, fear_heart=nc.fear_heart,
             solaces=lang.sep().join(s.name for s in spots if s.kind == "solace"),
             places=lang.sep().join(s.name for s in spots if s.kind == "place"))


def persona_block(npc, cfg) -> str:
    p, s = npc.persona, npc.seed
    lines = [t("persona.name", x=npc.name)]
    if lang.data("uses_first_person"):
        lines.append(t("persona.first_person", x=p.get("first_person", t("persona.first_person_default"))))
    lines += [
        t("persona.tone", x=s["tone"]),
        t("persona.catchphrase", x=p.get("catchphrase", "")),
        t("persona.background", x=p.get("background", "")),
        t("persona.likes", x=p.get("likes", "")),
        t("persona.dislikes", x=p.get("dislikes", "")),
        t("persona.goal", x=p.get("goal", "")),
        *([t("persona.help_view", x=p["help_view"])] if p.get("help_view") else []),
        t("persona.favorite_spot", x=s["favorite_spot"]),
        t("persona.traits", **s),
        t("persona.boot_cycles", x=s["boot_cycles"]),
    ]
    samples = p.get("sample_lines") or []
    if samples:
        lines.append(t("persona.samples") + " / ".join(t("persona.sample", x=x) for x in samples[:3]))
    if npc.warrior:
        lines.append(t("persona.warrior"))
    if npc.healer:
        lines.append(t("persona.healer", cast_sec=cfg.healer.cast_sec))
    return "\n".join(lines)


def _system(npc, cfg) -> dict:
    return {"role": "system", "content": world_rules(cfg) + "\n\n" + persona_block(npc, cfg)}


def say_messages(npc, partner, cfg, pair_memory: str, situation: str,
                 dialogue: list[tuple[str, str]], rescued_by: str | None) -> list[dict]:
    talk = "\n".join(f"{name}: {text}" for name, text in dialogue) or t("say.no_talk")
    note = t("say.rescued", name=rescued_by) if rescued_by else ""
    # 噂話をしてもいいと伝える（[memory] gossip）。材料は記憶の「ほかの住人の印象」「噂で聞いた話」（recall.talk_topics）
    gossip = t("say.gossip") if cfg.memory.gossip else ""
    user = t("say.user", partner=partner.name, pair_memory=pair_memory, situation=situation, talk=talk,
             me=npc.name, note=note, gossip=gossip)
    return [_system(npc, cfg), {"role": "user", "content": user}]


def intent_messages(npc, cfg, memory: str, situation: str, reason: str, raid_seen: bool) -> list[dict]:
    kinds = schemas.intent_kinds(npc.warrior, npc.healer, raid_seen)
    extra = "".join(t(f"intent.{k}") for k in ("rescue", "flee", "fight") if k in kinds)
    user = t("intent.user", memory=memory, situation=situation, reason=reason, kinds=" / ".join(kinds),
             extra=extra, names=lang.sep().join(s.name for s in cfg.world.spots),
             solaces=lang.sep().join(s.name for s in cfg.world.spots if s.kind == "solace"),
             rescue_target=t("intent.rescue_target") if "rescue" in kinds else "")
    return [_system(npc, cfg), {"role": "user", "content": user}]


def rescue_messages(npc, target, cfg, pair_memory: str, situation: str) -> list[dict]:
    """ヒーラーの救助判断（フリーズした住人のそばに来た）"""
    user = t("rescue.user", target=target.name, pair_memory=pair_memory, situation=situation,
             cast_sec=cfg.healer.cast_sec)
    return [_system(npc, cfg), {"role": "user", "content": user}]


def raider_messages(cfg, memories: list[str], situation: str, reason: str) -> list[dict]:
    """悪の魔物の判断（sim/raid.py）。住人とは別の system（世界を悪の視点で書く）"""
    rc, wc, hc, nc = cfg.raider, cfg.warrior, cfg.healer, cfg.npc
    system = t("raider.system", name=rc.name, strike_cooldown=rc.strike_cooldown_sec, strike_damage=rc.strike_damage,
               max_hp=nc.max_hp, give_up=rc.give_up_sec, warriors=wc.count, attack_range=wc.attack_range,
               attack_damage=wc.attack_damage, healers=hc.count, cast_sec=hc.cast_sec,
               max_stay=rc.max_stay_sec, victims=rc.victims)
    past = "\n".join(f"- {x}" for x in memories) or t("raider.no_past")
    user = t("raider.user", past=past, situation=situation, reason=reason,
             actions=" / ".join(schemas.RAIDER_ACTIONS))
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def summary_messages(npc, partner, cfg, old_summary: str, affinity: int,
                     dialogue: list[tuple[str, str]], cheers: str) -> list[dict]:
    talk = "\n".join(f"{name}: {text}" for name, text in dialogue)
    user = t("summary.user", partner=partner.name, old=old_summary or t("summary.no_old"), affinity=affinity,
             talk=talk, cheers=cheers, me=npc.name, heard_max=cfg.memory.heard_max)
    return [_system(npc, cfg), {"role": "user", "content": user}]


def persona_messages(seed: dict, name: str, cfg) -> list[dict]:
    user = t("persona_gen.user", name=name, **seed)
    return [{"role": "system", "content": world_rules(cfg)}, {"role": "user", "content": user}]
