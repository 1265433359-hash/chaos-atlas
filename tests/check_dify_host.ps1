[CmdletBinding()]
param(
    [string]$OutputRoot = ".\environment-reports"
)

# Read-only host assessment. Do not install, remove, restart, or mutate services.
$ErrorActionPreference = "Continue"
$reportDir = [System.IO.Path]::GetFullPath($OutputRoot)
[System.IO.Directory]::CreateDirectory($reportDir) | Out-Null

function Invoke-ObservedCommand {
    param([string]$Name, [string[]]$Arguments = @())
    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if (-not $command) {
        return [ordered]@{ present = $false; command = $Name; version = $null; output = $null; error = "not_found" }
    }
    try {
        $output = (& $command.Source @Arguments 2>&1 | Out-String).Trim()
        $first = ($output -split "`r?`n" | Where-Object { $_.Trim() } | Select-Object -First 1)
        return [ordered]@{ present = $true; command = $Name; version = $first; output = $output; error = $null }
    } catch {
        return [ordered]@{ present = $true; command = $Name; version = $null; output = $null; error = $_.Exception.Message }
    }
}

function Invoke-WslObserved {
    param([string[]]$Arguments)
    $wsl = Get-Command wsl.exe -ErrorAction SilentlyContinue
    if (-not $wsl) { return [ordered]@{ present = $false; output = $null; error = "wsl_not_found" } }
    try {
        $output = (& $wsl.Source @Arguments 2>&1 | Out-String).Trim()
        return [ordered]@{ present = $true; output = $output; error = $null }
    } catch {
        return [ordered]@{ present = $true; output = $null; error = $_.Exception.Message }
    }
}

function Get-PortState {
    param([int]$Port)
    $listeners = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
    return [ordered]@{ port = $Port; listening = ($listeners.Count -gt 0); owners = @($listeners | Select-Object -ExpandProperty OwningProcess -Unique) }
}

$os = Get-CimInstance Win32_OperatingSystem -ErrorAction SilentlyContinue
$computer = Get-CimInstance Win32_ComputerSystem -ErrorAction SilentlyContinue
$processor = Get-CimInstance Win32_Processor -ErrorAction SilentlyContinue | Select-Object -First 1
$systemDriveName = ($env:SystemDrive | ForEach-Object { $_.TrimEnd(":") })
if (-not $systemDriveName) { $systemDriveName = "C" }
$systemDrive = Get-PSDrive -Name $systemDriveName -ErrorAction SilentlyContinue

$dockerVersion = Invoke-ObservedCommand "docker" @("version", "--format", "{{json .}}")
$dockerInfo = Invoke-ObservedCommand "docker" @("info", "--format", "{{json .}}")
$wslStatus = Invoke-WslObserved @("--status")
$wslDistros = Invoke-WslObserved @("--list", "--verbose")

$toolResults = [ordered]@{}
foreach ($tool in @(
    @{ name = "python"; args = @("--version") },
    @{ name = "git"; args = @("--version") },
    @{ name = "kubectl"; args = @("version", "--client=true") },
    @{ name = "minikube"; args = @("version", "--short") },
    @{ name = "helm"; args = @("version", "--short") },
    @{ name = "docker"; args = @("compose", "version") }
)) { $toolResults[$tool.name] = Invoke-ObservedCommand $tool.name $tool.args }

