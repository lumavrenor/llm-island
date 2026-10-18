"""
効果音を合成して assets/sfx/*.wav に書き出す（素材ファイルを使わず、すべて計算で作る）

    python tools/gen_sfx.py

ビューア（viewer/sound.py）が出来事ごとに鳴らす。音を変えたいときはここを直して作り直す。
ピコピコした短い電子音にしている。
"""

from __future__ import annotations

import sys
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # python tools/gen_sfx.py で起動しても core/・lang/ などを import できるように

import numpy as np

from core.config import ROOT

SR = 44100
OUT = ROOT / "assets" / "sfx"
rng = np.random.default_rng(7)


def t_axis(dur: float) -> np.ndarray:
    return np.arange(int(SR * dur)) / SR


def env(dur: float, attack: float, decay: float) -> np.ndarray:
    """立ち上がり attack 秒、そのあと時定数 decay 秒で指数的に消える"""
    t = t_axis(dur)
    e = np.minimum(1.0, t / max(attack, 1e-4)) * np.exp(-np.maximum(0.0, t - attack) / decay)
    fade = np.minimum(1.0, (dur - t) / 0.01)    # 最後の 10ms でぷつっと鳴らないように
    return e * fade


def osc(freq, dur: float, shape: str = "sine") -> np.ndarray:
    """freq は一定値か、サンプルごとの配列（グライド）"""
    n = int(SR * dur)
    f = np.broadcast_to(np.asarray(freq, dtype=float), (n,))
    ph = 2 * np.pi * np.cumsum(f) / SR
    match shape:
        case "sine":
            return np.sin(ph)
        case "soft":     # 3 倍音を少し足した、ピコっとした音
            return np.sin(ph) + 0.25 * np.sin(3 * ph)
        case "square":   # 角を丸めた矩形
            return np.tanh(3.0 * np.sin(ph))
        case "saw":
            return 2 * ((ph / (2 * np.pi)) % 1.0) - 1
    raise ValueError(shape)


def bell(freq: float, dur: float, decay: float) -> np.ndarray:
    """ベル（少しずれた倍音を足す）"""
    return (osc(freq, dur) + 0.35 * osc(freq * 2.76, dur) * np.exp(-t_axis(dur) / (decay * 0.4))
            + 0.15 * osc(freq * 5.4, dur) * np.exp(-t_axis(dur) / (decay * 0.2))) * env(dur, 0.002, decay)


def lowpass(x: np.ndarray, cutoff) -> np.ndarray:
    """1 次のローパス（cutoff はサンプルごとの配列でもよい）"""
    c = np.broadcast_to(np.asarray(cutoff, dtype=float), x.shape)
    a = 1 - np.exp(-2 * np.pi * c / SR)
    y = np.empty_like(x)
    acc = 0.0
    for i in range(len(x)):
        acc += a[i] * (x[i] - acc)
        y[i] = acc
    return y


def noise(dur: float) -> np.ndarray:
    return rng.uniform(-1, 1, int(SR * dur))


def mix(dur: float, *parts: tuple[float, np.ndarray]) -> np.ndarray:
    """(開始秒, 音) を重ねる"""
    out = np.zeros(int(SR * dur))
    for start, x in parts:
        i = int(SR * start)
        n = min(len(x), len(out) - i)
        out[i:i + n] += x[:n]
    return out


def glide(f0: float, f1: float, dur: float, curve: float = 1.0) -> np.ndarray:
    k = (t_axis(dur) / dur) ** curve
    return f0 * (f1 / f0) ** k     # 指数的に（耳に自然な）音程を動かす


# ---------- 出来事ごとの音 ----------

def say():
    """会話：ピポッ（住人ごとに再生速度を変えて高さを変える）"""
    a = osc(1320, 0.05, "soft") * env(0.05, 0.003, 0.03)
    b = osc(1760, 0.08, "soft") * env(0.08, 0.003, 0.04)
    return mix(0.14, (0, a), (0.045, b))


def cheer():
    """励まし：キラリン（上がる分散和音）"""
    notes = (1047, 1319, 1568, 2093)
    return mix(0.9, *((i * 0.06, bell(f, 0.6, 0.18)) for i, f in enumerate(notes)))


def cast_start():
    """詠唱：ふわーっと上がる、ゆらぎのある音＋きらきら"""
    d = 0.9
    t = t_axis(d)
    f = glide(500, 1500, d, 0.7) * (1 + 0.02 * np.sin(2 * np.pi * 11 * t))
    swell = np.minimum(1, t / 0.35) * np.minimum(1, (d - t) / 0.3)
    body = (osc(f, d) + 0.4 * osc(f * 2, d)) * swell * 0.6
    sparks = [(rng.uniform(0.1, 0.75), bell(rng.uniform(2200, 3600), 0.2, 0.05) * 0.35) for _ in range(7)]
    return mix(d, (0, body), *sparks)


