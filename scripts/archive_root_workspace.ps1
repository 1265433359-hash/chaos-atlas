[CmdletBinding(SupportsShouldProcess)]
param(
    [string]$ArchiveRoot = 'C:\Users\23741\Desktop\XIAO\ChaosAtlas-local-archive-20260826',
    [string]$ArchiveName = '2026-08-30-root-cleanup'
)

$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$archive = Join-Path $ArchiveRoot $ArchiveName

if (Test-Path -LiteralPath $archive) {
    throw "Archive target already exists; refusing to overwrite: $archive"
}

$protected = @(
    '.git', '.planning', '.email-notify-outbox', '.venv',
    'src', 'cli', 'tools', 'scripts', 'tests', 'projects', 'workloads', 'docs'
)
$patterns = @(
    '.academic_review*', '.lo_profile_review*', '.review_*',
    '.pytest*', '.tmp-*', '.runs', 'runtime', '.docker-config*',
    '.zcode', 'build', 'train-ticket', 'online-boutique', 'otel-demo',
    '.worktrees', '.migration', 'ChaosAtlas-evidence*'
)

# Build a root-level tracked-path set so a future cleanup cannot move product files.
$tracked = [System.Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
foreach ($path in (git -C $repo ls-files)) {
    [void]$tracked.Add($path.Replace('/', '\'))
}

$sources = [System.Collections.Generic.List[System.IO.FileSystemInfo]]::new()
foreach ($entry in (Get-ChildItem -LiteralPath $repo -Force)) {
    if ($protected -contains $entry.Name) { continue }
    $matched = $false
    foreach ($pattern in $patterns) {
        if ($entry.Name -like $pattern) { $matched = $true; break }
    }
    if (-not $matched -and $entry.PSIsContainer -eq $false) {
        $matched = $entry.Name -like '*.docx' -or
            $entry.Name -like '*.pdf' -or
            $entry.Name -like 'github_candidate_snapshot_*.csv'
    }
    if (-not $matched) { continue }

    # Skip any root item that contains tracked files, including a tracked file deleted locally.
    $rootName = $entry.Name.Replace('\', '/')
    $hasTracked = $tracked | Where-Object { $_ -eq $rootName -or $_.StartsWith("$rootName/", [StringComparison]::OrdinalIgnoreCase) }
    if ($hasTracked) { continue }
    [void]$sources.Add($entry)
}
$sources = @($sources | Sort-Object Name)

if (@($sources).Count -eq 0) {
    Write-Host 'No root artifacts matched the archive policy.'
    return
}

if ($PSCmdlet.ShouldProcess($archive, 'create archive directory')) {
    New-Item -ItemType Directory -Path $archive | Out-Null
}

$manifest = [System.Collections.Generic.List[string]]::new()
$manifest.Add('ChaosAtlas root cleanup archive')
$manifest.Add("Created: $(Get-Date -Format o)")
$manifest.Add("Source: $repo")
$manifest.Add('')
$manifest.Add('Moved items:')
$failed = [System.Collections.Generic.List[string]]::new()

foreach ($source in $sources) {
    $destination = Join-Path $archive $source.Name
    try {
        if ($PSCmdlet.ShouldProcess($source.FullName, "move to $destination")) {
            Move-Item -LiteralPath $source.FullName -Destination $destination -ErrorAction Stop
        }
        $manifest.Add("- $($source.Name)")
    } catch {
        $message = $_.Exception.Message -replace '\s+', ' '
        $failed.Add("- $($source.Name): $message")
        Write-Warning "Could not archive $($source.Name): $message"
    }
}

if (-not $WhatIfPreference) {
    $manifest.Add('')
    $manifest.Add('Failed items:')
    if ($failed.Count -eq 0) {
        $manifest.Add('- none')
    } else {
        $manifest.AddRange($failed)
    }
    $manifest | Set-Content -LiteralPath (Join-Path $archive 'MANIFEST.txt') -Encoding utf8
    Write-Host "Archived $($sources.Count - $failed.Count) of $($sources.Count) root items to $archive"
    if ($failed.Count -gt 0) {
        Write-Warning "$($failed.Count) item(s) remain in the repository; see MANIFEST.txt and rerun after closing file-using processes."
    }
}
