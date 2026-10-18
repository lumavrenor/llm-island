"""
会話後の要約

会話が終わると、参加者それぞれの視点で要約リクエストを 1 件ずつ作る。
要約は NPC の行動を止めないので、同じウェーブに行動リクエストと一緒に乗せてよい。
結果は relations.summary と affinity に反映する。
返答の先頭の thought（心の中の振り返り）は、要約と好感度を決める前に考えさせるためのもの（CoT）。
events に summary_thought として残す。次の会話のペア記憶と「ほかの住人の印象」に入る（recall.py。[memory] thoughts）。

あわせて、相手が話した「ほかの住人・場所」の話（heard）を噂として beliefs に貯める。
LLM が作り話を混ぜないよう、名前が相手のセリフに実際に出ているものだけ採る。
"""

from __future__ import annotations

import lang
from lang import t
from llm import prompts, schemas
from llm.client import LLMRequest, LLMResult


def build_request(world, npc, session) -> LLMRequest:
    partner = world.npcs[session.partner_of(npc.id)]
    rel = world.db.get_relation(npc.id, partner.id)
    old = rel["summary"] if rel else ""
    affinity = rel["affinity"] if rel else 0
    dialogue = [(world.npcs[sid].name, text) for sid, text in session.lines]
    cheers = "\n".join(t("summary.cheer", a=world.npcs[a].name, b=world.npcs[b].name) for a, b in session.cheers)
    msgs = prompts.summary_messages(npc, partner, world.cfg, old, affinity, dialogue, cheers)
    partner_lines = [_without_raider(world, text) for sid, text in session.lines if sid == partner.id]
    mentioned = [n for n in list(world.npc_by_name) + list(world.spot_by_name)
                 if n not in (npc.name, partner.name) and any(lang.mentions(n, x) for x in partner_lines)]
    return LLMRequest("summary", npc.id, msgs, schemas.SUMMARY, 420,
                      meta={"partner_id": partner.id, "partner_name": partner.name,
                            "old_summary": old, "lines": len(session.lines), "session_id": session.id,
                            "partner_lines": partner_lines, "mentioned": mentioned})


def _without_raider(world, text: str) -> str:
    """悪の魔物の名前を消す。名前の一部が住人と同じでも（「ヤミノイズ」と住人「ノイズ」のように）当たらないように"""
    return text.replace(world.raider.name, "")


def resolve_name(world, about: str) -> str | None:
    """LLM が書いた about を住人か場所の名前に直す（敬称を外す。完全一致がなければ、含まれる最長の名前）。
    悪の魔物の話なら None（噂にするのは住人と場所だけ。名前の一部が住人と同じでも取り違えない）。
    英語は大文字小文字を区別しない（"the data spring" も場所の名前に直す）"""
    about = about.strip()
    for h in lang.data("honorific_prefixes"):
        about = about.removeprefix(h)
    for h in lang.data("honorific_suffixes"):
        about = about.removesuffix(h)
    names = list(world.npc_by_name) + list(world.spot_by_name) + [world.raider.name]
    exact = [n for n in names if n.lower() == about.lower()]
    hits = exact or [n for n in names if lang.mentions(n, about)]
    name = max(hits, key=len) if hits else None
    return None if name == world.raider.name else name


def apply_result(world, res: LLMResult):
    npc = world.npcs[res.req.npc_id]
    meta = res.req.meta
    partner_id = meta["partner_id"]
    if not res.ok:
        return  # 失敗したら前の要約のまま
    summary = lang.clip(str(res.data.get("summary", "")), 120)
    try:
        delta = max(-3, min(3, int(res.data.get("affinity_delta", 0))))
    except (TypeError, ValueError):
        delta = 0
    affinity = world.db.update_relation(npc.id, partner_id, summary, delta)
    thought = lang.clip(str(res.data.get("thought", "")).strip(), 80)
    if thought:
        world.db.add_event("summary_thought", npc.id, partner_id, "", thought,
                           session_id=meta["session_id"], affinity_delta=delta)
    if abs(delta) >= 2:
        world.emit("affinity", npc=npc.id, partner=partner_id, delta=delta, affinity=affinity)
    _apply_heard(world, npc, world.npcs[partner_id], res.data.get("heard"), meta)


def _apply_heard(world, npc, partner, heard, meta):
    if not isinstance(heard, list):
        return
    taken: set[str] = set()
    for item in heard:
        if len(taken) >= world.cfg.memory.heard_max:
            break
        if not isinstance(item, dict):
            continue
        about = resolve_name(world, str(item.get("about", "")))
        note = lang.clip(str(item.get("note", "")).strip(), 40)
        # 自分・相手のこと、同じ要約での重複、相手のセリフに名前が出ていない話（作り話）は採らない
        if (about is None or not note or about in (npc.name, partner.name) or about in taken
                or not any(lang.mentions(about, x) for x in meta["partner_lines"])):
            continue
        try:
            feel = max(-2, min(2, int(item.get("feel", 0))))
        except (TypeError, ValueError):
            feel = 0
        taken.add(about)
        # 話し手がこの会話より前に同じ相手・場所について噂を持っていたら、その続き（伝言の鎖）。
        # なければ話し手が自分で知っていた話（同じ会話で 2 体が互いに取り出した噂は、こだまなので鎖にしない）
        parent = world.db.latest_belief(partner.id, about, before_session=meta["session_id"])
        hops = parent["hops"] + 1 if parent else 1
        about_npc = world.npc_by_name.get(about)
        bid = world.db.add_belief(npc.id, about, about_npc.id if about_npc else None, note, feel,
                                  partner.id, meta["session_id"], hops, parent["id"] if parent else None)
        world.emit("hearsay", npc=npc.id, src=partner.id, about=about, text=note, feel=feel, hops=hops, belief=bid)
