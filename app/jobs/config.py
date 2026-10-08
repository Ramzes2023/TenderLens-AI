"""Bounded queue settings; explicit environment overrides dotenv."""
import math
import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv


@dataclass(frozen=True)
class JobSettings:
    worker_count: int = 2
    poll_seconds: float = 0.5
    lease_seconds: float = 60.0
    heartbeat_seconds: float = 10.0
    default_max_attempts: int = 3
    max_payload_bytes: int = 262144
    max_result_bytes: int = 262144
    shutdown_seconds: float = 30.0

    def __post_init__(self):
        try:
            for name, low, high in (("worker_count", 1, 32), ("default_max_attempts", 1, 20),
                                    ("max_payload_bytes", 1, 1048576), ("max_result_bytes", 1, 1048576)):
                value = getattr(self, name)
                if type(value) is not int or not low <= value <= high:
                    raise ValueError
            for name, low, high in (("poll_seconds", .01, 30), ("lease_seconds", .3, 3600),
                                    ("heartbeat_seconds", .05, 300), ("shutdown_seconds", 0, 300)):
                value = getattr(self, name)
                if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
                    raise ValueError
            if self.heartbeat_seconds > self.lease_seconds / 3:
                raise ValueError
        except (ValueError, TypeError, OverflowError):
            raise ValueError("Invalid job configuration.") from None


def load_job_settings(env_file=Path(__file__).resolve().parents[2] / '.env'):
    load_dotenv(env_file, override=False, encoding='utf-8-sig')
    names = {
        'worker_count': 'VALYQON_WORKER_COUNT', 'poll_seconds': 'VALYQON_JOB_POLL_SECONDS',
        'lease_seconds': 'VALYQON_JOB_LEASE_SECONDS', 'heartbeat_seconds': 'VALYQON_JOB_HEARTBEAT_SECONDS',
        'default_max_attempts': 'VALYQON_JOB_DEFAULT_MAX_ATTEMPTS',
        'max_payload_bytes': 'VALYQON_JOB_MAX_PAYLOAD_BYTES', 'max_result_bytes': 'VALYQON_JOB_MAX_RESULT_BYTES',
        'shutdown_seconds': 'VALYQON_WORKER_SHUTDOWN_SECONDS',
    }
    defaults = JobSettings()
    try:
        return JobSettings(**{name: type(getattr(defaults, name))(os.environ.get(env, getattr(defaults, name)))
                              for name, env in names.items()})
    except (ValueError, TypeError, OverflowError):
        raise ValueError('Invalid job configuration.') from None
