"""
DB の集計

    python tools/report.py               # world.db を集計（[locale] lang の DB。英語は world_en.db）
    python tools/report.py --db other.db

- 会話・発話・励まし・救助の件数（2026-10-13 から電力を廃止。救助はヒーラーの杖でフリーズを解いたもの）
- 救助の出来事ごとに「何体が知っているか」（当事者 2 体 + 会話で伝わった数、最大ホップ数）
- 救助された側が、その後の発話で救助者の名前を挙げたか
- 悪の魔物の襲来ごとの結果（撃退したか、被害の数、戦士の命中、去った理由）
- 悪の魔物の判断（LLM が誰を狙ったか・いつ去ると決めたか）
- 噂（beliefs）：段数ごとの件数、よく噂される住人と会った住人からの好感度、会う前に噂を聞いていた初対面、いちばん長い伝言の鎖
"""

import argparse
import json
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # python tools/report.py で起動しても core/・lang/ などを import できるように

import lang
from core.config import ROOT, load_config


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=None, help="既定は config.toml の [world] db_file")
    ap.add_argument("--config", default=str(ROOT / "config.toml"))
    ap.add_argument("--top", type=int, default=15)
    args = ap.parse_args()
    cfg = load_config(args.config)   # 名前の見つけ方（lang.mentions）も言語で決まる
    args.db = args.db or str(ROOT / cfg.world.db_file)
    c = sqlite3.connect(args.db)
    name = dict(c.execute("SELECT id, name FROM npc"))
    q = lambda sql, *a: c.execute(sql, a).fetchone()[0]

    kind_count = lambda k: q("SELECT COUNT(*) FROM events WHERE kind=?", k)
    print(f"住人 {len(name)} / 会話 {q('SELECT COUNT(*) FROM sessions')} / "
          f"発話 {q('SELECT COUNT(*) FROM utterances')} / 励まし {kind_count('cheer')} / "
          f"救助（杖） {kind_count('rescue')} / フリーズ {kind_count('frozen')}")

    # 救助の伝播
    rescues = c.execute("SELECT id, actor_id, target_id, t FROM events WHERE kind='rescue' ORDER BY id").fetchall()
    know = defaultdict(list)
    for npc_id, event_id, via, src in c.execute(
            "SELECT npc_id, event_id, via_session_id, from_id FROM knowledge ORDER BY t"):
        know[event_id].append((npc_id, via, src))
    print(f"\n救助の伝播（知っている住人の数。当事者 2 体を含む）上位 {args.top} 件:")
    rows = []
    for eid, actor, target, t in rescues:
        hops = {}
        for npc_id, via, src in know[eid]:
            hops[npc_id] = 0 if via is None else hops.get(src, 0) + 1
        rows.append((len(know[eid]), max(hops.values(), default=0), eid, actor, target, t))
    for n, h, eid, actor, target, t in sorted(rows, reverse=True)[: args.top]:
        print(f"  #{eid:<5} {name.get(actor)} → {name.get(target)}  知っている {n} 体  最大ホップ {h}")
    if rows:
        spread = [n - 2 for n, *_ in rows]
        print(f"  平均: 当事者以外に {sum(spread) / len(spread):.1f} 体へ伝わった（最大 {max(spread)} 体）")

    # 救助された側が救助者の名前を挙げたか
    hit = total = 0
    for eid, actor, target, t in rescues:
        first = c.execute("SELECT text FROM utterances WHERE speaker_id=? AND t>? ORDER BY t LIMIT 3",
                          (target, t)).fetchall()
        if first:
            total += 1
            hit += any(lang.mentions(name.get(actor, "?"), r[0]) for r in first)
    if total:
        print(f"\n救助された側が、その後 3 発話以内に救助者の名前を挙げた: {hit}/{total}")

    # 噂（beliefs。会話の要約が取り出した「相手が話したほかの住人・場所の話」）
    beliefs = c.execute("SELECT id, npc_id, about, about_id, text, feel, from_id, hops, parent_id FROM beliefs "
                        "ORDER BY id").fetchall() if c.execute(
        "SELECT 1 FROM sqlite_master WHERE name='beliefs'").fetchone() else []
    if beliefs:
        by_id = {b[0]: b for b in beliefs}
        hops = Counter(b[7] for b in beliefs)
        print(f"\n噂 {len(beliefs)} 件（持っている住人 {len({b[1] for b in beliefs})} 体）"
              f" 段数ごと: " + "、".join(f"{h}段 {hops[h]}" for h in sorted(hops)))
        # 住人についての噂：何体が聞いたか、聞いた側の感じ方の平均、会ったことがある住人からの好感度の平均
        about = defaultdict(list)
        for b in beliefs:
            if b[3] is not None:
                about[b[3]].append(b)
        print(f"  よく噂される住人 上位 {args.top}（聞いた住人数 / 感じ方の平均 / 会った住人からの好感度の平均）:")
        for aid, bs in sorted(about.items(), key=lambda kv: -len({b[1] for b in kv[1]}))[: args.top]:
            aff = c.execute("SELECT AVG(affinity), COUNT(*) FROM relations WHERE b_id=?", (aid,)).fetchone()
            met = f"{aff[0]:+.1f}（{aff[1]} 体）" if aff[1] else "なし"
            print(f"  {name.get(aid)}: {len({b[1] for b in bs})} 体  {sum(b[5] for b in bs) / len(bs):+.2f}  {met}")
        # 会う前に噂を聞いていた初対面（噂が先入観になりえた場面）
        first = c.execute("SELECT MIN(id), a_id, b_id FROM sessions GROUP BY MIN(a_id, b_id), MAX(a_id, b_id)").fetchall()
        pre = 0
        for sid, a, b in first:
            pre += bool(c.execute("SELECT 1 FROM beliefs WHERE ((npc_id=? AND about_id=?) OR (npc_id=? AND about_id=?)) "
                                  "AND session_id<? LIMIT 1", (a, b, b, a, sid)).fetchone())
        print(f"  初対面の会話 {len(first)} 回のうち、どちらかが相手の噂を先に聞いていた: {pre} 回")
        # いちばん長い伝言の鎖（元の話がどう変わったか）
        chain, b = [], max(beliefs, key=lambda b: b[7])
        while b is not None:
            chain.append(b)
            b = by_id.get(b[8])
        print(f"  いちばん長い伝言の鎖（{chain[0][2]}について、{len(chain)} 段）:")
        for b in reversed(chain):
            print(f"    {name.get(b[6])} → {name.get(b[1])}: {b[4]}（{b[5]:+d}）")

    # 要約の前に書かせた心の中の振り返り（summary_thought。2026-10-13 から）
    thoughts = c.execute("SELECT actor_id, target_id, detail_json FROM events WHERE kind='summary_thought' "
                         "ORDER BY id DESC LIMIT ?", (args.top,)).fetchall()
    if thoughts:
        print(f"\n要約の前の振り返り {kind_count('summary_thought')} 件。新しい {len(thoughts)} 件:")
        for a, b, d in thoughts:
            d = json.loads(d)
            print(f"  {name.get(a)} → {name.get(b)}（好感度 {d['affinity_delta']:+d}）: {d['text']}")

    # 悪の魔物の襲来（raid_end に 1 回ごとのまとめがある）
    raids = [json.loads(r[0]) for r in c.execute("SELECT detail_json FROM events WHERE kind='raid_end' ORDER BY id")]
    if raids:
        won = sum(1 for r in raids if r["result"] == "defeated")
        print(f"\n悪の魔物の襲来 {len(raids)} 回（撃退 {won} / 去られた {len(raids) - won}）:")
        shots, hits = defaultdict(int), defaultdict(int)
        for r in raids:
            fighters = "、".join(f"{name.get(int(i))} {r['hits'].get(i, 0)}/{n}" for i, n in r["shots"].items())
            how = "撃退" if r["result"] == "defeated" else f"去られた（{r.get('reason') or '?'}）"
            print(f"  {r['raid']:>3} 回目  {how}  {r['duration']:5.0f} 秒  "
                  f"被害 {len(r['victims'])} 体  残り体力 {r['hp']}  戦士（命中/発射）: {fighters or 'なし'}")
            for i, n in r["shots"].items():
                shots[int(i)] += n
                hits[int(i)] += r["hits"].get(i, 0)
        if shots:
            print("  戦士ごとの累計（命中/発射）: " + "、".join(f"{name.get(i)} {hits[i]}/{shots[i]}" for i in shots))
        counter = q("SELECT COUNT(*) FROM events WHERE kind='frozen' AND detail_json LIKE ?", '%"cause": "counter"%')
        print(f"  フリーズさせられた住人 {kind_count('frozen')} 体（うち戦士が反撃の弾で {counter} 体）"
              f" / 爪を受けたが逃れた {kind_count('struck')} 体")

    # 悪の魔物の判断（raider_plan。2026-10-11 から LLM が決める）
    plans = [json.loads(r[0]) for r in c.execute("SELECT detail_json FROM events WHERE kind='raider_plan' ORDER BY id")]
    if plans:
        hunts = [p for p in plans if p["action"] == "hunt"]
        # role は 2026-10-13 から言語によらないキー（それまでは日本語の「戦士」など）
        old = {"戦士": "warrior", "ヒーラー": "healer", "住人": "resident"}
        roles = Counter(old.get(p["role"], p["role"]) for p in hunts if p["valid"])
        print(f"\n悪の魔物の判断 {len(plans)} 回: 狙う {len(hunts)} 回（戦士 {roles['warrior']} / ヒーラー {roles['healer']}"
              f" / 住人 {roles['resident']} / 返答が無効で本能 {sum(not p['valid'] for p in hunts)}）、"
              f"去ると決めた {len(plans) - len(hunts)} 回")
        for p in plans[-args.top:]:
            hp = f"HP{p['target_hp']}" if "target_hp" in p else f"電力{p.get('battery', '?')}"   # 10-12 までの記録は電力
            if p["action"] == "hunt":   # 去る判断（leave）には role・target がない
                role = {"warrior": "戦士", "healer": "ヒーラー", "resident": "住人"}.get(p["role"], p["role"])
                what = f"{name.get(p['target'])}（{role}・約{p['dist']}m・{hp}）"
            else:
                what = "去る"
            print(f"  {p['raid']:>3} 回目 HP{p['hp']:>3} 被害{p['victims']:>2}  {what}  {p['thought']}  ← {p['reason']}")


if __name__ == "__main__":
    main()
