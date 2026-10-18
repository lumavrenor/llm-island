"""
LLM クライアント — ウェーブ方式

■ 方針（バグを生まないための約束）
- LLM リクエストは「ウェーブ」単位で扱う。メインループが全員分のリクエストを
  まとめて submit() し、返ってきた Wave の is_done() を毎フレームポーリングするだけ。
- 裏スレッドは HTTP 専用の 1 本だけ（asyncio ループ）。100 件はその中で
  asyncio.gather して並列に投げる。NPC ごとのスレッドは作らない。
- 裏スレッドは世界（NPC・セッション・DB）に一切触らない。入力は LLMRequest、
  出力は LLMResult という「ただのデータ」だけ。結果の反映はメインスレッドが行う。
- 1 件の失敗でウェーブ全体を止めない。_one() は例外を投げず、必ず LLMResult を返す。

SGLang の OpenAI 互換 API（/v1/chat/completions）に stream=True で投げ、
TTFT とトークン数を計測する。出力は JSON スキーマで強制する。
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import statistics
import threading
import time
from dataclasses import dataclass, field

import httpx

logger = logging.getLogger(__name__)


@dataclass
class LLMRequest:
    kind: str                  # "say" / "rescue" / "intent" / "summary" / "persona" / "ping"
    npc_id: int
    messages: list[dict]
    schema: dict | None        # None なら JSON を強制しない（ping 用）
    max_tokens: int
    meta: dict = field(default_factory=dict)  # 反映時に使う付帯情報（スタブの判断材料も兼ねる）


@dataclass
class LLMResult:
    req: LLMRequest
    ok: bool
    data: dict | None = None   # パース済み JSON（失敗時 None）
    text: str = ""
    error: str = ""
    ttft: float = 0.0
    latency: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    attempts: int = 1


def parse_json(text: str) -> dict | None:
    """JSON を取り出す（スキーマ強制していても、念のため前後のゴミに耐える）"""
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            return None
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
    return data if isinstance(data, dict) else None


def _pct(xs: list[float], p: float) -> float:
    if not xs:
        return 0.0
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(len(xs) * p))]


class Wave:
    """1 ウェーブ分のリクエスト。メインループは is_done() を見るだけでよい"""

    def __init__(self, requests: list[LLMRequest]):
        self.requests = requests
        self.sent_at = time.perf_counter()
        self.finished_at: float | None = None
        # 進捗（I/O スレッドが加算し、メインスレッドは読むだけ）
        self.started = 0
        self.finished = 0
        self._future = None          # concurrent.futures.Future（実 LLM）
        self._results: list[LLMResult] | None = None

    @property
    def total(self) -> int:
        return len(self.requests)

    @property
    def inflight(self) -> int:
        return self.started - self.finished

    @property
    def queued(self) -> int:
        """クライアント側でまだ投げていない件数（同時実行上限で待っている分）"""
        return self.total - self.started

    def is_done(self) -> bool:
        if self._results is not None:
            return True
        if self._future is not None and self._future.done():
            try:
                self._results = self._future.result()
            except Exception as e:  # _one() は投げないので本来ここには来ない
                logger.exception("ウェーブ全体が失敗: %s", e)
                self._results = [LLMResult(r, ok=False, error=repr(e)) for r in self.requests]
            self.finished_at = time.perf_counter()
            return True
        return False

    def results(self) -> list[LLMResult]:
        assert self._results is not None, "is_done() を確認してから呼ぶこと"
        return self._results

    @property
    def elapsed(self) -> float:
        end = self.finished_at if self.finished_at is not None else time.perf_counter()
        return end - self.sent_at

    def summary(self) -> dict:
        """計測値（is_done() 後に呼ぶ）"""
        rs = self.results()
        ok = [r for r in rs if r.ok]
        kinds: dict[str, int] = {}
        for r in rs:
            kinds[r.req.kind] = kinds.get(r.req.kind, 0) + 1
        tokens = sum(r.completion_tokens for r in rs)
        wall = max(self.elapsed, 1e-6)
        return {
            "n": len(rs),
            "kinds": kinds,
            "ok": len(ok),
            "fail": len(rs) - len(ok),
            "retries": sum(r.attempts - 1 for r in rs),
            "wall_sec": round(wall, 2),
            "tok_per_sec": round(tokens / wall, 1),
            "completion_tokens": tokens,
            "prompt_tokens_avg": round(statistics.mean([r.prompt_tokens for r in ok]), 0) if ok else 0,
            "ttft_p50": round(_pct([r.ttft for r in ok], 0.5), 2),
            "ttft_p95": round(_pct([r.ttft for r in ok], 0.95), 2),
            "latency_p50": round(_pct([r.latency for r in ok], 0.5), 2),
            "latency_p95": round(_pct([r.latency for r in ok], 0.95), 2),
            "errors": sorted({r.error for r in rs if r.error})[:3],
            # 種類ごと（どの種類が遅いか・出力が長いかを比べる用）
            "by_kind": {k: {"n": len(g), "tok_avg": round(statistics.mean([r.completion_tokens for r in g]), 1),
                            "lat_p50": round(_pct([r.latency for r in g], 0.5), 2),
                            "lat_max": round(max(r.latency for r in g), 2)}
                        for k in kinds if (g := [r for r in ok if r.req.kind == k])},
        }


@dataclass
class ServerInfo:
    """推論サーバーの名乗り（HUD の左上に出す）。ただのデータ"""
    engine: str            # 例: "SGLang 0.5.21"
    model: str             # 例: "Qwen3.8-27B-NVFP4"（served_model_name の別名ではなく、読み込んだモデルの名前）
    parallel: str = ""     # 例: "PP3"

    @property
    def label(self) -> str:
        detail = ", ".join(x for x in (self.engine, self.parallel) if x)
        return f"{self.model}（{detail}）" if detail else self.model


class PendingInfo:
    """fetch_info() の結果待ち。メインスレッドは毎フレーム is_done() を見るだけ（待たない）"""

    def __init__(self, future=None, value: ServerInfo | None = None):
        self._future = future
        self._value = value

    def is_done(self) -> bool:
        return self._future is None or self._future.done()

    def result(self) -> ServerInfo | None:
        if self._future is None:
            return self._value
        try:
            return self._future.result()
        except Exception:
            return None


_ENGINE_NAMES = {"sglang": "SGLang", "vllm": "vLLM", "llamacpp": "llama.cpp", "llama.cpp": "llama.cpp"}


def _model_basename(path: str) -> str:
    """"/path/to/Qwen3.8-27B-NVFP4" や "Qwen/Qwen3-8B" → 最後の部分だけ"""
    return path.rstrip("/").replace("\\", "/").split("/")[-1] or path


class LLMClient:
    """SGLang（OpenAI 互換）クライアント。HTTP 用の裏スレッドを 1 本だけ持つ"""

    def __init__(self, cfg):
        self.base_url = cfg.base_url.rstrip("/")
        self.model = cfg.model
        self.api_key = cfg.api_key
        self.max_concurrency = cfg.max_concurrency
        self.timeout = cfg.timeout_sec
        self.retries = cfg.retries
        self.temperature = cfg.temperature
        self._http: httpx.AsyncClient | None = None
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, name="llm-io", daemon=True)
        self._thread.start()

    # ---------- メインスレッドから呼ぶ ----------

    def submit(self, requests: list[LLMRequest]) -> Wave:
        wave = Wave(requests)
        wave._future = asyncio.run_coroutine_threadsafe(self._run_wave(wave), self._loop)
        return wave

    def ping(self) -> Wave:
        """接続確認＋ウォームアップ（1 トークンだけ生成させる）"""
        return self.submit([LLMRequest("ping", -1, [{"role": "user", "content": "ping"}], None, 1)])

    def fetch_info(self) -> PendingInfo:
        """サーバーの名乗り（エンジン名・バージョン・読み込んだモデル）を 1 回だけ聞く"""
        return PendingInfo(asyncio.run_coroutine_threadsafe(self._fetch_info(), self._loop))

    def close(self):
        async def _close():
            if self._http is not None:
                await self._http.aclose()
        try:
            asyncio.run_coroutine_threadsafe(_close(), self._loop).result(timeout=5)
        except Exception:
            pass
        self._loop.call_soon_threadsafe(self._loop.stop)

    # ---------- ここから下は I/O スレッド内だけで動く ----------

    def _client(self) -> httpx.AsyncClient:
        if self._http is None:
            limits = httpx.Limits(max_connections=self.max_concurrency + 8,
                                  max_keepalive_connections=self.max_concurrency + 8)
            self._http = httpx.AsyncClient(timeout=httpx.Timeout(self.timeout, connect=10.0),
                                           limits=limits)
        return self._http

    async def _fetch_info(self) -> ServerInfo | None:
        """SGLang は /get_server_info に読み込んだモデルのパス・バージョン・並列数を出す。
        ほかの OpenAI 互換サーバー（vLLM など）は /v1/models の owned_by と root で代わりにする"""
        http = self._client()
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        try:
            r = await http.get(f"{self.base_url}/get_server_info", headers=headers, timeout=5.0)
            if r.status_code == 200:
                d = r.json()
                parallel = " ".join(f"{k[:2].upper()}{d[k]}" for k in ("tp_size", "pp_size", "dp_size")
                                    if isinstance(d.get(k), int) and d[k] > 1)
                return ServerInfo(f"SGLang {d.get('version', '')}".strip(),
                                  _model_basename(d.get("model_path") or d.get("served_model_name") or self.model),
                                  parallel)
        except Exception as e:
            logger.debug("get_server_info に失敗: %s", e)
        try:
            r = await http.get(f"{self.base_url}/v1/models", headers=headers, timeout=5.0)
            m = (r.json().get("data") or [{}])[0]
            owner = str(m.get("owned_by") or "")
            return ServerInfo(_ENGINE_NAMES.get(owner.lower(), owner or "OpenAI 互換"),
                              _model_basename(str(m.get("root") or m.get("id") or self.model)))
        except Exception as e:
            logger.warning("サーバーの名乗りを取得できません: %s", e)
            return None

    async def _run_wave(self, wave: Wave) -> list[LLMResult]:
        self._client()
        sem = asyncio.Semaphore(self.max_concurrency)
        return await asyncio.gather(*(self._one(wave, r, sem) for r in wave.requests))

    async def _one(self, wave: Wave, req: LLMRequest, sem: asyncio.Semaphore) -> LLMResult:
        async with sem:
            wave.started += 1
            try:
                return await self._with_retry(req)
            finally:
                wave.finished += 1

    async def _with_retry(self, req: LLMRequest) -> LLMResult:
        last_error = ""
        for attempt in range(1, self.retries + 2):
            t0 = time.perf_counter()
            try:
                text, ttft, usage = await self._post_stream(req)
            except httpx.HTTPStatusError as e:
                code = e.response.status_code
                last_error = f"HTTP {code}"
                if code < 500 and code != 429:   # 400 などはリトライしても同じ
                    logger.error("LLM %s 失敗 %s: %s", req.kind, last_error, e.response.text[:300])
                    return LLMResult(req, ok=False, error=last_error, attempts=attempt,
                                     latency=time.perf_counter() - t0)
            except (httpx.TransportError, httpx.TimeoutException) as e:
                last_error = type(e).__name__
            except Exception as e:  # 想定外でもウェーブは止めない
                logger.exception("LLM %s で想定外の例外", req.kind)
                return LLMResult(req, ok=False, error=repr(e), attempts=attempt)
            else:
                latency = time.perf_counter() - t0
                data = parse_json(text) if req.schema is not None else {}
                if data is None:
                    return LLMResult(req, ok=False, text=text, error="json", ttft=ttft,
                                     latency=latency, attempts=attempt, **usage)
                return LLMResult(req, ok=True, data=data, text=text, ttft=ttft,
                                 latency=latency, attempts=attempt, **usage)
            await asyncio.sleep(1.0 * attempt)
        return LLMResult(req, ok=False, error=last_error, attempts=self.retries + 1)

    async def _post_stream(self, req: LLMRequest) -> tuple[str, float, dict]:
        payload = {
            "model": self.model,
            "messages": req.messages,
            "max_tokens": req.max_tokens,
            "temperature": self.temperature,
            "stream": True,
            "stream_options": {"include_usage": True},
            "chat_template_kwargs": {"enable_thinking": False},  # Qwen3 の思考は常にオフ
        }
        if req.schema is not None:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": req.kind, "schema": req.schema},
            }
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}

        t0 = time.perf_counter()
        ttft = 0.0
        parts: list[str] = []
        usage = {"prompt_tokens": 0, "completion_tokens": 0}
        async with self._http.stream("POST", f"{self.base_url}/v1/chat/completions",
                                     json=payload, headers=headers) as resp:
            if resp.status_code != 200:
                await resp.aread()
                resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.startswith("data:"):
                    continue
                body = line[5:].strip()
                if body == "[DONE]":
                    break
                chunk = json.loads(body)
                if chunk.get("choices"):
                    delta = chunk["choices"][0].get("delta") or {}
                    piece = delta.get("content")
                    if piece:
                        if not parts:
                            ttft = time.perf_counter() - t0
                        parts.append(piece)
                if chunk.get("usage"):
                    usage["prompt_tokens"] = chunk["usage"].get("prompt_tokens", 0)
                    usage["completion_tokens"] = chunk["usage"].get("completion_tokens", 0)
        return "".join(parts), ttft, usage
