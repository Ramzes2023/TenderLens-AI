"""Live strictly independent official South Ural procurement deadline proof."""
import asyncio
from datetime import datetime
from app.sources.south_ural_public import SouthUralPublicSource


def main():
    try:
        notices=asyncio.run(SouthUralPublicSource().fetch(limit=2))
        if len(notices)!=2 or any(n.deadline is None for n in notices):
            raise AssertionError("Two live separately verified source deadlines required")
        for n in notices:
            dt=datetime.fromisoformat(n.deadline)
            if (dt.tzinfo is None or dt.utcoffset() is None or
                    dt.isoformat(timespec="seconds") != n.deadline):
                raise AssertionError("Cannot prove verified timezone-aware deadline")
        print("RU_SOUTH_URAL_VERIFIED_DEADLINES=2")
        print("RU_SOUTH_URAL_DEADLINE_LIVE=PASS")
        print("PRODUCTION_CHANGED=NO")
        return 0
    except Exception as e:
        print("RU_SOUTH_URAL_DEADLINE_LIVE=BLOCKED_"+type(e).__name__)
        print("PRODUCTION_CHANGED=NO")
        return 2

if __name__=="__main__":
    raise SystemExit(main())
