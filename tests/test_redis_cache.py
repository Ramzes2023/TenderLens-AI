"""Offline Redis command contracts and deterministic local infrastructure tests."""
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock, patch
import threading
import pytest

from app.cache import Cache, CacheSettings, CacheConfigurationError, CacheUnavailable, CacheValueError, LockAcquisitionError, build_cache
from app.cache.config import load_cache_settings
from app.cache.backend import MemoryBackend, RedisBackend, RELEASE_SCRIPT, encode, decode


@pytest.mark.parametrize("kwargs", [
    {"url": "http://secret:password@host"}, {"url": "redis://secret:password@host:bad"},
    {"url": "redis://host/0?max_connections=999"}, {"url": "redis://host/#secret"},
    {"required": True}, {"required": "true"}, {"pool_max": 0}, {"pool_max": 101},
    {"pool_max": True}, {"connect_timeout": 0}, {"socket_timeout": float("nan")},
    {"namespace": "prod:*"}, {"url": "redis://host/-1"}, {"url": "redis://"},
])
def test_invalid_configuration_is_safe(kwargs):
    with pytest.raises(CacheConfigurationError) as error:
        CacheSettings(**kwargs)
    assert str(error.value) == "Invalid cache configuration."


@pytest.mark.parametrize("scheme", ["redis", "rediss"])
def test_configuration_redaction(scheme):
    settings = CacheSettings(url=f"{scheme}://secret:password@host:6379/1")
    assert all(part not in repr(settings) for part in ("secret", "password", "host", scheme + "://"))


def test_env_overrides_dotenv(monkeypatch, tmp_path):
    for key in ("VALYQON_REDIS_URL", "VALYQON_REDIS_REQUIRED", "VALYQON_REDIS_POOL_MAX",
                "VALYQON_REDIS_CONNECT_TIMEOUT", "VALYQON_REDIS_SOCKET_TIMEOUT", "VALYQON_CACHE_NAMESPACE"):
        monkeypatch.delenv(key, raising=False)
    env = tmp_path / ".env"
    env.write_text("VALYQON_REDIS_POOL_MAX=3\nVALYQON_CACHE_NAMESPACE=fixture\n")
    monkeypatch.setenv("VALYQON_REDIS_POOL_MAX", "7")
    assert load_cache_settings(env).pool_max == 7
    assert load_cache_settings(env).namespace == "fixture"
    monkeypatch.setenv("VALYQON_REDIS_REQUIRED", "secret")
    with pytest.raises(CacheConfigurationError, match="Invalid cache configuration"):
        load_cache_settings(env)


def local():
    now = [0.0]
    return Cache(MemoryBackend(clock=lambda: now[0]), "fixture"), now


def test_safe_keys_and_environment_and_lock_separation():
    cache, _ = local()
    key = cache.key("example", "secret@email.test:*\n")
    assert key.startswith("valyqon:fixture:cache:example:")
    assert "secret" not in key and "*" not in key
    assert key != Cache(MemoryBackend(), "other").key("example", "secret@email.test:*\n")
    assert key != cache.key("example", "secret@email.test:*\n", lock=True)
    with pytest.raises(CacheConfigurationError):
        cache.key("bad:*", "identifier")
    with pytest.raises(CacheValueError):
        cache.key("example", "")


@pytest.mark.parametrize("value", ["Unicode café", {"b": [1, True, None], "a": 1.25}, [], None, 42])
def test_serialization_and_invalidation(value):
    cache, _ = local()
    cache.set("example", "one", value, ttl=1)
    assert cache.get("example", "one") == value
    assert cache.exists("example", "one")
    assert cache.delete("example", "one")
    assert not cache.delete("example", "one")
    assert not cache.exists("example", "one")


@pytest.mark.parametrize("value", [object(), b"bytes", (1, 2), {1: "one"}, float("nan"), float("inf")])
def test_unsupported_values(value):
    with pytest.raises(CacheValueError):
        encode(value)


@pytest.mark.parametrize("raw", [b"pickle", b"t:\xff", b"j:{broken", b"j:NaN"])
def test_corrupt_serialization(raw):
    with pytest.raises(CacheValueError, match="Invalid cache encoding"):
        decode(raw)


def test_deterministic_json():
    assert encode({"b": 2, "a": 1}) == encode({"a": 1, "b": 2}) == b'j:{"a":1,"b":2}'


@pytest.mark.parametrize("ttl", [-1, 0, True, "1", float("nan"), float("inf"), 604801, .0001, 10**1000])
def test_invalid_ttl(ttl):
    cache, _ = local()
    with pytest.raises(CacheValueError):
        cache.set("example", "one", "value", ttl=ttl)
    assert not cache.exists("example", "one")


