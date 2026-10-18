"""
スタブ LLM（mode = "stub"）

LLMClient と同じ submit() → Wave のインタフェースで、ダミーの JSON を返す。
スレッドは使わない：投げた時点で結果を作っておき、疑似レイテンシが過ぎたら
is_done() が True になるだけ。配管（ウェーブ・ステート遷移・DB）の確認用。
判断材料は LLMRequest.meta に入っている。セリフは [locale] lang の言語の表（lang/ の stub.*）から。
"""

from __future__ import annotations

import random
import time

import lang
from lang import t
from llm.client import LLMRequest, LLMResult, PendingInfo, ServerInfo, Wave

class StubWave(Wave):
    def __init__(self, requests: list[LLMRequest], results: list[LLMResult]):
        super().__init__(requests)
        self._stub_results = results
        self._delays = [r.latency for r in results]

    def is_done(self) -> bool:
        if self._results is not None:
            return True
        elapsed = time.perf_counter() - self.sent_at
        self.started = self.total
        self.finished = sum(1 for d in self._delays if d <= elapsed)
        if self.finished == self.total:
            self._results = self._stub_results
            self.finished_at = self.sent_at + max(self._delays, default=0.0)
            return True
        return False


class StubLLMClient:
    def __init__(self, seed: int, min_latency: float, max_latency: float):
        self.rng = random.Random(seed)
        self.min_latency = min_latency
        self.max_latency = max_latency

    def submit(self, requests: list[LLMRequest]) -> Wave:
        results = []
        for r in requests:
            data = getattr(self, f"_{r.kind}")(r.meta)
            lat = self.rng.uniform(self.min_latency, self.max_latency)
            results.append(LLMResult(r, ok=True, data=data, text=str(data), ttft=lat * 0.3,
                                     latency=lat, prompt_tokens=800, completion_tokens=30))
        return StubWave(requests, results)

    def ping(self) -> Wave:
        return self.submit([LLMRequest("ping", -1, [], None, 1)])

    def fetch_info(self) -> PendingInfo:
        return PendingInfo(value=ServerInfo(*lang.data("stub.server")))

    def close(self):
        pass

    # ---- 種類ごとのダミー判断 ----

    def _ping(self, m):
        return {}

    def _say(self, m):
        rng = self.rng
        if m.get("rescued_by"):
            text = t("stub.thanks", name=m["rescued_by"])
        else:
            text = rng.choice(lang.data("stub.say_lines")).format(p=m["partner_name"])
            if m["gossip"] and rng.random() < 0.3:   # 印象・聞いた噂を話題にする（名前を出す）
                who, what = rng.choice(m["gossip"])
                text = lang.clip(t("stub.gossip", who=who) + what, 40)
        cheer = m["partner_heart"] < 50 and rng.random() < 0.3 + m["generosity"] / 15
        if cheer:
            text = t("stub.cheer", name=m["partner_name"])
        end = m["turn"] >= 2 and rng.random() < 0.3
        return {"say": text, "cheer": cheer, "end": end}

    def _intent(self, m):
        rng = self.rng
        if m["raider_dist"] is not None:
            if m["warrior"] and m["hp"] > 30 and rng.random() < 0.8:
                return {"intent": "fight", "target": "", "pace": "fast",
                        "manner": t("stub.m.fight"), "duration_sec": 90}
            if not m["warrior"] and m["raider_dist"] < 40 and rng.random() < 0.7:
                return {"intent": "flee", "target": "", "pace": "fast",
                        "manner": t("stub.m.flee"), "duration_sec": 60}
        if m["healer"] and m["frozen"] and rng.random() < 0.85:
            return {"intent": "rescue", "target": m["frozen"][0], "pace": "fast",
                    "manner": t("stub.m.rescue"), "duration_sec": 90}
        if (m["heart"] < 40 or m["hp"] < 50) and not m["at_solace"]:
            return {"intent": "go_spot", "target": m["nearest_solace"], "pace": "normal",
                    "manner": t("stub.m.solace"), "duration_sec": 90}
        roll = rng.random()
        if roll < 0.35:
            spot = m["favorite"] if rng.random() < 0.5 else rng.choice(m["places"])
            return {"intent": "go_spot", "target": spot, "pace": rng.choice(["slow", "normal"]),
                    "manner": t("stub.m.spot", spot=spot), "duration_sec": 60}
        if roll < 0.5 and m["nearby"]:
            return {"intent": rng.choice(["seek", "follow"]), "target": rng.choice(m["nearby"]),
                    "pace": "normal", "manner": t("stub.m.seek"), "duration_sec": 40}
        if roll < 0.7:
            return {"intent": "patrol", "target": "", "pace": "slow",
                    "manner": t("stub.m.patrol"), "duration_sec": 80}
        if roll < 0.85:
            return {"intent": "wander", "target": "", "pace": "slow",
                    "manner": t("stub.m.wander"), "duration_sec": 30}
        return {"intent": "wait", "target": "", "pace": "slow",
                "manner": t("stub.m.wait"), "duration_sec": 15}

    def _rescue(self, m):
        danger = m["raider_dist"] is not None and m["raider_dist"] < 12
        heal = self.rng.random() < (0.5 if danger else 0.92)
        say = t("stub.heal", name=m["target_name"]) if heal else t("stub.no_heal")
        return {"heal": heal, "say": say}

    def _raider(self, m):
        """悪の魔物：HP が減ったら去ることもある。戦士でない、逃げていない近い住人を狙う"""
        rng = self.rng
        if m["hp"] <= m["max_hp"] * 0.3 and rng.random() < 0.5:
            return {"action": "leave", "target": "", "say": t("stub.r.leave_say"), "thought": t("stub.r.leave_thought")}
        cands = m["candidates"]
        easy = [c for c in cands if not c["warrior"] and c["doing"] != "flee"]
        pick = min(easy or cands, key=lambda c: c["dist"], default=None)
        if pick is None:
            return {"action": "leave", "target": "", "say": "", "thought": t("stub.r.empty")}
        say = rng.choice(lang.data("stub.r.says"))
        return {"action": "hunt", "target": pick["name"], "say": say,
                "thought": t("stub.r.hunt", name=pick["name"])}

    def _summary(self, m):
        old = m.get("old_summary") or ""
        add = t("stub.s.add", name=m["partner_name"], n=m["lines"])
        # 相手のセリフに出た名前を、そのセリフのまま噂として持ち帰る
        def note(n):   # スタブのセリフ「○○って、…」の前置きと、伝わるたびに付く「らしい」は外す
            line = next(x for x in m["partner_lines"] if lang.mentions(n, x)).replace(t("stub.gossip", who=n), "")
            return t("stub.hearsay", x=lang.clip(line.replace(t("stub.hearsay_mark"), "").strip(), 30))
        heard = [{"about": n, "note": note(n),
                  "feel": self.rng.randint(-1, 1)} for n in m["mentioned"][:2]]
        return {"thought": t("stub.s.thought", name=m["partner_name"]), "summary": (old + add)[-lang.chars(100):],
                "affinity_delta": self.rng.randint(-1, 2), "heard": heard}

    def _persona(self, m):
        rng = self.rng
        s = m["seed"]
        firsts = lang.data("stub.p.first_persons")
        return {
            **({"first_person": rng.choice(firsts)} if firsts else {}),
            "catchphrase": rng.choice(lang.data("stub.p.catchphrases")),
            "background": t("stub.p.background", spot=s["favorite_spot"]),
            "likes": s["favorite_spot"],
            "dislikes": t("stub.p.dislikes"),
            "goal": t("stub.p.goal"),
            "help_view": t("stub.p.help_yes") if s["generosity"] >= 5 else t("stub.p.help_no"),
            "walk_mood": s["move_habit"],
            "sample_lines": list(lang.data("stub.p.samples")),
        }
