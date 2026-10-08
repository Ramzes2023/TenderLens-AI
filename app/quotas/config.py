"""Operator-owned, strict fair usage configuration."""
import json
import os
import re
from dataclasses import dataclass, field
from types import MappingProxyType


@dataclass(frozen=True)
class Limits:
    daily: int = 100
    monthly: int = 1000
    outstanding: int = 10

    def __post_init__(self):
        if any(type(v) is not int or not 0 <= v <= 1000000000
               for v in (self.daily, self.monthly, self.outstanding)):
            raise ValueError('Invalid quota configuration.')


@dataclass(frozen=True)
class QuotaSettings:
    enabled: bool = False
    limits: Limits = field(default_factory=Limits)
    overrides: dict = field(default_factory=dict)

    def __post_init__(self):
        if type(self.enabled) is not bool or not isinstance(self.limits, Limits):
            raise ValueError('Invalid quota configuration.')
        if not isinstance(self.overrides, dict) or len(self.overrides) > 1000:
            raise ValueError('Invalid quota configuration.')
        for key, value in self.overrides.items():
            if (type(key) is not str or not re.fullmatch(r'(account|organization):[1-9][0-9]{0,18}', key)
                    or int(key.split(':')[1]) >= 2**63 or not isinstance(value, Limits)):
                raise ValueError('Invalid quota configuration.')
        object.__setattr__(self, 'overrides', MappingProxyType(dict(self.overrides)))


def load_quota_settings():
    try:
        enabled = os.environ.get('VALYQON_QUOTAS_ENABLED', 'false').strip().lower()
        if enabled not in {'true', 'false'}:
            raise ValueError
        raw = os.environ.get('VALYQON_QUOTA_TENANT_OVERRIDES', '{}')
        if len(raw) > 131072:
            raise ValueError
        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError
                result[key] = value
            return result
        overrides = json.loads(raw, object_pairs_hook=unique)
        if type(overrides) is not dict:
            raise ValueError
        return QuotaSettings(enabled == 'true', Limits(**{
            name: int(os.environ.get('VALYQON_QUOTA_' + name.upper(), default))
            for name, default in (('daily', 100), ('monthly', 1000), ('outstanding', 10))}),
            {key: Limits(**value) for key, value in overrides.items()})
    except (ValueError, TypeError, OverflowError):
        raise ValueError('Invalid quota configuration.') from None
