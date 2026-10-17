# User-run on Windows, requiring their EXISTING AWS SSH key; never run on GitHub runners.
[CmdletBinding()]
param(
    [string]$Server = '63.189.75.15',
    [string]$SshUser = 'ubuntu',
    [string]$IdentityFile = (Join-Path $HOME '.ssh\tenderlens_vps_ed25519'),
    [switch]$PlanOnly,
    [switch]$NoBrowser,
    [switch]$ReuseExistingTunnel
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$remoteRoot = '/home/ubuntu/valyqon-personal-preview'
$project = 'valyqon-private-preview'
if ($Server -notmatch '\A[a-zA-Z0-9][a-zA-Z0-9.-]{0,252}\z' -or $SshUser -ne 'ubuntu') {
    throw 'Untrusted SSH target.'
}
Write-Host 'VALYQON AWS PRIVATE PREVIEW' -ForegroundColor Cyan
Write-Host 'Only the isolated valyqon-private-preview project is updated.'
if ($PlanOnly) {
    Write-Output ('PLAN_ONLY=YES; SERVER={0}; ROOT={1}; PROJECT={2}' -f $Server,$remoteRoot,$project)
    return
}
if (-not (Test-Path -LiteralPath $IdentityFile -PathType Leaf)) {
    throw "Existing SSH key is missing: $IdentityFile"
}
$ssh = (Get-Command ssh.exe -ErrorAction Stop).Source
$scp = (Get-Command scp.exe -ErrorAction Stop).Source
$git = (Get-Command git.exe -ErrorAction Stop).Source
$py = Get-Command py.exe -ErrorAction SilentlyContinue
$pythonArgs = @()
if ($py) { $python = $py.Source; $pythonArgs = @('-3.12') }
else { $python = (Get-Command python.exe -ErrorAction Stop).Source }
$work = Join-Path ([System.IO.Path]::GetTempPath()) ('valyqon-preview-' + [Guid]::NewGuid().ToString('N'))
$source = Join-Path $work 'source'
$archive = Join-Path $work 'source-only.tar.gz'
New-Item -ItemType Directory -Path $work | Out-Null
$target = ('{0}@{1}' -f $SshUser,$Server)
$sshOpts = @('-i', $IdentityFile, '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
             '-o', 'ConnectTimeout=12', '-o', 'ServerAliveInterval=20', '-o', 'ServerAliveCountMax=3')
$tunnel = $null
try {
    Write-Host 'Cloning current main into a fresh temporary checkout.'
    & $git clone --quiet --depth 1 --single-branch --branch main 'https://github.com/Ramzes2023/TenderLens-AI.git' $source
    if ($LASTEXITCODE -ne 0) { throw 'Isolated git clone failed.' }
    $sha = (& $git -C $source rev-parse HEAD).Trim().ToLowerInvariant()
    if ($LASTEXITCODE -ne 0 -or $sha -notmatch '\A[0-9a-f]{40}\z') { throw 'Invalid git HEAD.' }
    Write-Host ('PREVIEW_COMMIT={0}' -f $sha)
    & $python @pythonArgs (Join-Path $source 'artifacts\private-preview-preflight\build_safe_archive.py') $source $archive
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $archive)) { throw 'Source-only packaging failed.' }
    . (Join-Path $source 'ops\private_preview\host_bash_transport.ps1')
    $remoteCmd = Get-ValyqonPreviewBashCommand -RunId $sha
    $preflight = @'
