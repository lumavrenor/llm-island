"""
llm-island — 起動

    python main.py                   # ビューア（Ursina）
    python main.py --headless        # ビューアなし。ログとメトリクスだけで 100 体を回す
    python main.py --stub            # LLM なし（ダミー返答）で配管だけ確認
    python main.py --headless --minutes 30   # 世界の時刻で 30 分たったら終了（受け入れ確認用）
    python main.py --headless --stub --speed 8   # 8 倍速（HP・心・襲来のバランス調整用。ウェーブの待ちも 1/8 になる）
    python main.py --fresh-memory    # 記憶（events / sessions / relations ...）と世界の状態を消してから始める（reset.py と同じ）

前回終了時の世界（時刻・住人の位置と HP・心・状態異常・悪の襲来の回数）が world.db にあれば、そこから続ける。
world.db に住人がいなければ（初回）、先に gen_personas.py と同じ手順で性格を作ってから始める。
言語は config.toml の [locale] lang（"ja" / "en"）。DB は言語ごとに別のファイル（[world] db_file。英語は world_en.db）。

どちらのモードでも、メインループは「1 フレームごとに world.update(dt) を 1 回呼ぶ」だけ。
ログ: log/island.log（テキスト）, log/metrics.jsonl（ウェーブごとの計測）, log/prompts.txt（1 体分のプロンプト）
"""

import argparse
import logging
import sys
import time

from core import run_lock
from core.config import ROOT, load_config
from llm.client import LLMClient
from llm.stub import StubLLMClient
from memory.db import DB
from sim.world import World
from tools import gen_personas

logger = logging.getLogger("island")
FPS = 30


def setup_logging(log_dir, console_level):
    log_dir.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    root = logging.getLogger()
    root.setLevel(min(console_level, logging.INFO))
    fh = logging.FileHandler(log_dir / "island.log", mode="w", encoding="utf-8")   # 起動のたびに作り直す
    fh.setFormatter(fmt)
    fh.setLevel(logging.INFO)
    root.addHandler(fh)
    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    ch.setLevel(console_level)
    root.addHandler(ch)
    logging.getLogger("httpx").setLevel(logging.WARNING)


def log_feed(world: World, ev: dict):
    """ヘッドレス時：出来事を 1 行ずつログへ"""
    n = world.npcs
    match ev["kind"]:
        case "say":
            logger.info("[発話] %s → %s: %s", n[ev["npc"]].name, n[ev["partner"]].name, ev["text"])
        case "inner":
            logger.debug("[心の声] %s (%s %s): %s", n[ev["npc"]].name, ev["intent"], ev["target"], ev["text"])
        case "cheer":
            logger.info("[励まし] %s → %s（心 +%d）", n[ev["src"]].name, n[ev["dst"]].name, ev["amount"])
        case "frozen":
            logger.info("[フリーズ] %s", n[ev["npc"]].name)
        case "status" if ev["status"] == "fear":
            logger.debug("[状態] %s %s", n[ev["npc"]].name, "おびえた" if ev["on"] else "おびえが治った")
        case "raider_appear":
            logger.info("[悪] %s が %s の近くに現れた（%d 回目）", world.raider.name, ev["spot"], ev["raid"])
        case "raider_strike":
            logger.info("[悪] %s が爪を受けた（HP -%d → %d）", n[ev["npc"]].name, ev["damage"], ev["hp"])
        case "raider_counter" if ev["hit"]:
            logger.info("[悪] 戦士 %s が反撃の弾を受けた（HP -%d）", n[ev["npc"]].name, ev["damage"])
        case "raider_froze":
            logger.info("[悪] %s をフリーズさせた（%d 体目）", n[ev["npc"]].name, ev["victims"])
        case "raider_escaped_hit":
            logger.info("[悪] %s は爪で HP を %d 削られたが逃れた", n[ev["npc"]].name, ev["damage"])
        case "cast_start":
            logger.info("[詠唱] %s が %s のために杖を掲げた", n[ev["npc"]].name, n[ev["target"]].name)
        case "cast_cancel":
            logger.info("[詠唱] %s の詠唱は途中で止まった", n[ev["npc"]].name)
        case "raider_think":
            target = n[ev["target"]].name if ev["target"] is not None else "（去る）"
            logger.info("[悪の考え] 狙い %s: %s「%s」", target, ev["text"], ev["say"])
        case "heal":
            logger.info("[癒し] %s → %s", n[ev["src"]].name, n[ev["dst"]].name)
        case "attack" if ev["hit"]:
            logger.info("[戦士] %s の超能力が命中（悪の HP %d）", n[ev["npc"]].name, ev["hp"])
        case "raider_defeated":
            logger.info("[悪] 倒された！ 戦った戦士: %s（被害 %d 体）",
                        "、".join(n[i].name for i in ev["fighters"]), ev["victims"])
        case "raider_gone":
            logger.info("[悪] 去っていった（被害 %d 体、戦った戦士 %d 体）", ev["victims"], len(ev["fighters"]))
        case "rumor":
            logger.info("[噂] %s が %s から救助の話を聞いた", n[ev["npc"]].name, n[ev["src"]].name)
        case "hearsay":
            logger.info("[噂] %s が %s から %s のことを聞いた（%d 段目・%+d）: %s", n[ev["npc"]].name,
                        n[ev["src"]].name, ev["about"], ev["hops"], ev["feel"], ev["text"])
        case "system":
            logger.info("[system] %s", ev["text"])


