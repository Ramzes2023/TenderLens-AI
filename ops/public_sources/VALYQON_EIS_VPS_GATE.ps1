#Requires -Version 5.1
<# VALYQON EIS official upstream checks; no deployment/SQL/Caddy changes. #>
[CmdletBinding()]
param(
  [string]$Target='ubuntu@63.189.75.15',
  [string]$KeyPath=(Join-Path $HOME '.ssh\tenderlens_vps_ed25519')
)
$ErrorActionPreference='Stop'
if ($Target -notmatch '^[a-z_][a-z0-9_-]*@[A-Za-z0-9.-]+$') { throw 'Invalid SSH target' }
if (-not (Test-Path -LiteralPath $KeyPath -PathType Leaf)) { throw 'Known SSH identity missing' }
if (-not (Get-Command ssh -ErrorAction SilentlyContinue)) { throw 'OpenSSH missing' }
$script = @'
set -euo pipefail
test "$(id -u)" != 0 || { echo "EIS_STATUS=BLOCKED_ROOT"; exit 2; }
docker info >/dev/null 2>&1 || { echo "EIS_STATUS=BLOCKED_DOCKER"; exit 2; }
worker=$(docker ps --filter "label=com.docker.compose.project=valyqon-public-sources" --filter "label=com.docker.compose.service=worker" --format '{{.ID}}')
test "$(printf "%s\n" "$worker" | sed '/^$/d' | wc -l)" -eq 1 || { echo "EIS_STATUS=BLOCKED_NO_ISOLATED_WORKER"; exit 2; }
docker exec -i "$worker" python - <<'PY'
import asyncio, os
from pathlib import Path
if (os.getenv("VALYQON_ISOLATED_PUBLIC_SOURCES_ENABLED")!="true" or
    os.getenv("DATABASE_URL")!="sqlite:////app/data/isolated-public-sources.sqlite3" or
    os.getenv("TELEGRAM_BOT_TOKEN","")!="" or os.getenv("MONITORING_ENABLED")!="false"):
    print("EIS_STATUS=BLOCKED_WRONG_CONTAINER"); raise SystemExit(2)
from app.sources.eis_rss import EisRssSource, build_eis_rss_url
from app.sources.eis_223_rss import Eis223RssSource, build_eis_223_rss_url
ca=Path("/app/certs/russian_trusted_root_ca_pem.crt")
if not ca.is_file():
    print("EIS_STATUS=BLOCKED_CA"); raise SystemExit(2)
async def probe():
    works=True
    for label, src in (
        ("44", EisRssSource((build_eis_rss_url("поставка"),),timeout=15,direct=True,ca_bundle_file=ca)),
        ("223", Eis223RssSource((build_eis_223_rss_url("поставка"),),timeout=15,direct=True,ca_bundle_file=ca)),
    ):
        try:
            rows=await asyncio.wait_for(src.fetch(limit=8),timeout=26)
            print(f"EIS_{label}_RETRIEVED={len(rows)}")
            works &= len(rows)>0
        except Exception as e:
            print(f"EIS_{label}_ERROR_CLASS={type(e).__name__[:50]}")
            works=False
    print("EIS_UPSTREAM="+("CANDIDATE_ONLY" if works else "BLOCKED"))
    print("WORKER_SQL_AND_PUBLIC_HTTPS=NOT_VERIFIED")
    print("PRODUCTION_CHANGED=NO")
    return 0 if works else 2
raise SystemExit(asyncio.run(probe()))
PY
'@
$script | & ssh -i $KeyPath -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=12 $Target 'bash -s'
if ($LASTEXITCODE -ne 0) { throw "EIS_STATUS=BLOCKED_EXIT_$LASTEXITCODE" }
Write-Host "EIS_VPS_NETWORK_GATE=CHECKED_CANDIDATE_ONLY"
