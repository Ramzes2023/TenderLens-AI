"""Runtime-owned synchronous TTL boundary; async callers use asyncio.to_thread."""
from dataclasses import dataclass, field
from hashlib import sha256
import json
import math
import secrets
import threading
import time
from .config import segment


class CacheError(RuntimeError):
    pass


class CacheUnavailable(CacheError):
    pass


class CacheValueError(CacheError):
    pass


class LockAcquisitionError(CacheError):
    pass


def ttl_ms(ttl):
    if isinstance(ttl, bool) or not isinstance(ttl, (int, float)) or not .001 <= ttl <= 604800:
        raise CacheValueError("Cache TTL must be between 1 millisecond and 7 days.")
    return math.ceil(ttl * 1000)


def encode(value):
    try:
        if isinstance(value, str):
            return b"t:" + value.encode("utf-8")

        def validate(v):
            if v is None or type(v) in (str, bool, int):
                return
            if type(v) is float and math.isfinite(v):
                return
            if type(v) is list:
                for item in v:
                    validate(item)
                return
            if type(v) is dict and all(type(k) is str for k in v):
                for item in v.values():
                    validate(item)
                return
            raise ValueError

        validate(value)
        return b"j:" + json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (ValueError, TypeError, UnicodeError, RecursionError, OverflowError):
        raise CacheValueError("Unsupported cache value.") from None


def decode(raw):
    if raw is None:
        return None
    try:
        if raw[:2] == b"t:":
            return raw[2:].decode("utf-8")
        if raw[:2] == b"j:":
            value = json.loads(raw[2:].decode("utf-8"))
            encode(value)
            return value
        raise ValueError
    except (ValueError, TypeError, UnicodeError, RecursionError, CacheValueError):
        raise CacheValueError("Invalid cache encoding.") from None


class MemoryBackend:
    """Bounded store; capacity fails explicitly and never evicts live locks."""
    def __init__(self, *, clock=time.monotonic, max_entries=10000):
        if type(max_entries) is not int or max_entries < 1:
            raise CacheValueError("Invalid memory capacity.")
        self.clock, self.max_entries = clock, max_entries
        self._values = {}
        self._mutex = threading.RLock()
        self._closed = False

    def _clean(self):
        if self._closed:
            raise CacheUnavailable("Cache is closed.")
        now = self.clock()
        for key in list(self._values):
            if self._values[key][1] <= now:
                del self._values[key]

    def get(self, key):
        with self._mutex:
            self._clean()
            item = self._values.get(key)
            return item[0] if item else None

    def set(self, key, value, milliseconds, nx=False):
        with self._mutex:
            self._clean()
            if nx and key in self._values:
                return False
            if key not in self._values and len(self._values) >= self.max_entries:
                raise CacheUnavailable("Local cache capacity reached.")
            self._values[key] = (value, self.clock() + milliseconds / 1000)
            return True

    def delete(self, key):
        with self._mutex:
            self._clean()
            return self._values.pop(key, None) is not None

    def compare_delete(self, key, token):
        with self._mutex:
            self._clean()
            if self.get(key) != token:
                return False
            return self.delete(key)

    def status(self):
        return "unavailable" if self._closed else "memory"

    def close(self):
        with self._mutex:
            self._closed = True
            self._values.clear()


RELEASE_SCRIPT = "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) else return 0 end"