set -euo pipefail
run_id="$1"
test "$(id -un)" = ubuntu
command -v docker >/dev/null
docker compose version >/dev/null
root=/home/ubuntu/valyqon-personal-preview
test ! -L "$root"
mkdir -p "$root/releases/$run_id"
test ! -L "$root/releases"
test ! -L "$root/releases/$run_id"
test -w "$root/releases/$run_id"
free_mb="$(df -Pm "$root" | awk 'NR==2{print $4}')"
test "$free_mb" -ge 750
printf 'PREVIEW_HOST_PREFLIGHT=VERIFIED\n'
'@
    $preflight | & $ssh @sshOpts $target $remoteCmd
    if ($LASTEXITCODE -ne 0) { throw 'Host preflight failed. No upload or production change was made.' }
    $remotePackage = "$remoteRoot/releases/$sha/source-only.tar.gz"
    & $scp @sshOpts $archive ('{0}:{1}' -f $target,$remotePackage)
    if ($LASTEXITCODE -ne 0) { throw 'Source-only preview upload failed.' }
    $deploy = @'
set -euo pipefail
run_id="$1"
root=/home/ubuntu/valyqon-personal-preview
release="$root/releases/$run_id"
archive="$release/source-only.tar.gz"
test -f "$archive"
test ! -L "$release"
tar -tzf "$archive" >/dev/null
tar -xzf "$archive" -C "$release" --no-same-owner --no-same-permissions
test -f "$release/ops/private_preview/compose.yaml"
test -f "$release/ops/private_preview/Dockerfile.preview.txt"
test -f "$release/app/api/main.py"
test -f "$release/config/company_profile.example.json"
env_file="$root/.private-preview.env"
if [ ! -e "$env_file" ]; then
    python3 "$release/ops/private_preview/generate_env.py" "$env_file"
fi
test -f "$env_file"
test "$(stat -c '%a' "$env_file")" = 600
docker compose -p valyqon-private-preview --env-file "$env_file" -f "$release/ops/private_preview/compose.yaml" config --quiet
docker compose -p valyqon-private-preview --env-file "$env_file" -f "$release/ops/private_preview/compose.yaml" up -d --build --wait --wait-timeout 180
api_bind="$(docker compose -p valyqon-private-preview --env-file "$env_file" -f "$release/ops/private_preview/compose.yaml" port api 8000)"
mail_bind="$(docker compose -p valyqon-private-preview --env-file "$env_file" -f "$release/ops/private_preview/compose.yaml" port mailpit 8025)"
test "$api_bind" = "127.0.0.1:18765"
test "$mail_bind" = "127.0.0.1:18766"
python3 - <<'PY'
import json
from urllib.request import build_opener, ProxyHandler
client = build_opener(ProxyHandler({}))
for path in ('/', '/login', '/scoring-methodology', '/status.json', '/private-preview/ready'):
    with client.open('http://127.0.0.1:18765' + path, timeout=8) as response:
        assert response.status == 200, (path, response.status)
        data = response.read(262144)
    if path == '/private-preview/ready':
        value = json.loads(data)
        assert value.get('status') == 'ready' and value.get('external_integrations') == 'disabled'
    if path == '/status.json':
        states = {x['id']: x['state'] for x in json.loads(data)['components']}
        assert states['database'] == 'operational', states
        assert states['sources'] == 'unverified' and states['payments'] == 'not_enabled'
with client.open('http://127.0.0.1:18766/', timeout=8) as response:
    assert response.status == 200
