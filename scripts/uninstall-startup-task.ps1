$taskName = "CyberClaw Gateway"
Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
Write-Host "Removed startup task: $taskName"
