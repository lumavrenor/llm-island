"""
性格生成

種（数値・口調・好きな場所・移動の癖など）はプログラムが乱数で決め、
肉付け（来歴・口癖など）は LLM が作る。100 体分を 1 ウェーブで一度に投げる。
名前は data/names.txt（英語は data/names_en.txt。[world] names_file）の候補から乱数で選ぶ
（LLM に考えさせると実在の建物などの名前が混ざるため）。
口調・移動の癖・プロンプトは [locale] lang の言語で作る。作った言語は DB に記録する（sim/world.py が確かめる）。

    python tools/gen_personas.py            # config.toml の LLM で生成（world.db に住人がいれば何もしない）
                                      # main.py（start.sh）も住人がいなければ最初にこれを行う
    python tools/gen_personas.py --force    # 作り直す（記憶もすべて消える）
    python tools/gen_personas.py --stub     # LLM なし（ダミーの設定）
"""

import argparse
import logging
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # python tools/gen_personas.py で起動しても core/・lang/ などを import できるように

import lang
from core import run_lock
from core.config import ROOT, load_config
from llm import prompts, schemas
from llm.client import LLMClient, LLMRequest
from llm.stub import StubLLMClient
from memory.db import DB

TEXT_FIELDS = ("first_person", "catchphrase", "background", "likes", "dislikes", "goal", "help_view", "walk_mood")


def make_seeds(cfg, n: int, rng: random.Random) -> list[dict]:
    places = [s.name for s in cfg.world.spots if s.kind == "place"]
    return [{
        "sociability": rng.randint(0, 10), "generosity": rng.randint(0, 10),
        "curiosity": rng.randint(0, 10), "caution": rng.randint(0, 10),
        "tone": rng.choice(lang.data("tones")), "favorite_spot": rng.choice(places),
        "move_habit": rng.choice(list(lang.data("move_habits").values())), "boot_cycles": rng.randint(10, 99999),
    } for _ in range(n)]


def _clash(a: str, b: str) -> bool:
    a, b = a.lower(), b.lower()   # 英語の名前は大文字小文字を区別せずに見る（日本語は変わらない）
    return a in b or b in a


def load_names(cfg) -> list[str]:
    """名前の候補（names.txt）。名前は一意で、互いに部分一致もしないこと（噂の伝播をセリフ中の名前で追うため）。
    場所の名前・悪の魔物の名前とも部分一致しないこと。だめなら ValueError"""
    with open(ROOT / cfg.world.names_file, encoding="utf-8") as f:
        names = [line.split("#")[0].strip() for line in f]
    names = [x for x in names if x]
    others = [s.name for s in cfg.world.spots] + [cfg.raider.name]
    for i, a in enumerate(names):
        hit = next((b for b in names[i + 1:] + others if _clash(a, b)), None)
        if hit:
            raise ValueError(f"{cfg.world.names_file}: 「{a}」と「{hit}」が同じか、一方がもう一方を含んでいます")
    if len(names) < cfg.world.npc_count:
        raise ValueError(f"{cfg.world.names_file}: 候補が {len(names)} 個しかありません（npc_count = {cfg.world.npc_count}）")
    return names


def run_wave(llm, reqs, label: str):
    wave = llm.submit(reqs)
    # これは単発のスクリプトなので、ここだけは素直に待つ（ゲーム本体では待たない）
    while not wave.is_done():
        print(f"\r  {label}: {wave.finished}/{wave.total} 完了  {wave.elapsed:5.1f}s", end="", flush=True)
        time.sleep(0.5)
    s = wave.summary()
    print(f"\r  {label}: {wave.total}/{wave.total} 完了  {wave.elapsed:5.1f}s  "
          f"失敗 {s['fail']} / {s['tok_per_sec']} tok/s / 遅延 p50 {s['latency_p50']}s")
    return wave.results()


