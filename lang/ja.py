"""
日本語の文（[locale] lang = "ja"）。キーは lang/en.py と同じにする（lang.use() が確かめる）

{名前} は str.format の差し込み。プロンプトの文は 2026-10-13 までコードに書いていたものをそのまま移した。
"""

TEXT = {
    # ================= 共通 =================
    "sep": "、",                     # 並べるときの区切り
    "dot": "・",                     # 役割・状態を重ねるときの区切り
    "paren": "（{x}）",
    "none": "なし",
    "char_ratio": 1,                 # 日本語 1 文字を、この言語の何文字ぶんとして返答を切るか（lang.clip）
    "width_ratio": 1,                # 画面の 1 行に入る文字数の倍率（lang.fit / lang.wrap）
    "uses_first_person": True,       # 性格に「一人称」を持つか
    "honorific_prefixes": (),        # 噂の about から外す敬称（memory/summarize.py）
    "honorific_suffixes": ("さん", "くん", "ちゃん", "さま", "様", "殿"),
    # 発話がこれを含んだら「記憶に触れた」（ビューアの印。sim/world.py）
    "memory_words": ("前に", "この前", "覚えて", "また会", "あのとき", "あの時", "助け"),

    # ================= 性格の種（gen_personas.py）=================
    "tones": ["丁寧語で話す", "くだけたタメ口", "ぶっきらぼうで言葉が短い", "古風な言い回し", "子どもっぽく無邪気",
              "詩的で比喩が多い", "早口でせっかち", "おっとりのんびり", "理屈っぽい", "関西弁ふう"],
    # キーは sim/movement.py が見る癖の種類（lang.habit）
    "move_habits": {"straight": "まっすぐ歩く", "detour": "寄り道しがち", "outer": "外周を歩きたがる",
                    "pause": "ときどき立ち止まって観察する", "zigzag": "ふらふら蛇行する"},

    # ================= プロンプト（llm/prompts.py）=================
    "rules": (
        "# 世界\n"
        "ここは海に囲まれた小さな島。住人には食事・睡眠・家族・性別という概念はない。\n"
        "住人には HP（0〜{max_hp}）と心（0〜{max_heart}）がある。ふだんの暮らしで HP が減ることはない。\n"
        "HP が 0 になると「フリーズ」して、その場で固まって動けなくなる。壊れて消えるわけではない。\n"
        "フリーズを解けるのは、島に数体だけいるヒーラーの魔法の杖だけ。解かれると HP が満タンで目を覚ます。\n"
        "心は、怖い目にあったり、目の前で仲間がフリーズしたりすると減る。"
        "心が {fear_heart} を下回ると「おびえ」の状態になる。\n"
        "{solaces}のどれかのそばにいると、心がゆっくり回復する（HP も少し戻る）。"
        "会話で仲間を励ますと、相手の心が少し回復する。\n"
        "島の主な場所: {places}。\n"
        "ときどき、黒くて大きな悪の魔物が島の外からやって来る。自分で考えて獲物を選び、"
        "鋭い爪で住人の HP と心を削ってフリーズさせる（爪を 3 回受けたら普通の住人はフリーズする）。"
        "攻撃を受けると「ノイズ」の状態になり、しばらく心がじわじわ減る。"
        "何体もフリーズさせると去っていく。悪は普通に歩くより速いが、急げば（fast）引き離せる。\n"
        "住人の中には数体だけ戦士がいる。戦士は剣を持ち、超能力の電撃で悪を攻撃でき、何度も当てると悪は倒れる。"
        "ただし撃ってきた戦士には、悪が黒い弾で反撃してくる。戦士は守りが固く、受けるダメージが小さい。\n"
        "# 共通の約束\n"
        "- あなたは島の住人として振る舞う。AI であることやメタな話はしない。\n"
        "- 知らないことは知らないと言う。記憶にない出来事を作らない。\n"
        "- 返答は指定された JSON だけを出力する。"
    ),
    "persona.name": "# あなた\n名前: {x}",
    "persona.first_person": "一人称: {x}",
    "persona.first_person_default": "私",
    "persona.tone": "口調: {x}",
    "persona.catchphrase": "口癖: {x}",
    "persona.background": "来歴: {x}",
    "persona.likes": "好きなもの: {x}",
    "persona.dislikes": "苦手なもの: {x}",
    "persona.goal": "目標: {x}",
    "persona.help_view": "仲間を助けることへの考え: {x}",
    "persona.favorite_spot": "好きな場所: {x}",
    "persona.traits": "性格の数値（0〜10）: 社交性{sociability} 気前の良さ{generosity} 好奇心{curiosity} 慎重さ{caution}",
    "persona.boot_cycles": "起動してからのサイクル数: {x}",
    "persona.samples": "セリフ例: ",
    "persona.sample": "「{x}」",
    "persona.warrior": ("役割: あなたは戦士。剣を持ち、超能力の電撃で少し離れた所から悪の魔物を攻撃できる。"
                        "撃つと悪に反撃されるが、守りが固いので受けるダメージは小さい。"),
    "persona.healer": ("役割: あなたはヒーラー。魔法の杖を持ち、フリーズした住人のそばで {cast_sec:g} 秒詠唱すると、"
                       "フリーズを解いて HP 満タンで目覚めさせられる（詠唱の間は動けない）。"
                       "島のどこで住人がフリーズしても、気配で分かる。フリーズを解けるのは、島でヒーラーだけ。"
                       "ヒーラーも、ほかの住人と同じように悪に狙われることがある。"),

    "say.no_talk": "（まだ誰も話していない。あなたから話しかける）",
    "say.rescued": ("\n※あなたはさっき悪の魔物に HP を削られてフリーズしていたところを、ヒーラーの{name}の"
                    "魔法の杖で目覚めさせてもらったばかり。このセリフでそのことに触れること。"),
    "say.gossip": ("- 目の前の景色や気分のことだけでなく、ほかの住人のうわさ話をしてもいい。"
                   "「ほかの住人についてのあなたの印象」や「噂で聞いた話」にいる住人のことを、"
                   "あなたが本当に思っているとおりに（良いことも、苦手なところも）話題にしてよい。\n"),
    "say.user": (
        "# {partner}とのこれまで\n{pair_memory}\n\n"
        "# 今の状況\n{situation}\n\n"
        "# この会話（直近）\n{talk}\n\n"
        "# 指示\nあなた（{me}）の次のセリフを1つだけ返す。{note}\n"
        "- say: 40字以内。あなたの口調と一人称で。相手の言葉に応える。\n"
        "- cheer: このセリフで{partner}を励ますなら true（相手の心が少し回復する）。"
        "相手がおびえていたり落ち込んでいたりするときに。\n"
        "- end: この発話で会話を終えるなら true。話すことがなくなったら true にする。\n"
        "{gossip}"
        "- これまでのセリフと同じ文・同じ言い回しを繰り返さない。口癖はときどきだけ使う。"
    ),

    "intent.rescue": ", rescue=フリーズした住人のところへ行って癒す",
    "intent.flee": ", flee=悪の魔物から逃げる",
    "intent.fight": ", fight=悪の魔物に近づいて超能力で戦う",
    "intent.rescue_target": "、rescue ならフリーズしている住人の名前",
    "intent.user": (
        "# あなたの記憶\n{memory}\n\n"
        "# 今の状況\n{situation}\n"
        "（いま次の行動を決める理由: {reason}）\n\n"
        "# 指示\nこれからどう動くかを決める。\n"
        "- intent: {kinds}\n"
        "  go_spot=場所へ行く, seek=住人を探す, follow=住人について歩く, avoid=住人から離れる,\n"
        "  wander=近くをうろつく, patrol=好きな場所を巡回, wait=その場で待つ{extra}\n"
        "- target: go_spot なら場所名（{names}）、seek/follow/avoid なら住人の名前{rescue_target}。他は空文字。\n"
        "  心が減っているときは、{solaces}のどれかへ行くと回復できる。\n"
        "- pace: slow / normal / fast\n"
        "- manner: どんな気持ちでどう歩くか。心の声として 40字以内。\n"
        "- duration_sec: この行動を続ける秒数（10〜90）"
    ),

    "rescue.user": (
        "# {target}とのこれまで\n{pair_memory}\n\n"
        "# 今の状況\n{situation}\n"
        "目の前で{target}がフリーズしている。\n\n"
        "# 指示\n魔法の杖でフリーズを解くかどうかを、あなたの性格・HP・心・相手との関係・周りの様子（悪が近くにいるか）から決める。\n"
        "- heal: 癒すなら true。{cast_sec:g} 秒の詠唱のあいだあなたは動けず、終わると{target}は HP 満タンで目覚める。\n"
        "- say: そのときのひとこと（40字以内）"
    ),

    "raider.system": (
        "# あなた\nあなたは悪の魔物「{name}」。島の外に広がる、暗いノイズの海から来た。"
        "島の住人を爪で切り裂いてフリーズさせ、島をノイズで満たそうとしている。\n"
        "話し方は片言で、カタカナまじりの不気味な言葉。住人と仲良くすることはない。\n\n"
        "# あなたの力と弱点\n"
        "- 狙った住人に爪が届くと、{strike_cooldown:g} 秒ごとに HP を {strike_damage:g} 削る"
        "（住人の HP は最大 {max_hp}）。HP が 0 になった住人はフリーズして動けなくなる。\n"
        "- 住人が普通に歩くより速いが、住人が急ぐ（fast）と追いつけない。"
        "{give_up:g} 秒追っても爪が届かなければ、その住人はこの襲来ではもう追えない。\n"
        "- 戦士（島に {warriors} 体）は超能力の電撃で、{attack_range:g}m ほど離れた所から攻撃してくる。"
        "当たるたびにあなたの HP が {attack_damage} 減り、0 になると倒れて消える。"
        "撃ってきた戦士には、あなたが自動で黒い弾を撃ち返す。戦士は守りが固く、爪も弾も効きにくい。\n"
        "- ヒーラー（島に {healers} 体）は、フリーズした住人を魔法の杖で目覚めさせる。"
        "詠唱の {cast_sec:g} 秒は動けない。\n"
        "- 島にいられるのは最長 {max_stay:g} 秒。{victims} 体をフリーズさせると満腹になり、島を去る。\n\n"
        "# 共通の約束\n- 返答は指定された JSON だけを出力する。"
    ),
    "raider.no_past": "（まだない。初めての襲来）",
    "raider.user": (
        "# これまでの襲来\n{past}\n\n"
        "# 今の状況\n{situation}\n"
        "（いま次の行動を決める理由: {reason}）\n\n"
        "# 指示\n次にどうするかを決める。\n"
        "- action: {actions}（hunt=住人を狙って追いかけ、爪で攻撃する, leave=島を去る）\n"
        "- target: hunt なら狙う住人の名前（「狙える住人」の中から）。leave なら空文字。\n"
        "- say: 住人に聞こえるひとこと（20字以内、片言で）。黙っているなら空文字。\n"
        "- thought: 心の中の考え（40字以内）"
    ),

    "summary.no_old": "（なし。初対面）",
    "summary.cheer": "（{a}が{b}を励ました）",
    "summary.user": (
        "# {partner}についてのこれまでの記憶\n{old}\n"
        "好感度: {affinity}（-10〜10）\n\n"
        "# いま終わった会話\n{talk}\n{cheers}\n\n"
        "# 指示\nあなた（{me}）の視点で、{partner}についての記憶を書き直す。\n"
        "- thought: まず、この会話を振り返って{partner}について思ったこと・感じたことを、"
        "心の中の言葉で（60字以内）。ほかの項目はこれを踏まえて決める。\n"
        "- summary: 100字以内。これまでの記憶と今回の会話をまとめる。"
        "励ました・励まされた・助けた・助けられた出来事は必ず残す。\n"
        "- affinity_delta: この会話で好感度がどう変わったか（-3〜3）\n"
        "- heard: この会話で{partner}が名前を出して話した、ほかの住人や場所についての話。"
        "最大 {heard_max} 件。{partner}自身とあなた自身のことは入れない。なければ空の配列 []。\n"
        "  about=その住人か場所の名前, note=聞いた内容（30字以内。「〜らしい」の形で）,\n"
        "  feel=その話を聞いて、あなたがその住人・場所をどう感じたか（-2〜2）"
    ),

    "persona_gen.user": (
        "島の住人を1体つくる。名前は「{name}」（決まっている）。次の「種」に合う人物像を JSON で返す。\n"
        "- 口調: {tone}\n"
        "- 社交性 {sociability} / 気前の良さ {generosity} / "
        "好奇心 {curiosity} / 慎重さ {caution}（0〜10）\n"
        "- 好きな場所: {favorite_spot}\n"
        "- 移動の癖: {move_habit}\n"
        "- 起動してからのサイクル数: {boot_cycles}\n\n"
        "各項目:\n"
        "- first_person: 一人称\n"
        "- catchphrase: 口癖（15字以内）\n"
        "- background: 来歴（60字以内）\n"
        "- likes / dislikes: 好きなもの・苦手なもの（各30字以内）\n"
        "- goal: 目標（30字以内）\n"
        "- help_view: 困っている仲間を助けることへの考え方（40字以内。気前の良さを反映）\n"
        "- walk_mood: 歩くときの雰囲気（30字以内。移動の癖を反映）\n"
        "- sample_lines: セリフ例を 3 つ（各30字以内。口調を反映）"
    ),

    # ================= 記憶の注入（memory/recall.py）=================
    "recall.rumor": "- {about}{text}（{src}から聞いた）",
    "recall.rumor_about": "{x}: ",
    "recall.first_meet": "初対面。",
    "recall.no_summary": "前に話したことはあるが、まだよく知らない。",
    "recall.affinity": "好感度: {x}（-10〜10）",
    "recall.thought": "前に話したあとに思ったこと: {x}",
    "recall.strong": "忘れられない出来事:",
    "recall.rumors_about": "{name}について噂で聞いたこと:",
    "recall.partner_events": "{name}の最近の出来事:",
    "recall.my_events": "あなたの最近の出来事:",
    "recall.heard": "聞いた話:",
    "recall.nothing": "特に覚えていることはない。",
    "recall.impressions": "ほかの住人についてのあなたの印象:",
    "recall.impression": "- {name}: {summary}（好感度 {affinity}）",
    "recall.impression_thought": "\n  思ったこと: {x}",
    "recall.rumors": "噂で聞いた話:",

    # ================= 世界（sim/world.py）=================
    "sys.connecting": "LLM サーバーに接続しています…",
    "sys.connected": "LLM 接続 OK。世界を動かします",
    "sys.connect_fail": "LLM に接続できません（{error}）。5 秒後に再試行",
    "sys.no_npcs": "{db} に住人がいません。先に python tools/gen_personas.py を実行してください",
    "sys.lang_mismatch": ("{db} の住人は lang = \"{stored}\" で作られています（config.toml は \"{lang}\"）。"
                          "[locale] lang を合わせるか、別の --db を使ってください"),
    "cond": "HP {hp}/{max_hp}、心 {heart}/{max_heart}、状態異常: {status}",
    "sit.place": "場所: {x}",
    "sit.me": "あなた: {x}",
    "sit.other": "{name}: {x}",
    "sit.near": "近くにいる住人: ",
    "sit.near_frozen": "近くでフリーズしている住人: ",
    "sit.at_solace": "いま{name}のそばにいて、心が回復している",
    "sit.nearest_solace": "いちばん近い、心が回復する場所: {name}（約{d}m）",
    "sit.frozen_none": "フリーズしている住人の気配: なし",
    "sit.frozen_heading": "、ヒーラーの{name}が向かっている",
    "sit.frozen_list": "フリーズしている住人の気配（島じゅうで{total}体。近い順）: ",
    "sit.frozen_item": "{name}（{place}、約{d}m{heading}）",
    "role.warrior": "戦士",
    "role.healer": "ヒーラー",
    "doing.frozen": "フリーズ中",
    "doing.talking": "会話中",
    "doing.casting": "詠唱中",
    "doing.fear": "おびえている",
    "place.near": "{name}の近く（約{d}m）",
    "manner.rest": "ここで心を休めよう",
    "stub.like": "いい子だよ",
    "stub.dislike": "ちょっと苦手",
    # 出来事の記録（DB に残り、あとで記憶としてプロンプトに入る）
    "ev.cheer": "{a}が{b}を励まし、{b}の心が少し軽くなった（{spot}）",
    "ev.talk": "{a}と{b}が{spot}で話した（{n}発話）",
    "ev.arrived": "{a}が{spot}に着いた",
    "ev.rescue": "ヒーラーの{a}が魔法の杖で、フリーズしていた{b}を目覚めさせた（{spot}）",
    # 移動意図を聞き直す理由（プロンプトの「いま次の行動を決める理由」）
    "why.heal_already": "{name}を癒そうとしたら、もう目を覚ましていた",
    "why.heal_declined": "{name}を癒さないと決めた",
    "why.talk_end": "会話が終わった",
    "why.raider_down": "悪の魔物が倒れた",
    "why.raider_gone": "悪の魔物がいなくなった",
    "why.arrived": "{x}に着いた",
    "why.found": "{x}を見つけた",
    "why.avoided": "{x}から十分に離れた",
    "why.rescue_woke": "癒しに行った{x}は、もう目を覚ましていた",
    "why.rescue_at": "癒しに行った{x}のそばに着いた",
    "why.fled": "悪の魔物から十分に離れた",
    "why.done": "目的を果たした",
    "why.felt_freeze": "{name}が{spot}でフリーズした気配を感じた",
    "why.already_awake": "{name}はもう目を覚ましていた",
    "why.revived": "ヒーラーの{name}の魔法の杖でフリーズが解けて、目を覚ました（HP {hp}）",
    "why.healed": "{name}のフリーズを解いた",
    # sim/npc.py
    "why.woke": "島で目を覚ました",
    "why.solace_calm": "心が落ち着いた",
    "why.wait_bored": "待つのに飽きた",
    "why.long": "しばらく同じ行動を続けた",
    "why.heart_low": "心が{th}を下回った（{status}）",
    "status": {"freeze": "フリーズ", "noise": "ノイズ", "fear": "おびえ"},

    # ================= 悪の魔物（sim/raid.py）=================
    # プログラムが決めた出来事のときだけのひとこと（ふきだし用。ほかのセリフは LLM が決める）
    "taunts": {"full": "……ミチタ……", "time": "……ジカン……カ……", "empty": "……エモノ……イナイ……",
               "defeated": "グ……ガ……"},
    "leave_how": {"choice": "自分から去っていった", "full": "満腹になって去っていった",
                  "time": "時間切れで去っていった", "empty": "獲物がいなくなって去っていった"},
    "r.cause.strike": "悪の魔物{name}の爪",
    "r.cause.counter": "悪の魔物{name}の反撃",
    "r.why.arrived": "島に着いた（{spot}の近く）",
    "r.why.idle": "しばらく考えずに動いていた",
    "r.why.no_target": "狙う住人が決まっていない",
    "r.why.escaped": "{name}を{sec:g}秒追ったが、逃げられた（この襲来ではもう追えない）",
    "r.why.target_frozen": "狙っていた{name}がフリーズした",
    "r.why.froze": "{name}を爪で攻撃してフリーズさせた",
    "r.why.counter_froze": "反撃で戦士{name}をフリーズさせた",
    "r.why.revived": "ヒーラーの{healer}が{target}を目覚めさせた",
    "r.why.shot": "戦士{name}が超能力で攻撃してきた",
    "r.why.hit": "戦士{name}の超能力が当たり、HPが{hp}まで減った",
    "r.alert.appear": "悪の魔物{name}が{spot}の近くに現れた気配を感じた",
    "r.alert.near": "悪の魔物{name}が近づいてきた",
    "r.alert.grab": "悪の魔物{name}に爪で攻撃されている",
    "r.who.warrior": "戦士の{name}",
    "r.who.healer": "ヒーラーの{name}",
    "r.who.resident": "{name}",
    "r.ev.appear": "悪の魔物{name}が{spot}の近くに現れた",
    "r.ev.frozen": "{who}が{spot}で悪の魔物{raider}の爪を受けてHPが0になり、フリーズした",
    "r.ev.struck": "{name}が{spot}で悪の魔物{raider}の爪でHPを{dealt}削られたが、逃れた",
    "r.ev.counter_frozen": "戦士の{name}が{spot}で悪の魔物{raider}の反撃の弾を受けてHPが0になり、フリーズした",
    "r.ev.plan_leave": "悪の魔物{name}は島を去ると決めた",
    "r.ev.plan_hunt": "悪の魔物{name}は{target}を狙うと決めた",
    "r.ev.defeated": "{name}が{spot}で悪の魔物{raider}を倒した{with_whom}。{name}の超能力は{shots}回中{hits}回当たった",
    "r.ev.fought": "{name}が{spot}で悪の魔物{raider}と戦ったが、去られた{with_whom}。{name}の超能力は{shots}回中{hits}回当たった",
    "r.ev.raid_end": ("{no}回目の襲来: 悪の魔物{raider}が{how}。{sec}秒で{victims}体をフリーズさせ、"
                      "{revived}体はヒーラーにフリーズを解かれた。戦ってきた戦士: {fought}"),
    "r.with": "（一緒に戦ったのは{names}）",
    "r.alone": "（ひとりで戦った）",
    "r.how.defeated": "戦士たちに倒された",
    "r.how.default": "去っていった",
    "r.fought_item": "{name}（{shots}発中{hits}発命中）",
    "r.nobody": "いない",
    # 悪の「今の状況」
    "r.sit.hp": "あなたの HP: {hp}/{max_hp}",
    "r.sit.time": "島に来てから: {sec}秒（最長 {max:g}秒）",
    "r.sit.victims": "フリーズさせた住人: {n}体（あと{left}体で満腹）",
    "r.sit.victim_names": " … {names}",
    "r.sit.target": "いま狙っている住人: {name}（約{d}m）",
    "r.sit.no_target": "いま狙っている住人: なし",
    "r.sit.attackers": "いま攻撃してきている戦士: ",
    "r.sit.attacker": "{name}（約{d}m、{shots}発中{hits}発命中）",
    "r.sit.escaped": "逃げられた住人（もう追えない）: {names}",
    "r.sit.revived": "ヒーラーにフリーズを解かれた住人: ",
    "r.sit.revived_item": "{target}（ヒーラー{healer}）",
    "r.sit.frozen_count": "島でフリーズしている住人: {n}体",
    "r.sit.cands": "狙える住人（近い順）:",
    "r.sit.cand": "- {name}: 約{d}m、HP{hp}、{label}",
    "r.sit.no_cands": "狙える住人: いない",
    "r.doing.fight": "あなたと戦おうとしている",
    "r.doing.flee": "逃げている",
    "r.doing.casting": "杖を掲げて詠唱している（動けない）",
    "r.doing.rescue": "フリーズした住人を癒そうとしている",
    "r.doing.solace": "心を回復している",
    "r.doing.walk": "歩いている",
    "r.doing.stand": "立ち止まっている",
    # 住人の「今の状況」に入る悪の様子
    "r.d.down": "戦士たちに倒されて、崩れかけている",
    "r.d.leaving": "島から去っていくところ",
    "r.d.you": "あなたを狙っている",
    "r.d.other": "{name}を狙っている",
    "r.d.search": "次の獲物を探している",
    "r.d.text": ("悪の魔物{raider}: {place}、あなたから約{d}m。{doing}。"
                 "HP {hp}/{max_hp}、これまでに{victims}体が爪や弾を受けてフリーズした"),
    "r.d.fighters": "。戦っている戦士: ",

    # ================= スタブ（llm/stub.py）=================
    "stub.server": ("LLM なし", "スタブ"),
    "stub.say_lines": [
        "やあ、{p}。今日の電流はどう？", "{p}、またここで会ったね", "この辺は静かでいいね",
        "乱数の泉の水、今日はきらきらしてたよ", "最近、心が軽いんだ",
        "ちょっと考えごとしてたんだ", "{p}はどこへ行くの？", "そうなんだ、知らなかった",
        "うん、わかるよ", "じゃあ、またね", "コアダンプ遺跡に何かあるって噂だよ",
    ],
    "stub.thanks": "{name}が助けてくれたんだ。ありがとう",
    "stub.gossip": "{who}って、",            # 噂を話すセリフの前置き（このあとに印象・噂が続く）
    "stub.cheer": "{name}、元気出して。大丈夫だよ",
    "stub.hearsay": "{x}らしい",
    "stub.hearsay_mark": "らしい",           # 伝わるたびに重ならないように外す
    "stub.m.fight": "悪は許さない。超能力で追い払う",
    "stub.m.flee": "黒いのが来る！逃げなきゃ",
    "stub.m.rescue": "固まっている子がいる。杖で癒しに行かなきゃ",
    "stub.m.solace": "心がざわざわする。休みに行こう",
    "stub.m.spot": "{spot}へ行ってみよう",
    "stub.m.seek": "あの子が気になる",
    "stub.m.patrol": "いつもの道をぐるっと回ろう",
    "stub.m.wander": "ぶらぶらしよう",
    "stub.m.wait": "少しここで休もう",
    "stub.heal": "{name}、目を覚まして",
    "stub.no_heal": "ごめん、今ここで詠唱するのは危ない",
    "stub.r.leave_say": "……キョウハ……ヒク……",
    "stub.r.leave_thought": "戦士が強すぎる。引こう",
    "stub.r.empty": "獲物がいない",
    "stub.r.says": ["コオレ……", "ニゲテモ……ムダ……", "", "ノイズニ……ソマレ……"],
    "stub.r.hunt": "{name}を爪で固めてやる",
    "stub.s.add": "{name}と{n}回ほど言葉を交わした。",
    "stub.s.thought": "{name}と話せてよかった",
    "stub.p.first_persons": ["わたし", "ぼく", "おれ", "うち", "わし"],
    "stub.p.catchphrases": ["ピピッ", "なるほどね", "ふむふむ", "えへへ", "まあいいか"],
    "stub.p.background": "{spot}の近くで暮らす住人。",
    "stub.p.dislikes": "ノイズ",
    "stub.p.goal": "島のすべての場所を見ること",
    "stub.p.help_yes": "困っている子は放っておけない",
    "stub.p.help_no": "自分のことは自分で守る",
    "stub.p.samples": ["こんにちは", "静かな時間が好き", "またね"],

    # ================= ビューア（viewer/）=================
    "hud.help": "左ドラッグ・WASD 移動 / 右ドラッグ 回転 / ホイール ズーム / クリック 追従 / Esc 自動 / V 心の声 / M 音 / Shift+Q 終了",
    "hud.residents": "住人 {npcs}: 歩行 {moving}  会話 {talking}  回復中 {resting}  フリーズ {frozen}  返答待ち {waiting}",
    "hud.hp": "HP 平均 {hp:.0f}  心 平均 {heart:.0f}  状態異常: おびえ {fear}  ノイズ {noise}",
    "hud.llm_wait": "LLM 同時 {inflight}  未送信 {queued}  完了 {done}/{total}  {elapsed:.1f}s",
    "hud.llm_idle": "LLM 同時 0",
    "hud.last_wave": "直近ウェーブ {n}件 {wall:.1f}s  {tps:.0f} tok/s  TTFT p50 {p50:.2f} / p95 {p95:.2f}s  失敗 {fail}",
    "hud.totals": "累計 会話 {sessions}  発話 {utterances}  励まし {cheers}  癒し {rescues}  フリーズ {freezes}  LLM失敗 {llm_fail}",
    "hud.healers": "ヒーラー: 癒しに向かう {healing}  癒さないと決めた {declined}",
    "hud.camera": "カメラ: {mode}   心の声: {inner}   音: {sound}",
    "hud.raid_total": "襲来 {raids} 回 / 撃退 {defeated} 回 / フリーズさせられた {frozen} 体",
    "hud.raid_none": "悪: いない（{total}）",
    "hud.raid_doing": {"appear": "出現", "hunt": "襲撃中", "leave": "撤退中", "defeated": "撃退"},
    "hud.thinking": "考え中…",
    "hud.raid": ("悪 {name} [{doing}] HP {hp}/{max_hp}  フリーズさせた {victims}/{max_victims}  狙い {aim}  "
                 "戦う {fighting}  逃げる {fleeing}  命中 {hits}/{shots}  反撃 {chits}/{counters}"),
    "hud.raid_thought": "\n  心の声: {x}",
    "hud.no_model": "{model}（モデル名は取得できず）",
    "hud.checking": "確認中…",
    "info.frozen": "フリーズ中（ヒーラーの杖を待っている）",
    "info.talking": "{name}と会話中",
    "info.casting": "{name}のフリーズを解く詠唱中",
    "info.thinking": "考え中",
    "info.warrior": "【戦士】",
    "info.healer": "【ヒーラー】",
    "info.waiting": "  返答待ち:{x}",
    "info.hp": "HP {hp:.0f}/{max_hp}  心 {heart:.0f}/{max_heart}  状態異常: {status}",
    "info.solace": "  （{name}で回復中）",
    "info.seed": "{tone} / {habit} / 好きな場所 {spot}",
    "info.traits": "社交{sociability} 気前{generosity} 好奇心{curiosity} 慎重{caution}",
    "info.persona": "口癖「{catch}」  目標: {goal}",
    "info.now": "いま: {x}",
    "info.events": "― 最近の出来事 ―",
    "info.relations": "― 関係 ―",
    "camera.modes": {"auto": "自動（ディレクター）", "manual": "手動", "follow": "追従"},
    "app.frozen_label": "フリーズ",
    "log.title": "― 画面外の会話 ―",
    "log.heal": "{a}が{b}のフリーズを解いた",
    "log.raider_thought": "{name}（心）: {x}",
    "log.raider_appear": "悪の魔物{name}が{spot}の近くに現れた！",
    "log.froze": "{name}がフリーズした（{n}体目）",
    "log.escaped_hit": "{name}は爪でHPを{dmg}削られたが逃れた",
    "log.defeated": "{name}が倒された！ {names}",
    "log.gone": "{name}が去っていった（被害{n}体）",
}
