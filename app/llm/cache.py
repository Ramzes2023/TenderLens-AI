"""Opt-in exact-generation caching around the independent AI gateway."""
import asyncio
import hashlib
import json
import math
import os
import re
import sys
from dataclasses import dataclass

from app.cache.backend import CacheUnavailable, CacheValueError, LockAcquisitionError, encode
from .base import LLMConfigurationError, LLMTimeoutError
from .gateway import AIGateway
from .models import LLMResponse


@dataclass(frozen=True)
class Operation:
    namespace: str
    version: int = 1

    def __post_init__(self):
        if (type(self.namespace) is not str or not re.fullmatch(r"[a-z][a-z0-9-]{0,63}", self.namespace)
                or type(self.version) is not int or not 1 <= self.version <= 1000000):
            raise LLMConfigurationError("Invalid AI operation identity.")


TENDER_ANALYSIS = Operation("tender-analysis")
COMPANY_PROFILE = Operation("company-search-profile")
RAG_ANSWER = Operation("rag-answer")


@dataclass(frozen=True)
class AICacheSettings:
    enabled: bool = False
    ttl_seconds: float = 3600
    lock_ttl_seconds: float = 60
    wait_seconds: float = 65
    poll_seconds: float = .05

    def __post_init__(self):
        if type(self.enabled) is not bool:
            raise LLMConfigurationError("Invalid AI cache configuration.")
        for value, lower, upper in ((self.ttl_seconds, 1, 604800),
                                    (self.lock_ttl_seconds, 1, 600),
                                    (self.wait_seconds, .01, 600),
                                    (self.poll_seconds, .01, 2)):
            if type(value) not in (int, float) or not lower <= value <= upper or not math.isfinite(value):
                raise LLMConfigurationError("Invalid AI cache configuration.")
        if self.poll_seconds > self.wait_seconds:
            raise LLMConfigurationError("Invalid AI cache configuration.")


def load_ai_cache_settings():
    # Gateway/environment loader runs first in composition.
    try:
        enabled = os.environ.get("VALYQON_AI_CACHE_ENABLED", "false").lower().strip()
        if enabled not in {"true", "false", "1", "0"}:
            raise ValueError
        return AICacheSettings(enabled=enabled in {"true", "1"}, **{
            field: float(os.environ.get(env, default)) for field, env, default in (
                ("ttl_seconds", "VALYQON_AI_CACHE_TTL_SECONDS", "3600"),
                ("lock_ttl_seconds", "VALYQON_AI_CACHE_LOCK_TTL_SECONDS", "60"),
                ("wait_seconds", "VALYQON_AI_CACHE_WAIT_SECONDS", "65"),
                ("poll_seconds", "VALYQON_AI_CACHE_POLL_SECONDS", ".05"))})
    except (ValueError, TypeError, OverflowError):
        raise LLMConfigurationError("Invalid AI cache configuration.") from None


def safe_identity(identity):
    # Explicit narrow contract prevents accidental credential-bearing metadata.
    return (type(identity) is dict and set(identity) == {"model", "adapter"}
            and all(type(v) is str and 0 < len(v) <= 256 for v in identity.values()))


