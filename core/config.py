"""
config.toml の読み込み

cfg.llm.base_url のように属性で引けるようにするだけ。既定値はコードに持たない
（値の出どころを config.toml 1 か所にするため）。

言語（[locale] lang = "ja" / "en"）で変わる値は { ja = ..., en = ... } と書く。
読み込むときに lang の方の値だけが残る（cfg.raider.name は文字列 1 つになる）。
あわせて lang.use() で、コード側の文（プロンプト・画面）の言語も決める。
"""

import sys

if sys.version_info < (3, 11):   # tomllib が 3.11 から。古い Python で分かりにくい ImportError にしない
    sys.exit(f"[error] Python 3.11 or later is required (this is {sys.version.split()[0]}).")

import tomllib
from pathlib import Path
from types import SimpleNamespace

import lang

ROOT = Path(__file__).resolve().parent.parent   # プロジェクトのフォルダ（core/ の 1 つ上）


def _pick(value, code: str):
    """{ ja = ..., en = ... } を lang の値にする（入れ子の中も）"""
    if isinstance(value, dict):
        if set(value) == set(lang.LANGS):
            return _pick(value[code], code)
        return {k: _pick(v, code) for k, v in value.items()}
    if isinstance(value, list):
        return [_pick(v, code) for v in value]
    return value


def _ns(value):
    if isinstance(value, dict):
        return SimpleNamespace(**{k: _ns(v) for k, v in value.items()})
    if isinstance(value, list):
        return [_ns(v) for v in value]
    return value


def load_config(path: str | Path = ROOT / "config.toml") -> SimpleNamespace:
    with open(path, "rb") as f:
        raw = tomllib.load(f)
    code = raw["locale"]["lang"]
    lang.use(code)
    return _ns(_pick(raw, code))
