# Host-only helper. Dot-sourcing this file performs no remote operation.
# Normalize at the receiver: Windows native stdin can append CRLF even when
# the PowerShell string itself has already been converted to LF.
function Get-ValyqonPreviewBashCommand {
    [CmdletBinding()]
    param([Parameter(Mandatory = $true)][string]$RunId)

    if ($RunId -notmatch '\A[A-Za-z0-9][A-Za-z0-9_-]{0,127}\z') {
        throw 'Preview run ID must contain only ASCII letters, digits, underscores or hyphens (maximum 128 characters).'
    }
    # POSIX tr octal escape avoids embedding an actual CR in command text.
    # Only the supplied script stream is filtered; no server files are changed.
    return ("tr -d '\015' | bash -s -- '{0}'" -f $RunId)
}
