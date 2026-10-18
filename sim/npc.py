"""
NPC（島の住人）

ステート（core/state.py の StateMachine で管理。毎フレーム update() が 1 回だけ呼ばれ、必ずすぐ戻る）:

    idle ──(意図が届く)──▶ moving ──(到着/時間切れ)──▶ idle
      ▲                      │
      └──(会話が終わる)── talking ◀──(遭遇)──┘
    idle ──(ヒーラーが癒すと決めた)──▶ casting ──(詠唱が終わる)──▶ idle
    どこからでも ──(HP 0)──▶ frozen ──(ヒーラーに癒される)──▶ idle

■ HP・心・状態異常（2026-10-13 に電力から置き換え）
    hp      … 0〜[npc] max_hp。減るのはヤミゴーストの攻撃だけ（World.damage() を通す）。0 で状態異常 freeze
    heart   … 心 0〜[npc] max_heart。攻撃・ノイズ・目の前のフリーズで減り、solace・励ましで回復する
    status  … 状態異常の辞書 {名前: 始まった世界の時刻}。名前は lang の status のキー
        freeze … HP 0 で動けない。ヒーラーの癒しだけが解く（HP 100% で目覚める）
        noise  … 攻撃を受けてから [npc] noise_sec のあいだ、心がじわじわ減る
        fear   … 心が [npc] fear_heart 未満のあいだの「おびえ」（プロンプトと見た目に出る）

■ 判定はフィールド、振る舞いはステート
StateMachine.change() は「次のフレームから」遷移する。同じフレーム内の判定（遭遇できるか等）が
1 フレーム古いステートを見ないように、可否の判定は次のフィールドで行う:
    "freeze" in status     … フリーズ中（frozen プロパティ）
    session is not None    … 会話中
    waiting is not None    … LLM の返答待ち（返答待ちの間は新しい出来事に巻き込まない）
    casting is not None    … 詠唱中（ヒーラーだけ。癒している相手の id）
    rescue_target          … 救助判断の待ち（ヒーラーだけ。フリーズした住人を癒すかどうか）
    intent.kind が fight / flee … 悪と戦っている・悪から逃げている（会話や救助判断に巻き込まない）
"""

from __future__ import annotations

import math

import lang
from lang import t
from sim import movement
from core.state import StateMachine