class RedisBackend:
    def __init__(self, settings, *, client_factory=None, pool_factory=None):
        self._pool = self._client = None
        self._closed = False
        try:
            if client_factory is None or pool_factory is None:
                from redis import Redis, ConnectionPool
                client_factory, pool_factory = Redis, ConnectionPool.from_url
            self._pool = pool_factory(settings.url, max_connections=settings.pool_max,
                socket_connect_timeout=settings.connect_timeout, socket_timeout=settings.socket_timeout,
                decode_responses=False)
            self._client = client_factory(connection_pool=self._pool)
            if not self._call("ping"):
                raise CacheUnavailable("Redis unavailable.")
        except Exception:
            self.close()
            raise CacheUnavailable("Redis startup unavailable.") from None

    def _call(self, method, *args, **kwargs):
        if self._closed:
            raise CacheUnavailable("Cache is closed.")
        try:
            return getattr(self._client, method)(*args, **kwargs)
        except Exception:
            raise CacheUnavailable("Redis unavailable.") from None

    def get(self, key):
        return self._call("get", key)

    def set(self, key, value, milliseconds, nx=False):
        return bool(self._call("set", key, value, px=milliseconds, nx=nx))

    def delete(self, key):
        return bool(self._call("delete", key))

    def compare_delete(self, key, token):
        return bool(self._call("eval", RELEASE_SCRIPT, 1, key, token))

    def status(self):
        try:
            return "ready" if self._call("ping") else "unavailable"
        except CacheUnavailable:
            return "unavailable"

    def close(self):
        if self._closed:
            return
        self._closed = True
        for resource, method in ((self._client, "close"), (self._pool, "disconnect")):
            if resource is not None:
                try:
                    getattr(resource, method)()
                except Exception:
                    pass


class UnavailableBackend:
    def status(self):
        return "unavailable"

    def close(self):
        pass

    def __getattr__(self, name):
        def fail(*args, **kwargs):
            raise CacheUnavailable("Configured cache unavailable.")
        return fail


@dataclass(frozen=True)
class LockLease:
    _key: str = field(repr=False)
    _token: bytes = field(repr=False)
    _owner: object = field(repr=False)


class Cache:
    def __init__(self, backend, namespace="local"):
        self.backend, self.namespace = backend, segment(namespace)

    def key(self, domain, identifier, *, lock=False):
        segment(domain)
        if not isinstance(identifier, str) or not identifier or len(identifier) > 4096:
            raise CacheValueError("Invalid cache identifier.")
        try:
            digest = sha256(identifier.encode("utf-8")).hexdigest()
        except UnicodeError:
            raise CacheValueError("Invalid cache identifier.") from None
        return f"valyqon:{self.namespace}:{'lock' if lock else 'cache'}:{domain}:{digest}"

    def get(self, domain, identifier):
        return decode(self.backend.get(self.key(domain, identifier)))

    def set(self, domain, identifier, value, *, ttl):
        return self.backend.set(self.key(domain, identifier), encode(value), ttl_ms(ttl))

    def set_if_absent(self, domain, identifier, value, *, ttl):
        return self.backend.set(self.key(domain, identifier), encode(value), ttl_ms(ttl), nx=True)

    def delete(self, domain, identifier):
        return self.backend.delete(self.key(domain, identifier))

    def exists(self, domain, identifier):
        return self.backend.get(self.key(domain, identifier)) is not None

    def acquire_lock(self, domain, identifier, *, ttl, timeout=0):
        milliseconds = ttl_ms(ttl)
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 0 <= timeout <= 120:
            raise CacheValueError("Invalid lock acquisition timeout.")
        key, token = self.key(domain, identifier, lock=True), secrets.token_bytes(32)
        deadline = time.monotonic() + timeout
        while True:
            if self.backend.set(key, token, milliseconds, nx=True):
                return LockLease(key, token, self)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise LockAcquisitionError("Cache lock acquisition timed out.")
            time.sleep(min(.01, remaining))

    def release_lock(self, lease):
        if not isinstance(lease, LockLease) or lease._owner is not self:
            raise CacheValueError("Invalid cache lock lease.")
        return self.backend.compare_delete(lease._key, lease._token)

    def status(self):
        return self.backend.status()

    def close(self):
        self.backend.close()


def build_cache(settings=None):
    if settings is None:
        from .config import load_cache_settings
        settings = load_cache_settings()
    if not settings.url:
        return Cache(MemoryBackend(), settings.namespace)
    try:
        backend = RedisBackend(settings)
    except CacheUnavailable:
        if settings.required:
            raise
        backend = UnavailableBackend()
    return Cache(backend, settings.namespace)
