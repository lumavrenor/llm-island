"""
SQLite アクセス（world.db）

メインスレッドからだけ触る（裏スレッドは HTTP 専用で DB を知らない）。
書き込みはその場で execute し、commit は World がまとめて数秒おきに行う。
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

SCHEMA = """
-- battery 列は 2026-10-13 から HP を入れている（列の名前は既存の world.db のまま）
CREATE TABLE IF NOT EXISTS npc(
    id INTEGER PRIMARY KEY, name TEXT UNIQUE, seed_json TEXT, persona_json TEXT, battery REAL);
CREATE TABLE IF NOT EXISTS events(
    id INTEGER PRIMARY KEY AUTOINCREMENT, t REAL, kind TEXT, actor_id INTEGER, target_id INTEGER,
    spot TEXT, detail_json TEXT);
CREATE INDEX IF NOT EXISTS events_actor ON events(actor_id, id);
CREATE INDEX IF NOT EXISTS events_target ON events(target_id, id);
CREATE TABLE IF NOT EXISTS sessions(
    id INTEGER PRIMARY KEY AUTOINCREMENT, t_start REAL, t_end REAL, a_id INTEGER, b_id INTEGER,
    spot TEXT, end_reason TEXT);
CREATE TABLE IF NOT EXISTS utterances(
    id INTEGER PRIMARY KEY AUTOINCREMENT, session_id INTEGER, t REAL, speaker_id INTEGER, text TEXT);
CREATE INDEX IF NOT EXISTS utterances_session ON utterances(session_id);
CREATE TABLE IF NOT EXISTS relations(
    a_id INTEGER, b_id INTEGER, affinity INTEGER DEFAULT 0, last_talk_t REAL, summary TEXT DEFAULT '',
    PRIMARY KEY(a_id, b_id));
-- 誰がどの出来事（主に救助）を知っているか。via_session_id が NULL なら当事者として知った
CREATE TABLE IF NOT EXISTS knowledge(
    npc_id INTEGER, event_id INTEGER, t REAL, via_session_id INTEGER, from_id INTEGER,
    PRIMARY KEY(npc_id, event_id));
-- 聞いた噂（会話の要約で、相手が名前を出して話した「ほかの住人・場所」についての話を取り出したもの）。
-- about は住人か場所の名前（about_id は住人なら id、場所なら NULL）。feel は聞いた側がそれをどう感じたか（-2〜2）。
-- parent_id は話し手が同じ about について持っていた噂（伝言の鎖をたどる用）、hops は鎖の長さ（話し手が自分で知っていたなら 1）
CREATE TABLE IF NOT EXISTS beliefs(
    id INTEGER PRIMARY KEY AUTOINCREMENT, t REAL, npc_id INTEGER, about TEXT, about_id INTEGER, text TEXT,
    feel INTEGER, from_id INTEGER, session_id INTEGER, hops INTEGER, parent_id INTEGER);