def fingerprint(operation, provider, identity, prompt, max_tokens):
    if type(operation) is not Operation or not safe_identity(identity):
        raise LLMConfigurationError("Invalid AI cache identity.")
    source = {"schema": "valyqon-ai-request-v1", "operation": operation.namespace,
              "operation_version": operation.version, "provider": provider,
              "identity": identity, "prompt": prompt, "generation": {"max_tokens": max_tokens}}
    return hashlib.sha256(json.dumps(source, sort_keys=True, separators=(",", ":"),
                                    ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()


class CachedAI:
    DOMAIN = "ai-result"
    MAX_VALUE_BYTES = 524288
    FIELDS = {"schema", "text", "provider", "model", "input_tokens", "output_tokens", "finish_reason"}

    def __init__(self, gateway, cache, settings=None, *, required=False):
        self.gateway, self.cache = gateway, cache
        self.settings = settings or AICacheSettings()
        self.required = required
        # Includes gateway semaphore wait and all retries, plus cleanup/network margin.
        self.lock_ttl = max(self.settings.lock_ttl_seconds,
                            gateway.maximum_generation_seconds + 10)

    async def generate(self, prompt, *, max_tokens=512, operation=None, bypass=False):
        try:
            identity = self.gateway.cache_identity()
        except Exception:
            identity = None
        if not self.settings.enabled or bypass or operation is None or not safe_identity(identity):
            return await self.gateway.generate(prompt, max_tokens=max_tokens)
        # Validate before fingerprinting/cache access just as gateway would.
        if (type(prompt) is not str or not prompt.strip() or len(prompt) > AIGateway.MAX_PROMPT_CHARS
                or type(max_tokens) is not int or not 1 <= max_tokens <= 4096):
            return await self.gateway.generate(prompt, max_tokens=max_tokens)
        try:
            digest = fingerprint(operation, self.gateway.settings.provider, identity, prompt, max_tokens)
        except UnicodeError:
            return await self.gateway.generate(prompt, max_tokens=max_tokens)
        try:
            return await self._singleflight(digest, prompt, max_tokens)
        except CacheUnavailable:
            if self.required:
                raise
            return await self.gateway.generate(prompt, max_tokens=max_tokens)

    async def _call(self, method, *args, **kwargs):
        return await asyncio.to_thread(getattr(self.cache, method), *args, **kwargs)

    async def _read(self, digest):
        try:
            value = await self._call("get", self.DOMAIN, digest)
            if value is None:
                return None
            if (type(value) is not dict or set(value) != self.FIELDS or value["schema"] != 1
                    or type(value["schema"]) is not int
                    or type(value["provider"]) is not str
                    or value["provider"] not in self.gateway.result_providers
                    or len(value["provider"]) > 32
                    or any(v is not None and (type(v) is not int or not 0 <= v <= 1000000000)
                           for v in (value["input_tokens"], value["output_tokens"]))
                    or len(encode(value)) > self.MAX_VALUE_BYTES):
                raise CacheValueError("Invalid AI cache value.")
            response = LLMResponse(**{k: v for k, v in value.items() if k != "schema"}, attempts=0)
            if not AIGateway._valid_response(response):
                raise CacheValueError("Invalid AI cache value.")
            return response
        except CacheValueError:
            await self._call("delete", self.DOMAIN, digest)
            return None

    async def _singleflight(self, digest, prompt, max_tokens):
        deadline = asyncio.get_running_loop().time() + self.settings.wait_seconds
        while True:
            result = await self._read(digest)
            if result is not None:
                return result
            # Shield acquisition: if cancellation arrives while the thread acquires,
            # recover its token and release it before propagating cancellation.
            task = asyncio.create_task(self._call("acquire_lock", self.DOMAIN, digest,
                                                 ttl=self.lock_ttl, timeout=0))
            try:
                lease = await asyncio.shield(task)
            except asyncio.CancelledError:
                try:
                    lease = await task
                except (LockAcquisitionError, CacheUnavailable):
                    pass
                else:
                    try:
                        await asyncio.shield(self._call("release_lock", lease))
                    except CacheUnavailable:
                        pass
                raise
            except LockAcquisitionError:
                remaining = deadline - asyncio.get_running_loop().time()
                if remaining <= 0:
                    raise LLMTimeoutError("AI duplicate wait timed out.") from None
                await asyncio.sleep(min(self.settings.poll_seconds, remaining))
                continue
            try:
                result = await self._read(digest)  # Mandatory second check under lease.
                if result is not None:
                    return result
                result = await self.gateway.generate(prompt, max_tokens=max_tokens)
                value = {"schema": 1, **{k: getattr(result, k) for k in self.FIELDS if k != "schema"}}
                try:
                    if (all(v is None or v <= 1000000000 for v in (result.input_tokens, result.output_tokens))
                            and len(encode(value)) <= self.MAX_VALUE_BYTES):
                        try:
                            write = asyncio.create_task(self._call("set", self.DOMAIN, digest, value,
                                                                   ttl=self.settings.ttl_seconds))
                            try:
                                await asyncio.shield(write)
                            except asyncio.CancelledError:
                                try:
                                    await write
                                    await asyncio.shield(self._call("delete", self.DOMAIN, digest))
                                except CacheUnavailable:
                                    pass
                                raise
                        except CacheUnavailable:
                            if self.required:
                                raise
                            # Execution already succeeded; never repeat it for a write outage.
                except CacheValueError:
                    pass  # Valid gateway response may be unencodable/too large for cache.
                return result
            finally:
                failed = sys.exc_info()[0] is not None
                try:
                    await asyncio.shield(self._call("release_lock", lease))
                except CacheUnavailable:
                    # Preserve primary provider errors/cancellation; otherwise required fails closed.
                    if self.required and not failed:
                        raise

    async def invalidate(self, digest):
        if type(digest) is not str or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise CacheValueError("Invalid AI fingerprint.")
        try:
            return await self._call("delete", self.DOMAIN, digest)
        except CacheUnavailable:
            if self.required:
                raise
            return False


async def generate_operation(provider, operation, prompt, *, max_tokens):
    """Preserve injected legacy provider contracts without adding kwargs to fakes."""
    if isinstance(provider, CachedAI):
        return await provider.generate(prompt, max_tokens=max_tokens, operation=operation)
    return await provider.generate(prompt, max_tokens=max_tokens)


def compose_cached_ai(gateway, cache):
    from app.cache.config import load_cache_settings
    return CachedAI(gateway, cache, load_ai_cache_settings(), required=load_cache_settings().required)