class Npc:
    def __init__(self, row: dict, x: float, z: float, hp: float, heart: float):
        self.id: int = row["id"]
        self.name: str = row["name"]
        self.seed: dict = row["seed"]
        self.persona: dict = row["persona"]
        self.x, self.z = x, z
        self.heading = 0.0
        self.hp = hp
        self.heart = heart
        self.status: dict[str, float] = {}    # 状態異常 {名前: 始まった世界の時刻}
        self.state = StateMachine("idle")

        self.intent: movement.Intent | None = None
        self.need_intent: str | None = t("why.woke")   # 移動意図を聞く理由（None なら聞かない）
        self.waiting: str | None = None       # 返答待ちのリクエスト種別
        self.session = None                   # encounter.Session
        self.solace = None                    # いま中にいる solace（World.Spot）。毎フレーム決め直す
        self.rescue_target: int | None = None  # 救助判断の相手（フリーズ住人の id。ヒーラーだけ）
        self.rescuer: int | None = None       # 自分がフリーズ中、救助判断・詠唱をしてくれているヒーラーの id
        self.rescued_by: str | None = None    # 復活直後の最初の発話で触れるヒーラーの名前
        self.casting: int | None = None       # 詠唱中に癒している相手の id（ヒーラーだけ）
        self.cast_end = 0.0                   # 詠唱が終わる世界の時刻
        self.summaries_due: list = []         # 要約待ちの Session
        self.moving_now = False               # このフレームで歩いたか（ビューアのアニメ用）
        # --- 悪の魔物（sim/raid.py）---
        self.warrior = False                  # 戦士（剣と超能力で悪と戦える。悪から受けるダメージが減る）
        self.attack_ready_at = 0.0            # 次に超能力を撃てる世界の時刻
        self.alerted_raid = 0                 # 気づいている襲来の番号（Raider.raid_no と同じなら気づいている）
        self.raid_news = 0                    # 悪について新しく知ったら増える（返答待ちの意図が古くなったかの判定）
        # --- ヒーラー ---
        self.healer = False                   # フリーズした住人を魔法の杖で目覚めさせられる（起こせるのはヒーラーだけ）

    # ---------- 可否の判定（フィールドで見る）----------

    @property
    def frozen(self) -> bool:
        return "freeze" in self.status

    @property
    def free(self) -> bool:
        """新しい出来事（遭遇・救助判断）に巻き込んでよいか"""
        return (not self.frozen and self.session is None and self.waiting is None
                and self.casting is None and self.rescue_target is None
                and (self.intent is None or self.intent.kind not in ("fight", "flee")))

    def dist_to(self, other) -> float:
        return math.hypot(self.x - other.x, self.z - other.z)

    def face(self, other):
        self.heading = math.degrees(math.atan2(other.x - self.x, other.z - self.z))

    # ---------- 状態異常 ----------

    def add_status(self, name: str, now: float):
        """付ける（すでに付いていれば始まりの時刻だけ更新する＝続く時間が延びる）"""
        self.status[name] = now

    def remove_status(self, name: str):
        self.status.pop(name, None)

    def status_text(self) -> str:
        """プロンプト・画面用（なければ「なし」）"""
        labels = lang.data("status")
        return t("dot").join(labels[k] for k in labels if k in self.status) or t("none")

    # ---------- 意図 ----------

    def set_intent(self, intent: movement.Intent, world):
        self.intent = intent
        movement.start(intent, self, world)
        self.state.change("idle" if intent.kind == "wait" else "moving")

    def ask_intent(self, reason: str):
        if self.need_intent is None:
            self.need_intent = reason

    # ---------- 毎フレーム ----------

    def update(self, dt: float, world):
        moved = 0.0

        match self.state.update():
            case "idle":
                it = self.intent
                if it is not None and it.kind == "wait" and world.now - it.started >= it.duration:
                    self.ask_intent(t("why.solace_calm") if it.target in world.solace_spots
                                    else t("why.wait_bored"))

            case "moving":
                moved, arrived = movement.step(self, world, dt)
                if arrived:
                    world.on_arrived(self)
                elif world.now - self.intent.started >= self.intent.duration:
                    self.ask_intent(t("why.long"))   # 新しい意図が届くまでは今の動きを続ける

            case "talking":
                partner = world.npcs[self.session.partner_of(self.id)]
                self.face(partner)

            case "casting":
                target = world.npcs[self.casting]
                self.face(target)
                if world.now >= self.cast_end:
                    world.finish_heal(self)   # ここで idle へ戻る

            case "frozen":
                pass

        self.moving_now = moved > 0.0
        if self.frozen:
            self.solace = None
            return
        self._recover(dt, world)

    def _recover(self, dt: float, world):
        """HP・心の自然な増減と、時間で変わる状態異常（フリーズしていないときだけ）"""
        nc = world.cfg.npc
        before = self.heart
        self.solace = world.solace_at(self)
        hp_rate, heart_rate = nc.hp_regen, 0.0
        if self.solace is not None:
            hp_rate += world.cfg.solace.hp_rate
            heart_rate += world.cfg.solace.heart_rate
        if "noise" in self.status:
            if world.now - self.status["noise"] >= nc.noise_sec:
                self.remove_status("noise")
            else:
                heart_rate -= nc.noise_heart_drain
        self.hp = min(float(nc.max_hp), self.hp + hp_rate * dt)
        self.heart = max(0.0, min(float(nc.max_heart), self.heart + heart_rate * dt))
        self.update_fear(world)
        for th in nc.heart_low_thresholds:
            if before >= th > self.heart and self.session is None and self.casting is None:
                self.ask_intent(t("why.heart_low", th=th, status=self.status_text()))

    def update_fear(self, world):
        """心の値から「おびえ」を付け外しする"""
        if self.heart < world.cfg.npc.fear_heart:
            if "fear" not in self.status:
                self.add_status("fear", world.now)
                world.emit("status", npc=self.id, status="fear", on=True)
        elif "fear" in self.status:
            self.remove_status("fear")
            world.emit("status", npc=self.id, status="fear", on=False)
