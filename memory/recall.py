"""
会話・判断のときに注入する記憶

1. 相手とのペア記憶（relations.summary）＋ 前に話したあとに思ったこと（要約の前の振り返り）
   ＋ 強い記憶（救助・励まし。要約から消えても必ず出す）
   ＋ 相手について噂で聞いたこと（beliefs。初対面でも入る＝会う前の先入観）
2. 相手が関わった最近の出来事
3. 自分の最近の出来事
4. 聞いた話（会話で伝わってきた救助の出来事）
5. 会話（say）のときだけ: ほかの住人についての自分の印象（relations ＋ 思ったこと）と、噂で聞いた話（beliefs）。
   話題にすると、聞き手の要約がそれを噂として取り出す（summarize.py）。移動意図には入れない
"""

from __future__ import annotations

from lang import t


def _rumor_line(world, b, with_about: bool) -> str:
    src = world.npcs[b["from_id"]].name
    return t("recall.rumor", about=t("recall.rumor_about", x=b["about"]) if with_about else "", text=b["text"], src=src)


def _thoughts(world, me, others: list[int]) -> dict[int, str]:
    """要約の前に書いた振り返り（summary_thought）のうち、相手ごとに最新のもの（[memory] thoughts が false なら入れない）"""
    return world.db.latest_thoughts(me.id, others) if world.cfg.memory.thoughts else {}


def pair_memory(world, me, partner) -> str:
    db = world.db
    rel = db.get_relation(me.id, partner.id)
    lines = []
    if rel is None:
        lines.append(t("recall.first_meet"))
    else:
        lines.append(rel["summary"] or t("recall.no_summary"))
        lines.append(t("recall.affinity", x=rel["affinity"]))
        thought = _thoughts(world, me, [partner.id]).get(partner.id)
        if thought:
            lines.append(t("recall.thought", x=thought))
    strong = db.pair_strong_texts(me.id, partner.id)
    if strong:
        lines.append(t("recall.strong"))
        lines += [f"- {x}" for x in strong]
    rumors = db.beliefs_about(me.id, partner.name, world.cfg.memory.rumors_about)
    if rumors:
        lines.append(t("recall.rumors_about", name=partner.name))
        lines += [_rumor_line(world, b, False) for b in rumors]
    return "\n".join(lines)


def heard_texts(world, me, limit: int) -> list[str]:
    """会話で聞いた救助の話（自分が当事者のものは除く）"""
    ids = [eid for eid in world.known.get(me.id, [])
           if me.id not in world.rescue_parties.get(eid, ())]
    texts = world.db.event_texts(ids[-limit:])
    return [texts[i] for i in ids[-limit:] if i in texts]


def others_memory(world, me, partner=None) -> str:
    cfg = world.cfg.memory
    db = world.db
    out = []
    if partner is not None:
        ev = db.recent_event_texts(partner.id, cfg.partner_events, exclude_with=me.id)
        if ev:
            out.append(t("recall.partner_events", name=partner.name) + "\n" + "\n".join(f"- {x}" for x in ev))
    mine = db.recent_event_texts(me.id, cfg.recent_events,
                                 exclude_with=partner.id if partner else None)
    if mine:
        out.append(t("recall.my_events") + "\n" + "\n".join(f"- {x}" for x in mine))
    heard = heard_texts(world, me, cfg.heard_events)
    if heard:
        out.append(t("recall.heard") + "\n" + "\n".join(f"- {x}" for x in heard))
    if partner is not None:
        out += talk_topics(world, me, partner)
    return "\n".join(out) or t("recall.nothing")


def talk_topics(world, me, partner) -> list[str]:
    """会話のときだけ入れる「ほかの住人の印象」と「噂で聞いた話」（相手と自分のことは除く）"""
    cfg, db, out = world.cfg.memory, world.db, []
    rels = [r for r in db.top_relations(me.id, cfg.known_others + 1)
            if r["b_id"] != partner.id and r["summary"]][:cfg.known_others]
    if rels:
        thoughts = _thoughts(world, me, [r["b_id"] for r in rels])
        out.append(t("recall.impressions") + "\n" + "\n".join(
            t("recall.impression", name=world.npcs[r["b_id"]].name, summary=r["summary"], affinity=r["affinity"])
            + (t("recall.impression_thought", x=thoughts[r["b_id"]]) if r["b_id"] in thoughts else "") for r in rels))
    rumors = db.recent_beliefs(me.id, cfg.heard_rumors, exclude=(me.name, partner.name), exclude_from=partner.id)
    if rumors:
        out.append(t("recall.rumors") + "\n" + "\n".join(_rumor_line(world, b, True) for b in rumors))
    return out
