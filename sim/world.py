"""
世界（World）— 1 フレームで世界全体を 1 歩進める

■ フレームの約束
- メインループ（ヘッドレスの while ループ、または Ursina の update()）が毎フレーム
  World.update(dt) を 1 回呼ぶ。World はその中で、決まった順番で全員を 1 歩ずつ動かして戻る。
      1. LLM ウェーブを 1 歩進める（collect / wait / play。悪の魔物の判断も同じウェーブに乗る）
      2. NPC を id 順に 1 体ずつ update()
      3. 悪の魔物（襲来・追跡・吸い取り）→ 戦士の攻撃
      4. 押し合い → 救助判定 → 遭遇判定
- HP を減らすのは World.damage() だけ（0 になったら freeze_npc() でフリーズさせる）
- どこにも while で待つ処理は書かない。待つものは StateMachine で「待ち状態」にして、
  毎フレーム「もう終わった？」と確認するだけ。
- 裏スレッドは LLMClient の HTTP 1 本だけ。世界のデータを書き換えるのはこのファイルの
  メインスレッドのコードだけ。

■ LLM ウェーブ（wave_state）
    collect … 手が空いている全員分のリクエストを集めて、一度に submit()
    wait    … 全部返るまで待つ（その間も世界は動き続ける）
    play    … 結果をまとめて反映し、セリフを見せる時間だけ待つ → collect へ
  リクエストが返ってくる順番がバラバラでも、反映はウェーブ単位で 1 回だけ。
"""

from __future__ import annotations

import json
import logging
import math
import random
import time
from dataclasses import dataclass
from pathlib import Path

import lang
from lang import t
from llm import prompts, schemas
from llm.client import LLMRequest, LLMResult
from memory import recall, summarize
from sim import encounter, heal, movement, raid
from sim.npc import Npc
from core.state import StateMachine

logger = logging.getLogger(__name__)


@dataclass
class Spot:
    name: str
    x: float
    z: float
    radius: float
    kind: str   # "solace"（心が回復する）/ "place"


