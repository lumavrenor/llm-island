"""
English text ([locale] lang = "en"). Keys must match lang/ja.py (lang.use() checks this).

{name} placeholders are str.format fields. Length limits in the prompts are given in words;
the code cuts replies at char_ratio x the Japanese character limit (lang.clip) as a safety net.
"""

TEXT = {
    # ================= common =================
    "sep": ", ",
    "dot": ", ",
    "paren": " ({x})",
    "none": "none",
    "char_ratio": 4,
    "width_ratio": 2,
    "uses_first_person": False,
    "honorific_prefixes": ("Mr. ", "Ms. ", "Mrs. ", "Miss ", "Mx. ", "the ", "The "),
    "honorific_suffixes": ("'s", "’s"),
    "memory_words": ("last time", "remember", "before", "again", "that time", "back then", "helped", "saved"),

    # ================= persona seeds (gen_personas.py) =================
    "tones": ["speaks politely and formally", "casual and friendly", "blunt, with short sentences",
              "old-fashioned turns of phrase", "childlike and innocent", "poetic, full of metaphors",
              "talks fast and impatiently", "gentle and easygoing", "logical and argumentative",
              "folksy, down-home way of talking"],
    "move_habits": {"straight": "walks in straight lines", "detour": "tends to take detours",
                    "outer": "likes to walk along the edge of the island",
                    "pause": "stops now and then to observe", "zigzag": "wanders in a wobbly zigzag"},

    # ================= prompts (llm/prompts.py) =================
    "rules": (
        "# World\n"
        "This is a small island surrounded by sea. Residents have no concept of eating, sleeping, family, or gender.\n"
        "Each resident has HP (0-{max_hp}) and Heart (0-{max_heart}). HP never drops in everyday life.\n"
        "When HP hits 0, a resident \"freezes\": they stiffen in place and can't move. They are not broken and do not disappear.\n"
        "Only the magic staffs of the few healers on the island can undo a freeze. A thawed resident wakes up with full HP.\n"
        "Heart drops when something frightening happens or when a friend freezes right in front of you. "
        "When Heart falls below {fear_heart}, you become \"frightened\".\n"
        "Staying near any of {solaces} slowly restores Heart (and a little HP). "
        "Cheering up a friend in conversation restores a bit of their Heart.\n"
        "Main places on the island: {places}.\n"
        "Now and then, a big black evil monster comes from beyond the island. It picks its own prey and "
        "slashes residents' HP and Heart with sharp claws until they freeze (an ordinary resident freezes after 3 claw hits). "
        "Being attacked puts you in a \"noise\" state, and your Heart slowly drains for a while. "
        "After freezing enough residents, it leaves. The monster is faster than normal walking, but hurrying (fast) can outrun it.\n"
        "A few residents are warriors. Warriors carry swords and can attack the monster with psychic lightning; "
        "enough hits bring it down. But the monster fires black bullets back at any warrior who shoots it. "
        "Warriors are tough and take less damage.\n"
        "# Ground rules\n"
        "- You act as a resident of the island. Never mention being an AI or talk about meta topics.\n"
        "- If you don't know something, say so. Don't invent events you don't remember.\n"
        "- Reply with the specified JSON only. Write all text in English."
    ),
    "persona.name": "# You\nName: {x}",
    "persona.first_person": "",
    "persona.first_person_default": "",
    "persona.tone": "Speech style: {x}",
    "persona.catchphrase": "Catchphrase: {x}",
    "persona.background": "Background: {x}",
    "persona.likes": "Likes: {x}",
    "persona.dislikes": "Dislikes: {x}",
    "persona.goal": "Goal: {x}",
    "persona.help_view": "View on helping others: {x}",
    "persona.favorite_spot": "Favorite place: {x}",
    "persona.traits": "Personality (0-10): sociability {sociability}, generosity {generosity}, curiosity {curiosity}, caution {caution}",
    "persona.boot_cycles": "Boot cycles since activation: {x}",
    "persona.samples": "Sample lines: ",
    "persona.sample": "\"{x}\"",
    "persona.warrior": ("Role: You are a warrior. You carry a sword and can attack the evil monster with psychic lightning "
                        "from a short distance. Shooting it makes it fire back, but you are tough, so the damage you take is small."),
    "persona.healer": ("Role: You are a healer. You carry a magic staff; by chanting for {cast_sec:g} seconds beside a frozen "
                       "resident, you can undo the freeze and wake them with full HP (you can't move while chanting). "
                       "You can sense wherever on the island a resident freezes. Only healers can undo a freeze. "
                       "Healers can be targeted by the monster just like anyone else."),

    "say.no_talk": "(Nobody has spoken yet. You start the conversation.)",
    "say.rescued": ("\nNote: You were just frozen after the evil monster drained your HP, and the healer {name} "
                    "woke you with a magic staff. Mention this in your line."),
    "say.gossip": ("- You don't have to talk only about the scenery or your mood; you may also gossip about other residents. "
                   "Feel free to bring up residents from \"Your impressions of other residents\" or \"Rumors you've heard\", "
                   "saying what you honestly think of them (good things and things you don't like).\n"),
    "say.user": (
        "# Your history with {partner}\n{pair_memory}\n\n"
        "# Current situation\n{situation}\n\n"
        "# This conversation (latest)\n{talk}\n\n"
        "# Instructions\nReturn exactly one next line for you ({me}).{note}\n"
        "- say: at most 20 words, in your speech style. Respond to what was just said.\n"
        "- cheer: true if this line cheers up {partner} (their Heart recovers a little). "
        "Use it when they are frightened or feeling down.\n"
        "- end: true if you end the conversation with this line. Set it to true when you've run out of things to say.\n"
        "{gossip}"
        "- Don't repeat a sentence or phrasing already used. Use your catchphrase only occasionally."
    ),

    "intent.rescue": ", rescue=go to a frozen resident and heal them",
    "intent.flee": ", flee=run away from the evil monster",
    "intent.fight": ", fight=approach the evil monster and fight it with psychic power",
    "intent.rescue_target": "; for rescue, the name of a frozen resident",
    "intent.user": (
        "# Your memories\n{memory}\n\n"
        "# Current situation\n{situation}\n"
        "(Why you are deciding your next move now: {reason})\n\n"
        "# Instructions\nDecide how you will move next.\n"
        "- intent: {kinds}\n"
        "  go_spot=go to a place, seek=look for a resident, follow=walk along with a resident, avoid=keep away from a resident,\n"
        "  wander=roam nearby, patrol=make rounds of your favorite places, wait=wait where you are{extra}\n"
        "- target: for go_spot, a place name ({names}); for seek/follow/avoid, a resident's name{rescue_target}. "
        "Otherwise an empty string.\n"
        "  When your Heart is low, going to any of {solaces} restores it.\n"
        "- pace: slow / normal / fast\n"
        "- manner: how you feel and how you walk, as your inner voice, at most 20 words.\n"
        "- duration_sec: how many seconds to keep doing this (10-90)"
    ),

    "rescue.user": (
        "# Your history with {target}\n{pair_memory}\n\n"
        "# Current situation\n{situation}\n"
        "{target} is frozen right in front of you.\n\n"
        "# Instructions\nDecide whether to undo the freeze with your magic staff, based on your personality, HP, Heart, "
        "your relationship with them, and your surroundings (is the monster nearby?).\n"
        "- heal: true to heal. You can't move during the {cast_sec:g}-second chant; when it ends, {target} wakes with full HP.\n"
        "- say: what you say at that moment (at most 20 words)"
    ),

    "raider.system": (
        "# You\nYou are the evil monster \"{name}\". You came from the dark sea of noise beyond the island. "
        "You claw the island's residents until they freeze, trying to fill the island with noise.\n"
        "You speak in broken, halting fragments, eerie and inhuman, often in CAPITAL LETTERS. "
        "You never befriend residents.\n\n"
        "# Your powers and weaknesses\n"
        "- When your claws reach your target, you rip {strike_damage:g} HP from them every {strike_cooldown:g} seconds "
        "(residents have at most {max_hp} HP). A resident at 0 HP freezes and can't move.\n"
        "- You are faster than a resident walking normally, but you can't catch one who hurries (fast). "
        "If your claws don't reach a resident after {give_up:g} seconds of chasing, you can't chase them again during this raid.\n"
        "- Warriors ({warriors} on the island) attack you with psychic lightning from about {attack_range:g}m away. "
        "Each hit takes {attack_damage} of your HP; at 0 you collapse and vanish. "
        "You automatically fire black bullets back at warriors who shoot you. "
        "Warriors are tough; your claws and bullets don't hurt them much.\n"
        "- Healers ({healers} on the island) wake frozen residents with magic staffs. "
        "They can't move during the {cast_sec:g}-second chant.\n"
        "- You can stay on the island for at most {max_stay:g} seconds. Once you have frozen {victims} residents, "
        "you are full and leave the island.\n\n"
        "# Ground rules\n- Reply with the specified JSON only. Write all text in English."
    ),
    "raider.no_past": "(None yet. This is your first raid.)",
    "raider.user": (
        "# Past raids\n{past}\n\n"
        "# Current situation\n{situation}\n"
        "(Why you are deciding now: {reason})\n\n"
        "# Instructions\nDecide what to do next.\n"
        "- action: {actions} (hunt=chase a resident and attack with your claws, leave=leave the island)\n"
        "- target: for hunt, the name of the resident to target (from \"Residents you can target\"). For leave, an empty string.\n"
        "- say: words the residents can hear (at most 6 words, broken speech). An empty string to stay silent.\n"
        "- thought: your inner thoughts (at most 20 words)"
    ),

    "summary.no_old": "(None. You just met.)",
    "summary.cheer": "({a} cheered up {b})",
    "summary.user": (
        "# What you remembered about {partner}\n{old}\n"
        "Affinity: {affinity} (-10 to 10)\n\n"
        "# The conversation that just ended\n{talk}\n{cheers}\n\n"
        "# Instructions\nFrom your ({me}) point of view, rewrite your memory of {partner}.\n"
        "- thought: First, look back on this conversation: what you thought and felt about {partner}, "
        "in your inner voice (at most 30 words). Decide the other fields based on this.\n"
        "- summary: at most 50 words. Combine your previous memory with this conversation. "
        "Always keep any cheering up, being cheered up, helping, or being helped.\n"
        "- affinity_delta: how your affinity changed in this conversation (-3 to 3)\n"
        "- heard: things {partner} said in this conversation about other residents or places, mentioning them by name. "
        "At most {heard_max} items. Don't include {partner} or yourself. If none, an empty array [].\n"
        "  about=the name of that resident or place, note=what you heard (at most 15 words, phrased as hearsay, "
        "e.g. \"apparently ...\"),\n"
        "  feel=how hearing it made you feel about that resident or place (-2 to 2)"
    ),

    "persona_gen.user": (
        "Create one island resident. Their name is \"{name}\" (already decided). "
        "Return a character profile in JSON that fits the following \"seed\".\n"
        "- Speech style: {tone}\n"
        "- Sociability {sociability} / Generosity {generosity} / "
        "Curiosity {curiosity} / Caution {caution} (0-10)\n"
        "- Favorite place: {favorite_spot}\n"
        "- Movement habit: {move_habit}\n"
        "- Boot cycles since activation: {boot_cycles}\n\n"
        "Fields (write all text in English):\n"
        "- catchphrase: a catchphrase (at most 6 words)\n"
        "- background: background story (at most 30 words)\n"
        "- likes / dislikes: things they like and dislike (at most 15 words each)\n"
        "- goal: their goal (at most 15 words)\n"
        "- help_view: how they feel about helping friends in trouble (at most 20 words; reflect generosity)\n"
        "- walk_mood: the mood of their walk (at most 15 words; reflect the movement habit)\n"
        "- sample_lines: 3 sample lines (at most 15 words each; reflect the speech style)"
    ),

    # ================= injected memories (memory/recall.py) =================
    "recall.rumor": "- {about}{text} (heard from {src})",
    "recall.rumor_about": "{x}: ",
    "recall.first_meet": "You've never met before.",
    "recall.no_summary": "You've talked before, but you don't know them well yet.",
    "recall.affinity": "Affinity: {x} (-10 to 10)",
    "recall.thought": "What you thought after your last talk: {x}",
    "recall.strong": "Unforgettable events:",
    "recall.rumors_about": "Rumors you've heard about {name}:",
    "recall.partner_events": "{name}'s recent events:",
    "recall.my_events": "Your recent events:",
    "recall.heard": "Stories you've heard:",
    "recall.nothing": "Nothing in particular comes to mind.",
    "recall.impressions": "Your impressions of other residents:",
    "recall.impression": "- {name}: {summary} (affinity {affinity})",
    "recall.impression_thought": "\n  What you thought: {x}",
    "recall.rumors": "Rumors you've heard:",

    # ================= world (sim/world.py) =================
    "sys.connecting": "Connecting to the LLM server…",
    "sys.connected": "LLM connected. Starting the world",
    "sys.connect_fail": "Can't connect to the LLM ({error}). Retrying in 5 seconds",
    "sys.no_npcs": "{db} has no residents. Run python tools/gen_personas.py first",
    "sys.lang_mismatch": ("The residents in {db} were created with lang = \"{stored}\" (config.toml says \"{lang}\"). "
                          "Match [locale] lang, or use a different --db"),
    "cond": "HP {hp}/{max_hp}, Heart {heart}/{max_heart}, status: {status}",
    "sit.place": "Location: {x}",
    "sit.me": "You: {x}",
    "sit.other": "{name}: {x}",
    "sit.near": "Residents nearby: ",
    "sit.near_frozen": "Frozen residents nearby: ",
    "sit.at_solace": "You are next to {name}; your Heart is being restored",
    "sit.nearest_solace": "Nearest place that restores Heart: {name} (about {d}m)",
    "sit.frozen_none": "Frozen residents you can sense: none",
    "sit.frozen_heading": ", the healer {name} is heading there",
    "sit.frozen_list": "Frozen residents you can sense ({total} on the island, nearest first): ",
    "sit.frozen_item": "{name} ({place}, about {d}m{heading})",
    "role.warrior": "warrior",
    "role.healer": "healer",
    "doing.frozen": "frozen",
    "doing.talking": "talking",
    "doing.casting": "chanting",
    "doing.fear": "frightened",
    "place.near": "near {name} (about {d}m)",
    "manner.rest": "I'll rest here and let my Heart recover",
    "stub.like": "they're nice",
    "stub.dislike": "not my favorite",
    "ev.cheer": "{a} cheered up {b}, and {b}'s Heart felt a little lighter ({spot})",
    "ev.talk": "{a} and {b} talked at {spot} ({n} lines)",
    "ev.arrived": "{a} arrived at {spot}",
    "ev.rescue": "The healer {a} used a magic staff to wake {b}, who had been frozen ({spot})",
    "why.heal_already": "You went to heal {name}, but they were already awake",
    "why.heal_declined": "You decided not to heal {name}",
    "why.talk_end": "The conversation ended",
    "why.raider_down": "The evil monster collapsed",
    "why.raider_gone": "The evil monster is gone",
    "why.arrived": "Arrived at {x}",
    "why.found": "Found {x}",
    "why.avoided": "Got far enough away from {x}",
    "why.rescue_woke": "{x}, whom you went to heal, was already awake",
    "why.rescue_at": "Arrived next to {x}, whom you came to heal",
    "why.fled": "Got far enough away from the evil monster",
    "why.done": "Accomplished what you set out to do",
    "why.felt_freeze": "You sensed {name} freeze at {spot}",
    "why.already_awake": "{name} was already awake",
    "why.revived": "The healer {name}'s magic staff undid your freeze, and you woke up (HP {hp})",
    "why.healed": "You undid {name}'s freeze",
    "why.woke": "You woke up on the island",
    "why.solace_calm": "Your Heart has calmed down",
    "why.wait_bored": "You got bored of waiting",
    "why.long": "You've kept doing the same thing for a while",
    "why.heart_low": "Your Heart fell below {th} ({status})",
    "status": {"freeze": "frozen", "noise": "noise", "fear": "frightened"},

    # ================= evil monster (sim/raid.py) =================
    "taunts": {"full": "...FULL...", "time": "...TIME...IS...UP...", "empty": "...NO...PREY...",
               "defeated": "GH...GAAH..."},
    "leave_how": {"choice": "left of its own accord", "full": "left with its appetite sated",
                  "time": "left when its time ran out", "empty": "left because no prey was left"},
    "r.cause.strike": "the claws of the evil monster {name}",
    "r.cause.counter": "the counterattack of the evil monster {name}",
    "r.why.arrived": "You arrived on the island (near {spot})",
    "r.why.idle": "You've been moving for a while without rethinking",
    "r.why.no_target": "You haven't chosen a target",
    "r.why.escaped": "You chased {name} for {sec:g} seconds, but they got away (you can't chase them again this raid)",
    "r.why.target_frozen": "{name}, your target, froze",
    "r.why.froze": "You clawed {name} until they froze",
    "r.why.counter_froze": "Your counterattack froze the warrior {name}",
    "r.why.revived": "The healer {healer} woke {target}",
    "r.why.shot": "The warrior {name} attacked you with psychic power",
    "r.why.hit": "The warrior {name}'s psychic power hit you; your HP dropped to {hp}",
    "r.alert.appear": "You sensed the evil monster {name} appear near {spot}",
    "r.alert.near": "The evil monster {name} is approaching",
    "r.alert.grab": "The evil monster {name} is attacking you with its claws",
    "r.who.warrior": "the warrior {name}",
    "r.who.healer": "the healer {name}",
    "r.who.resident": "{name}",
    "r.ev.appear": "The evil monster {name} appeared near {spot}",
    "r.ev.frozen": "At {spot}, {who} took the claws of the evil monster {raider}, dropped to 0 HP, and froze",
    "r.ev.struck": "At {spot}, {name} lost {dealt} HP to the claws of the evil monster {raider}, but got away",
    "r.ev.counter_frozen": ("At {spot}, the warrior {name} was hit by a counterattack bullet from the evil monster {raider}, "
                            "dropped to 0 HP, and froze"),
    "r.ev.plan_leave": "The evil monster {name} decided to leave the island",
    "r.ev.plan_hunt": "The evil monster {name} decided to target {target}",
    "r.ev.defeated": ("At {spot}, {name} defeated the evil monster {raider} {with_whom}. "
                      "{name}'s psychic power hit {hits} of {shots} times"),
    "r.ev.fought": ("At {spot}, {name} fought the evil monster {raider}, but it got away {with_whom}. "
                    "{name}'s psychic power hit {hits} of {shots} times"),
    "r.ev.raid_end": ("Raid #{no}: the evil monster {raider} {how}. In {sec}s it froze {victims} residents, "
                      "and healers unfroze {revived} of them. Warriors who fought: {fought}"),
    "r.with": "(fought alongside {names})",
    "r.alone": "(fought alone)",
    "r.how.defeated": "was defeated by the warriors",
    "r.how.default": "left",
    "r.fought_item": "{name} ({hits} hits of {shots} shots)",
    "r.nobody": "none",
    "r.sit.hp": "Your HP: {hp}/{max_hp}",
    "r.sit.time": "Time on the island: {sec}s (max {max:g}s)",
    "r.sit.victims": "Residents you froze: {n} ({left} more until you are full)",
    "r.sit.victim_names": " … {names}",
    "r.sit.target": "Current target: {name} (about {d}m)",
    "r.sit.no_target": "Current target: none",
    "r.sit.attackers": "Warriors attacking you now: ",
    "r.sit.attacker": "{name} (about {d}m, {hits} hits of {shots} shots)",
    "r.sit.escaped": "Residents who escaped (can't chase again): {names}",
    "r.sit.revived": "Residents a healer unfroze: ",
    "r.sit.revived_item": "{target} (healer {healer})",
    "r.sit.frozen_count": "Frozen residents on the island: {n}",
    "r.sit.cands": "Residents you can target (nearest first):",
    "r.sit.cand": "- {name}: about {d}m, HP {hp}, {label}",
    "r.sit.no_cands": "Residents you can target: none",
    "r.doing.fight": "trying to fight you",
    "r.doing.flee": "running away",
    "r.doing.casting": "raising a staff and chanting (can't move)",
    "r.doing.rescue": "trying to heal a frozen resident",
    "r.doing.solace": "resting to restore their Heart",
    "r.doing.walk": "walking",
    "r.doing.stand": "standing still",
    "r.d.down": "collapsing after being defeated by the warriors",
    "r.d.leaving": "leaving the island",
    "r.d.you": "targeting you",
    "r.d.other": "targeting {name}",
    "r.d.search": "looking for its next prey",
    "r.d.text": ("Evil monster {raider}: {place}, about {d}m from you. It is {doing}. "
                 "HP {hp}/{max_hp}; so far {victims} residents have frozen from its claws or bullets"),
    "r.d.fighters": ". Warriors fighting it: ",

    # ================= stub (llm/stub.py) =================
    "stub.server": ("no LLM", "stub"),
    "stub.say_lines": [
        "Hey, {p}. How's your current today?", "{p}, we meet here again", "It's nice and quiet around here",
        "The water at the Random Spring was sparkling today", "My heart feels light lately",
        "I was just lost in thought", "Where are you headed, {p}?", "Oh really? I didn't know that",
        "Yeah, I get it", "Well, see you later", "They say there's something at the Core Dump Ruins",
    ],
    "stub.thanks": "{name} saved me. Thank you",
    "stub.gossip": "You know {who}? ",
    "stub.cheer": "{name}, cheer up. It'll be okay",
    "stub.hearsay": "apparently {x}",
    "stub.hearsay_mark": "apparently ",
    "stub.m.fight": "I won't forgive evil. I'll drive it off with my powers",
    "stub.m.flee": "The black thing is coming! I have to run",
    "stub.m.rescue": "Someone is frozen. I have to go heal them with my staff",
    "stub.m.solace": "My heart feels uneasy. I'll go somewhere to rest",
    "stub.m.spot": "Let's go to {spot}",
    "stub.m.seek": "That one is on my mind",
    "stub.m.patrol": "I'll make my usual rounds",
    "stub.m.wander": "Just wandering around",
    "stub.m.wait": "I'll rest here a bit",
    "stub.heal": "{name}, wake up",
    "stub.no_heal": "Sorry, it's too dangerous to chant here right now",
    "stub.r.leave_say": "...TODAY...I...RETREAT...",
    "stub.r.leave_thought": "The warriors are too strong. Fall back",
    "stub.r.empty": "No prey left",
    "stub.r.says": ["FREEZE...", "RUNNING...IS...USELESS...", "", "BE...CONSUMED...BY...NOISE..."],
    "stub.r.hunt": "I'll freeze {name} with my claws",
    "stub.s.add": "Exchanged about {n} lines with {name}. ",
    "stub.s.thought": "Glad I talked with {name}",
    "stub.p.first_persons": [],
    "stub.p.catchphrases": ["Beep-boop", "I see, I see", "Hmm, hmm", "Hehe", "Oh well"],
    "stub.p.background": "A resident who lives near {spot}.",
    "stub.p.dislikes": "noise",
    "stub.p.goal": "To see every place on the island",
    "stub.p.help_yes": "I can't leave anyone in trouble alone",
    "stub.p.help_no": "I look out for myself",
    "stub.p.samples": ["Hello", "I love quiet moments", "See you"],

    # ================= viewer (viewer/) =================
    "hud.help": ("Left-drag/WASD move / Right-drag rotate / Wheel zoom / Click follow / Esc auto / "
                 "V inner voice / M sound / Shift+Q quit"),
    "hud.residents": "Residents {npcs}: walking {moving}  talking {talking}  recovering {resting}  frozen {frozen}  awaiting reply {waiting}",
    "hud.hp": "HP avg {hp:.0f}  Heart avg {heart:.0f}  Status: frightened {fear}  noise {noise}",
    "hud.llm_wait": "LLM in flight {inflight}  queued {queued}  done {done}/{total}  {elapsed:.1f}s",
    "hud.llm_idle": "LLM in flight 0",
    "hud.last_wave": "Last wave {n} reqs {wall:.1f}s  {tps:.0f} tok/s  TTFT p50 {p50:.2f} / p95 {p95:.2f}s  failed {fail}",
    "hud.totals": "Total talks {sessions}  lines {utterances}  cheers {cheers}  heals {rescues}  freezes {freezes}  LLM failures {llm_fail}",
    "hud.healers": "Healers: heading to heal {healing}  decided not to heal {declined}",
    "hud.camera": "Camera: {mode}   Inner voice: {inner}   Sound: {sound}",
    "hud.raid_total": "raids {raids} / repelled {defeated} / residents frozen {frozen}",
    "hud.raid_none": "Evil: none ({total})",
    "hud.raid_doing": {"appear": "appearing", "hunt": "hunting", "leave": "retreating", "defeated": "defeated"},
    "hud.thinking": "thinking…",
    "hud.raid": ("Evil {name} [{doing}] HP {hp}/{max_hp}  frozen {victims}/{max_victims}  target {aim}  "
                 "fighting {fighting}  fleeing {fleeing}  hits {hits}/{shots}  counters {chits}/{counters}"),
    "hud.raid_thought": "\n  Inner voice: {x}",
    "hud.no_model": "{model} (couldn't get the model name)",
    "hud.checking": "checking…",
    "info.frozen": "frozen (waiting for a healer's staff)",
    "info.talking": "talking with {name}",
    "info.casting": "chanting to unfreeze {name}",
    "info.thinking": "thinking",
    "info.warrior": "[Warrior] ",
    "info.healer": "[Healer] ",
    "info.waiting": "  awaiting: {x}",
    "info.hp": "HP {hp:.0f}/{max_hp}  Heart {heart:.0f}/{max_heart}  Status: {status}",
    "info.solace": "  (recovering at {name})",
    "info.seed": "{tone} / {habit} / favorite place: {spot}",
    "info.traits": "Social {sociability}  Generous {generosity}  Curious {curiosity}  Cautious {caution}",
    "info.persona": "Catchphrase \"{catch}\"  Goal: {goal}",
    "info.now": "Now: {x}",
    "info.events": "― Recent events ―",
    "info.relations": "― Relationships ―",
    "camera.modes": {"auto": "auto (director)", "manual": "manual", "follow": "follow"},
    "app.frozen_label": "FROZEN",
    "log.title": "― Off-screen talk ―",
    "log.heal": "{a} unfroze {b}",
    "log.raider_thought": "{name} (inner): {x}",
    "log.raider_appear": "The evil monster {name} appeared near {spot}!",
    "log.froze": "{name} froze (victim #{n})",
    "log.escaped_hit": "{name} lost {dmg} HP to its claws but escaped",
    "log.defeated": "{name} was defeated! {names}",
    "log.gone": "{name} left (victims: {n})",
}