def test_expiry_reacquisition_and_capacity_cleanup():
    now = [0.0]
    cache = Cache(MemoryBackend(clock=lambda: now[0], max_entries=1))
    assert cache.set_if_absent("example", "one", "value", ttl=1)
    assert not cache.set_if_absent("example", "one", "other", ttl=1)
    with pytest.raises(CacheUnavailable):
        cache.set("example", "two", 1, ttl=1)
    now[0] = 1
    assert cache.get("example", "one") is None
    assert cache.set_if_absent("example", "one", "new", ttl=1)
    now[0] = 2
    assert cache.set("example", "two", 1, ttl=1)
    assert len(cache.backend._values) == 1


def test_concurrent_set_if_absent_one_winner():
    cache, _ = local()
    barrier = threading.Barrier(8)
    def compete(i):
        barrier.wait(timeout=5)
        return cache.set_if_absent("example", "shared", i, ttl=1)
    with ThreadPoolExecutor(max_workers=8) as executor:
        assert sum(executor.map(compete, range(8))) == 1


def test_thread_safe_concurrent_accesses():
    cache, _ = local()
    def use(i):
        for _ in range(20):
            cache.set("example", str(i), {"i": i}, ttl=1)
            assert cache.get("example", str(i)) == {"i": i}
            assert cache.exists("example", str(i))
            assert cache.delete("example", str(i))
    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(use, range(8)))


def test_lock_contention_and_stale_owner():
    cache, now = local()
    old = cache.acquire_lock("example", "shared", ttl=1)
    assert "token" not in repr(old) and old._token not in repr(old).encode()
    with pytest.raises(LockAcquisitionError):
        cache.acquire_lock("example", "shared", ttl=1)
    now[0] = 1
    new = cache.acquire_lock("example", "shared", ttl=1)
    assert old._token != new._token
    assert not cache.release_lock(old)
    assert cache.release_lock(new)
    assert not cache.release_lock(new)
    cache.acquire_lock("example", "shared", ttl=1)


def test_concurrent_lock_one_owner():
    cache, _ = local()
    barrier = threading.Barrier(8)
    def compete(_):
        barrier.wait(timeout=5)
        try:
            return cache.acquire_lock("example", "shared", ttl=1)
        except LockAcquisitionError:
            return None
    with ThreadPoolExecutor(max_workers=8) as executor:
        leases = list(executor.map(compete, range(8)))
    assert sum(lease is not None for lease in leases) == 1


def test_lock_timeout_is_bounded():
    cache, _ = local()
    cache.acquire_lock("example", "shared", ttl=1)
    with pytest.raises(LockAcquisitionError):
        cache.acquire_lock("example", "shared", ttl=1, timeout=.02)
    with pytest.raises(CacheValueError):
        cache.acquire_lock("example", "shared", ttl=1, timeout=-1)
    other, _ = local()
    with pytest.raises(CacheValueError):
        other.release_lock(cache.acquire_lock("example", "other", ttl=1))


def redis_fixture():
    memory = MemoryBackend()
    client, pool = MagicMock(), MagicMock()
    client.ping.return_value = True
    client.get.side_effect = memory.get
    client.set.side_effect = lambda key, value, px, nx: memory.set(key, value, px, nx)
    client.delete.side_effect = memory.delete
    client.eval.side_effect = lambda script, count, key, token: memory.compare_delete(key, token)
    factory = MagicMock(return_value=pool)
    backend = RedisBackend(CacheSettings(url="rediss://synthetic:secret@fixture/1", pool_max=4,
        connect_timeout=3, socket_timeout=5), client_factory=MagicMock(return_value=client), pool_factory=factory)
    return backend, client, pool, factory


def test_redis_pool_and_commands_and_owner_compare_delete():
    backend, client, pool, factory = redis_fixture()
    assert factory.call_args.kwargs == dict(max_connections=4, socket_connect_timeout=3,
        socket_timeout=5, decode_responses=False)
    cache = Cache(backend)
    assert cache.set_if_absent("example", "one", "value", ttl=.5)
    assert client.set.call_args.kwargs == {"px": 500, "nx": True}
    assert cache.get("example", "one") == "value"
    lease = cache.acquire_lock("example", "one", ttl=1)
    assert len(lease._token) == 32
    assert cache.release_lock(lease)
    client.eval.assert_called_once_with(RELEASE_SCRIPT, 1, lease._key, lease._token)
    assert "redis.call('get'" in RELEASE_SCRIPT and "ARGV[1]" in RELEASE_SCRIPT
    assert cache.delete("example", "one")
    assert cache.status() == "ready"
    cache.close()
    cache.close()
    client.close.assert_called_once()
    pool.disconnect.assert_called_once()
    assert cache.status() == "unavailable"


