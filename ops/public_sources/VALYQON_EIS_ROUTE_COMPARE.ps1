#Requires -Version 5.1
<# Fixed-origin read-only host/exact isolated Worker network comparison.
No mounts, SQL, env-file reads, service restarts, Caddy edits or notifications.
Each vantage point has a 25-second timeout including DNS. No image pull.
#>
[CmdletBinding()]
param(
    [string]$Target = 'ubuntu@63.189.75.15',
    [string]$KeyPath = (Join-Path $HOME '.ssh\tenderlens_vps_ed25519')
)
$ErrorActionPreference = 'Stop'
if ($Target -notmatch '^[a-z_][a-z0-9_-]*@[A-Za-z0-9.-]+$') { throw 'Invalid SSH target' }
if (-not (Test-Path -LiteralPath $KeyPath -PathType Leaf)) { throw 'Existing identity missing' }
$probePath = Join-Path $PSScriptRoot '..\..\scripts\eis_socket_route_probe.py'
$payload = [Convert]::ToBase64String([IO.File]::ReadAllBytes($probePath))
$remote = @'
set -euo pipefail
test "$(id -u)" != 0 || exit 2
payload='__PAYLOAD__'
command="import base64;exec(compile(base64.b64decode('$payload'),'route_probe','exec'))"
echo VANTAGE=HOST
timeout 25s python3 -c "$command"
for service in worker worker-v6; do
    ids=$(docker ps -aq --filter label=com.docker.compose.project=valyqon-public-sources --filter "label=com.docker.compose.service=$service")
    count=$(printf '%s\n' "$ids" | sed '/^$/d' | wc -l)
    test "$count" -eq 1 || { echo "CONTAINER_GATE=AMBIGUOUS_$service"; exit 2; }
    image=$(docker inspect -f '{{.Image}}' "$ids")
    docker image inspect "$image" >/dev/null
    network=''
    while IFS= read -r candidate; do
        test -n "$candidate" || continue
        info=$(docker network inspect -f '{{index .Labels "com.docker.compose.network"}}|{{.Internal}}' "$candidate")
        if [ "$info" = 'publisher_outbound|false' ]; then
            test -z "$network" || exit 2
            network="$candidate"
        fi
    done < <(docker inspect -f '{{range $name,$v := .NetworkSettings.Networks}}{{println $name}}{{end}}' "$ids")
    test -n "$network" || { echo NETWORK_GATE=NO_EXACT_EGRESS; exit 2; }
    echo "VANTAGE=$service NETWORK=$network IMAGE=$image"
    timeout 25s docker run --rm --pull never --network "$network" --read-only \
        --cap-drop ALL --security-opt no-new-privileges --pids-limit 32 \
        --memory 128m --user 10001:10001 --env PYTHONDONTWRITEBYTECODE=1 \
        --entrypoint python "$image" -c "$command"
done
echo PRODUCTION_MUTATIONS=NONE
'@
# Base64 keeps the SSH command ASCII; normalize Windows CRLF before bash.
$remote = $remote.Replace('__PAYLOAD__', $payload).Replace("`r", '')
$remote | & ssh -i $KeyPath -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=8 -o ConnectionAttempts=1 $Target 'bash -s'
if ($LASTEXITCODE -ne 0) { throw "ROUTE_COMPARISON_INCOMPLETE_EXIT_$LASTEXITCODE" }
