[English](README.md) | **日本語**

# llm-island

100 体の住人が島を歩き回り、出会った相手とローカル LLM で会話する島のシミュレーションです。
住人は会話の中で噂を広め、仲間を励まし、ときどき島の外から現れる悪の魔物から逃げたり、
戦ったり、フリーズした仲間を助けに行ったりします。何を話し、どこへ行き、誰を助けるかは、
すべて住人それぞれの LLM が決めます。

[![llm-island のデモ動画（YouTube）](https://img.youtube.com/vi/LGSwWh7aHrw/hqdefault.jpg)](https://www.youtube.com/watch?v=LGSwWh7aHrw)

▶ デモ動画（YouTube）: https://www.youtube.com/watch?v=LGSwWh7aHrw

これは個人の趣味のプロジェクトです。質問や要望には対応していません。
ただし、権利・ライセンス上の懸念や問題のご報告は GitHub の Issues で歓迎します。

すべて Python で書いています。3D 表示は [Ursina](https://www.ursinaengine.org/) エンジンで、
住人・剣・魔法の杖・悪の魔物の見た目は、外部のモデルファイルを使わずコードだけで組み立てています。
姉妹プロジェクトの [llm-radio-daemon](https://github.com/lumavrenor/llm-radio-daemon) から、
クレイ風の 3D キャラと BGM を持ってきています。

## 本プロジェクトの位置づけ

実用のソフトウェアではなく、プログラマーが自分の PC で遊ぶための実験です。
見たいのは「1 台の PC の推論サーバーで、100 体の LLM の住人を同時に動かすと、何が起きるか」です。

- 噂は誰から誰へ、何段先まで伝わるか。伝わるうちに中身はどう変わるか
- 助けられた住人は、助けてくれた相手を覚えていて、ほかの住人に話すか
- 悪の魔物が現れたとき、住人は逃げるか、戦うか。ヒーラーは誰を先に助けるか

ゲームではありません。プレイヤーが操作するものはなく、画面は観察するためのものです。
住人のふるまいをコードで決めてしまうのではなく、LLM がなぜそう判断したのかを見ることを大事にしています。

## LLM が生成する内容について（重要）

住人のセリフ・心の声・噂・悪の魔物のセリフは、すべてローカル LLM がその場で生成した作り話です。
誰も中身を確かめていません。LLM は指示を無視したり、間違ったことや不適切なことを、自信のある口調で
言ったりすることがあります。今の生成 AI の技術では、これをゼロにはできません。

- 住人の言うことを、事実や助言として受け取らないでください。
- 本ソフトウェアの出力によって生じた損害について、作者は一切の責任を負いません。

## 特徴

- **100 体が同時に LLM で動く** — 1 体ごとにスレッドを作るのではなく、返答が必要な全員分のリクエストを
  「ウェーブ」としてまとめて推論サーバーに投げます。サーバーの同時処理（バッチ処理）を使い切るための作りです。
- **会話と記憶** — 出会った 2 体が 1 発話ずつ交互に話します。会話のあとに LLM が要約を書き、
  相手との関係（好き嫌い）と、聞いた噂を SQLite に覚えます。次に会ったとき、その記憶をプロンプトに入れます。
- **噂の伝わり方** — 住人は会話で聞いた「ほかの住人の話」を、また別の住人に話します。
  `report.py` で、噂が何段先まで伝わったか、誰から誰へ伝わったかを集計できます。
- **悪の魔物・戦士・ヒーラー** — ときどき悪の魔物「ヤミゴースト」が現れ、住人を爪で攻撃してフリーズさせます。
  戦士は超能力で戦い、ヒーラーは魔法の杖でフリーズを解きます。悪の魔物も、誰を狙うか・いつ去るかを LLM で考えます。
- **HP・心・状態異常** — 住人は HP と心を持ち、怖い目にあうと心が減って「おびえ」になります。
  心が回復する場所（solace）のそばにいたり、会話で励まされたりすると回復します。
- **前回の続きから始まる** — 世界の時刻・住人の位置・HP・心・記憶は `world.db` に保存され、
  次に起動すると続きから始まります。
- **LLM なしでも動く** — `--stub` でダミーの返答を使えば、GPU がなくても仕組みだけ確かめられます。

## 必要なもの

- **Windows 10 / 11**（作者は Windows 11 で確認しています）
  - ビューアは Windows でしか確認していません。日本語フォントを Windows のシステムフォントからしか探さないので、
    Linux / macOS ではビューアの日本語が文字化けします。`start.sh` 自体は Linux / macOS でも動き、
    `--headless` ならフォントは要りません
- **Python 3.11 以降**（作者は 3.14 を使っています。`tomllib` を使うため 3.11 以上が必要です）
- **OpenAI 互換 API の推論サーバー**（作者は [SGLang](https://github.com/sgl-project/sglang) を使っています）
  - JSON Schema による構造化出力（`response_format` の `json_schema`）に対応している必要があります
  - 100 体分のリクエストを一度に投げるので、同時処理に強いサーバー（SGLang や vLLM）が向いています
  - 作者の環境は Qwen3.8-27B（NVFP4）を GPU 3 枚のパイプライン並列（PP3）で動かしています。
    ほかのモデルでは確かめていませんが、小さいモデルの方が同じ VRAM で多くの住人を動かせるかもしれません
    （住人の数は `--npcs` で減らせます）

### 推論サーバーの用意

推論サーバーの入れ方は、GPU の種類（NVIDIA の世代・AMD Radeon）・VRAM・CUDA や ROCm の版・OS（Windows なら WSL2）で
大きく変わります。作者の手順をそのまま写しても、ほかの PC で動くとは限りません。
いちばん確実なのは、Claude Code などのコーディングエージェントに、その PC を調べながら作ってもらうことです。
下の「ゲームの負荷」と「作者の環境」も読ませると、エージェントが値を決めやすくなります。頼み方の例:

> この PC に SGLang（GPU に合わなければ vLLM）を入れて、OpenAI 互換 API を `http://127.0.0.1:30000` で動かして。
> `--served-model-name` は `npc`。JSON Schema の構造化出力（`response_format` の `json_schema`）が使えること。
> GPU と VRAM に合う Qwen3 系のモデルと量子化を選び、README.ja.md の「推論サーバーの用意」にある負荷に合わせて
> 同時処理数などを調整して。最後に `python tools/gen_personas.py` が通るか確かめて。

`gen_personas.py` は 100 体分のリクエストを 1 ウェーブで投げるので、サーバーの確認にちょうどよい負荷です
（住人がもういる DB は `--force` を付けない限り書き換えません）。

#### ゲームの負荷

| 項目 | 値 |
|---|---|
| 投げ方 | 返答が必要な住人の分を「ウェーブ」で一度に投げる（最大 100 件。[config.toml](config.toml) の `[llm] max_concurrency`） |
| プロンプト | 平均 約 840 トークン（性格・記憶・状況の文） |
| 返答 | JSON Schema の構造化出力。最大 100〜160 トークン（性格の生成だけ 700） |
| 思考 | 常にオフ（`chat_template_kwargs: {"enable_thinking": false}` を付けて呼ぶ） |

「プロンプトが長く返答が短いリクエストが、一度にたくさん来る」形なので、1 件の生成速度よりも
プロンプト処理（prefill）をどれだけまとめてさばけるかで速さが決まります。

#### 作者の環境

- RTX 5060 Ti 16GB × 3（計 48GB、P2P なし・PCIe 接続、1 枚は画面出力と兼用）/ WSL2 / SGLang 0.5.21
- Qwen3.8-27B NVFP4 をパイプライン並列 3 段（PP3）で、同時処理 48

```bash
CUDA_VISIBLE_DEVICES=1,2,0 \
SGLANG_PP_LAYER_PARTITION=18,24,22 \
PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
python -m sglang.launch_server \
  --model-path Qwen3.8-27B-NVFP4 --served-model-name npc \
  --tp-size 1 --pp-size 3 \
  --context-length 8192 --mem-fraction-static 0.93 --kv-cache-dtype fp8_e4m3 \
  --max-running-requests 48 --max-queued-requests 192 \
  --cuda-graph-max-bs-decode 48 --disable-prefill-cuda-graph \
  --disable-radix-cache --reasoning-parser qwen3 \
  --host 127.0.0.1 --port 30000
```

調べてわかったこと（ほかの環境でも考え方は使えます）:

- **同時処理数（`--max-running-requests`）がいちばん効きます。** 大きくすれば速いわけではありません。
  Qwen3.8 は層の多くが線形アテンションで、1 リクエストごとに大きな状態を持ちます。同時処理数ぶんの状態を
  起動時に確保し、その残りが KV キャッシュになります。100 にすると KV が足りず実際には 9 件ほどしか回らず、
  48 の方が速くなりました。起動ログの `max_total_num_tokens`（KV 容量）が「同時処理数 × 約 1,000 トークン」より
  十分大きくなるように決めます
- 同時処理数を超えた分は待ち行列（`--max-queued-requests`）で待ちます。ゲームは 1 ウェーブ最大 100 件なので、
  同時処理数 + 待ち行列が 100 を超えていれば、あふれてエラーになることはありません
- `--cuda-graph-max-bs-decode` は同時処理数と同じにします。小さいままだと、それを超えたとき数倍遅くなります
- `--disable-radix-cache`: このモデルでは prefix キャッシュを有効にすると同時処理数が数件に制限されたため、切っています
  （線形アテンションのない普通のモデルなら、有効のままの方が速い可能性があります）
- GPU 間で P2P が使えないため、テンソル並列（TP2）はパイプライン並列（PP3）の 4 分の 1 ほどの速さでした。
  NVLink や P2P がある環境では TP の方が速いかもしれません
- `--context-length` は 8192 で足ります
- 同じ環境・同じモデルで vLLM 0.29.0 も同じ構成（PP3・同時処理 48）に調整して比べましたが、SGLang より遅く、
  処理できる量は 6 割ほどでした（100 件を一斉に投げて全部返るまで SGLang 28 秒、vLLM 73 秒）。
  このモデルでは vLLM の KV のブロックが 1,568 トークンと大きく、prefix キャッシュも効きませんでした。
  ただし比べたのはゲームに似せた負荷テストのスクリプトだけで、ゲーム本体を vLLM で動かしてはいません

#### ほかの GPU の場合

作者が確かめたのは上の 48GB の環境だけです。**VRAM 32GB や 16GB で 100 体を動かせるかは確かめていません。**
以下は手がかりとしての目安です。

- **NVFP4 は RTX 50 系（Blackwell）以降だけ**です。RTX 40 / 30 系では AWQ・GPTQ など別の量子化のモデルを選ぶことになりそうです。
  FP8 に対応しない GPU（RTX 30 系など）では `--kv-cache-dtype` も既定（bf16）にする必要があると思います
- **AMD Radeon** では ROCm 版の SGLang / vLLM を使うことになると思います（作者は試していません）
- VRAM が少ないときは、小さいモデル（Qwen3-8B / 14B など）を試すとよさそうです。重みが軽い分 KV キャッシュに回せる
  メモリが増えるので、同時にさばける住人はむしろ増えるかもしれません（返答の質は下がる可能性があります）。
  それでも重いときは住人を減らせます（`python main.py --npcs 20`）。
  返答が遅いときは、[config.toml](config.toml) の `[llm] timeout_sec`（1 件の打ち切り）も見直してください
- vLLM でも同じ考え方で調整できると思います（同時処理数は `--max-num-seqs`）

手で起動するいちばん簡単な例です（モデルは GPU のメモリに合わせて選んでください）。

```
python -m sglang.launch_server --model-path Qwen/Qwen3-8B --served-model-name npc --host 127.0.0.1 --port 30000
```

接続先は [config.toml](config.toml) の `[llm]`（`base_url` と `model`）です。Qwen3 の「思考」は常にオフにして呼びます。

## セットアップ（Windows / PowerShell）

```
py -3.14 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\activate
```

`start.bat`（Git Bash では `./start.sh`）は `.venv` が無ければこの 2 行（venv の作成と `pip install`）を
自動で行ってから起動します。world.db に住人がいなければ、性格の生成（`gen_personas.py`）も先に行います。
つまり最初から `start.bat` / `./start.sh` だけで始められます。以下の `python ...` は `.venv` を有効にした
（`activate` した）状態で打ちます。

## 起動

```
python tools/gen_personas.py                 # 100 体の性格を生成して world.db に保存（最初に 1 回。省略可）
python main.py                         # ビューア
python main.py --headless              # ビューアなし（ログとメトリクスだけ）
python main.py --headless --minutes 30 # 30 分で終了
python tools/report.py                       # 集計（噂がどこまで伝わったか、救助、襲来の結果 など）
```

| オプション | 内容 |
|---|---|
| `--stub` | LLM を使わずダミーの返答で動かす（仕組みの確認用。`gen_personas.py --stub` も同様） |
| `--speed 8` | ヘッドレスで世界の時間を 8 倍速にする（スタブでのバランス調整用） |
| `--npcs 20` | 住人を減らす |
| `--fresh-memory` | 記憶と世界の状態を消して、新しい世界で始める |
| `--minutes 30` | 起動してから世界の時刻で 30 分たったら終了 |
| `--db PATH` | `world.db`（英語は `world_en.db`）の代わりに別のファイルを使う |
| `-v` | 心の声（移動意図の manner）もログに出す |

`start.bat`（Git Bash では `./start.sh`）は `.venv` の Python で `main.py` を起動します（引数はそのまま渡します。
`.venv` が無ければ先に作ります）。

起動は**前回終了時の世界から続けます**（世界の時刻・住人の位置と HP・心・状態異常・記憶・悪の襲来の回数。
`world.db` に 3 秒ごとと終了時に保存）。新しい世界で始めるときは、先にデータを消します。

```
reset.bat           # 記憶と世界の状態を消す（住人の性格は残す）。Git Bash では ./reset.sh
reset.bat --all     # world.db ごと消す（次の起動で住人の性格から作り直す）
```

スタブでの確認（`--stub`）も同じ `world.db` の続きを進めるので、本番の世界を残したいときは
`--db` で `world.db` のコピーに向けて動かしてください。

## 言語（日本語 / 英語）

住人は日本語でも英語でも暮らせます。[config.toml](config.toml) のいちばん上で選びます。

```toml
[locale]
lang = "en"    # "ja" / "en"
```

住人の会話・名前（英語は `names_en.txt` から）・場所の名前・悪の魔物の名前・プロンプト・画面の文字が
切り替わります。言語で変わる設定値は config.toml に `{ ja = ..., en = ... }` と書いてあります。

住人の性格と記憶は作ったときの言語で書かれているので、DB は言語ごとに別のファイルです
（`[world] db_file`。日本語は `world.db`、英語は `world_en.db`）。初めて切り替えたときは、
その言語の住人を作ってから起動します。

```
python tools/gen_personas.py      # lang = "en" なら world_en.db に作る
python main.py
```

DB を作った言語と `lang` が違うと、`main.py` は起動しません。
開発用のログ（`log/island.log`・`python tools/report.py`）は日本語のままです。

## ビューアの操作

| 操作 | 内容 |
|---|---|
| 左ドラッグ / WASD | 平行移動（20 秒操作がなければ自動カメラに戻る） |
| 右ドラッグ / ホイール | 回転 / ズーム |
| クリック | その住人を追いかけて情報パネルを出す |
| Esc | 自動カメラ（ディレクター）に戻る |
| V | 心の声の表示 ON/OFF |
| M | 音（BGM・効果音）の ON/OFF |
| Shift+Q | 終了 |

自動カメラは、いま島で起きている出来事（会話・救助・襲来など）に点数をつけ、いちばん面白い所を映します。
左上の HUD の 2 行目には、推論サーバーが名乗ったモデル名とバージョンが出ます。

## LLM の流れ（ウェーブ方式）

```
collect ─▶ wait ─────────────▶ play ─▶ collect ...
 全員分を   全部返るまで待つ      結果をまとめて反映し、
 一度に投げる（世界は動き続ける） セリフを見せる時間だけ待つ
```

- 1 体につき 1 ウェーブ 1 リクエストまで（発話 > 救助判断 > 移動意図）。会話後の要約と、悪の魔物の判断（1 件）は同じウェーブに追加で乗ります
- 会話は 1 発話 = 1 リクエスト。2 体が 1 ウェーブずつ交互に話します
- 裏で動くスレッドは HTTP 用の 1 本だけです。結果の反映はメインスレッドがウェーブ単位で行います

## HP・心・状態異常

住人は **HP** と **心** を持ちます。

- HP はふだんの暮らしでは減りません。減らすのは悪の魔物の攻撃だけです。0 になると**フリーズ**（氷のかたまりに閉じこめられて動けない）
- 心は、悪の魔物の攻撃・攻撃のあとの「ノイズ」・目の前で仲間がフリーズしたのを見ること で減ります。
  **心が回復する場所**（config.toml の spots で kind = "solace"）のそばにいる間と、会話で**励まされた**ときに回復します

| 状態異常 | 付くとき | 効果 | 見た目 |
|---|---|---|---|
| フリーズ | HP 0 | 動けない。ヒーラーの杖だけが解く（HP 満タンで目覚める） | 氷のかたまり、青白い |
| ノイズ | 攻撃を受けた（受けるたびに延びる） | しばらく心がじわじわ減る | 紫にチカチカ |
| おびえ | 心が一定より低い | プロンプトに出る（逃げる・塔へ行く判断の材料） | 青みがかって震える |

設定は [config.toml](config.toml) の `[npc]` / `[solace]` です。

## 悪の魔物・戦士・ヒーラー

ときどき黒くて大きな悪の魔物「ヤミゴースト」が 1 体だけ島の端に現れます。狙った住人に爪が届くと HP と心を削り
（普通の住人は 3 発でフリーズ）、何体もフリーズさせると満腹で去ります。
**誰を狙うか・いつ去るかは、ヤミゴースト自身の LLM が決めます**。

100 体のうち 5 体は**戦士**（名前が金色、剣を持つ）で、超能力の弾で悪の魔物の HP を削れます。
ただし撃ってきた戦士には、ヤミゴーストが黒紫の弾で反撃します。

100 体のうち 3 体の**ヒーラー**（名前が若葉色、魔法の杖を持つ）だけが、フリーズを解けます。
解くと決めたら杖を掲げて詠唱し、終わると相手は HP 満タンで目を覚まします。
ヒーラーは島のどこで住人がフリーズしても気配で分かり、どこへ癒しに行くかを LLM で決めます。

- 住人が逃げるか戦うか（戦士だけ）は、LLM が移動意図として決めます
- 設定は [config.toml](config.toml) の `[raider]` / `[warrior]` / `[healer]`。仕組みは [sim/raid.py](sim/raid.py)（悪の魔物・戦士）と [sim/heal.py](sim/heal.py)（ヒーラー）
- `python tools/report.py` に、襲来ごとの結果（撃退したか・フリーズさせた数・戦士ごとの命中）と、ヤミゴーストの判断の一覧が出ます

## 住人の見た目（3D キャラ）

llm-radio-daemon のクレイ風キャラ（[viewer/poly_character.py](viewer/poly_character.py)）を移植したものです。
髪型 6 種・胴体 2 種・装飾品 4 種。見た目は乱数で決まり（住人ごとにいつも同じ）、個別に決めたい住人は
[config.toml](config.toml) の `[[look.npc]]` に書けます。

```
python -m viewer.preview                 # 住人 0〜9 を並べる
python -m viewer.preview --catalog       # 選べる髪型・装飾品の一覧
python -m viewer.preview --roles         # 戦士とヒーラー（剣と杖を持った姿）
python -m viewer.preview --ids 0-4 --raider   # 悪の魔物も並べる（大きさ比べ）
```

## ログ

- `log/island.log` … 発話・噂・励まし・救助・フリーズ・攻撃・ウェーブごとの計測
- `log/metrics.jsonl` … ウェーブごとの件数・所要時間・tok/s・TTFT と、10 秒ごとの世界の状態
- `log/prompts.txt` … 住人 1 体（既定は 0 番）と悪の魔物の、プロンプトと返答

ログは起動のたびに作り直します。

## 参考: 作者の環境での結果（2026-10-11）

SGLang（PP3・同時処理 48）、Qwen3.8-27B NVFP4、住人 100 体、ヘッドレスで 30 分。

| 項目 | 結果 |
|---|---|
| エラー・例外 | 0 件 |
| リクエスト | 82 ウェーブで 4,387 件、失敗 0 |
| ウェーブ 1 回の時間 | 中央値 17 秒（件数の中央値 54） |
| 全体 tok/s | 中央値 164 |
| TTFT p50 | 中央値 3.8 秒 |
| プロンプト | 平均 836 トークン |

## 構成

```
main.py            起動（ヘッドレス / ビューア）
config.toml        すべての設定値
start.bat/.sh      起動（初回は .venv も作る）   reset.bat/.sh  データの削除
core/    config.py（config.toml の読み込み） state.py（ステート管理） run_lock.py（同時起動の防止）
tools/   gen_personas.py（性格の生成。種は乱数、肉付けは LLM。100 体を 1 ウェーブで）
         gen_sfx.py（効果音の合成。assets/sfx/*.wav を作る） report.py（DB の集計） reset.py（データの削除）
data/    names.txt（住人の名前の候補。英語は names_en.txt）
save/    world.db（英語は world_en.db） window.json（ウィンドウの位置・サイズ）… 実行時に作られる
lang/              言語ごとの文（ja.py / en.py）: プロンプト・状況の文・出来事の記録・スタブの返答・画面の文字
sim/     world.py（フレーム更新・ウェーブ・ダメージとフリーズ） npc.py movement.py encounter.py
         heal.py（救助） raid.py（悪の魔物・戦士）
llm/     client.py（ウェーブ・HTTP） stub.py prompts.py schemas.py
memory/  db.py recall.py（記憶の注入） summarize.py（会話後の要約・噂）
viewer/  app.py bubbles.py camera.py hud.py sound.py poly_character.py weapons.py raider_figure.py ほか
assets/  bgm/（BGM） sfx/（効果音。tools/gen_sfx.py の出力）
```

## クレジット

3D 表示は [Ursina](https://www.ursinaengine.org/)（MIT）と、その土台の [Panda3D](https://www.panda3d.org/)
（Modified BSD）を使っています。HTTP は [HTTPX](https://www.python-httpx.org/)（BSD-3-Clause）、
数値計算は [NumPy](https://numpy.org/)（BSD-3-Clause）です。

同梱の BGM（`assets/bgm/`）は、作者が llm-radio-daemon のために、すべての音をコードで合成して作ったものです。
外部の録音やサンプルは含みません。効果音（`assets/sfx/`）は `tools/gen_sfx.py` でコードから合成しています。

推論サーバー（SGLang など）と LLM のモデル（Qwen など）は本リポジトリに含みません。
それぞれのライセンス・利用規約を確認して使ってください。

## ライセンス

本ソフトウェアの著作権は作者にあります。個人が非商用の目的で、自宅で動かして楽しむのは自由です。
個人が紹介・感想・技術解説を目的として、動作の様子を動画や配信で見せることも、チャンネルの収益化の有無を問わず自由です。
複製物や改変版の公開・配布、出力そのものを主な内容とした継続的な配信、商用利用は認めていません。
詳しくは [LICENSE](LICENSE) を見てください。
本ソフトウェアは無保証です。利用によって生じた損害やトラブルについて、作者は一切の責任を負いません。

依存している推論サーバー・LLM のモデル、およびクレジットに挙げたライブラリには、それぞれ別のライセンス・利用規約があります。
各自で確認してください。

この README と LICENSE の内容が食い違う場合は、LICENSE が優先します。