$dockerParsed = $null
if ($dockerInfo.output) { try { $dockerParsed = $dockerInfo.output | ConvertFrom-Json } catch { $dockerParsed = $null } }
$dockerVersionParsed = $null
if ($dockerVersion.output) { try { $dockerVersionParsed = $dockerVersion.output | ConvertFrom-Json } catch { $dockerVersionParsed = $null } }
$wslStatusNormalized = ($wslStatus.output -replace "[\x00]", "")
$memoryGb = if ($computer.TotalPhysicalMemory) { [math]::Round($computer.TotalPhysicalMemory / 1GB, 1) } else { $null }
$availableMemoryHintGb = $null
try {
    $memoryInfo = [System.GC]::GetGCMemoryInfo()
    if ($memoryInfo.TotalAvailableMemoryBytes) {
        $availableMemoryHintGb = [math]::Round($memoryInfo.TotalAvailableMemoryBytes / 1GB, 1)
    }
} catch {
    $availableMemoryHintGb = $null
}
if (-not $memoryGb) {
    try {
        Add-Type -AssemblyName Microsoft.VisualBasic -ErrorAction Stop
        $computerInfo = [Microsoft.VisualBasic.Devices.ComputerInfo]::new()
        if ($computerInfo.TotalPhysicalMemory) { $memoryGb = [math]::Round($computerInfo.TotalPhysicalMemory / 1GB, 1) }
        if (-not $availableMemoryHintGb -and $computerInfo.AvailablePhysicalMemory) { $availableMemoryHintGb = [math]::Round($computerInfo.AvailablePhysicalMemory / 1GB, 1) }
    } catch { }
}
$cores = if ($processor.NumberOfLogicalProcessors) { [int]$processor.NumberOfLogicalProcessors } else { [Environment]::ProcessorCount }
$freeDiskGb = if ($systemDrive.Free) { [math]::Round($systemDrive.Free / 1GB, 1) } else { $null }
if (-not $freeDiskGb) {
    try {
        $driveInfo = [System.IO.DriveInfo]::new(($systemDriveName + ":\"))
        if ($driveInfo.AvailableFreeSpace) { $freeDiskGb = [math]::Round($driveInfo.AvailableFreeSpace / 1GB, 1) }
    } catch { $freeDiskGb = $null }
}
$virtualization = if ($processor) { $processor.VirtualizationFirmwareEnabled } else { $null }
$osCaption = if ($os.Caption) { $os.Caption } else { (Get-ItemProperty "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion" -ErrorAction SilentlyContinue).ProductName }
$osVersion = if ($os.Version) { $os.Version } else { [Environment]::OSVersion.Version.ToString() }

$recommendation = [ordered]@{
    minikube_driver = "docker"
    profile_kind = "disposable"
    recommended_cpu = if ($cores -and $cores -ge 12) { 12 } elseif ($cores -and $cores -ge 8) { 8 } else { 6 }
    recommended_memory_gb = if ($memoryGb -and $memoryGb -ge 32) { 24 } elseif ($memoryGb -and $memoryGb -ge 24) { 16 } else { 12 }
    recommended_disk_gb = 80
    rationale = "Dify plus databases, workers, Chaos Mesh and evidence collection need a larger disposable cluster."
}

$checks = [ordered]@{
    docker_daemon = [bool]($dockerInfo.present -and $dockerVersionParsed.Server -and $dockerInfo.output -notmatch "permission denied|Access is denied")
    docker_server_available = [bool]$dockerVersionParsed.Server
    wsl_available = [bool]($wslStatus.present -and -not $wslStatus.error)
    wsl_query_ok = [bool]($wslStatus.output -and $wslStatusNormalized -notmatch "ACCESSDENIED|E_ACCESSDENIED|Access is denied")
    kubectl_present = [bool]$toolResults.kubectl.present
    minikube_present = [bool]$toolResults.minikube.present
    helm_present = [bool]$toolResults.helm.present
    physical_memory_ok = [bool](($memoryGb -and $memoryGb -ge 16) -or ($availableMemoryHintGb -and $availableMemoryHintGb -ge 16))
    cpu_ok = [bool]($cores -and $cores -ge 8)
    disk_ok = [bool]($freeDiskGb -and $freeDiskGb -ge 80)
    virtualization_visible = [bool]($virtualization -eq $true)
}

$ports = @(80, 443, 3000, 5001, 5432, 6379, 8080, 9090, 10250 | ForEach-Object { Get-PortState $_ })
$report = [ordered]@{
    schema_version = "chaosatlas-dify-host-report-v1"
    generated_at = (Get-Date).ToUniversalTime().ToString("o")
    read_only = $true
    host = [ordered]@{
        computer_name = $env:COMPUTERNAME
        os = $osCaption
        os_version = $osVersion
        architecture = $env:PROCESSOR_ARCHITECTURE
        logical_processors = $cores
        physical_memory_gb = $memoryGb
        available_memory_hint_gb = $availableMemoryHintGb
        system_drive_free_gb = $freeDiskGb
        virtualization_firmware_enabled = $virtualization
    }
    docker = [ordered]@{ version = $dockerVersion; info = $dockerParsed; raw_info_error = $dockerInfo.error }
    wsl = [ordered]@{ status = $wslStatus; distros = $wslDistros }
    tools = $toolResults
    ports = $ports
    checks = $checks
    recommendation = $recommendation
    next_steps = @(
        "Install missing CLI tools reported above on the new computer; this script does not install them.",
        "Enable Docker Desktop WSL2 integration for the selected distro.",
        "Create a disposable Minikube profile with the recommended CPU, memory and disk settings.",
        "Deploy Dify and Chaos Mesh only after the host checks pass."
    )
}

$jsonPath = Join-Path $reportDir "host-report.json"
$mdPath = Join-Path $reportDir "host-report.md"
$report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $jsonPath -Encoding UTF8

$lines = [System.Collections.Generic.List[string]]::new()
$lines.Add("# Dify Host Environment Report")
$lines.Add("")
$lines.Add("Generated: $($report.generated_at)")
$lines.Add("Read-only: $($report.read_only)")
$lines.Add("")
$lines.Add("## Host")
$lines.Add("")
$lines.Add("- OS: $($report.host.os) $($report.host.os_version)")
$lines.Add("- CPU logical processors: $($report.host.logical_processors)")
$lines.Add("- Physical memory (GB): $($report.host.physical_memory_gb)")
$lines.Add("- System drive free (GB): $($report.host.system_drive_free_gb)")
$lines.Add("- Virtualization firmware enabled: $($report.host.virtualization_firmware_enabled)")
$lines.Add("")
$lines.Add("## Checks")
$lines.Add("")
foreach ($entry in $report.checks.GetEnumerator()) { $lines.Add("- $($entry.Key): $($entry.Value)") }
$lines.Add("")
$lines.Add("## Minikube Recommendation")
$lines.Add("")
$lines.Add("- Driver: $($recommendation.minikube_driver)")
$lines.Add("- Profile: $($recommendation.profile_kind)")
$lines.Add("- CPU: $($recommendation.recommended_cpu) vCPU")
$lines.Add("- Memory: $($recommendation.recommended_memory_gb) GB")
$lines.Add("- Disk target: $($recommendation.recommended_disk_gb) GB free")
$lines.Add("")
$lines.Add("## Tool Summary")
$lines.Add("")
foreach ($entry in $report.tools.GetEnumerator()) { $lines.Add("- $($entry.Key): present=$($entry.Value.present), version=$($entry.Value.version)") }
$lines | Set-Content -LiteralPath $mdPath -Encoding UTF8

Write-Output ("JSON report: " + $jsonPath)
Write-Output ("Markdown report: " + $mdPath)
Write-Output ("Recommended Minikube: " + $recommendation.recommended_cpu + " vCPU / " + $recommendation.recommended_memory_gb + " GB RAM / Docker driver")
