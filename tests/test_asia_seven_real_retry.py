"""Offline queue retry safety only; separate real source acceptance stays mandatory."""
from types import SimpleNamespace
from scripts.asia_seven_live_query_acceptance import run_bounded_jetro_claim


class Worker:
    def __init__(self, states): self.states, self.pos = states, -1
    def run_once(self):
        self.pos += 1
        return self.pos < len(self.states)


class Jobs:
    def __init__(self, worker): self.worker = worker
    def get(self, job_id, *, scope):
        pos = self.worker.pos
        return self.worker.states[pos] if 0 <= pos < len(self.worker.states) else None


def job(state, attempts, micros=0, limit=3):
    return SimpleNamespace(state=state, attempt_count=attempts, available_at=micros,
                           max_attempts=limit, failure_code="handler_error" if state=="queued" else None)


def run(states):
    worker = Worker(states)
    sleeps=[]
    final, code = run_bounded_jetro_claim(worker, Jobs(worker), "job-id",
                                         clock=lambda:0, sleeper=sleeps.append)
    return worker, final, code, sleeps


def test_actual_retry_claims_reach_real_terminal_success():
    worker, final, code, waits = run([job("queued",1,1_000_000),
                                     job("queued",2,2_000_000),job("succeeded",3)])
    assert (final.state,code,worker.pos)==("succeeded","TERMINAL",2)
    assert len(waits)==2 and all(0 < value < 5 for value in waits)


def test_unresolved_or_failed_source_never_goes_green():
    _, final, code, _ = run([job("failed",1)])
    assert (final.state,code)==("failed","TERMINAL")
    _, final, code, _ = run([job("queued",1),job("queued",2),job("queued",3)])
    assert (final.state,code)==("queued","RETRIES_EXHAUSTED")


def test_cannot_skip_authoritative_queue_delay():
    worker, final, code, waits=run([job("queued",1,10_000_000)])
    assert (final.state,code,worker.pos)==("queued","RETRY_WINDOW_TOO_LONG",0)
    assert waits==[]


def test_no_real_lease_cannot_pass():
    _, final, code, _ = run([])
    assert final is None and code=="NO_LEASE_CLAIM"
