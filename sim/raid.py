"""
悪の魔物（Raider）と、戦士の攻撃

- ときどき 1 体だけ島の端に現れ、狙った住人を爪で攻撃して HP と心を削り、フリーズさせる。
  victims 体フリーズさせたら満腹で去る。戦士の攻撃で HP が 0 になると倒れる
- 撃ってきた戦士には黒い弾で反撃する（戦士も攻撃を受ける）。ヒーラーもほかの住人と同じく狙われる
- **何をするかは LLM が決める**（リクエスト種別 "raider"。住人と同じウェーブに 1 件だけ乗る）:
      hunt  … 誰を狙うか（target に住人の名前）
      leave … 島を去る
  プログラムがするのは、決めたことの実行（追いかける・届いたら爪で攻撃する・反撃する・去る）と、
  島の決まりごと（満腹・最長滞在・逃げ切られたら追えない）だけ
- 考え直すきっかけ（need_think に理由を入れる。ウェーブの collect で拾われる）:
  現れた / 獲物をフリーズさせた / 逃げられた / 狙っていた住人がほかの理由で止まった / 戦士に撃たれた・HP が減った /
  ヒーラーが住人を起こした / think_every_sec たった
  返答を待つ間も、今の獲物を追い続ける（獲物がいなければ島の中央へ漂う）
- 住人が逃げるか戦うかは住人の LLM が決める（移動意図の flee / fight）。ここでするのは
  「気づかせる」こと（need_intent に理由を入れる）と、状況の文に悪のことを書く材料を出すことだけ
- 戦士（Npc.warrior）は fight の意図のあいだ、射程に入ったら自動で超能力を撃つ。
  戦士は守りが固く、悪から受ける HP ダメージが defense の割合だけ減る
- 住人の HP・心を減らすのは world.damage() だけ（HP 0 でフリーズ）

ステート（core/state.py の StateMachine）。世界の時刻（--speed で速くなる）で数えるので、経過時間は
state.elapsed ではなく進入時に控えた since との差で見る（NPC の intent.started と同じ）:

    away     … 島にいない。next_at を過ぎたら appear
    appear   … 島の端に現れる（せり上がる演出の appear_sec だけ待つ。最初の判断はここで投げる）→ hunt
    hunt     … LLM が決めた獲物を追いかけ、届いたら爪で攻撃する。満腹・max_stay_sec・LLM の leave で leave
    leave    … いちばん近い島の端から出ていく → away
    defeated … 戦士に倒された。defeated_sec たったら消える → away

■ 同じフレーム内の判定はフィールドで見る（change() は次のフレームから）
    present  … 島にいる（見える・攻撃できる）
    hp > 0   … まだ倒れていない（hp は 0〜max_hp）
    active   … 考えて動いている（appear〜hunt）。去る・倒れると決まった時点で False（返答の反映はこれを見る）
    waiting  … LLM の返答待ち（1 ウェーブに 1 件まで）
"""

from __future__ import annotations

import math

import lang
from lang import t
from llm import prompts, schemas
from llm.client import LLMRequest, LLMResult
from core.state import StateMachine

RAIDER_ID = -1   # カメラ・ふきだし・LLMRequest.npc_id で悪を指す id（住人の id は 0 から）

# プログラムが決めた出来事のときだけのひとこと（ふきだし用。ほかのセリフは LLM が決める）は lang の taunts、
# 去り方の文は lang の leave_how（キーは leave_reason）