CREATE INDEX IF NOT EXISTS beliefs_npc ON beliefs(npc_id, about, id);
-- 前回終了時の世界（時刻・住人の位置と HP・心・状態異常・悪の襲来）。次の起動はここから続ける。無ければ新しく始める
CREATE TABLE IF NOT EXISTS world_state(key TEXT PRIMARY KEY, value_json TEXT);
-- 記憶を消しても残す情報。lang = 住人を作ったときの [locale] lang（無ければ 2026-10-13 より前の日本語の world.db）
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
"""

MEMORY_TABLES = ("events", "sessions", "utterances", "relations", "knowledge", "beliefs", "world_state")


class DB:
    def __init__(self, path: str | Path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)   # 初回は save/ がまだ無い
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def commit(self):
        self.conn.commit()

    def close(self):
        self.conn.commit()
        self.conn.close()

    def clear_memory(self):
        for t in MEMORY_TABLES:
            self.conn.execute(f"DELETE FROM {t}")
        self.conn.commit()

    # ---------- meta ----------

    def lang(self) -> str:
        """住人を作ったときの言語（記録が無い world.db は日本語で作ったもの）"""
        row = self.conn.execute("SELECT value FROM meta WHERE key='lang'").fetchone()
        return row["value"] if row else "ja"

    def set_lang(self, lang: str):
        self.conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES('lang', ?)", (lang,))

    # ---------- npc ----------

    def load_npcs(self) -> list[dict]:
        rows = self.conn.execute("SELECT * FROM npc ORDER BY id").fetchall()
        return [{"id": r["id"], "name": r["name"], "seed": json.loads(r["seed_json"]),
                 "persona": json.loads(r["persona_json"]), "battery": r["battery"]} for r in rows]

    def replace_npcs(self, npcs: list[dict]):
        self.conn.execute("DELETE FROM npc")
        self.conn.executemany(
            "INSERT INTO npc(id, name, seed_json, persona_json, battery) VALUES(?,?,?,?,?)",
            [(n["id"], n["name"], json.dumps(n["seed"], ensure_ascii=False),
              json.dumps(n["persona"], ensure_ascii=False), n["battery"]) for n in npcs])
        self.conn.commit()

    def save_hp(self, pairs: list[tuple[float, int]]):
        """(hp, id) の列。HP は battery 列に入れる（SCHEMA のコメント）"""
        self.conn.executemany("UPDATE npc SET battery=? WHERE id=?", pairs)

    # ---------- world_state（続きから始めるための世界の状態）----------

    def load_snapshot(self) -> dict | None:
        r = self.conn.execute("SELECT value_json FROM world_state WHERE key='snapshot'").fetchone()
        return json.loads(r[0]) if r else None

    def save_snapshot(self, snap: dict):
        self.conn.execute("INSERT OR REPLACE INTO world_state(key, value_json) VALUES('snapshot', ?)",
                          (json.dumps(snap, ensure_ascii=False),))

    # ---------- events ----------

    def add_event(self, kind: str, actor_id: int, target_id: int | None, spot: str,
                  text: str, **extra) -> int:
        detail = {"text": text, **extra}
        cur = self.conn.execute(
            "INSERT INTO events(t, kind, actor_id, target_id, spot, detail_json) VALUES(?,?,?,?,?,?)",
            (time.time(), kind, actor_id, target_id, spot, json.dumps(detail, ensure_ascii=False)))
        return cur.lastrowid

    def recent_event_texts(self, npc_id: int, limit: int, exclude_with: int | None = None,
                           kinds: tuple[str, ...] = ("talk", "cheer", "rescue", "frozen", "struck",
                                                     "defeated_raider", "fought_raider")) -> list[str]:
        q = (f"SELECT detail_json FROM events WHERE (actor_id=? OR target_id=?) "
             f"AND kind IN ({','.join('?' * len(kinds))})")
        args: list = [npc_id, npc_id, *kinds]
        if exclude_with is not None:   # 相手との出来事はペア記憶に入るので除く
            q += " AND NOT (actor_id IN (?,?) AND target_id IN (?,?))"
            args += [npc_id, exclude_with, npc_id, exclude_with]
        q += " ORDER BY id DESC LIMIT ?"
        args.append(limit)
        return [json.loads(r[0])["text"] for r in self.conn.execute(q, args)]

    def pair_strong_texts(self, a: int, b: int) -> list[str]:
        """救助・励まし（強い記憶。要約から消えても必ず注入する）"""
        rows = self.conn.execute(
            "SELECT detail_json FROM events WHERE kind IN ('rescue','cheer') "
            "AND ((actor_id=? AND target_id=?) OR (actor_id=? AND target_id=?)) ORDER BY id DESC LIMIT 4",
            (a, b, b, a))
        return [json.loads(r[0])["text"] for r in rows]

    def latest_thoughts(self, a: int, others: list[int]) -> dict[int, str]:
        """a が要約の前に書いた振り返り（summary_thought）の、相手ごとに最新のもの"""
        if not others:
            return {}
        rows = self.conn.execute(
            f"SELECT target_id, detail_json FROM events WHERE kind='summary_thought' AND actor_id=? "
            f"AND target_id IN ({','.join('?' * len(others))}) ORDER BY id", (a, *others))
        return {r[0]: json.loads(r[1])["text"] for r in rows}   # 後の行（新しいもの）で上書き

    def kind_texts(self, kind: str, limit: int) -> list[str]:
        """ある種類の出来事の説明文を、新しいもの limit 件だけ古い順に（悪の魔物の記憶など）"""
        rows = self.conn.execute("SELECT detail_json FROM events WHERE kind=? ORDER BY id DESC LIMIT ?",
                                 (kind, limit)).fetchall()
        return [json.loads(r[0])["text"] for r in reversed(rows)]

    def event_texts(self, ids: list[int]) -> dict[int, str]:
        if not ids:
            return {}
        rows = self.conn.execute(
            f"SELECT id, detail_json FROM events WHERE id IN ({','.join('?' * len(ids))})", ids)
        return {r[0]: json.loads(r[1])["text"] for r in rows}

    def rescue_events(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT id, actor_id, target_id, detail_json FROM events WHERE kind='rescue' ORDER BY id")
        return [{"id": r[0], "actor_id": r[1], "target_id": r[2], **json.loads(r[3])} for r in rows]

    # ---------- sessions / utterances ----------

    def start_session(self, a_id: int, b_id: int, spot: str) -> int:
        cur = self.conn.execute("INSERT INTO sessions(t_start, a_id, b_id, spot) VALUES(?,?,?,?)",
                                (time.time(), a_id, b_id, spot))
        return cur.lastrowid

    def end_session(self, session_id: int, reason: str):
        self.conn.execute("UPDATE sessions SET t_end=?, end_reason=? WHERE id=?",
                          (time.time(), reason, session_id))

    def add_utterance(self, session_id: int, speaker_id: int, text: str):
        self.conn.execute("INSERT INTO utterances(session_id, t, speaker_id, text) VALUES(?,?,?,?)",
                          (session_id, time.time(), speaker_id, text))

    # ---------- relations（a から見た b）----------

    def get_relation(self, a: int, b: int) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM relations WHERE a_id=? AND b_id=?", (a, b)).fetchone()

    def touch_relation(self, a: int, b: int):
        """会話した時刻だけ更新（要約は後から低優先度で届く）"""
        self.conn.execute(
            "INSERT INTO relations(a_id, b_id, affinity, last_talk_t, summary) VALUES(?,?,0,?,'') "
            "ON CONFLICT(a_id, b_id) DO UPDATE SET last_talk_t=excluded.last_talk_t",
            (a, b, time.time()))

    def top_relations(self, a: int, limit: int) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT b_id, affinity, summary FROM relations WHERE a_id=? ORDER BY ABS(affinity) DESC, last_talk_t DESC LIMIT ?",
            (a, limit)).fetchall()

    def update_relation(self, a: int, b: int, summary: str, affinity_delta: int) -> int:
        self.conn.execute(
            "INSERT INTO relations(a_id, b_id, affinity, last_talk_t, summary) VALUES(?,?,0,?,'') "
            "ON CONFLICT(a_id, b_id) DO NOTHING", (a, b, time.time()))
        self.conn.execute(
            "UPDATE relations SET summary=?, affinity=MAX(-10, MIN(10, affinity + ?)) WHERE a_id=? AND b_id=?",
            (summary, affinity_delta, a, b))
        return self.get_relation(a, b)["affinity"]

    # ---------- knowledge（噂の伝播）----------

    def add_knowledge(self, npc_id: int, event_id: int, via_session_id: int | None, from_id: int | None):
        self.conn.execute(
            "INSERT OR IGNORE INTO knowledge(npc_id, event_id, t, via_session_id, from_id) VALUES(?,?,?,?,?)",
            (npc_id, event_id, time.time(), via_session_id, from_id))

    def load_knowledge(self) -> dict[int, list[int]]:
        known: dict[int, list[int]] = {}
        for r in self.conn.execute("SELECT npc_id, event_id FROM knowledge ORDER BY t"):
            known.setdefault(r[0], []).append(r[1])
        return known

    # ---------- beliefs（聞いた噂）----------

    def add_belief(self, npc_id: int, about: str, about_id: int | None, text: str, feel: int,
                   from_id: int, session_id: int, hops: int, parent_id: int | None) -> int:
        cur = self.conn.execute(
            "INSERT INTO beliefs(t, npc_id, about, about_id, text, feel, from_id, session_id, hops, parent_id) "
            "VALUES(?,?,?,?,?,?,?,?,?,?)",
            (time.time(), npc_id, about, about_id, text, feel, from_id, session_id, hops, parent_id))
        return cur.lastrowid

    def latest_belief(self, npc_id: int, about: str, before_session: int) -> sqlite3.Row | None:
        """npc_id が about について、会話 before_session より前に聞いた最新の噂"""
        return self.conn.execute("SELECT * FROM beliefs WHERE npc_id=? AND about=? AND session_id<? "
                                 "ORDER BY id DESC LIMIT 1", (npc_id, about, before_session)).fetchone()

    def beliefs_about(self, npc_id: int, about: str, limit: int) -> list[sqlite3.Row]:
        """npc_id が about について聞いた噂（新しい順）"""
        return self.conn.execute("SELECT * FROM beliefs WHERE npc_id=? AND about=? ORDER BY id DESC LIMIT ?",
                                 (npc_id, about, limit)).fetchall()

    def recent_beliefs(self, npc_id: int, limit: int, exclude: tuple[str, ...] = (),
                       exclude_from: int | None = None) -> list[sqlite3.Row]:
        """npc_id が聞いた噂のうち新しいもの（about ごとに最新の 1 件だけ、新しい順）"""
        q = "SELECT * FROM beliefs WHERE id IN (SELECT MAX(id) FROM beliefs WHERE npc_id=?"
        args: list = [npc_id]
        if exclude:
            q += f" AND about NOT IN ({','.join('?' * len(exclude))})"
            args += exclude
        if exclude_from is not None:   # その相手から聞いた話は、その相手に話し返さない
            q += " AND from_id<>?"
            args.append(exclude_from)
        q += " GROUP BY about) ORDER BY id DESC LIMIT ?"
        args.append(limit)
        return self.conn.execute(q, args).fetchall()
