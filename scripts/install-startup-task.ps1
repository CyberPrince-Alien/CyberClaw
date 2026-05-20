$projectRoot = Split-Path -Parent $PSScriptRoot
$taskName = "CyberClaw Gateway"
$scriptPath = Join-Path $PSScriptRoot "cyberclaw-start-hidden.vbs"
$action = New-ScheduledTaskAction -Execute "wscript.exe" -Argument "`"$scriptPath`""
$trigger = New-ScheduledTaskTrigger -AtLogOn
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Description "Start CyberClaw gateway at logon" -Force
Write-Host "Installed startup task: $taskName"
