"""
音（BGM と効果音）

■ BGM（Bgm）
    assets/bgm/ の曲（llm-radio-daemon の自作曲）を、毎巡シャッフルして順に流す。
    曲の頭と終わりはフェードし、曲の間は少し空ける。
    ステート: play（1 曲流す）→ gap（曲間）→ play …

■ 効果音（SoundBoard）
    viewer/app.py の on_event が、出来事の位置といっしょに play() を呼ぶ。鳴らすのは update() で:
    - カメラから近いほど大きく、[audio] far より遠い出来事は鳴らさない（reach で音ごとに伸び縮み）
    - 画面の左右に合わせて左右に振る
    - 同じフレームに同じ音がたくさん来たら（ウェーブの play で発話がまとめて届く）、近いものから max_per_frame 個だけ。
      jitter 秒の範囲でばらして鳴らす
    音は gen_sfx.py で合成した assets/sfx/*.wav。同じ音を重ねられるように、1 つの音に voices 個の声を持つ。

スレッドは使わない（毎フレーム update() で、鳴らす時刻が来たものを鳴らすだけ）。
"""

from __future__ import annotations

import logging
import random
import time
from pathlib import Path

from panda3d.core import AudioSound, Filename

from core.config import ROOT
from core.state import StateMachine

logger = logging.getLogger(__name__)

AUDIO_EXTENSIONS = {".ogg", ".wav", ".mp3", ".flac"}


def _load(loader, path: Path, music: bool) -> AudioSound:
    fn = Filename.from_os_specific(str(path))
    return loader.loadMusic(fn) if music else loader.loadSfx(fn)


class Bgm:
    def __init__(self, acfg, loader):
        self.cfg = acfg
        self.loader = loader
        folder = ROOT / acfg.bgm_dir
        self.files = sorted(p for p in folder.glob("*") if p.suffix.lower() in AUDIO_EXTENSIONS) if folder.is_dir() else []
        self.order: list[Path] = []
        self.last: Path | None = None
        self.sound: AudioSound | None = None
        self.title = ""
        on = bool(self.files) and acfg.bgm_volume > 0
        if not on:
            logger.info("BGM なし（%s に曲がない、または bgm_volume = 0）", folder)
        self.state = StateMachine("play" if on else "off")

    def _next(self) -> Path:
        if not self.order:   # 1 巡したらシャッフルし直す（直前の曲が続けて来ないように）
            self.order = random.sample(self.files, len(self.files))
            if len(self.order) > 1 and self.order[0] == self.last:
                self.order.append(self.order.pop(0))
        self.last = self.order.pop(0)
        return self.last

    def update(self, muted: bool):
        c = self.cfg
        match self.state.update():
            case "play":
                if self.state.entered:
                    path = self._next()
                    self.sound = _load(self.loader, path, music=True)
                    self.sound.setVolume(0.0)
                    self.sound.play()
                    self.title = path.stem.replace("_", " ")
                    logger.info("BGM: %s", self.title)
                t, length = self.state.elapsed, self.sound.length()
                fade = min(1.0, t / c.bgm_fade_sec, max(0.0, length - t) / c.bgm_fade_sec)
                self.sound.setVolume(0.0 if muted else c.bgm_volume * fade)
                if t >= length or (t > 1.0 and self.sound.status() != AudioSound.PLAYING):
                    self.sound.stop()
                    self.state.change("gap")
            case "gap":
                if self.state.elapsed >= c.bgm_gap_sec:
                    self.state.change("play")
            case "off":
                pass


class SoundBoard:
    def __init__(self, acfg, loader):
        self.cfg = acfg
        self.muted = False
        self.bgm = Bgm(acfg, loader)
        self.voices: dict[str, list[AudioSound]] = {}
        self.next_voice: dict[str, int] = {}
        folder = ROOT / acfg.sfx_dir
        for name in vars(acfg.sfx):
            path = folder / f"{name}.wav"
            if not path.exists():
                logger.warning("効果音 %s がありません（python tools/gen_sfx.py で作る）", path)
                continue
            self.voices[name] = [_load(loader, path, music=False) for _ in range(acfg.voices)]
            self.next_voice[name] = 0
        self.pending: list[tuple[str, object, float]] = []           # このフレームに来た (音, 位置, 速さ)
        self.scheduled: list[tuple[float, str, object, float]] = []  # (鳴らす時刻, 音, 位置, 速さ)

    def play(self, name: str, pos, rate: float = 1.0):
        """出来事の位置 pos（Vec3）で音 name を鳴らす。rate は再生速度（音の高さ）"""
        if name in self.voices and not self.muted:
            self.pending.append((name, pos, rate * (1 + random.uniform(-1, 1) * self.cfg.pitch_jitter)))

    def toggle_mute(self) -> bool:
        self.muted = not self.muted
        if self.muted:
            self.pending.clear()
            self.scheduled.clear()
        return self.muted

    def update(self, cam_pos, cam_right):
        self.bgm.update(self.muted)
        now = time.time()
        if self.pending:
            by_name: dict[str, list] = {}
            for name, pos, rate in self.pending:
                by_name.setdefault(name, []).append(((pos - cam_pos).length(), pos, rate))
            self.pending.clear()
            for name, items in by_name.items():
                sc = getattr(self.cfg.sfx, name)
                items.sort(key=lambda x: x[0])
                for i, (_, pos, rate) in enumerate(items[: self.cfg.max_per_frame]):
                    delay = 0.0 if i == 0 else random.uniform(0, sc.jitter)
                    self.scheduled.append((now + delay, name, pos, rate))
        if not self.scheduled:
            return
        later = []
        for item in self.scheduled:
            if item[0] > now:
                later.append(item)
            else:
                self._sound(item[1], item[2], item[3], cam_pos, cam_right)
        self.scheduled = later

    def _sound(self, name: str, pos, rate: float, cam_pos, cam_right):
        c, sc = self.cfg, getattr(self.cfg.sfx, name)
        to = pos - cam_pos
        d = to.length()
        near, far = c.near * sc.reach, c.far * sc.reach
        k = max(0.0, min(1.0, (far - d) / (far - near)))
        volume = c.sfx_volume * sc.gain * k * k
        if volume < 0.005:
            return
        voices = self.voices[name]
        i = self.next_voice[name]
        self.next_voice[name] = (i + 1) % len(voices)
        s = voices[i]
        s.stop()
        s.setVolume(volume)
        s.setBalance(max(-1.0, min(1.0, to.dot(cam_right) / max(d, 1.0) * c.pan)))
        s.setPlayRate(rate)
        s.play()