class Raider:
    def __init__(self, cfg):
        rc = cfg.raider
        self.name: str = rc.name
        self.state = StateMachine("away")
        self.since = 0.0                     # 今のステートに入った世界の時刻
        self.next_at: float = rc.first_delay_sec
        self.x, self.z, self.heading = 0.0, 0.0, 0.0
        self.max_hp: int = rc.max_hp
        self.hp: int = rc.max_hp
        self.present = False
        self.active = False
        self.raid_no = 0                     # 何回目の襲来か（Npc.alerted_raid と比べる）
        self.raid_start = 0.0
        self.result = ""                     # 直近の襲来の終わり方: "left" / "defeated"
        self.leave_reason = ""               # 去った理由: choice（LLM）/ full / time / empty
        # --- LLM ---
        self.need_think: str | None = None   # 考え直す理由（None なら聞かない）
        self.waiting = False
        self.thought_at = 0.0                # 最後に判断を反映した世界の時刻
        self.thought = ""                    # 直近の考え（HUD 用）
        # --- 獲物 ---
        self.target_id: int | None = None    # LLM が決めた獲物
        self.chase_since = 0.0
        self.contact: int | None = None      # いま爪が届いている住人
        self.contact_dealt = 0.0             # その住人に、届いてから与えた HP ダメージ
        self.strike_ready_at = 0.0           # 次に爪で攻撃できる世界の時刻
        self.counter_ready_at = 0.0          # 次に反撃できる世界の時刻
        self.strike_pose_until = 0.0         # この世界の時刻まで腕を振り抜いた姿勢（ビューアの演出用）
        self.dealt: dict[int, float] = {}    # 住人 id → この襲来で与えた HP ダメージ
        self.victims: list[int] = []         # フリーズさせた住人
        self.escaped: set[int] = set()       # 追いかけて逃げ切られた住人（この襲来では狙えない）
        self.revived: list[tuple[str, str]] = []   # この襲来でヒーラーが起こした住人（起こされた, ヒーラー）
        # --- 戦士 ---
        self.attackers: dict[int, float] = {}   # 戦士 id → 最後に撃ってきた時刻
        self.shots: dict[int, int] = {}         # 戦士 id → 撃った回数
        self.hits: dict[int, int] = {}          # 戦士 id → 当てた回数
        self.exit = (0.0, 0.0)

    def dist(self, other) -> float:
        return math.hypot(self.x - other.x, self.z - other.z)

    def face(self, other):
        self.heading = math.degrees(math.atan2(other.x - self.x, other.z - self.z))

    def ask(self, reason: str):
        """考え直す理由を積む（すでに積まれていればそちらを優先）"""
        if self.active and self.need_think is None:
            self.need_think = reason

    def wants_think(self) -> bool:
        """このウェーブで判断のリクエストを出すか"""
        return self.active and not self.waiting and self.need_think is not None

    # ---------- 毎フレーム ----------

    def update(self, dt: float, world):
        rc = world.cfg.raider
        current = self.state.update()
        if self.state.entered:
            self.since = world.now
        match current:
            case "away":
                if world.now >= self.next_at:
                    self.state.change("appear")

            case "appear":
                if self.state.entered:
                    self._appear(world)
                elif world.now - self.since >= rc.appear_sec:
                    self.state.change("hunt")

            case "hunt":
                self._alert_nearby(world)
                self._hunt(dt, world)
                if self.active:
                    self._counter(world)

            case "leave":
                if self.state.entered:
                    self._start_leave(world)
                if self._walk_to(self.exit, dt, rc.speed, 0.5):
                    self._finish(world, "left")
                    self.state.change("away")

            case "defeated":
                if world.now - self.since >= rc.defeated_sec:
                    self.present = False
                    self.state.change("away")

    # ---------- 襲来 ----------

    def _appear(self, world):
        rng = world.rng
        self.raid_no += 1
        self.hp = self.max_hp
        self.present = True
        self.active = True
        self.raid_start = world.now
        self.thought_at = world.now
        self.result = self.leave_reason = self.thought = ""
        self.target_id = self.contact = None
        self.strike_ready_at = self.counter_ready_at = self.strike_pose_until = 0.0
        self.dealt, self.victims, self.escaped, self.revived = {}, [], set(), []
        self.attackers, self.shots, self.hits = {}, {}, {}
        # 島の端のどこか（4 辺のどれか）
        h = world.half - 2.0
        u = rng.uniform(-h, h)
        self.x, self.z = [(u, -h), (u, h), (-h, u), (h, u)][rng.randrange(4)]
        self.heading = math.degrees(math.atan2(-self.x, -self.z))   # 島の中央を向く
        world.counters["raids"] += 1
        spot = world.nearest_spot(self).name
        self.need_think = t("r.why.arrived", spot=spot)
        world.db.add_event("raid", None, None, spot, t("r.ev.appear", name=self.name, spot=spot))
        world.emit("raider_appear", raid=self.raid_no, spot=spot)
        # 戦士は島のどこにいても気配を感じる
        for npc in world.npcs:
            if npc.warrior:
                self.alert(npc, world, t("r.alert.appear", name=self.name, spot=spot))

    def alert(self, npc, world, reason: str, force: bool = False):
        """住人に悪のことを気づかせる（この襲来で 1 回だけ。force なら何度でも）"""
        if npc.frozen or (npc.alerted_raid == self.raid_no and not force):
            return
        npc.alerted_raid = self.raid_no
        npc.raid_news += 1   # 返答待ちの移動意図は、これが変わっていたら捨てて聞き直す（world._apply_intent）
        # 会話中は意図を聞かないので、理由は入れない（状況の文には悪のことが出る）。詠唱中は終わってから聞く
        if npc.session is None:
            npc.need_intent = reason   # ほかの理由より優先する
        world.emit("raider_alert", npc=npc.id)

    def _alert_nearby(self, world):
        radius = world.cfg.raider.alert_radius
        for npc in world.npcs:
            if npc.alerted_raid != self.raid_no and not npc.frozen and self.dist(npc) <= radius:
                self.alert(npc, world, t("r.alert.near", name=self.name))

    def _hunt(self, dt: float, world):
        rc = world.cfg.raider
        if len(self.victims) >= rc.victims:
            self._go_leave(world, "full")
            return
        if world.now - self.raid_start >= rc.max_stay_sec:
            self._go_leave(world, "time")
            return
        if not self.waiting and world.now - self.thought_at >= rc.think_every_sec:
            self.ask(t("r.why.idle"))
        target = self._current_target(world)
        if target is not None and self.contact is not None and (self.contact != target.id or
                                                                self.dist(target) > rc.reach):
            self._release(world)   # 触れていた住人から離れた（獲物を変えた・振り切られた）
        if target is None:
            self._release(world)
            if not self.waiting:
                self.ask(t("r.why.no_target"))
            self._walk_to((0.0, 0.0), dt, rc.prowl_speed, 10.0)   # 返答を待つ間は島の中央へ漂う
            return
        if self.dist(target) > rc.reach:
            self._walk_to((target.x, target.z), dt, rc.speed, rc.reach * 0.8)
            if world.now - self.chase_since >= rc.give_up_sec:
                self.escaped.add(target.id)   # 逃げ切られた
                self.target_id = None
                world.emit("raider_escaped", npc=target.id)
                self.ask(t("r.why.escaped", name=target.name, sec=rc.give_up_sec))
            return
        self.face(target)
        self._strike(target, world)

    def _current_target(self, world):
        """LLM が決めた獲物（まだ狙えるなら）"""
        if self.target_id is None:
            return None
        target = world.npcs[self.target_id]
        if target.frozen:   # 自分の爪以外の理由でフリーズした（反撃の弾など）
            self.target_id = None
            self.ask(t("r.why.target_frozen", name=target.name))
            return None
        return target

    def _strike(self, target, world):
        """爪が届いている：strike_cooldown_sec ごとに一撃（戦士は defense の分だけ HP ダメージが減る）"""
        rc, wc = world.cfg.raider, world.cfg.warrior
        if self.contact != target.id:
            self.contact, self.contact_dealt = target.id, 0.0
            self._grab(target, world)
        self.chase_since = world.now   # 届いている間は「追いかけている」時間を数えない
        if world.now < self.strike_ready_at:
            return
        self.strike_ready_at = world.now + rc.strike_cooldown_sec
        self.strike_pose_until = world.now + 0.4
        dmg = rc.strike_damage * ((1.0 - wc.defense) if target.warrior else 1.0)
        dmg = min(dmg, target.hp)
        self.dealt[target.id] = self.dealt.get(target.id, 0.0) + dmg
        self.contact_dealt += dmg
        world.counters["strikes"] += 1
        froze = world.damage(target, dmg, rc.strike_heart, t("r.cause.strike", name=self.name))
        world.emit("raider_strike", npc=target.id, damage=round(dmg), hp=round(target.hp), frozen=froze)
        if not froze:
            return
        # フリーズさせた
        self.contact = None
        self.target_id = None
        self.victims.append(target.id)
        world.counters["raider_frozen"] += 1
        spot = world.spot_name(target)
        who = t(f"r.who.{role_key(target)}", name=target.name)
        world.db.add_event("frozen", target.id, None, spot,
                           t("r.ev.frozen", who=who, spot=spot, raider=self.name),
                           cause="strike", raid=self.raid_no)
        world.emit("raider_froze", npc=target.id, victims=len(self.victims))
        self.ask(t("r.why.froze", name=target.name))

    def _release(self, world):
        """爪が届いていた住人から離れた。フリーズさせずに済んだなら「攻撃を受けたが逃れた」を残す"""
        i, self.contact = self.contact, None
        if i is None:
            return
        npc = world.npcs[i]
        dealt = int(round(self.contact_dealt))
        if npc.frozen or dealt < 1:
            return
        spot = world.spot_name(npc)
        world.db.add_event("struck", i, None, spot,
                           t("r.ev.struck", name=npc.name, spot=spot, raider=self.name, dealt=dealt),
                           damage=dealt, raid=self.raid_no)
        world.emit("raider_escaped_hit", npc=i, damage=dealt)

    def _grab(self, target, world):
        """爪が届いた。会話は打ち切られ、逃げも戦いもしていなければ意図を聞き直す"""
        if target.session is not None:
            world.end_session(target.session, "raider")
        busy = target.intent is not None and target.intent.kind in ("flee", "fight")
        self.alert(target, world, t("r.alert.grab", name=self.name), force=not busy)
        world.emit("raider_grab", npc=target.id)

    def _counter(self, world):
        """反撃：aggro_sec 以内に撃ってきた戦士のうち、counter_range に入っているいちばん近い 1 体へ黒い弾"""
        rc = world.cfg.raider
        if self.hp <= 0 or world.now < self.counter_ready_at:
            return
        foes = [world.npcs[i] for i, at in self.attackers.items()
                if world.now - at <= rc.aggro_sec and not world.npcs[i].frozen
                and self.dist(world.npcs[i]) <= rc.counter_range]
        if not foes:
            return
        foe = min(foes, key=self.dist)
        self.counter_ready_at = world.now + rc.counter_cooldown_sec
        hit = world.rng.random() < rc.counter_hit_chance
        world.counters["counters"] += 1
        froze = False
        dmg = 0.0
        if hit:
            world.counters["counter_hits"] += 1
            dmg = min(foe.hp, rc.counter_damage * (1.0 - world.cfg.warrior.defense))
            self.dealt[foe.id] = self.dealt.get(foe.id, 0.0) + dmg
            froze = world.damage(foe, dmg, rc.counter_heart, t("r.cause.counter", name=self.name))
        world.emit("raider_counter", npc=foe.id, hit=hit, damage=round(dmg), frozen=froze)
        if froze:
            self.victims.append(foe.id)
            world.counters["raider_frozen"] += 1
            if self.target_id == foe.id:
                self.target_id = None
                self._release(world)
            spot = world.spot_name(foe)
            world.db.add_event("frozen", foe.id, None, spot,
                               t("r.ev.counter_frozen", name=foe.name, spot=spot, raider=self.name),
                               cause="counter", raid=self.raid_no)
            world.emit("raider_froze", npc=foe.id, victims=len(self.victims))
            self.ask(t("r.why.counter_froze", name=foe.name))

    def on_revived(self, world, target, healer):
        """ヒーラーが住人を起こした（world._apply_rescue から）"""
        if not self.active:
            return
        self.revived.append((target.name, healer.name))
        self.ask(t("r.why.revived", healer=healer.name, target=target.name))

    # ---------- LLM ----------

    def build_request(self, world) -> LLMRequest:
        """判断のリクエスト（world._build_requests から。wants_think() のときだけ）"""
        reason, self.need_think = self.need_think, None
        self.waiting = True
        cands = self._candidates(world)
        memories = world.db.kind_texts("raid_end", 3)   # これまでの襲来（今回の分は終わるまで入らない）
        msgs = prompts.raider_messages(world.cfg, memories, self._situation(world, cands), reason)
        return LLMRequest("raider", RAIDER_ID, msgs, schemas.RAIDER, 160, meta={
            "raid_no": self.raid_no, "reason": reason, "hp": self.hp, "max_hp": self.max_hp,
            "victims": len(self.victims),
            "candidates": [{"name": n.name, "dist": round(self.dist(n)), "hp": round(n.hp),
                            "warrior": n.warrior, "healer": n.healer,
                            "doing": n.intent.kind if n.intent else ""} for n in cands]})

    def apply_result(self, world, res: LLMResult):
        """判断の反映（ウェーブの play の前。返答を待つ間に状況が変わっていないかを先に見る）"""
        self.waiting = False
        if not self.active or res.req.meta["raid_no"] != self.raid_no:
            return   # 返答を待つ間に倒された・去った
        data = res.data if res.ok and res.data else {}
        action = data.get("action")
        say = lang.clip(str(data.get("say") or "").strip(), 20)
        thought = lang.clip(str(data.get("thought") or "").strip(), 40)
        reason = res.req.meta["reason"]
        self.thought_at = world.now
        self.thought = thought
        spot = world.nearest_spot(self).name
        if action == "leave":
            world.db.add_event("raider_plan", None, None, spot, t("r.ev.plan_leave", name=self.name),
                               action="leave", reason=reason, thought=thought, say=say,
                               raid=self.raid_no, hp=self.hp, victims=len(self.victims))
            world.emit("raider_think", text=thought, say=say, target=None)
            self._go_leave(world, "choice")
            return
        target = world.npc_by_name.get(str(data.get("target") or "").strip()) if action == "hunt" else None
        valid = target is not None and not target.frozen and target.id not in self.escaped
        if not valid:
            # 返答の失敗・名前の間違い・待つ間に止まった：本能でいちばん近い住人を狙う
            world.counters["invalid_raider"] += 1
            target = min((n for n in world.npcs if not n.frozen and n.id not in self.escaped),
                         key=self.dist, default=None)
            if target is None:
                self._go_leave(world, "empty")
                return
        if target.id != self.target_id:
            self.target_id = target.id
            self.chase_since = world.now
        world.db.add_event("raider_plan", None, None, spot, t("r.ev.plan_hunt", name=self.name, target=target.name),
                           action="hunt", target=target.id, role=role_key(target), valid=valid, reason=reason,
                           thought=thought, say=say, dist=round(self.dist(target)), target_hp=round(target.hp),
                           raid=self.raid_no, hp=self.hp, victims=len(self.victims))
        world.emit("raider_think", text=thought, say=say, target=target.id)

    def _candidates(self, world) -> list:
        """状況の文に載せる「狙える住人」（フリーズしていない・逃げ切られていない。近い順）"""
        ok = (n for n in world.npcs if not n.frozen and n.id not in self.escaped)
        return sorted(ok, key=self.dist)[:world.cfg.raider.candidates]

    def _situation(self, world, cands) -> str:
        rc = world.cfg.raider
        names = lambda ids: lang.sep().join(world.npcs[i].name for i in ids)
        lines = [
            t("sit.place", x=world.place_name(self)),
            t("r.sit.hp", hp=max(0, self.hp), max_hp=self.max_hp),
            t("r.sit.time", sec=int(world.now - self.raid_start), max=rc.max_stay_sec),
            t("r.sit.victims", n=len(self.victims), left=rc.victims - len(self.victims))
            + (t("r.sit.victim_names", names=names(self.victims)) if self.victims else ""),
        ]
        if self.target_id is not None:
            tg = world.npcs[self.target_id]
            lines.append(t("r.sit.target", name=tg.name, d=int(self.dist(tg))))
        else:
            lines.append(t("r.sit.no_target"))
        recent = [i for i, at in self.attackers.items() if world.now - at <= rc.aggro_sec]
        if recent:
            lines.append(t("r.sit.attackers") + lang.sep().join(
                t("r.sit.attacker", name=world.npcs[i].name, d=int(self.dist(world.npcs[i])),
                  shots=self.shots.get(i, 0), hits=self.hits.get(i, 0)) for i in recent))
        if self.escaped:
            lines.append(t("r.sit.escaped", names=names(self.escaped)))
        if self.revived:
            lines.append(t("r.sit.revived") + lang.sep().join(
                t("r.sit.revived_item", target=a, healer=h) for a, h in self.revived[-4:]))
        lines.append(t("r.sit.frozen_count", n=sum(1 for n in world.npcs if n.frozen)))
        if cands:
            lines.append(t("r.sit.cands"))
            lines += [t("r.sit.cand", name=n.name, d=int(self.dist(n)), hp=int(n.hp), label=self._label(n, world))
                      for n in cands]
        else:
            lines.append(t("r.sit.no_cands"))
        return "\n".join(lines)

    def _label(self, npc, world) -> str:
        role = t("role.warrior") if npc.warrior else t("role.healer") if npc.healer else ""
        kind = npc.intent.kind if npc.intent is not None else ""
        if kind == "fight":
            doing = t("r.doing.fight")
        elif kind == "flee":
            doing = t("r.doing.flee")
        elif npc.session is not None:
            doing = t("doing.talking")
        elif npc.casting is not None:
            doing = t("r.doing.casting")
        elif npc.rescue_target is not None or kind == "rescue":
            doing = t("r.doing.rescue")
        elif npc.solace is not None:
            doing = t("r.doing.solace")
        elif npc.moving_now:
            doing = t("r.doing.walk")
        else:
            doing = t("r.doing.stand")
        return t("dot").join(x for x in (role, doing) if x)

    # ---------- 去る・倒れる ----------

    def _go_leave(self, world, why: str):
        """去ると決まった（LLM の leave / 満腹 / 時間切れ / 獲物がいない）"""
        self._release(world)
        self.active = False
        self.need_think = None
        self.target_id = None
        self.leave_reason = why
        self.state.change("leave")
        if why in lang.data("taunts"):
            world.emit("raider_say", text=lang.data("taunts")[why])

    def _start_leave(self, world):
        h = world.half + 4.0   # 島の外まで歩いてから消える
        self.exit = min([(self.x, -h), (self.x, h), (-h, self.z), (h, self.z)],
                        key=lambda p: math.hypot(p[0] - self.x, p[1] - self.z))
        world.emit("raider_leave", victims=len(self.victims), reason=self.leave_reason)

    def defeat(self, world):
        """戦士の攻撃で HP が 0 になった（raid.warrior_attacks から呼ぶ）"""
        self._release(world)
        self.hp = 0
        self.active = False
        self.need_think = None
        self.target_id = None
        self.state.change("defeated")
        world.counters["raiders_defeated"] += 1
        world.emit("raider_say", text=lang.data("taunts")["defeated"])
        self._finish(world, "defeated")

    def _finish(self, world, result: str):
        """襲来の終わり。戦った戦士それぞれの記憶と、襲来のまとめを DB に残す（まとめは悪の記憶にもなる）"""
        rc = world.cfg.raider
        self.result = result
        if result == "left":
            self.present = False
        self.next_at = world.now + world.rng.uniform(rc.interval_min_sec, rc.interval_max_sec)
        spot = world.nearest_spot(self).name
        fighters = sorted(self.shots, key=lambda i: -self.hits.get(i, 0))
        for i in fighters:
            npc = world.npcs[i]
            others = lang.sep().join(world.npcs[j].name for j in fighters if j != i)
            with_whom = t("r.with", names=others) if others else t("r.alone")
            kind = "defeated_raider" if result == "defeated" else "fought_raider"
            world.db.add_event(kind, i, None, spot,
                               t("r.ev.defeated" if result == "defeated" else "r.ev.fought", name=npc.name, spot=spot,
                                 raider=self.name, with_whom=with_whom, shots=self.shots[i], hits=self.hits.get(i, 0)))
        how = t("r.how.defeated") if result == "defeated" else \
            lang.data("leave_how").get(self.leave_reason, t("r.how.default"))
        fought = lang.sep().join(t("r.fought_item", name=world.npcs[i].name, shots=self.shots[i],
                                   hits=self.hits.get(i, 0)) for i in fighters)
        world.db.add_event("raid_end", None, None, spot,
                           t("r.ev.raid_end", no=self.raid_no, raider=self.name, how=how,
                             sec=int(world.now - self.raid_start), victims=len(self.victims),
                             revived=len(self.revived), fought=fought or t("r.nobody")),
                           result=result, reason=self.leave_reason, raid=self.raid_no, victims=self.victims,
                           revived=len(self.revived), shots=self.shots, hits=self.hits, hp=self.hp,
                           duration=round(world.now - self.raid_start, 1))
        world.emit("raider_gone" if result == "left" else "raider_defeated",
                   victims=len(self.victims), fighters=fighters)

    # ---------- 補助 ----------

    def _walk_to(self, goal: tuple[float, float], dt: float, speed: float, stop_dist: float) -> bool:
        """goal へ向かって 1 フレーム分歩く。stop_dist 以内に入っていたら True"""
        dx, dz = goal[0] - self.x, goal[1] - self.z
        d = math.hypot(dx, dz)
        if d <= stop_dist:
            return True
        step = min(d - stop_dist, speed * dt)
        self.x += dx / d * step
        self.z += dz / d * step
        self.heading = math.degrees(math.atan2(dx, dz))
        return False

    def describe(self, world, npc) -> str | None:
        """npc の「今の状況」に入れる悪の様子（気づいていなければ None）"""
        if not self.present or not (npc.warrior or npc.alerted_raid == self.raid_no):
            return None
        place = world.place_name(self)
        d = int(self.dist(npc))
        if self.hp <= 0:
            doing = t("r.d.down")
        elif self.state.current == "leave":
            doing = t("r.d.leaving")
        elif self.target_id == npc.id:
            doing = t("r.d.you")
        elif self.target_id is not None:
            doing = t("r.d.other", name=world.npcs[self.target_id].name)
        else:
            doing = t("r.d.search")
        fighters = [n.name for n in world.npcs if n.warrior and not n.frozen
                    and n.intent is not None and n.intent.kind == "fight"]
        text = t("r.d.text", raider=self.name, place=place, d=d, doing=doing, hp=max(0, self.hp),
                 max_hp=self.max_hp, victims=len(self.victims))
        if fighters:
            text += t("r.d.fighters") + lang.sep().join(fighters[:5])
        return text