def test_redis_failure_redaction_and_shutdown():
    backend, client, pool, _ = redis_fixture()
    client.get.side_effect = RuntimeError("password@secret-host")
    with pytest.raises(CacheUnavailable) as error:
        backend.get("safe")
    assert str(error.value) == "Redis unavailable."
    client.ping.side_effect = RuntimeError("secret")
    assert backend.status() == "unavailable"
    client.close.side_effect = RuntimeError("secret")
    backend.close()
    pool.disconnect.assert_called_once()


def test_failed_startup_cleans_pool():
    client, pool = MagicMock(), MagicMock()
    client.ping.side_effect = RuntimeError("secret")
    with pytest.raises(CacheUnavailable, match="Redis startup unavailable"):
        RedisBackend(CacheSettings(url="redis://fixture"), client_factory=MagicMock(return_value=client),
                     pool_factory=MagicMock(return_value=pool))
    client.close.assert_called_once()
    pool.disconnect.assert_called_once()


def test_required_optional_and_unconfigured_policy():
    with patch("app.cache.backend.RedisBackend", side_effect=CacheUnavailable("Redis startup unavailable.")):
        with pytest.raises(CacheUnavailable):
            build_cache(CacheSettings(url="redis://fixture", required=True))
        cache = build_cache(CacheSettings(url="redis://fixture"))
        assert cache.status() == "unavailable"
        with pytest.raises(CacheUnavailable):
            cache.set("example", "one", 1, ttl=1)
    assert build_cache(CacheSettings()).status() == "memory"


def test_missing_redis_dependency_is_lazy_and_safe():
    import sys
    with patch.dict(sys.modules, {"redis": None}):
        assert build_cache(CacheSettings()).status() == "memory"
        assert build_cache(CacheSettings(url="redis://fixture")).status() == "unavailable"
        with pytest.raises(CacheUnavailable, match="Redis startup unavailable"):
            build_cache(CacheSettings(url="redis://fixture", required=True))


def test_redis_stale_owner_release_uses_atomic_command():
    now = [0.0]
    memory = MemoryBackend(clock=lambda: now[0])
    backend, client, _, _ = redis_fixture()
    client.set.side_effect = lambda key, value, px, nx: memory.set(key, value, px, nx)
    client.eval.side_effect = lambda script, count, key, token: memory.compare_delete(key, token)
    cache = Cache(backend)
    old = cache.acquire_lock("example", "shared", ttl=1)
    now[0] = 1
    new = cache.acquire_lock("example", "shared", ttl=1)
    assert not cache.release_lock(old)
    assert memory.get(new._key) == new._token
    assert cache.release_lock(new)
    backend.close()


def test_runtime_ownership_and_independent_database_health():
    from app.api.runtime import ApiRuntime
    cache = MagicMock()
    cache.status.return_value = "unavailable"
    database = MagicMock()
    database.healthy.return_value = True
    runtime = ApiRuntime(cache=cache, database=database, tender_repository=object())
    assert runtime.component_status()["cache"] == "unavailable"
    assert runtime.component_status()["database"] == "ready"
    runtime.close()
    cache.close.assert_not_called()
    runtime.owns_cache = True
    runtime.close()
    cache.close.assert_called_once()
    assert ApiRuntime().component_status()["cache"] == "disabled"


def test_required_runtime_failure_closes_database(tmp_path):
    from app.api.runtime import build_runtime
    from app.database.config import DatabaseSettings
    with patch("app.database.load_database_settings", return_value=DatabaseSettings("", tmp_path / "fixture.db")), \
         patch("app.cache.build_cache", side_effect=CacheUnavailable("Redis startup unavailable.")), \
         patch("app.database.backend.Database.close") as close:
        with pytest.raises(CacheUnavailable):
            build_runtime()
    close.assert_called_once()


@pytest.mark.parametrize("status,overall", [("memory", "ok"), ("ready", "ok"), ("unavailable", "degraded")])
def test_health_and_fastapi_cache_lifecycle(status, overall):
    from fastapi.testclient import TestClient
    from app.api.main import create_app
    from app.api.config import ApiSettings
    from app.api.runtime import ApiRuntime
    cache = MagicMock()
    cache.status.return_value = status
    runtime = ApiRuntime(cache=cache, owns_cache=True, tender_repository=object(), company_profile=object())
    with patch("app.api.main.build_runtime", return_value=runtime):
        with TestClient(create_app(settings=ApiSettings("127.0.0.1", 8000, False))) as client:
            payload = client.get("/health").json()
            assert payload["status"] == overall
            assert payload["components"]["cache"] == status
        cache.close.assert_called_once()
    cache.close.reset_mock()
    with TestClient(create_app(runtime=runtime, settings=ApiSettings("127.0.0.1", 8000, False))):
        pass
    cache.close.assert_not_called()
