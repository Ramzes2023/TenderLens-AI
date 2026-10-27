"""Real external MikroTon -> isolated Compose Worker/SQLite -> real guest HTTP.

No fixture result, external email, Telegram or production deployment. Fail
closed when original HTTPS, queue, database or web API is unavailable.
"""
from __future__ import annotations
import json
import subprocess
import time
from urllib.error import URLError
from urllib.request import urlopen

COMPOSE = ["docker", "compose", "-p", "valyqon-ready-sources-ci",
           "-f", "ops/ready_sources/compose.yaml"]


def docker(*args):
    r = subprocess.run([*COMPOSE, *args], capture_output=True, text=True,
                       check=True, timeout=150)
    return r.stdout.strip()


def parse(raw):
    for line in reversed(raw.splitlines()):
        line=line.strip()
        if line.startswith("{") and line.endswith("}"):
            obj=json.loads(line)
            if isinstance(obj,dict): return obj
    raise AssertionError("Expected machine-readable operator status")


def acceptance():
    docker("up", "-d", "--build", "api", "worker", "mailpit")
    for attempt in range(70):
        try:
            with urlopen("http://127.0.0.1:18965/health", timeout=3) as r:
                if r.status==200: break
        except (URLError,OSError):
            pass
        time.sleep(2)
    else:
        raise AssertionError("Isolated Docker HTTP server unavailable")

    first=parse(docker("run", "--rm", "--no-deps", "enqueue"))
    jobs=first.get("jobs") or {}
    if set(jobs)!={"mikroton_tender"}:
        raise AssertionError("Missing or unapproved source in operator batch")
    uid=jobs["mikroton_tender"].get("job_id")
    if not isinstance(uid,str) or len(uid)<16:
        raise AssertionError("Invalid queued source job ID")
    second=parse(docker("run", "--rm", "--no-deps", "enqueue"))
    if second.get("jobs",{}).get("mikroton_tender",{}).get("job_id")!=uid:
        raise AssertionError("Same-hour queue repeat duplicated work")
    current={}
    for attempt in range(85):
        current=parse(docker("exec", "-T", "api", "python", "-m",
                             "app.sources.enqueue", "--status", uid))
        if current.get("state") in ("succeeded","failed","dead"): break
        time.sleep(2)
    if current.get("state")!="succeeded":
        raise AssertionError("Real connector worker did not complete")
    receipt=current.get("result") or {}
    count=receipt.get("accepted_count")
    if not isinstance(count,int) or count<1 or receipt.get("source_id")!="mikroton_tender":
        raise AssertionError("Worker did not commit actual original notices")

    with urlopen("http://127.0.0.1:18965/api/v1/public/opportunities",timeout=12) as r:
        if r.status!=200: raise AssertionError("Public API HTTP unsuccessful")
        payload=json.load(r)
    if not isinstance(payload,dict) or not 1<=payload.get("shown",0)<=count:
        raise AssertionError("Guest API missing genuine worker records")
    serialized=json.dumps(payload,ensure_ascii=False).lower()
    if any(field in serialized for field in (
        "tender.mt52.ru/tenders/","customer_inn","external_id",
        "buyer_inn","original_url","source_id"
    )):
        raise AssertionError("Protected procurement identity leaked in guest API")
    return {"source":"mikroton_tender","real_worker_accepted":count,
            "guest_http_shown":payload["shown"],"one_hour_queue_idempotent":True,
            "docker_live_worker_api":True,"telegram_sent":False,
            "external_email_sent":False,"production_changed":False}


if __name__=="__main__":
    try:
        result=acceptance()
        print("READY_REAL_DOCKER_INTEGRATION_EVIDENCE="+json.dumps(result,sort_keys=True))
        print("READY_REAL_DOCKER_INTEGRATION=PASS")
    except Exception as exc:
        print("READY_REAL_DOCKER_INTEGRATION=BLOCKED_OR_FAILED")
        print("FAILURE_CLASS="+type(exc).__name__)
        raise SystemExit(2)
    finally:
        # This name identifies disposable GitHub CI volumes ONLY.
        try: docker("down","--volumes","--remove-orphans")
        except Exception: print("READY_REAL_DOCKER_CLEANUP=INCOMPLETE")
