# Power BI Desktop Automated Refresh Script
# Mimics Power BI Service scheduled refresh behavior
# 
# Usage: Run this script via Windows Task Scheduler hourly
# Prerequisites: Power BI Desktop installed, .pbix file saved

param(
    [string]$PbixPath = "C:\Users\Vytas K\Documents\Software Projects\Fintegrate\powerbi\Fintegrate_Analytics_Dashboard.pbix",
    [string]$LogPath = "C:\Users\Vytas K\Documents\Software Projects\Fintegrate\powerbi\refresh_log.txt"
)

$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
$logEntry = "$timestamp - Starting Power BI refresh..."

try {
    # Check if Power BI Desktop is installed
    $pbiPath = "C:\Program Files\Microsoft Power BI Desktop\bin\PBIDesktop.exe"
    if (-not (Test-Path $pbiPath)) {
        throw "Power BI Desktop not found at $pbiPath"
    }

    # Check if .pbix file exists
    if (-not (Test-Path $PbixPath)) {
        throw "Dashboard file not found at $PbixPath"
    }

    # Open Power BI file (this triggers refresh if configured)
    Write-Host "Opening Power BI Desktop..." -ForegroundColor Cyan
    Start-Process $pbiPath -ArgumentList "`"$PbixPath`"" -PassThru
    
    # Wait for Power BI to open (30 seconds)
    Start-Sleep -Seconds 30
    
    # Send keystroke to trigger refresh (Ctrl+R or Alt+H, R)
    # Note: This requires Power BI to be focused window
    Add-Type -AssemblyName System.Windows.Forms
    [System.Windows.Forms.SendKeys]::SendWait("^r")  # Ctrl+R (Refresh)
    
    # Wait for refresh to complete (estimate 10 seconds for small dataset)
    Start-Sleep -Seconds 10
    
    # Save file (Ctrl+S)
    [System.Windows.Forms.SendKeys]::SendWait("^s")
    Start-Sleep -Seconds 2
    
    # Close Power BI (Alt+F4)
    [System.Windows.Forms.SendKeys]::SendWait("%{F4}")
    
    $logEntry += "`n$timestamp - Refresh completed successfully"
    Write-Host "Refresh completed!" -ForegroundColor Green
    
} catch {
    $logEntry += "`n$timestamp - ERROR: $($_.Exception.Message)"
    Write-Host "Refresh failed: $($_.Exception.Message)" -ForegroundColor Red
}

# Append to log file
$logEntry | Out-File -FilePath $LogPath -Append

# Optional: Send email notification (requires SMTP configured)
# Uncomment and configure if you want email alerts like Power BI Service
<#
$emailParams = @{
    From = "fintegrate@gmail.com"
    To = "vytaske11@gmail.com"
    Subject = "Power BI Refresh - Fintegrate Dashboard"
    Body = $logEntry
    SmtpServer = "smtp.gmail.com"
    Port = 587
    UseSsl = $true
    Credential = (Get-Credential)  # Prompt for credentials
}
Send-MailMessage @emailParams
#>
