# Read-only smoke of the isolated local website review server. No secrets or writes.
[CmdletBinding()]
param([string]$BaseUrl='http://127.0.0.1:18865',
      [string]$MailpitUrl='http://127.0.0.1:18866')
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
foreach($value in @($BaseUrl,$MailpitUrl)) {
    $uri=[uri]$value
    if($uri.Scheme -ne 'http' -or $uri.Host -notin @('localhost','127.0.0.1') -or $uri.AbsolutePath -ne '/' -or $uri.Query -or $uri.Fragment -or $uri.UserInfo) {
        throw 'SAFETY=REFUSED_NON_LOOPBACK: localhost preview only'
    }
}
Add-Type -AssemblyName System.Net.Http
$handler=[System.Net.Http.HttpClientHandler]::new()
$handler.AllowAutoRedirect=$false
$handler.UseCookies=$false
$client=[System.Net.Http.HttpClient]::new($handler)
$client.Timeout=[TimeSpan]::FromSeconds(8)
$results=New-Object 'System.Collections.Generic.List[object]'
$failed=$false
function Test-Route {
    param([string]$Name,[string]$Url,[int[]]$Allowed,[string]$Contains='')
    $resp=$null
    try {
        $resp=$client.GetAsync($Url).GetAwaiter().GetResult()
        $code=[int]$resp.StatusCode
        $ok=$Allowed -contains $code
        if($ok -and $Contains) {
            $body=$resp.Content.ReadAsStringAsync().GetAwaiter().GetResult()
            $ok=$body.Contains($Contains)
        }
        $results.Add([pscustomobject]@{name=$Name;http=$code;pass=[bool]$ok})
        if(-not $ok){$script:failed=$true}
        Write-Host ("{0}={1} HTTP_{2}" -f $Name,$(if($ok){'PASS'}else{'FAIL'}),$code)
    } catch {
        $results.Add([pscustomobject]@{name=$Name;http=$null;pass=$false})
        $script:failed=$true
        Write-Host ("{0}=FAIL NETWORK" -f $Name)
    } finally { if($null -ne $resp){$resp.Dispose()} }
}
try {
    Test-Route 'HOME' "$BaseUrl/" @(200) 'guestSearchForm'
    Test-Route 'PUBLIC_CHART' "$BaseUrl/" @(200) 'vqPulseChart'
    Test-Route 'LOGIN' "$BaseUrl/login" @(200)
    Test-Route 'REGISTER' "$BaseUrl/register" @(200)
    Test-Route 'PASSWORD_RESET' "$BaseUrl/forgot-password" @(200)
    foreach($name in @('planner.js','planner.css','tender_team.js','tender_team.css','source_history.js')) {
        Test-Route ("ASSET_"+$name.Replace('.','_')) "$BaseUrl/assets/$name" @(200)
    }
    foreach($item in @(
        @{name='AUTH_ME_PRIVATE';path='/api/v1/auth/me'},
        @{name='SAVED_PRIVATE';path='/api/v1/organizations/1/shortlist'},
        @{name='TEAM_PRIVATE';path='/api/v1/organizations/1/shortlist/1/team'},
        @{name='HISTORY_PRIVATE';path='/api/v1/organizations/1/shortlist/1/source-history'},
        @{name='WORKFLOW_PRIVATE';path='/api/v1/organizations/1/shortlist/1/workflow'}
    )) {
        Test-Route $item.name ($BaseUrl+$item.path) @(401,403)
    }
    Test-Route 'MAILPIT' "$MailpitUrl/api/v1/messages" @(200)
} finally {
    $client.Dispose()
    $handler.Dispose()
}
$report=Join-Path ([IO.Path]::GetTempPath()) 'valyqon-review-functional-smoke.json'
[pscustomobject]@{
    type='LOCAL_REVIEW_READ_ONLY_HTTP'
    checked_utc=[DateTime]::UtcNow.ToString('o')
    passed=(-not $failed)
    authenticated_browser='NOT_TESTED'
    real_source_worker_to_user='NOT_TESTED'
    external_email='NOT_TESTED_MAILPIT_ONLY'
    merchant_payment='DISABLED_NOT_TESTED'
    checks=@($results.ToArray())
} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $report -Encoding UTF8
Write-Host "AUDIT_FILE=$report"
if($failed){throw 'VALYQON_FUNCTIONAL_SMOKE=FAIL; see AUDIT_FILE for read-only check results.'}
Write-Host 'VALYQON_FUNCTIONAL_SMOKE=PASS'