class World:
    def __init__(self, cfg, db, llm, log_dir: Path, speed: float):
        self.cfg = cfg
        # 世界の時刻の倍率（--speed）。ウェーブの待ち（collect / play）は実時計で数えるので、
        # 同じだけ縮めて「世界の時刻あたりのウェーブ数」を等倍と同じにする
        self.speed = speed
        self.db = db
        self.llm = llm
        self.rng = random.Random(cfg.world.seed)
        self.half = cfg.world.size / 2
        self.now = 0.0          # シミュレーション時刻 [秒]（running 中だけ進む）

        self.spots = [Spot(s.name, s.x, s.z, s.radius, s.kind) for s in cfg.world.spots]
        self.spot_by_name = {s.name: s for s in self.spots}
        self.solace_spots = {s.name: s for s in self.spots if s.kind == "solace"}

        rows = db.load_npcs()[: cfg.world.npc_count]
        if not rows:
            raise SystemExit(t("sys.no_npcs", db=db.path))
        # 住人の性格・名前・記憶は作ったときの言語で書かれている。言語を混ぜない
        stored = db.lang()
        if stored != lang.code:
            raise SystemExit(t("sys.lang_mismatch", db=db.path, stored=stored, lang=lang.code))
        assert [r["id"] for r in rows] == list(range(len(rows))), "npc.id は 0 から連番であること"
        nc = cfg.npc
        # 前回終了時の世界があればそこから続ける（reset.sh / --fresh-memory で消える）
        snap = db.load_snapshot()
        saved = {int(k): v for k, v in snap["npcs"].items()} if snap else {}
        self.npcs: list[Npc] = []
        for r in rows:
            # 続きから始めるときも乱数は同じだけ引く（ほかの乱数の並びを変えない）
            x, z = self.clamp(self.rng.uniform(-self.half, self.half), self.rng.uniform(-self.half, self.half))
            hp, heart, status = float(nc.max_hp), self.rng.uniform(nc.start_heart_min, nc.start_heart_max), {}
            if r["id"] in saved:
                v = saved[r["id"]]
                if isinstance(v, dict):
                    x, z, hp, heart, status = v["x"], v["z"], v["hp"], v["heart"], dict(v["status"])
                else:   # 2026-10-12 までの形式 [x, z, 電力]：電力 0 だった住人はフリーズしたまま
                    x, z = v[0], v[1]
                    if v[2] <= 0:
                        hp, status = 0.0, {"freeze": 0.0}
            npc = Npc(r, x, z, hp, heart)
            npc.status = status
            if npc.frozen:   # フリーズしたまま終了した住人は、フリーズしたまま（ヒーラーが癒すまで起きない）
                npc.hp = 0.0
                npc.state.change("frozen")
                npc.need_intent = None
            self.npcs.append(npc)
        self.npc_by_name = {n.name: n for n in self.npcs}
        warriors, healers = pick_roles(cfg, len(self.npcs))
        for i in warriors:
            self.npcs[i].warrior = True
        for i in healers:
            self.npcs[i].healer = True
        self.raider = raid.Raider(cfg)
        if snap:
            self.now = snap["now"]
            self.raider.raid_no = snap["raid_no"]
            self.raider.next_at = snap["raider_next_at"]
            logger.info("前回の続きから始めます（世界の時刻 %.0f 秒、悪の襲来 %d 回、フリーズ %d 体）",
                        self.now, self.raider.raid_no, sum(n.frozen for n in self.npcs))
        else:
            logger.info("新しい世界で始めます")
        self.start_now = self.now   # この起動を始めた世界の時刻（--minutes はここから数える）

        self.sessions: dict[int, encounter.Session] = {}
        self.pair_cooldown: dict[tuple[int, int], float] = {}
        self.rescue_cooldown: dict[tuple[int, int], float] = {}

        # 救助の出来事と、それを誰が知っているか（噂の伝播）
        self.known: dict[int, list[int]] = db.load_knowledge()
        self.rescue_parties: dict[int, tuple[int, int]] = {}
        self.rescue_names: dict[int, tuple[str, str]] = {}
        for ev in db.rescue_events():
            self.rescue_parties[ev["id"]] = (ev["actor_id"], ev["target_id"])
            if ev["actor_id"] < len(self.npcs) and ev["target_id"] < len(self.npcs):
                self.rescue_names[ev["id"]] = (self.npcs[ev["actor_id"]].name, self.npcs[ev["target_id"]].name)

        self.state = StateMachine("boot")
        self.wave_state = StateMachine("collect")
        self.wave = None
        self.wave_no = 0
        self.play_sec = 0.0
        self.last_wave: dict | None = None
        self.feed: list[dict] = []      # ビューア／ログ向けの出来事（毎フレーム drain_feed() で取り出す）
        self.counters = {"sessions": 0, "utterances": 0, "rescues": 0, "freezes": 0, "cheers": 0,
                         "invalid_intents": 0, "llm_fail": 0, "raids": 0, "raiders_defeated": 0,
                         "raider_frozen": 0, "strikes": 0, "counters": 0, "counter_hits": 0,
                         "warrior_shots": 0, "warrior_hits": 0, "heal_declined": 0,
                         "raider_thoughts": 0, "invalid_raider": 0}
        self._ping = None
        self._info = None               # llm.fetch_info() の結果待ち
        self.server_info = None         # llm.client.ServerInfo（推論エンジン名・モデル名。HUD 用）
        self.server_info_failed = False
        self._commit_at = 0.0
        self._metrics_at = 0.0
        log_dir.mkdir(parents=True, exist_ok=True)
        self._metrics = open(log_dir / "metrics.jsonl", "w", encoding="utf-8")   # 起動のたびに作り直す
        # 1 体分のプロンプトと返答（起動のたびに作り直す。量を増やしすぎないため）
        self._prompts = open(log_dir / "prompts.txt", "w", encoding="utf-8") \
            if self.cfg.log.prompt_npc >= 0 or self.cfg.log.prompt_raider else None
        self._prompt_system = ""        # 前回書いた system（同じなら省く）

    # ================= 毎フレーム =================

    def update(self, dt: float):
        self._info_frame()
        match self.state.update():
            case "boot":
                self._boot_frame()

            case "boot_retry":
                if self.state.elapsed >= 5.0:
                    self.state.change("boot")

            case "running":
                self.now += dt
                self._wave_frame()
                for npc in self.npcs:
                    npc.update(dt, self)
                self.raider.update(dt, self)
                raid.warrior_attacks(self)
                grid = encounter.Grid(self.npcs, max(self.cfg.encounter.radius, self.cfg.move.separation))
                encounter.separate(self, grid)
                heal.check_rescues(self)
                encounter.check_encounters(self, grid)
                self._housekeeping_frame()

    def _boot_frame(self):
        """LLM サーバーに 1 回だけ投げて、返ってきたら世界を動かし始める"""
        if self.state.entered:
            self.emit("system", text=t("sys.connecting"))
            self._ping = self.llm.ping()
            if self.server_info is None and self._info is None:
                self._info = self.llm.fetch_info()
        if not self._ping.is_done():
            return
        res = self._ping.results()[0]
        if res.ok:
            logger.info("LLM 接続 OK（%.1f 秒）", res.latency)
            self.emit("system", text=t("sys.connected"))
            self.state.change("running")
        else:
            logger.warning("LLM に接続できません（%s）。5 秒後に再試行", res.error)
            self.emit("system", text=t("sys.connect_fail", error=res.error))
            self.state.change("boot_retry")

    def _info_frame(self):
        """サーバーの名乗りが返ってきたら控える（待たない。返るまで毎フレーム見るだけ）"""
        if self._info is None or not self._info.is_done():
            return
        self.server_info = self._info.result()
        self._info = None
        self.server_info_failed = self.server_info is None
        if self.server_info is not None:
            logger.info("推論サーバー: %s", self.server_info.label)
        else:
            # 次に boot へ入ったとき（再接続）に聞き直す
            logger.warning("推論サーバーの名乗りを取得できませんでした")

    # ================= LLM ウェーブ =================

    def _wave_frame(self):
        wcfg = self.cfg.wave
        match self.wave_state.update():
            case "collect":
                count = sum(1 for n in self.npcs if self._action_kind(n)) \
                    + sum(len(n.summaries_due) for n in self.npcs) + self.raider.wants_think()
                if count == 0:
                    return
                if count < wcfg.min_batch and self.wave_state.elapsed < wcfg.max_collect_sec / self.speed:
                    return
                reqs = self._build_requests()
                self.wave_no += 1
                self.wave = self.llm.submit(reqs)
                self.wave_state.change("wait")

            case "wait":
                if not self.wave.is_done():
                    return
                self.play_sec = self._apply_wave(self.wave.results())
                self._log_wave()
                self.wave = None
                self.wave_state.change("play")

            case "play":
                if self.wave_state.elapsed >= self.play_sec / self.speed:
                    self.wave_state.change("collect")

    def _action_kind(self, npc: Npc) -> str | None:
        """この NPC が今回のウェーブで出す行動リクエストの種類（優先度: 発話 > 救助判断 > 移動意図）"""
        if npc.waiting is not None or npc.frozen or npc.casting is not None:
            return None
        if npc.session is not None:
            return "say" if npc.session.next_speaker == npc.id else None
        if npc.rescue_target is not None:
            return "rescue"
        if npc.need_intent:
            return "intent"
        return None

    def _build_requests(self) -> list[LLMRequest]:
        reqs = []
        for npc in self.npcs:
            match self._action_kind(npc):
                case "say":
                    reqs.append(self._req_say(npc))
                case "rescue":
                    reqs.append(self._req_rescue(npc))
                case "intent":
                    reqs.append(self._req_intent(npc))
            # 要約は行動を止めないので、同じウェーブに一緒に乗せる
            while npc.summaries_due:
                reqs.append(summarize.build_request(self, npc, npc.summaries_due.pop(0)))
        if self.raider.wants_think():
            reqs.append(self.raider.build_request(self))   # 悪の魔物も 1 件まで
        return reqs

    def _apply_wave(self, results: list[LLMResult]) -> float:
        """ウェーブの結果をまとめて反映する。戻り値は再生フェーズの秒数"""
        longest = 0
        for res in results:
            if not res.ok:
                self.counters["llm_fail"] += 1
            if res.req.npc_id == self.cfg.log.prompt_npc or (res.req.kind == "raider" and self.cfg.log.prompt_raider):
                self._log_prompt(res)
            if res.req.kind in ("say", "rescue", "intent"):
                self.npcs[res.req.npc_id].waiting = None
            match res.req.kind:
                case "say":
                    longest = max(longest, self._apply_say(res))
                case "rescue":
                    longest = max(longest, self._apply_rescue(res))
                case "intent":
                    self._apply_intent(res)
                case "summary":
                    summarize.apply_result(self, res)
                case "raider":
                    self.counters["raider_thoughts"] += 1
                    self.raider.apply_result(self, res)
        w = self.cfg.wave
        return max(w.min_play_sec, min(w.max_play_sec, longest * w.play_sec_per_char))

    # ---------- リクエストの組み立て ----------

    def _req_say(self, npc: Npc) -> LLMRequest:
        s = npc.session
        partner = self.npcs[s.partner_of(npc.id)]
        dialogue = [(self.npcs[sid].name, text) for sid, text in s.lines[-self.cfg.memory.dialogue_turns:]]
        memory = recall.pair_memory(self, npc, partner) + "\n" + recall.others_memory(self, npc, partner)
        msgs = prompts.say_messages(npc, partner, self.cfg, memory, self.situation(npc, partner),
                                    dialogue, npc.rescued_by)
        npc.waiting = "say"
        return LLMRequest("say", npc.id, msgs, schemas.SAY, 120, meta={
            "session_id": s.id, "partner_id": partner.id, "partner_name": partner.name,
            "turn": len(s.lines), "rescued_by": npc.rescued_by, "heart": npc.heart,
            "partner_heart": partner.heart, "generosity": npc.seed["generosity"],
            "gossip": self._stub_gossip(npc, partner)})

    def _stub_gossip(self, npc: Npc, partner: Npc) -> list[tuple[str, str]]:
        """スタブのセリフ用：プロンプトの「印象」「噂」と同じ材料を (名前, ひとこと) で"""
        mem = self.cfg.memory
        out = [(self.npcs[r["b_id"]].name, t("stub.like") if r["affinity"] > 0 else t("stub.dislike"))
               for r in self.db.top_relations(npc.id, mem.known_others + 1) if r["b_id"] != partner.id]
        out += [(b["about"], b["text"]) for b in self.db.recent_beliefs(
            npc.id, mem.heard_rumors, exclude=(npc.name, partner.name), exclude_from=partner.id)]
        return out

    def _req_rescue(self, npc: Npc) -> LLMRequest:
        target = self.npcs[npc.rescue_target]
        msgs = prompts.rescue_messages(npc, target, self.cfg, recall.pair_memory(self, npc, target),
                                       self.situation(npc, target))
        npc.waiting = "rescue"
        r = self.raider
        return LLMRequest("rescue", npc.id, msgs, schemas.RESCUE, 100, meta={
            "target_id": target.id, "target_name": target.name, "hp": npc.hp, "heart": npc.heart,
            "raider_dist": round(r.dist(npc)) if r.present and r.hp > 0 else None,
            "generosity": npc.seed["generosity"]})

    def _req_intent(self, npc: Npc) -> LLMRequest:
        reason, npc.need_intent = npc.need_intent, None
        r = self.raider
        raid_seen = r.describe(self, npc) is not None
        msgs = prompts.intent_messages(npc, self.cfg, recall.others_memory(self, npc),
                                       self.situation(npc), reason, raid_seen)
        npc.waiting = "intent"
        nearby = [o.name for o in self.npcs if o is not npc and not o.frozen
                  and npc.dist_to(o) <= self.cfg.move.sight]
        schema = schemas.intent_schema(npc.warrior, npc.healer, raid_seen)
        return LLMRequest("intent", npc.id, msgs, schema, 120, meta={
            "hp": npc.hp, "heart": npc.heart, "favorite": npc.seed["favorite_spot"],
            "places": [s.name for s in self.spots if s.kind == "place"],
            "nearest_solace": self.nearest_solace(npc).name, "at_solace": npc.solace is not None,
            "nearby": nearby[:6],
            "frozen": [o.name for o in self.frozen_for_healer(npc)] if npc.healer else [],
            "generosity": npc.seed["generosity"], "warrior": npc.warrior, "healer": npc.healer,
            "raid_news": npc.raid_news,
            "raider_dist": round(r.dist(npc)) if raid_seen else None})

    def condition(self, npc: Npc) -> str:
        """HP・心・状態異常（状況の文用）"""
        nc = self.cfg.npc
        return t("cond", hp=int(npc.hp), max_hp=nc.max_hp, heart=int(npc.heart), max_heart=nc.max_heart,
                 status=npc.status_text())

    def situation(self, npc: Npc, partner: Npc | None = None) -> str:
        lines = [t("sit.place", x=self.place_name(npc)), t("sit.me", x=self.condition(npc))]
        if partner is not None:
            lines.append(t("sit.other", name=partner.name, x=self.condition(partner)))
        near = sorted((o for o in self.npcs if o is not npc and o is not partner
                       and npc.dist_to(o) <= self.cfg.move.sight), key=npc.dist_to)[:6]
        if near:
            lines.append(t("sit.near") + lang.sep().join(
                o.name + (t("paren", x=self.label(o)) if self.label(o) else "") for o in near))
        if npc.healer:
            lines.append(self._frozen_for_healer_line(npc))
        else:
            frozen = [o.name for o in self.npcs if o.frozen and o is not npc and npc.dist_to(o) <= 40.0]
            if frozen:
                lines.append(t("sit.near_frozen") + lang.sep().join(frozen[:4]))
        if npc.solace is not None:
            lines.append(t("sit.at_solace", name=npc.solace.name))
        else:
            s = self.nearest_solace(npc)
            lines.append(t("sit.nearest_solace", name=s.name, d=int(math.hypot(npc.x - s.x, npc.z - s.z))))
        raider = self.raider.describe(self, npc)
        if raider:
            lines.append(raider)
        return "\n".join(lines)

    @staticmethod
    def label(o: Npc) -> str:
        """「近くにいる住人」に添える役割と様子（戦士・会話中 など）"""
        doing = (t("doing.frozen") if o.frozen else t("doing.talking") if o.session else
                 t("doing.casting") if o.casting is not None else t("doing.fear") if "fear" in o.status else "")
        role = t("role.warrior") if o.warrior else t("role.healer") if o.healer else ""
        return t("dot").join(x for x in (role, doing) if x)

    def frozen_for_healer(self, healer: Npc) -> list[Npc]:
        """ヒーラーが気配で分かるフリーズ住人（島じゅう。近い順に [healer] listed 体）"""
        frozen = sorted((o for o in self.npcs if o.frozen), key=healer.dist_to)
        return frozen[:self.cfg.healer.listed]

    def _frozen_for_healer_line(self, healer: Npc) -> str:
        frozen = self.frozen_for_healer(healer)
        if not frozen:
            return t("sit.frozen_none")

        def heading(o):
            """ほかのヒーラーがその住人を癒しに向かっているか"""
            for h in self.npcs:
                if h is healer or not h.healer or h.frozen:
                    continue
                if h.rescue_target == o.id or h.casting == o.id or (
                        h.intent is not None and h.intent.kind == "rescue" and h.intent.target_id == o.id):
                    return t("sit.frozen_heading", name=h.name)
            return ""
        total = sum(1 for o in self.npcs if o.frozen)
        return t("sit.frozen_list", total=total) + lang.sep().join(
            t("sit.frozen_item", name=o.name, place=self.place_name(o), d=int(healer.dist_to(o)), heading=heading(o))
            for o in frozen)

    # ---------- 結果の反映（ここでだけ世界を書き換える）----------

    def _apply_say(self, res: LLMResult) -> int:
        npc = self.npcs[res.req.npc_id]
        s = self.sessions.get(res.req.meta["session_id"])
        if s is None or s.ended or npc.frozen:
            return 0   # 返答待ちの間に会話が終わっていた
        partner = self.npcs[s.partner_of(npc.id)]
        data = res.data if res.ok else None
        if data is None:
            text, cheer, end = "……", False, True   # 失敗したら黙って会話を終える
        else:
            text = lang.clip(str(data.get("say") or "").strip(), 40) or "……"
            cheer = bool(data.get("cheer"))
            end = bool(data.get("end"))
        if res.req.meta.get("rescued_by"):
            npc.rescued_by = None   # 救助者に触れる最初の発話を済ませた
        repeated = any(sid == npc.id and t == text for sid, t in s.lines)   # 同じセリフのループを止める

        s.lines.append((npc.id, text))
        self.counters["utterances"] += 1
        self.db.add_utterance(s.id, npc.id, text)
        self.emit("say", npc=npc.id, partner=partner.id, text=text, session=s.id,
                  memory=self._mentions_memory(text, npc, partner))
        self._spread_rumors(npc, partner, text, s)

        nc = self.cfg.npc
        # 励まし：同じ会話で同じ相手を励ますのは 1 回まで（心が満ちている相手には効かない）
        if cheer and (npc.id, partner.id) not in s.cheers and partner.heart < nc.max_heart:
            gain = min(float(nc.cheer_heart), nc.max_heart - partner.heart)
            partner.heart += gain
            partner.update_fear(self)
            s.cheers.append((npc.id, partner.id))
            self.counters["cheers"] += 1
            self.db.add_event("cheer", npc.id, partner.id, s.spot,
                              t("ev.cheer", a=npc.name, b=partner.name, spot=s.spot))
            self.emit("cheer", src=npc.id, dst=partner.id, amount=round(gain))
        if end or repeated or len(s.lines) >= s.max_turns:
            self.end_session(s, "end" if end else "repeated" if repeated else "max_turns")
        else:
            s.next_speaker = partner.id
        return len(text)

    def _apply_rescue(self, res: LLMResult) -> int:
        npc = self.npcs[res.req.npc_id]
        target = self.npcs[res.req.meta["target_id"]]
        npc.rescue_target = None
        if target.rescuer == npc.id:
            target.rescuer = None
        self.rescue_cooldown[(npc.id, target.id)] = self.now + self.cfg.npc.rescue_cooldown_sec
        if npc.frozen:
            return 0
        data = res.data if res.ok else {}
        heal = bool(data.get("heal")) and target.frozen and target.rescuer is None
        say = lang.clip(str(data.get("say") or "").strip(), 40)
        if say:
            self.emit("say", npc=npc.id, partner=target.id, text=say, session=None, memory=False)
        if not target.frozen:
            npc.ask_intent(t("why.heal_already", name=target.name))
            return len(say)   # 判断している間に、ほかのヒーラーが癒していた
        if not heal:
            self.counters["heal_declined"] += 1
            self.emit("rescue_declined", npc=npc.id, target=target.id)
            npc.ask_intent(t("why.heal_declined", name=target.name))
            return len(say)
        self.start_heal(npc, target)
        return len(say)

    def _apply_intent(self, res: LLMResult):
        npc = self.npcs[res.req.npc_id]
        if npc.frozen or npc.session is not None or npc.casting is not None or npc.rescue_target is not None:
            return   # 返答待ちの間に状況が変わった（会話が始まった・救助判断になった等）。今の行動を優先
        if res.req.meta["raid_news"] != npc.raid_news:
            return   # 返答待ちの間に悪が来た・襲われた。理由は need_intent に入っているので次のウェーブで聞き直す
        intent, valid = movement.validate(res.data if res.ok else {}, npc, self)
        if not valid:
            self.counters["invalid_intents"] += 1
        npc.need_intent = None
        npc.set_intent(intent, self)
        if intent.manner:
            self.emit("inner", npc=npc.id, text=intent.manner, intent=intent.kind, target=intent.target)

    # ================= 世界の出来事（メインスレッドから呼ぶ）=================

    def start_session(self, a: Npc, b: Npc):
        spot = self.spot_name(a)
        sid = self.db.start_session(a.id, b.id, spot)
        first = a if a.seed["sociability"] >= b.seed["sociability"] else b
        s = encounter.Session(sid, a.id, b.id, first.id, spot, self.cfg.encounter.max_turns)
        self.sessions[sid] = s
        for n, o in ((a, b), (b, a)):
            n.session = s
            n.face(o)
            n.state.change("talking")
        self.counters["sessions"] += 1
        first_meeting = self.db.get_relation(a.id, b.id) is None
        self.emit("talk_start", a=a.id, b=b.id, session=sid, first=first_meeting)

    def end_session(self, s: encounter.Session, reason: str):
        if s.ended:
            return
        s.ended = True
        self.sessions.pop(s.id, None)
        self.db.end_session(s.id, reason)
        a, b = self.npcs[s.a], self.npcs[s.b]
        key = (min(a.id, b.id), max(a.id, b.id))
        self.pair_cooldown[key] = self.now + self.cfg.encounter.cooldown_sec
        for n in (a, b):
            n.session = None
            if not n.frozen:
                n.state.change("idle")
                n.need_intent = t("why.talk_end")
            if s.lines:
                n.summaries_due.append(s)
        if s.lines:
            self.db.touch_relation(a.id, b.id)
            self.db.touch_relation(b.id, a.id)
            self.db.add_event("talk", a.id, b.id, s.spot,
                              t("ev.talk", a=a.name, b=b.name, spot=s.spot, n=len(s.lines)))
        self.emit("talk_end", a=a.id, b=b.id, session=s.id, reason=reason)

    def on_arrived(self, npc: Npc):
        it = npc.intent
        if it.kind == "go_spot":
            spot = self.spot_by_name[it.target]
            self.db.add_event("arrived", npc.id, None, spot.name, t("ev.arrived", a=npc.name, spot=spot.name))
            nc = self.cfg.npc
            if spot.kind == "solace" and npc.heart < nc.max_heart - 5:
                # solace に着いたら、心が満ちるまで（最長 rest_max_sec）そのまま休む。LLM には聞かない
                sc = self.cfg.solace
                rest = min(sc.rest_max_sec, max(10.0, (nc.max_heart - npc.heart) / sc.heart_rate))
                rest_intent = movement.Intent("wait", spot.name, "slow", t("manner.rest"), rest)
                npc.need_intent = None
                npc.set_intent(rest_intent, self)
                self.emit("inner", npc=npc.id, text=rest_intent.manner, intent="wait", target=spot.name)
                return
        npc.state.change("idle")
        r = self.raider
        gone = t("why.raider_down") if r.hp <= 0 else t("why.raider_gone")
        healed = it.kind == "rescue" and not self.npcs[it.target_id].frozen
        why = {"go_spot": "why.arrived", "seek": "why.found", "avoid": "why.avoided",
               "rescue": "why.rescue_woke" if healed else "why.rescue_at"}.get(it.kind)
        if why:
            npc.ask_intent(t(why, x=it.target))
        elif it.kind == "fight":
            npc.ask_intent(gone)
        elif it.kind == "flee":
            npc.ask_intent(t("why.fled") if r.present and r.hp > 0 else gone)
        else:
            npc.ask_intent(t("why.done"))

    def damage(self, npc: Npc, hp: float, heart: float, cause: str) -> bool:
        """HP・心を減らすときは必ずここを通す（HP が 0 になったらフリーズさせる）。
        攻撃を受けたら状態異常「ノイズ」が付く（続いていれば延びる）。戻り値はこれでフリーズしたか"""
        if npc.frozen:
            return False
        npc.hp = max(0.0, npc.hp - hp)
        npc.heart = max(0.0, npc.heart - heart)
        npc.add_status("noise", self.now)
        npc.update_fear(self)
        if npc.hp <= 0:
            self.freeze_npc(npc, cause)
            return True
        return False

    def freeze_npc(self, npc: Npc, cause: str):
        """HP 0。状態異常 freeze を付けて、その場で動けなくする（解けるのはヒーラーの癒しだけ）"""
        npc.hp = 0.0
        npc.status = {"freeze": self.now}   # ほかの状態異常は目覚めるときにまっさらにする
        npc.state.change("frozen")
        npc.intent = None
        npc.need_intent = None
        npc.rescued_by = None
        if npc.session is not None:
            self.end_session(npc.session, "freeze")
        if npc.rescue_target is not None:
            target = self.npcs[npc.rescue_target]
            if target.rescuer == npc.id:
                target.rescuer = None
            npc.rescue_target = None
        if npc.casting is not None:   # 詠唱の途中でフリーズした：癒しは届かない
            target = self.npcs[npc.casting]
            if target.rescuer == npc.id:
                target.rescuer = None
            npc.casting = None
            self.emit("cast_cancel", npc=npc.id, target=target.id)
        self.counters["freezes"] += 1
        spot = self.spot_name(npc)
        self.emit("frozen", npc=npc.id)
        # 目の前でフリーズしたのを見た住人は、心が減る
        nc = self.cfg.npc
        for o in self.npcs:
            if o is not npc and not o.frozen and o.dist_to(npc) <= nc.witness_radius:
                o.heart = max(0.0, o.heart - nc.witness_heart)
                o.update_fear(self)
        # ヒーラーは島のどこで止まっても気配を感じる（癒しに向かっている・判断している・詠唱中なら邪魔しない）
        for h in self.npcs:
            if h.healer and not h.frozen and h.rescue_target is None and h.session is None \
                    and h.casting is None and (h.intent is None or h.intent.kind != "rescue"):
                h.ask_intent(t("why.felt_freeze", name=npc.name, spot=spot))

    def start_heal(self, healer: Npc, target: Npc):
        """ヒーラーが癒すと決めた：杖を掲げて詠唱を始める（cast_sec のあいだ動けない）"""
        healer.casting = target.id
        healer.cast_end = self.now + self.cfg.healer.cast_sec
        target.rescuer = healer.id   # 詠唱が終わるまで、ほかのヒーラーは判断しない
        healer.intent = None
        healer.need_intent = None
        healer.face(target)
        healer.state.change("casting")
        self.emit("cast_start", npc=healer.id, target=target.id)

    def finish_heal(self, healer: Npc):
        """詠唱が終わった：フリーズを解いて HP 100% で目覚めさせる（Npc の casting ステートから呼ぶ）"""
        target = self.npcs[healer.casting]
        healer.casting = None
        healer.state.change("idle")
        if target.rescuer == healer.id:
            target.rescuer = None
        if not target.frozen:   # 念のため（詠唱の間に起きることはないはず）
            healer.ask_intent(t("why.already_awake", name=target.name))
            return
        nc, hc = self.cfg.npc, self.cfg.healer
        spot = self.spot_name(target)
        eid = self.db.add_event("rescue", healer.id, target.id, spot,
                                t("ev.rescue", a=healer.name, b=target.name, spot=spot))
        self.rescue_parties[eid] = (healer.id, target.id)
        self.rescue_names[eid] = (healer.name, target.name)
        self._learn(healer.id, eid, None, None)
        self._learn(target.id, eid, None, None)
        self.counters["rescues"] += 1
        target.status = {}
        target.hp = float(nc.max_hp)
        target.heart = max(target.heart, float(hc.revive_heart))
        target.update_fear(self)
        target.state.change("idle")
        target.intent = None
        target.rescued_by = healer.name
        target.need_intent = t("why.revived", name=healer.name, hp=nc.max_hp)
        healer.ask_intent(t("why.healed", name=target.name))
        self.emit("heal", src=healer.id, dst=target.id)
        self.emit("revived", npc=target.id, by=healer.id)
        self.raider.on_revived(self, target, healer)
        logger.info("癒し: %s → %s", healer.name, target.name)

    # ---------- 噂の伝播 ----------

    def _learn(self, npc_id: int, event_id: int, via_session: int | None, from_id: int | None):
        known = self.known.setdefault(npc_id, [])
        if event_id not in known:
            known.append(event_id)
            self.db.add_knowledge(npc_id, event_id, via_session, from_id)

    def _spread_rumors(self, speaker: Npc, listener: Npc, text: str, s):
        """話し手が知っている救助の当事者の名前がセリフに出たら、聞き手もその出来事を知る"""
        for eid in self.known.get(speaker.id, []):
            names = self.rescue_names.get(eid)
            if names and (lang.mentions(names[0], text) or lang.mentions(names[1], text)) \
                    and eid not in self.known.get(listener.id, []):
                self._learn(listener.id, eid, s.id, speaker.id)
                self.emit("rumor", npc=listener.id, src=speaker.id, event=eid)

    def _mentions_memory(self, text: str, npc: Npc, partner: Npc) -> bool:
        if any(w in text.lower() for w in lang.data("memory_words")):
            return True
        return any(lang.mentions(o.name, text) for o in self.npcs if o is not npc and o is not partner)

    # ================= 補助 =================

    def clamp(self, x: float, z: float) -> tuple[float, float]:
        h = self.half - 1.0
        return max(-h, min(h, x)), max(-h, min(h, z))

    def nearest_spot(self, npc: Npc) -> Spot:
        return min(self.spots, key=lambda s: math.hypot(npc.x - s.x, npc.z - s.z) - s.radius)

    def spot_name(self, npc: Npc) -> str:
        """出来事の記録用（いちばん近いスポットの名前だけ）"""
        return self.nearest_spot(npc).name

    def place_name(self, npc: Npc) -> str:
        """「今の状況」用（離れていれば距離も書く）"""
        spot = self.nearest_spot(npc)
        d = math.hypot(npc.x - spot.x, npc.z - spot.z)
        return spot.name if d <= spot.radius * 1.3 else t("place.near", name=spot.name, d=int(d))

    def nearest_solace(self, npc: Npc) -> Spot:
        return min(self.solace_spots.values(), key=lambda s: math.hypot(npc.x - s.x, npc.z - s.z))

    def solace_at(self, npc: Npc) -> Spot | None:
        """npc が半径の中にいる solace（いなければ None）"""
        for s in self.solace_spots.values():
            if math.hypot(npc.x - s.x, npc.z - s.z) <= s.radius:
                return s
        return None

    def emit(self, kind: str, **data):
        self.feed.append({"kind": kind, "t": self.now, **data})

    def drain_feed(self) -> list[dict]:
        out, self.feed = self.feed, []
        return out

    def stats(self) -> dict:
        n = self.npcs
        w = self.wave
        return {
            "phase": self.state.current if self.state.current != "running" else self.wave_state.current,
            "wave": self.wave_no,
            "npcs": len(n),
            "frozen": sum(1 for x in n if x.frozen),
            "talking": sum(1 for x in n if x.session is not None),
            "resting": sum(1 for x in n if x.solace is not None),
            "fear": sum(1 for x in n if "fear" in x.status),
            "noise": sum(1 for x in n if "noise" in x.status),
            "hp_avg": round(sum(x.hp for x in n) / max(1, len(n)), 1),
            "heart_avg": round(sum(x.heart for x in n) / max(1, len(n)), 1),
            "moving": sum(1 for x in n if x.state.current == "moving"),
            "waiting": sum(1 for x in n if x.waiting is not None),
            "inflight": w.inflight if w else 0,
            "queued": w.queued if w else 0,
            "wave_done": w.finished if w else 0,
            "wave_total": w.total if w else 0,
            "wave_elapsed": round(w.elapsed, 1) if w else 0.0,
            "raider": self.raider.state.current,
            "raider_hp": self.raider.hp,
            "raider_victims": len(self.raider.victims),
            "fighting": sum(1 for x in n if x.intent is not None and x.intent.kind == "fight"),
            "fleeing": sum(1 for x in n if x.intent is not None and x.intent.kind == "flee"),
            "healing": sum(1 for x in n if x.healer and not x.frozen and (
                x.rescue_target is not None or x.casting is not None
                or (x.intent is not None and x.intent.kind == "rescue"))),
            **self.counters,
        }

    # ---------- 記録 ----------

    def _log_wave(self):
        s = self.wave.summary()
        self.last_wave = s
        rec = {"type": "wave", "wall_time": time.time(), "sim_t": round(self.now, 1),
               "wave": self.wave_no, **s, "world": self.stats()}
        self._metrics.write(json.dumps(rec, ensure_ascii=False) + "\n")
        self._metrics.flush()
        logger.info("wave %d: n=%d %s ok=%d fail=%d %.1fs tok/s=%.0f TTFT p50=%.2f p95=%.2f "
                    "lat p50=%.2f p95=%.2f", self.wave_no, s["n"], s["kinds"], s["ok"], s["fail"],
                    s["wall_sec"], s["tok_per_sec"], s["ttft_p50"], s["ttft_p95"],
                    s["latency_p50"], s["latency_p95"])
        if s["by_kind"]:
            logger.info("wave %d 種類ごと（出力の平均 tok / 遅延 p50・最大）: %s", self.wave_no, " | ".join(
                f"{k} {v['tok_avg']:.0f}tok {v['lat_p50']:.1f}s・{v['lat_max']:.1f}s" for k, v in s["by_kind"].items()))
        if s["errors"]:
            logger.warning("wave %d errors: %s", self.wave_no, s["errors"])

    def _housekeeping_frame(self):
        if self.now >= self._commit_at:
            self._commit_at = self.now + 3.0
            self.save()
        if self.now >= self._metrics_at:
            self._metrics_at = self.now + self.cfg.log.metrics_every_sec
            st = self.stats()
            self._metrics.write(json.dumps({"type": "world", "wall_time": time.time(),
                                            "sim_t": round(self.now, 1), **st}, ensure_ascii=False) + "\n")
            logger.info("t=%5.0fs %s wave#%d | 歩行%d 会話%d 休息%d フリーズ%d おびえ%d 返答待ち%d | "
                        "HP平均%.0f 心平均%.0f | 同時%d 未送信%d | 会話%d 発話%d 励まし%d 救助%d フリーズ累計%d 失敗%d | "
                        "悪 %s HP%d 被害%d 戦う%d 逃げる%d",
                        self.now, st["phase"], st["wave"], st["moving"], st["talking"], st["resting"],
                        st["frozen"], st["fear"], st["waiting"], st["hp_avg"], st["heart_avg"],
                        st["inflight"], st["queued"], st["sessions"], st["utterances"], st["cheers"],
                        st["rescues"], st["freezes"], st["llm_fail"],
                        st["raider"], st["raider_hp"], st["raider_victims"], st["fighting"], st["fleeing"])

    def _log_prompt(self, res: LLMResult):
        """log.prompt_npc の NPC（と悪の魔物）のプロンプトと返答を prompts.txt に書く（system は変わったときだけ）"""
        if self._prompts is None:
            return
        name = self.raider.name if res.req.kind == "raider" else self.npcs[res.req.npc_id].name
        status = "ok" if res.ok else f"失敗 {res.error}"
        out = [f"===== wave {self.wave_no}  t={self.now:.1f}s  {name}  {res.req.kind}  {status}  "
               f"入力{res.prompt_tokens}tok 出力{res.completion_tokens}tok  "
               f"TTFT {res.ttft:.2f}s  {res.latency:.2f}s ====="]
        for m in res.req.messages:
            if m["role"] == "system":
                if m["content"] == self._prompt_system:
                    out.append("--- system ---\n（前回と同じ）")
                    continue
                self._prompt_system = m["content"]
            out.append(f"--- {m['role']} ---\n{m['content']}")
        reply = json.dumps(res.data, ensure_ascii=False, indent=2) if res.data is not None else res.text
        out.append(f"--- 返答 ---\n{reply}\n\n")
        self._prompts.write("\n".join(out))
        self._prompts.flush()

    def save(self):
        """次の起動で続きから始めるための状態を書いて commit する（数秒おきと終了時）"""
        self.db.save_hp([(n.hp, n.id) for n in self.npcs])
        # 襲来の途中で終わったら、その襲来は終わったことにして、起動直後と同じ間をおいてまた現れる
        r = self.raider
        next_at = self.now + self.cfg.raider.first_delay_sec if r.present else r.next_at
        self.db.save_snapshot({"now": self.now, "raid_no": r.raid_no, "raider_next_at": next_at,
                               "npcs": {n.id: {"x": n.x, "z": n.z, "hp": n.hp, "heart": n.heart,
                                               "status": n.status} for n in self.npcs}})
        self.db.commit()

    def close(self):
        if self.state.current == "running":   # LLM につながる前に閉じたら、前回の状態をそのまま残す
            self.save()
        else:
            self.db.commit()
        self._metrics.close()
        if self._prompts is not None:
            self._prompts.close()


def pick_roles(cfg, n: int) -> tuple[list[int], list[int]]:
    """戦士とヒーラーの id（world.seed で決まる。self.rng とは別の乱数にして、ほかの乱数の並びを変えない）。
    viewer/preview.py も同じ住人に剣・杖を持たせるためにこれを使う"""
    warriors = random.Random(f"warrior-{cfg.world.seed}").sample(range(n), min(cfg.warrior.count, n))
    others = [i for i in range(n) if i not in warriors]   # ヒーラーは戦士以外から（これも別の乱数）
    healers = random.Random(f"healer-{cfg.world.seed}").sample(others, min(cfg.healer.count, len(others)))
    return warriors, healers
