"""Ordered availability policy over two independently bounded gateways."""
import hashlib
import json

from .base import LLMConfigurationError, LLMNetworkError, LLMProviderUnavailable
from .gateway import AIGateway


def fallback_eligible(error):
    # Includes timeout (network subclass) and rate limit (unavailable subclass).
    return isinstance(error, (LLMNetworkError, LLMProviderUnavailable))


class FailoverGateway:
    def __init__(self, primary, fallback):
        # Concrete gateways only: prohibit nested failover routes/cycles.
        if (type(primary) is not AIGateway or type(fallback) is not AIGateway
                or primary.settings.provider != "gigachat" or fallback.settings.provider != "groq"):
            raise LLMConfigurationError("Invalid AI failover route.")
        self.primary, self.fallback = primary, fallback
        self.settings = primary.settings

    @property
    def maximum_generation_seconds(self):
        return self.primary.maximum_generation_seconds + self.fallback.maximum_generation_seconds

    @property
    def result_providers(self):
        return frozenset(("gigachat", "groq"))

    def cache_identity(self):
        from .cache import safe_identity
        identities = [self.primary.cache_identity(), self.fallback.cache_identity()]
        if not all(safe_identity(identity) for identity in identities):
            return None
        source = {"revision": "valyqon-failover-v1", "route": [
            {"provider": gateway.settings.provider, "identity": identity}
            for gateway, identity in zip((self.primary, self.fallback), identities)]}
        digest = hashlib.sha256(json.dumps(source, sort_keys=True, separators=(",", ":"),
                                           ensure_ascii=False).encode("utf-8")).hexdigest()
        return {"model": digest, "adapter": "valyqon-failover-v1"}

    async def generate(self, prompt, *, max_tokens=512):
        try:
            return await self.primary.generate(prompt, max_tokens=max_tokens)
        except Exception as error:
            if not fallback_eligible(error):
                raise
        # Outside primary handler: final fallback category wins, without chaining.
        return await self.fallback.generate(prompt, max_tokens=max_tokens)