def run_headless(world: World, minutes: float | None, speed: float = 1.0):
    last = time.perf_counter()
    try:
        while True:
            now = time.perf_counter()
            dt, last = min(now - last, 0.25), now
            world.update(dt * speed)
            for ev in world.drain_feed():
                log_feed(world, ev)
            if minutes is not None and world.now - world.start_now >= minutes * 60:
                logger.info("起動してから世界の時刻で %.1f 分経過したので終了します", minutes)
                break
            # フレームの残り時間だけ休む（処理を抱え込まず、毎フレーム必ずここに戻ってくる）
            time.sleep(max(0.0, 1.0 / FPS - (time.perf_counter() - now)))
    except KeyboardInterrupt:
        logger.info("Ctrl+C で終了します")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--headless", action="store_true", help="ビューアなしで起動")
    ap.add_argument("--stub", action="store_true", help="LLM を使わずダミーの返答で動かす")
    ap.add_argument("--minutes", type=float, default=None, help="起動してから世界の時刻で指定分数たったら終了")
    ap.add_argument("--npcs", type=int, default=None, help="住人の数（config より少なくするとき）")
    ap.add_argument("--fresh-memory", action="store_true", help="記憶と世界の状態を消して、新しい世界で始める")
    ap.add_argument("--db", default=None, help="既定は config.toml の [world] db_file")
    ap.add_argument("--config", default=str(ROOT / "config.toml"))
    ap.add_argument("--speed", type=float, default=1.0, help="ヘッドレス時の時間の倍率（スタブでの調整用）")
    ap.add_argument("--screenshot", default=None, help="ビューア終了時に画面を保存するパス（--minutes と併用）")
    ap.add_argument("-v", "--verbose", action="store_true", help="心の声もログに出す")
    args = ap.parse_args()

    cfg = load_config(args.config)
    args.db = args.db or str(ROOT / cfg.world.db_file)
    log_dir = ROOT / cfg.log.dir
    lock = run_lock.acquire(log_dir / "running.lock")   # ログを作り直す前に取る（ほかの実行のログを消さない）
    if lock is None:
        print("ほかの main.py か gen_personas.py が動いています。終わってから起動してください", file=sys.stderr)
        return 1
    setup_logging(log_dir, logging.DEBUG if args.verbose else logging.INFO)

    speed = args.speed if args.headless else 1.0   # ビューアは常に等倍
    use_stub = args.stub or cfg.llm.mode == "stub"

    # 初回（と reset.py --all のあと）は住人がいないので、先に性格を作る（gen_personas.py と同じ）。
    # --npcs より前に作るので、作るのは config の npc_count 体
    db = DB(args.db)
    has_npcs = bool(db.load_npcs())
    db.close()
    if not has_npcs:
        logger.info("%s に住人がいないので、先に性格を生成します", args.db)
        if not gen_personas.generate(cfg, args.db, use_stub):
            return 1
    if args.npcs is not None:
        cfg.world.npc_count = args.npcs
    if use_stub:
        # 倍速でも世界の時刻あたりのウェーブ数が等倍と同じになるように、疑似レイテンシも縮める
        llm = StubLLMClient(cfg.world.seed, cfg.stub.min_latency_sec / speed, cfg.stub.max_latency_sec / speed)
    else:
        llm = LLMClient(cfg.llm)
        if speed != 1.0:
            logger.warning("実 LLM の待ち時間は --speed で縮まないので、会話や意図の回数が等倍より少なくなります")
    logger.info("LLM: %s", "スタブ" if use_stub else f"{cfg.llm.base_url} model={cfg.llm.model}")
    logger.info("言語: %s / DB: %s", cfg.locale.lang, args.db)

    db = DB(args.db)
    if args.fresh_memory:
        db.clear_memory()
    world = World(cfg, db, llm, log_dir, speed)
    logger.info("住人 %d 体で開始", len(world.npcs))

    try:
        if args.headless:
            run_headless(world, args.minutes, speed)
        else:
            from viewer.app import run_viewer   # Ursina はビューアのときだけ読み込む
            run_viewer(world, cfg, args.minutes, args.screenshot)
    finally:
        world.close()
        db.close()
        llm.close()


if __name__ == "__main__":
    sys.exit(main())
