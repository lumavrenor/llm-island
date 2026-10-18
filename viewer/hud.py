"""
HUD（左上：メトリクス）と情報パネル（左下：クリックした NPC の詳細）

文字列の作り直しは数フレームおき（毎フレーム Text を作り直すと重い）。
"""

from __future__ import annotations

from ursina import Text, Vec2, camera, color, window

import lang
from lang import t


class HUD:
    def __init__(self, world, rig):
        self.world, self.rig = world, rig
        self.text = Text(parent=camera.ui, text="", origin=(-0.5, 0.5), scale=0.78,
                         position=window.top_left + Vec2(0.02, -0.02))
        self.text.create_background(padding=0.02, radius=0.01, color=color.rgba(0, 0, 0, 0.45))
        self.help = Text(parent=camera.ui, text=t("hud.help"), origin=(0, -0.5), scale=0.7,
                         position=window.bottom + Vec2(0, 0.01), color=color.rgba(1, 1, 1, 0.6))
        self.timer = 0.0
        self.inner_voice = True
        self.muted = False

    def update(self, dt: float):
        self.timer -= dt
        if self.timer > 0:
            return
        self.timer = 0.25
        st = self.world.stats()
        lw = self.world.last_wave
        lines = [
            f"llm-island   wave #{st['wave']}  [{st['phase']}]",
            f"LLM: {self._llm_label()}",
            t("hud.residents", **st),
            t("hud.hp", hp=st["hp_avg"], heart=st["heart_avg"], fear=st["fear"], noise=st["noise"]),
        ]
        if st["phase"] == "wait":
            lines.append(t("hud.llm_wait", inflight=st["inflight"], queued=st["queued"], done=st["wave_done"],
                           total=st["wave_total"], elapsed=st["wave_elapsed"]))
        else:
            lines.append(t("hud.llm_idle"))
        if lw:
            lines.append(t("hud.last_wave", n=lw["n"], wall=lw["wall_sec"], tps=lw["tok_per_sec"],
                           p50=lw["ttft_p50"], p95=lw["ttft_p95"], fail=lw["fail"]))
        lines.append(t("hud.totals", **st))
        lines.append(t("hud.healers", healing=st["healing"], declined=st["heal_declined"]))
        lines.append(self._raid_line(st))
        lines.append(t("hud.camera", mode=self.rig.mode_label, inner="ON" if self.inner_voice else "OFF",
                       sound="OFF" if self.muted else "ON"))
        self.text.text = "\n".join(lines)
        self.text.create_background(padding=0.02, radius=0.01, color=color.rgba(0, 0, 0, 0.45))


    def _raid_line(self, st: dict) -> str:
        r = self.world.raider
        total = t("hud.raid_total", raids=st["raids"], defeated=st["raiders_defeated"], frozen=st["raider_frozen"])
        if not r.present:
            return t("hud.raid_none", total=total)
        doing = lang.data("hud.raid_doing").get(st["raider"], "")
        w = self.world
        aim = t("hud.thinking") if r.waiting else (w.npcs[r.target_id].name if r.target_id is not None else t("none"))
        return (t("hud.raid", name=r.name, doing=doing, hp=max(0, r.hp), max_hp=r.max_hp, victims=st["raider_victims"],
                  max_victims=w.cfg.raider.victims, aim=aim, fighting=st["fighting"], fleeing=st["fleeing"],
                  hits=sum(r.hits.values()), shots=sum(r.shots.values()), chits=w.counters["counter_hits"],
                  counters=w.counters["counters"])
                + (t("hud.raid_thought", x=r.thought) if r.thought and r.present and r.hp > 0 else ""))

    def _llm_label(self) -> str:
        """推論エンジン名とモデル名（サーバーに聞いた名乗り。聞けなければ config の model 名）"""
        w = self.world
        if w.server_info is not None:
            return w.server_info.label
        if w.server_info_failed:
            return t("hud.no_model", model=w.cfg.llm.model)
        return t("hud.checking")


class InfoPanel:
    def __init__(self, world):
        self.world = world
        self.npc_id: int | None = None
        self.text = Text(parent=camera.ui, text="", origin=(-0.5, -0.5), scale=0.72,
                         position=window.bottom_left + Vec2(0.02, 0.05), enabled=False)
        self.timer = 0.0

    def show(self, npc_id: int | None):
        self.npc_id = npc_id
        self.text.enabled = npc_id is not None
        self.timer = 0.0

    def update(self, dt: float):
        if self.npc_id is None:
            return
        self.timer -= dt
        if self.timer > 0:
            return
        self.timer = 0.5
        w = self.world
        n = w.npcs[self.npc_id]
        s, p = n.seed, n.persona
        if n.frozen:
            doing = t("info.frozen")
        elif n.session:
            doing = t("info.talking", name=w.npcs[n.session.partner_of(n.id)].name)
        elif n.casting is not None:
            doing = t("info.casting", name=w.npcs[n.casting].name)
        elif n.intent:
            doing = f"{n.intent.kind} {n.intent.target} ({n.intent.pace}) {n.intent.manner}"
        else:
            doing = t("info.thinking")
        nc = w.cfg.npc
        lines = [
            (t("info.warrior") if n.warrior else t("info.healer") if n.healer else "") + f"{n.name}  [{n.state.current}]"
            + (t("info.waiting", x=n.waiting) if n.waiting else ""),
            t("info.hp", hp=n.hp, max_hp=nc.max_hp, heart=n.heart, max_heart=nc.max_heart, status=n.status_text())
            + (t("info.solace", name=n.solace.name) if n.solace is not None else ""),
            t("info.seed", tone=s["tone"], habit=s["move_habit"], spot=s["favorite_spot"]),
            t("info.traits", **s),
            lang.fit(t("info.persona", catch=p.get("catchphrase", ""), goal=p.get("goal", "")), 60),
            lang.fit(t("info.now", x=doing), 60),
            t("info.events"),
            *[lang.fit(f" {x}", 52) for x in w.db.recent_event_texts(n.id, 4)],
            t("info.relations"),
            *[lang.fit(f" {w.npcs[r['b_id']].name} ({r['affinity']:+d}) {r['summary']}", 52)
              for r in w.db.top_relations(n.id, 3) if r["b_id"] < len(w.npcs)],
        ]
        self.text.text = "\n".join(lines)
        self.text.create_background(padding=0.02, radius=0.01, color=color.rgba(0, 0, 0, 0.55))
