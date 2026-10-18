"""
キャラクターモデル種別の登録表（ursina 非依存の純データ）

llm-radio-daemon の display/models.py から移植。config.toml の [look] と
looks.py の妥当性チェックがこの表を使う（＝髪型・装飾品の一覧の唯一の出どころ）。
増やすときはこの表に 1 行足し、poly_character.py 側に生成関数を足す。
"""

from __future__ import annotations

DEFAULT_MODEL = "girl"

# model キーワード -> poly_character.Character のメッシュ構成（既定値）。
#   hair_style: HAIR_STYLES のいずれか
#   body_style: BODY_STYLES のいずれか
# look で hair_style / body_style を明示すれば、ここの既定値を個別に上書きできる。
MODEL_PRESETS: dict[str, dict[str, str]] = {
    "girl": {"hair_style": "bob", "body_style": "dress"},  # ボブ・ワンピース
    "boy": {"hair_style": "cap", "body_style": "box"},     # 短髪・箱型
}

# 髪型。poly_character.py 側の生成関数と対応。
#   ショート: bob（ボブ） / bear_buns（熊ダンゴ） / blunt_bangs（前髪パッツン） / cap（浅い短髪）
#   ミディアム: medium（ノーマル） / medium_twintail（ツインテール）
HAIR_STYLES: tuple[str, ...] = (
    "bob",
    "bear_buns",
    "blunt_bangs",
    "cap",
    "medium",
    "medium_twintail",
)

# 胴体。dress = 上が細く下が広がる円錐台（ワンピース） / box = 肩から腰までまっすぐな箱型
BODY_STYLES: tuple[str, ...] = ("dress", "box")

# 頭に足せる装飾品。poly_character.py 側に対応する _make_<type>() がある。
#   headphones … 頭頂をまたぐバンド＋左右のイヤーカップ（side は無視して常に両耳）
#   cat_ears   … 頭頂の左右に立つ三角の猫耳
#   pin        … 前髪脇に留める一文字のヘアピン（side で左右／両方を選ぶ）
#   hairband   … 頭を前から耳の上を通ってまたぐ細いカチューシャ（side は取らない）
# color 省略時は poly_character 側の既定（cat_ears/pin/hairband は髪色、headphones は暗色）。
# side 省略時は type ごとの既定（headphones/cat_ears は "both"、pin は "left"）。
ACCESSORY_TYPES: tuple[str, ...] = (
    "headphones",
    "cat_ears",
    "pin",
    "hairband",
)

# side は「キャラの正面から見た画面の」左右（"left" が -X 側）
ACCESSORY_SIDES: tuple[str, ...] = ("left", "right", "both")


def resolve_model(model: str) -> dict[str, str]:
    """model キーワード -> メッシュ構成。妥当性は looks.py 側で先に弾く"""
    return MODEL_PRESETS.get(model, MODEL_PRESETS[DEFAULT_MODEL])
