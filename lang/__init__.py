"""
言語（config.toml の [locale] lang = "ja" / "en"）

LLM に見せる文（プロンプト・状況の文・出来事の記録）、スタブの返答、ビューアの文字は、
言語ごとの表（lang/ja.py・lang/en.py の TEXT）から引く。コードには文を書かない。
config.load_config() が use() を 1 回だけ呼ぶ（1 つのプロセスでは 1 つの言語だけ）。

    t("ev.arrived", a=..., spot=...)   … 文（str.format の書式。引数がなければそのまま）
    data("tones")                      … 文以外（一覧・辞書・真偽）

言語で変わる「名前の見つけ方」もここに置く:
    mentions(name, text) … 文の中に名前が出ているか。日本語は部分一致（いままでどおり）、
                           英語は単語単位で大文字小文字を区別しない（"Ana" が "banana" に当たらないように）
    clip(text, n)        … LLM の返答を日本語 n 文字ぶんの長さに切る（英語は単語の切れ目で）
    fit(text, n)         … 画面に出す 1 行を日本語 n 文字ぶんの幅に切る
"""

from __future__ import annotations

import re
import textwrap
from importlib import import_module

LANGS = ("ja", "en")

code = ""                       # 使っている言語（use() のあと）
_text: dict = {}


def use(lang: str):
    """言語を決める（config.load_config() から）。表のキーが日本語と同じでなければ止める（訳し漏れ）"""
    global code, _text
    if lang not in LANGS:
        raise ValueError(f'[locale] lang は {" / ".join(LANGS)} のどれか（"{lang}"）')
    table = import_module(f"lang.{lang}").TEXT
    base = import_module("lang.ja").TEXT
    if set(table) != set(base):
        diff = sorted(set(table) ^ set(base))
        raise ValueError(f"lang/{lang}.py のキーが lang/ja.py と違います: {diff[:10]}")
    code, _text = lang, table


def t(key: str, **kw) -> str:
    s = _text[key]
    return s.format(**kw) if kw else s


def data(key: str):
    return _text[key]


def sep() -> str:
    """並べるときの区切り（日本語「、」/ 英語 ", "）"""
    return _text["sep"]


def mentions(name: str, text: str) -> bool:
    if code == "en":
        return re.search(rf"(?<![A-Za-z]){re.escape(name)}(?![A-Za-z])", text, re.IGNORECASE) is not None
    return name in text


def chars(n: int) -> int:
    """日本語 n 文字ぶんの、この言語での文字数（LLM の返答の長さの上限）"""
    return int(n * _text["char_ratio"])


def clip(text: str, n: int) -> str:
    limit = chars(n)
    if len(text) <= limit:
        return text
    cut = text[:limit]
    if code == "en" and " " in cut[limit // 2:]:
        cut = cut[:cut.rindex(" ")]   # 単語の途中で切らない
    return cut.rstrip()


def fit(text: str, n: int) -> str:
    """画面の 1 行（日本語は全角なので、英語は 2 倍の文字数まで入る）"""
    return text[:int(n * _text["width_ratio"])]


def wrap(text: str, width: int) -> str:
    """ふきだしの折り返し（width は日本語の 1 行の文字数。英語は単語の切れ目で）"""
    if code == "en":
        return "\n".join(textwrap.wrap(text, int(width * _text["width_ratio"]))) or " "
    return "\n".join(text[i:i + width] for i in range(0, len(text), width)) or " "


def habit(move_habit: str, key: str) -> bool:
    """種の「移動の癖」（文で保存されている）が key（straight / detour / outer / pause / zigzag）か。
    どちらの言語で作った住人でも当たるように、両方の表と比べる"""
    return any(move_habit == import_module(f"lang.{x}").TEXT["move_habits"][key] for x in LANGS)