def heal():
    """癒し（フリーズが解ける）：パリンと氷が砕けて、明るい和音のチャイム"""
    hp = noise(0.3) - lowpass(noise(0.3), 3000)          # 高い音だけの雑音＝ガラスっぽさ
    crash = hp * env(0.3, 0.001, 0.05) * 0.8
    chord = [(0.06 + i * 0.035, bell(f, 1.3, 0.45) * 0.5) for i, f in enumerate((784, 988, 1175, 1568))]
    return mix(1.4, (0, crash), *chord)


def frozen():
    """フリーズ：キーンと下がりながら、パキパキ凍る"""
    d = 0.8
    t = t_axis(d)
    f = glide(1800, 420, d, 0.6)
    tone = osc(f * (1 + 0.01 * np.sin(2 * np.pi * 30 * t)), d) * env(d, 0.005, 0.35) * 0.7
    cracks = []
    for _ in range(9):
        c = noise(0.025) - lowpass(noise(0.025), 2500)
        cracks.append((rng.uniform(0.15, 0.7), c * env(0.025, 0.0005, 0.006) * rng.uniform(0.4, 0.8)))
    return mix(d, (0, tone), *cracks)


def attack():
    """戦士の超能力：ビュン（高いところから急に下がる電撃）"""
    d = 0.22
    zap = osc(glide(2200, 320, d, 0.5), d, "square") * env(d, 0.002, 0.08) * 0.5
    crackle = (noise(d) - lowpass(noise(d), 4000)) * env(d, 0.001, 0.03) * 0.4
    return zap + crackle


def raider_counter():
    """悪の反撃：ドゥン（低く濁った弾）"""
    d = 0.35
    f = glide(420, 70, d, 0.6)
    x = (osc(f, d, "saw") + osc(f * 1.01, d, "saw")) * env(d, 0.003, 0.12)
    return np.tanh(lowpass(x, 1400) * 2.5) * 0.6


def raider_strike():
    """悪の爪：シャッ（2 回の切り裂き）"""
    def slash(d):
        cut = glide(6000, 900, d, 0.5)
        return lowpass(noise(d), cut) * env(d, 0.004, 0.05) * 1.6
    return mix(0.3, (0, slash(0.18)), (0.07, slash(0.2) * 0.8))


def raider_appear():
    """悪の襲来：ゴゴゴ…（低いうなりがふくらみ、不気味に下がる）"""
    d = 2.6
    t = t_axis(d)
    f = 55 * (1 - 0.15 * t / d)
    drone = sum(osc(f * m, d, "saw") * g for m, g in ((1, 1), (1.013, 0.8), (1.5, 0.35), (2.02, 0.3)))
    shape = np.minimum(1, t / 0.9) * np.minimum(1, (d - t) / 1.0)
    wob = 1 + 0.35 * np.sin(2 * np.pi * 5 * t)
    low = lowpass(drone, 600) * shape * wob
    whine = osc(glide(900, 300, d, 1.2), d) * shape * 0.08
    return np.tanh(low * 1.5) * 0.7 + whine


def raider_defeated():
    """悪を倒した：短いファンファーレ"""
    notes = ((0.0, 523, 0.11), (0.11, 659, 0.11), (0.22, 784, 0.11), (0.33, 1047, 0.6))
    parts = []
    for start, f, d in notes:
        t = t_axis(d)
        vib = 1 + (0.008 * np.sin(2 * np.pi * 6 * t) if d > 0.3 else 0)
        parts.append((start, osc(f * vib, d, "square") * env(d, 0.004, d * 0.6) * 0.35))
        parts.append((start, bell(f * 2, d, d * 0.5) * 0.25))
    return mix(1.0, *parts)


def raider_gone():
    """悪が去る：シュウゥ…（遠ざかる風と下がる音）"""
    d = 1.3
    t = t_axis(d)
    shape = np.minimum(1, t / 0.15) * np.exp(-t / 0.5)
    wind = lowpass(noise(d), glide(3000, 300, d)) * shape * 1.2
    tone = osc(glide(320, 90, d), d, "saw") * shape * 0.15
    return lowpass(tone, 900) + wind


SOUNDS = {f.__name__: f for f in (say, cheer, cast_start, heal, frozen, attack, raider_counter,
                                   raider_strike, raider_appear, raider_defeated, raider_gone)}


def write_wav(path: Path, x: np.ndarray):
    x = x / max(1e-9, np.max(np.abs(x))) * 0.85
    pcm = (x * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for name, fn in SOUNDS.items():
        x = fn()
        write_wav(OUT / f"{name}.wav", x)
        print(f"{name}.wav  {len(x) / SR:.2f} 秒")


if __name__ == "__main__":
    main()