def role_key(npc) -> str:
    """出来事の記録に残す役割（言語によらないキー。report.py が数える）"""
    return "warrior" if npc.warrior else "healer" if npc.healer else "resident"


def warrior_attacks(world):
    """fight の意図の戦士が、射程に入っていてクールダウンが明けていれば撃つ（World.update から毎フレーム）"""
    r = world.raider
    if not (r.present and r.hp > 0):
        return
    wc = world.cfg.warrior
    for npc in world.npcs:
        if (not npc.warrior or npc.frozen or npc.session is not None or npc.intent is None
                or npc.intent.kind != "fight" or world.now < npc.attack_ready_at
                or r.dist(npc) > wc.attack_range):
            continue
        npc.attack_ready_at = world.now + wc.attack_cooldown_sec
        npc.face(r)
        hit = world.rng.random() < wc.hit_chance
        if npc.id not in r.shots:
            r.ask(t("r.why.shot", name=npc.name))
        r.attackers[npc.id] = world.now
        r.shots[npc.id] = r.shots.get(npc.id, 0) + 1
        world.counters["warrior_shots"] += 1
        if hit:
            before = r.hp
            r.hp = max(0, r.hp - wc.attack_damage)
            r.hits[npc.id] = r.hits.get(npc.id, 0) + 1
            world.counters["warrior_hits"] += 1
            for th in (r.max_hp // 2, r.max_hp * 3 // 10):   # 半分と 3 割を切ったら考え直す
                if before > th >= r.hp > 0:
                    r.ask(t("r.why.hit", name=npc.name, hp=r.hp))
        world.emit("attack", npc=npc.id, hit=hit, hp=r.hp)
        if r.hp <= 0:
            r.defeat(world)
            return
