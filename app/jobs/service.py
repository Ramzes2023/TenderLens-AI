"""Business-facing infrastructure boundary. Callers must still authorize stored scope."""
from .models import job_type_name
from inspect import iscoroutinefunction


class HandlerRegistry:
    def __init__(self):
        self._handlers = {}
        self._frozen = False

    def register(self, job_type, handler):
        job_type_name(job_type)
        if self._frozen or job_type in self._handlers or not callable(handler) or iscoroutinefunction(handler):
            raise ValueError('Invalid or duplicate job handler registration.')
        self._handlers[job_type] = handler

    def freeze(self):
        self._frozen = True

    def resolve(self, job_type):
        return self._handlers.get(job_type)

    def __len__(self):
        return len(self._handlers)


class JobService:
    def __init__(self, repository):
        self.repository = repository

    def enqueue(self, job_type, payload, *, scope, **policy):
        return self.repository.enqueue(job_type, payload, scope=scope, **policy)

    def get(self, job_id, *, scope):
        return self.repository.get(job_id, scope=scope)

    def cancel(self, job_id, *, scope):
        return self.repository.cancel(job_id, scope=scope)
