"""Offline-only bounded durable retry contract. Live source acceptance stays mandatory."""
from types import SimpleNamespace
from scripts.asia_jetro_bid_worker_acceptance import run_real_queued_job

class Queue:
    def __init__(self, states):
        self.states, self.pos = states, -1
    def run_once(self):
        self.pos += 1
        return self.pos < len(self.states)

class Repo:
    def __init__(self, queue):
        self.queue=queue
    def get(self, job_id, *, scope):
        if self.queue.pos < 0 or self.queue.pos >= len(self.queue.states):
            return None
        return self.queue.states[self.queue.pos]

def state(kind, attempt, ready=0, mx=3):
    return SimpleNamespace(state=kind, attempt_count=attempt,
        max_attempts=mx, available_at=ready,
        failure_code="handler_error" if kind=="queued" else None)

def test_bounded_queued_retries_require_real_terminal_success():
    q=Queue([state("queued",1,1_000_000),
             state("queued",2,2_000_000),state("succeeded",3)])
    sleeps=[]
    final,policy=run_real_queued_job(q,Repo(q),"some-id",clock=lambda:0,sleeper=sleeps.append)
    assert final.state=="succeeded" and policy=="FINISHED"
    assert len(sleeps)==2 and all(0<seconds<5 for seconds in sleeps)

def test_terminated_failure_is_never_green():
    q=Queue([state("failed",1)])
    final,policy=run_real_queued_job(q,Repo(q),"some-id",clock=lambda:0,sleeper=lambda _:None)
    assert final.state=="failed" and policy=="FINISHED" and q.pos==0

def test_scheduled_retry_must_not_skip_long_wait_or_exhaustion():
    q=Queue([state("queued",1,20_000_000)])
    final,policy=run_real_queued_job(q,Repo(q),"some-id",clock=lambda:0,sleeper=lambda _:None)
    assert final.state=="queued" and policy=="RETRY_DELAY_OUT_OF_BOUNDS"
    q=Queue([state("queued",3,0)])
    final,policy=run_real_queued_job(q,Repo(q),"some-id",clock=lambda:0,sleeper=lambda _:None)
    assert final.state=="queued" and policy=="RETRIES_EXHAUSTED"

def test_empty_claim_fails():
    q=Queue([])
    final,policy=run_real_queued_job(q,Repo(q),"some-id",clock=lambda:0,sleeper=lambda _:None)
    assert final is None and policy=="NO_RUNNABLE_JOB"