print('PREVIEW_SERVER_HTTP=VERIFIED')
print('PRIVATE_PREVIEW_READY=VERIFIED')
print('PAYMENTS_AND_EXTERNAL_SOURCES=DISABLED')
PY
printf 'PREVIEW_DEPLOYED_COMMIT=%s\n' "$run_id"
'@
    $deploy | & $ssh @sshOpts $target $remoteCmd
    if ($LASTEXITCODE -ne 0) { throw 'Preview Compose startup or server HTTP checks failed.' }
    if ($ReuseExistingTunnel) {
        # Explicit opt-in for browser review without interrupting an existing SSH session.
        # Reuse only if the same SSH process owns BOTH known preview local ports.
        $listeners = foreach ($port in @(18765,18766)) {
            $matches = @(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
                Where-Object { $_.LocalAddress -eq '127.0.0.1' })
            if ($matches.Count -ne 1) {
                throw "Existing preview tunnel on 127.0.0.1:$port is missing or ambiguous."
            }
            $matches[0]
        }
        if ($listeners[0].OwningProcess -ne $listeners[1].OwningProcess) {
            throw 'The two preview ports are not owned by the same SSH tunnel.'
        }
        $owner = Get-CimInstance Win32_Process -Filter (
            'ProcessId=' + [string]$listeners[0].OwningProcess
        )
        if (-not $owner -or $owner.Name -ne 'ssh.exe' -or
            $owner.CommandLine -notlike ('*' + $target + '*') -or
            $owner.CommandLine -notlike '*127.0.0.1:18765:127.0.0.1:18765*' -or
            $owner.CommandLine -notlike '*127.0.0.1:18766:127.0.0.1:18766*') {
            throw 'The preview ports are not owned by the expected existing SSH tunnel.'
        }
        $base = 'http://127.0.0.1:18765'
        $res = Invoke-RestMethod -Uri ($base + '/private-preview/ready') -TimeoutSec 8
        if ($res.status -ne 'ready' -or $res.external_integrations -ne 'disabled') {
            throw 'Existing SSH tunnel does not expose a healthy private preview.'
        }
        Write-Host 'AWS_PRIVATE_PREVIEW=VERIFIED' -ForegroundColor Green
        Write-Host ('SOURCE_COMMIT={0}' -f $sha)
        Write-Host ('REUSED_TUNNEL_PID={0}' -f $listeners[0].OwningProcess)
        Write-Host 'UI:      http://127.0.0.1:18765/'
        Write-Host 'MAILPIT: http://127.0.0.1:18766/'
        if (-not $NoBrowser) { Start-Process ($base + '/') }
        return
    }
    foreach ($port in @(18765,18766)) {
        if (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) {
            throw "Local port $port is occupied. Close the old tunnel or use a clean terminal."
        }
    }
    $forwardArgs = @('-N', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
        '-o', 'ExitOnForwardFailure=yes', '-i', ('"' + $IdentityFile + '"'),
        '-L', '127.0.0.1:18765:127.0.0.1:18765',
        '-L', '127.0.0.1:18766:127.0.0.1:18766', $target)
    $tunnel = Start-Process -FilePath $ssh -ArgumentList $forwardArgs -PassThru -WindowStyle Hidden
    $base = 'http://127.0.0.1:18765'
    $available = $false
    for ($attempt = 0; $attempt -lt 12; $attempt++) {
        if ($tunnel.HasExited) { throw 'SSH tunnel exited before verifying preview readiness.' }
        try {
            $result = Invoke-RestMethod -Uri ($base + '/private-preview/ready') -TimeoutSec 5 -ErrorAction Stop
            if ($result.status -eq 'ready' -and $result.external_integrations -eq 'disabled') {
                $available = $true
                break
            }
        } catch { Start-Sleep -Milliseconds 750 }
    }
    if (-not $available) { throw 'SSH tunnel could not serve the private preview.' }
    Write-Host 'AWS_PRIVATE_PREVIEW=VERIFIED' -ForegroundColor Green
    Write-Host ('SOURCE_COMMIT={0}' -f $sha)
    Write-Host ('TUNNEL_PID={0} | Stop-Process -Id {0}' -f $tunnel.Id)
    Write-Host 'UI:      http://127.0.0.1:18765/'
    Write-Host 'LOGIN:   http://127.0.0.1:18765/login'
    Write-Host 'STATUS:  http://127.0.0.1:18765/status'
    Write-Host 'MAILPIT: http://127.0.0.1:18766/'
    Write-Host 'Use a new synthetic account; external feeds, alerts, AI and payments are disabled.'
    if (-not $NoBrowser) { Start-Process ($base + '/') }
    $tunnel = $null
} catch {
    if ($tunnel -and -not $tunnel.HasExited) {
        Stop-Process -Id $tunnel.Id -ErrorAction SilentlyContinue
    }
    throw
} finally {
    if (Test-Path -LiteralPath $work) { Remove-Item -LiteralPath $work -Force -Recurse }
}
