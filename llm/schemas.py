"""
LLM 出力の JSON スキーマ

文字数・数値の範囲はスキーマに書かず、反映側（sim/world.py）で切り詰め・クランプする
（制約デコードの実装差で 400 エラーになるのを避けるため）。
"""

# 意図の種類。誰でも選べるものに、役割と状況で選べるものが足される:
#   rescue … ヒーラーだけ（フリーズした住人のところへ行って癒す）
#   flee   … 悪の魔物に気づいているとき（全員）
#   fight  … 悪の魔物に気づいているとき（戦士だけ）
INTENTS = ("go_spot", "seek", "follow", "avoid", "wander", "patrol", "wait")
ALL_INTENTS = INTENTS + ("rescue", "flee", "fight")
PACES = ("slow", "normal", "fast")


def _obj(props: dict) -> dict:
    return {"type": "object", "properties": props,
            "required": list(props), "additionalProperties": False}


SAY = _obj({
    "say": {"type": "string"},
    "cheer": {"type": "boolean"},
    "end": {"type": "boolean"},
})


def _intent(kinds) -> dict:
    return _obj({
        "intent": {"type": "string", "enum": list(kinds)},
        "target": {"type": "string"},
        "pace": {"type": "string", "enum": list(PACES)},
        "manner": {"type": "string"},
        "duration_sec": {"type": "integer"},
    })


_INTENT_SCHEMAS: dict[tuple[str, ...], dict] = {}


def intent_kinds(warrior: bool, healer: bool, raid_seen: bool) -> tuple[str, ...]:
    """この住人がいま選べる意図"""
    return (INTENTS + (("rescue",) if healer else ()) + (("flee",) if raid_seen else ())
            + (("fight",) if warrior and raid_seen else ()))


def intent_schema(warrior: bool, healer: bool, raid_seen: bool) -> dict:
    kinds = intent_kinds(warrior, healer, raid_seen)
    if kinds not in _INTENT_SCHEMAS:
        _INTENT_SCHEMAS[kinds] = _intent(kinds)
    return _INTENT_SCHEMAS[kinds]


# ヒーラーの救助判断（フリーズした住人のそばで、杖で癒すかどうか）
RESCUE = _obj({
    "heal": {"type": "boolean"},
    "say": {"type": "string"},
})

# 悪の魔物の判断（sim/raid.py）
RAIDER_ACTIONS = ("hunt", "leave")
RAIDER = _obj({
    "action": {"type": "string", "enum": list(RAIDER_ACTIONS)},
    "target": {"type": "string"},
    "say": {"type": "string"},
    "thought": {"type": "string"},
})

# thought: 先に書かせる心の中の振り返り（CoT。JSON は項目の順に生成されるので、要約・好感度より前に置く）
# heard: 相手が話した「ほかの住人・場所」の噂（件数・名前の確かさは memory/summarize.py で確かめる）
SUMMARY = _obj({
    "thought": {"type": "string"},
    "summary": {"type": "string"},
    "affinity_delta": {"type": "integer"},
    "heard": {"type": "array", "items": _obj({
        "about": {"type": "string"},
        "note": {"type": "string"},
        "feel": {"type": "integer"},
    })},
})

def persona(first_person: bool) -> dict:
    """性格の肉付け。一人称は日本語だけ（lang の uses_first_person）"""
    return _obj({
        **({"first_person": {"type": "string"}} if first_person else {}),
        "catchphrase": {"type": "string"},
        "background": {"type": "string"},
        "likes": {"type": "string"},
        "dislikes": {"type": "string"},
        "goal": {"type": "string"},
        "help_view": {"type": "string"},
        "walk_mood": {"type": "string"},
        "sample_lines": {"type": "array", "items": {"type": "string"}},
    })