def generate(cfg, db_path: str, use_stub: bool) -> bool:
    """性格を作って db_path に保存する（記憶もすべて消える）。失敗したら False（DB は変更しない）。
    呼ぶ側が running.lock を持っていること。main.py も住人がいないときにこれを呼ぶ"""
    try:
        pool = load_names(cfg)
    except ValueError as e:
        print(f"{e}。world.db は変更していません", file=sys.stderr)
        return False
    rng = random.Random(cfg.world.seed)
    n = cfg.world.npc_count
    seeds = make_seeds(cfg, n, rng)
    names = rng.sample(pool, n)

    llm = StubLLMClient(cfg.world.seed, 0.0, 0.0) if use_stub else LLMClient(cfg.llm)
    if not use_stub:
        # つながらないまま進むと全員がダミーになって保存され、記憶も消える。DB に触る前に確かめる
        ping = run_wave(llm, [LLMRequest("ping", -1, [{"role": "user", "content": "ping"}], None, 1)], "接続確認")[0]
        if not ping.ok:
            print(f"LLM に接続できません（{cfg.llm.base_url}: {ping.error}）。world.db は変更していません", file=sys.stderr)
            llm.close()
            return False
    print(f"{n} 体分の性格を一度に生成します（{'スタブ' if use_stub else cfg.llm.base_url}）")

    # JSON が崩れた住人だけ作り直す（これも 1 ウェーブで一度に投げる）
    accepted: dict[int, dict] = {}
    todo = list(range(n))
    for attempt in range(1, 4):
        schema = schemas.persona(lang.data("uses_first_person"))
        reqs = [LLMRequest("persona", i, prompts.persona_messages(seeds[i], names[i], cfg), schema, 700,
                           meta={"seed": seeds[i]}) for i in todo]
        results = run_wave(llm, reqs, f"{attempt} 回目")
        # 通信の失敗（JSON 崩れ以外）は作り直しても直らない。ダミーで埋めずに止める
        down = [r for r in results if not r.ok and r.error != "json"]
        if down:
            print(f"LLM への送信が {len(down)} 件失敗しました（{down[0].error}）。world.db は変更していません",
                  file=sys.stderr)
            llm.close()
            return False
        todo = []
        for res in results:
            if res.ok:
                accepted[res.req.npc_id] = res.data
            else:
                todo.append(res.req.npc_id)
        if not todo:
            break
        print(f"  JSON が崩れた {len(todo)} 体を作り直します")

    if todo:
        print(f"  3 回作り直してもだめだった {len(todo)} 体はダミーの設定にします（名前は候補のまま）")
    stub = StubLLMClient(cfg.world.seed + 1, 0.0, 0.0)
    for i in todo:
        accepted[i] = stub._persona({"seed": seeds[i]})

    npcs = []
    for i in range(n):
        p = accepted[i]
        persona = {k: lang.clip(str(p.get(k) or ""), 80) for k in TEXT_FIELDS}
        lines = p.get("sample_lines") if isinstance(p.get("sample_lines"), list) else []
        persona["sample_lines"] = [lang.clip(str(x), 40) for x in lines[:3]]
        npcs.append({"id": i, "name": names[i], "seed": seeds[i], "persona": persona, "battery": float(cfg.npc.max_hp)})

    db = DB(db_path)
    db.clear_memory()
    db.replace_npcs(npcs)
    db.set_lang(lang.code)
    db.commit()
    db.close()
    llm.close()
    print(f"{len(npcs)} 体を {db_path} に保存しました。例:")
    for npc in npcs[:5]:
        print(f"  {npc['name']}（{npc['seed']['tone']}・{npc['seed']['move_habit']}）{npc['persona']['catchphrase']}")
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="作り直す（記憶もすべて消える）")
    ap.add_argument("--stub", action="store_true", help="LLM を使わずダミーで作る")
    ap.add_argument("--db", default=None, help="既定は config.toml の [world] db_file")
    ap.add_argument("--config", default=str(ROOT / "config.toml"))
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    cfg = load_config(args.config)
    args.db = args.db or str(ROOT / cfg.world.db_file)
    lock = run_lock.acquire(ROOT / cfg.log.dir / "running.lock")   # 動いている main.py の DB を書き換えない
    if lock is None:
        print("main.py か gen_personas.py が動いています。終わってから実行してください", file=sys.stderr)
        return 1
    db = DB(args.db)
    has_npcs = bool(db.load_npcs())
    db.close()
    if has_npcs and not args.force:
        print(f"{args.db} にはもう住人がいます（作り直すなら --force）")
        return
    return 0 if generate(cfg, args.db, args.stub or cfg.llm.mode == "stub") else 1


if __name__ == "__main__":
    sys.exit(main())
