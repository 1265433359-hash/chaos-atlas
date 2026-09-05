[CmdletBinding(SupportsShouldProcess)]
param(
    [string]$ArchiveRoot,
    [string]$ArchiveName = "$(Get-Date -Format 'yyyy-MM-dd-HHmmss')-repository-cleanup",
    [switch]$IncludeDependencies,
    [string[]]$ExcludeRootName = @(),
    [switch]$Resume
)

$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path

if (-not $ArchiveRoot) {
    if ($env:CHAOSATLAS_STATE_ROOT) {
        $stateRoot = [System.IO.Path]::GetFullPath($env:CHAOSATLAS_STATE_ROOT)
    } elseif ($env:LOCALAPPDATA) {
        $stateRoot = Join-Path $env:LOCALAPPDATA 'ChaosAtlas'
    } else {
        $stateRoot = Join-Path ([Environment]::GetFolderPath('UserProfile')) '.local\state\chaosatlas'
    }
    $ArchiveRoot = Join-Path $stateRoot 'archive'
}

$archiveRootResolved = [System.IO.Path]::GetFullPath($ArchiveRoot)
$archive = [System.IO.Path]::GetFullPath((Join-Path $archiveRootResolved $ArchiveName))
$repoPrefix = $repo.TrimEnd('\') + '\'
$archivePrefix = $archive.TrimEnd('\') + '\'

if ($archive -eq $repo -or $archive.StartsWith($repoPrefix, [StringComparison]::OrdinalIgnoreCase)) {
    throw "Archive must be outside the repository: $archive"
}
if ($archive -eq [System.IO.Path]::GetPathRoot($archive)) {
    throw "Refusing to use a filesystem root as the archive target: $archive"
}
if ((Test-Path -LiteralPath $archive) -and -not $Resume) {
    throw "Archive target already exists; refusing to overwrite: $archive"
}
if ($Resume -and -not (Test-Path -LiteralPath $archive)) {
    throw "Cannot resume because the archive does not exist: $archive"
}

function Get-TreeSummary {
    param([Parameter(Mandatory)][string]$Path)

    $resolved = (Resolve-Path -LiteralPath $Path).Path
    $item = Get-Item -LiteralPath $resolved -Force
    $enumerationErrors = @()
    $files = if ($item.PSIsContainer) {
        @(Get-ChildItem -LiteralPath $resolved -Recurse -Force -File -ErrorAction SilentlyContinue -ErrorVariable +enumerationErrors | Sort-Object FullName)
    } else {
        @($item)
    }

    $aggregate = [System.Security.Cryptography.IncrementalHash]::CreateHash(
        [System.Security.Cryptography.HashAlgorithmName]::SHA256
    )
    $bytes = [long]0
    foreach ($file in $files) {
        $bytes += $file.Length
        $relative = if ($item.PSIsContainer) {
            [System.IO.Path]::GetRelativePath($resolved, $file.FullName).Replace('\', '/')
        } else {
            $file.Name
        }
        try {
            $fileHash = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256 -ErrorAction Stop).Hash.ToLowerInvariant()
        } catch {
            $enumerationErrors += $_
            continue
        }
        $record = "$relative`t$($file.Length)`t$fileHash`n"
        $aggregate.AppendData([System.Text.Encoding]::UTF8.GetBytes($record))
    }
    $treeHash = [Convert]::ToHexString($aggregate.GetHashAndReset()).ToLowerInvariant()
    $aggregate.Dispose()
    [pscustomobject]@{
        files = $files.Count
        bytes = $bytes
        sha256_tree = $treeHash
        hash_complete = $enumerationErrors.Count -eq 0
        read_errors = $enumerationErrors.Count
    }
}

$rootNames = @(
    '.email-notify-outbox',
    '.pytest_cache',
    '.runs',
    'ChaosAtlas-evidence',
    'ChaosAtlas-evidence-v2',
    'environment-reports',
    'runtime'
)
$sources = [System.Collections.Generic.List[System.IO.FileSystemInfo]]::new()
foreach ($name in $rootNames) {
    if ($ExcludeRootName -contains $name) {
        continue
    }
    $candidate = Join-Path $repo $name
    if (Test-Path -LiteralPath $candidate) {
        [void]$sources.Add((Get-Item -LiteralPath $candidate -Force))
    }
}
foreach ($candidate in Get-ChildItem -LiteralPath $repo -Force) {
    if ($candidate.Name.StartsWith('.tmp-', [StringComparison]::OrdinalIgnoreCase) -or
        $candidate.Name.StartsWith('.pytest-tmp-', [StringComparison]::OrdinalIgnoreCase)) {
        if (-not ($sources.FullName -contains $candidate.FullName)) {
            [void]$sources.Add($candidate)
        }
    }
}
$generatedDirectories = @(Get-ChildItem -LiteralPath $repo -Directory -Recurse -Force -ErrorAction SilentlyContinue | Where-Object {
    $_.FullName -notlike "$repo\.git\*" -and
    $_.FullName -notlike "$repo\.venv\*" -and
    ($_.Name -eq '__pycache__' -or $_.Name -like '*.egg-info')
})
foreach ($candidate in $generatedDirectories) {
    $relativeRoot = [System.IO.Path]::GetRelativePath($repo, $candidate.FullName).Split([System.IO.Path]::DirectorySeparatorChar)[0]
    if ($ExcludeRootName -contains $relativeRoot) {
        continue
    }
    $covered = $false
    foreach ($selected in $sources) {
        $selectedPrefix = $selected.FullName.TrimEnd('\') + '\'
        if ($candidate.FullName.StartsWith($selectedPrefix, [StringComparison]::OrdinalIgnoreCase)) {
            $covered = $true
            break
        }
    }
    if (-not $covered) {
        [void]$sources.Add($candidate)
    }
}
if ($IncludeDependencies) {
    $appsRoot = Join-Path $repo 'projects\chaosatlas-apps'
    if (Test-Path -LiteralPath $appsRoot) {
        $dependencyCandidates = @(Get-ChildItem -LiteralPath $appsRoot -Directory -Recurse -Force -Filter 'node_modules' | Sort-Object { $_.FullName.Length })
        foreach ($candidate in $dependencyCandidates) {
            $packageManifest = Join-Path $candidate.Parent.FullName 'package.json'
            if (Test-Path -LiteralPath $packageManifest) {
                try {
                    $package = Get-Content -LiteralPath $packageManifest -Raw | ConvertFrom-Json
                    if ($package.workspaces) {
                        Write-Warning "Skipping npm workspace node_modules because it may contain links to project source: $($candidate.FullName)"
                        continue
                    }
                } catch {
                    throw "Cannot validate dependency archive boundary from ${packageManifest}: $($_.Exception.Message)"
                }
            }
            $candidatePrefix = $candidate.FullName.TrimEnd('\') + '\'
            $alreadyCovered = $false
            foreach ($selected in $sources) {
                $selectedPrefix = $selected.FullName.TrimEnd('\') + '\'
                if ($candidate.FullName.StartsWith($selectedPrefix, [StringComparison]::OrdinalIgnoreCase) -or
                    $selected.FullName.StartsWith($candidatePrefix, [StringComparison]::OrdinalIgnoreCase)) {
                    $alreadyCovered = $true
                    break
                }
            }
            if (-not $alreadyCovered) {
                [void]$sources.Add($candidate)
            }
        }
    }
}
$sources = @($sources | Sort-Object FullName -Unique)

if ($sources.Count -eq 0) {
    Write-Host 'No generated workspace state matched the archive policy.'
    return
}

foreach ($source in $sources) {
    $resolvedSource = (Resolve-Path -LiteralPath $source.FullName).Path
    if (-not ($resolvedSource -eq $repo -or $resolvedSource.StartsWith($repoPrefix, [StringComparison]::OrdinalIgnoreCase))) {
        throw "Refusing source outside repository: $resolvedSource"
    }
    if ($resolvedSource -eq $repo) {
        throw 'Refusing to archive the repository root.'
    }
}

if ($WhatIfPreference) {
    foreach ($source in $sources) {
        $relative = [System.IO.Path]::GetRelativePath($repo, $source.FullName)
        $destination = Join-Path $archive $relative
        $PSCmdlet.ShouldProcess($source.FullName, "move to $destination") | Out-Null
    }
    return
}

New-Item -ItemType Directory -Path $archive -Force | Out-Null
$commit = (git -C $repo rev-parse HEAD).Trim()

foreach ($source in $sources) {
    $relative = [System.IO.Path]::GetRelativePath($repo, $source.FullName).Replace('\', '/')
    $destination = Join-Path $archive ($relative.Replace('/', '\'))
    $destinationParent = Split-Path -Parent $destination
    New-Item -ItemType Directory -Path $destinationParent -Force | Out-Null
    if (-not $destination.StartsWith($archivePrefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Resolved destination escaped archive root: $destination"
    }
    if ($PSCmdlet.ShouldProcess($source.FullName, "move to $destination")) {
        Move-Item -LiteralPath $source.FullName -Destination $destination -ErrorAction Stop
        Write-Host "Moved $relative"
    }
}

$archivedItems = [System.Collections.Generic.List[System.IO.FileSystemInfo]]::new()
foreach ($name in $rootNames) {
    $candidate = Join-Path $archive $name
    if (Test-Path -LiteralPath $candidate) {
        [void]$archivedItems.Add((Get-Item -LiteralPath $candidate -Force))
    }
}
foreach ($candidate in Get-ChildItem -LiteralPath $archive -Force) {
    if ($candidate.Name.StartsWith('.tmp-', [StringComparison]::OrdinalIgnoreCase) -or
        $candidate.Name.StartsWith('.pytest-tmp-', [StringComparison]::OrdinalIgnoreCase)) {
        if (-not ($archivedItems.FullName -contains $candidate.FullName)) {
            [void]$archivedItems.Add($candidate)
        }
    }
}
$generatedArchiveDirectories = @(Get-ChildItem -LiteralPath $archive -Directory -Recurse -Force -ErrorAction SilentlyContinue | Where-Object {
    $_.Name -eq '__pycache__' -or $_.Name -like '*.egg-info'
})
foreach ($candidate in $generatedArchiveDirectories) {
    $relativeParts = [System.IO.Path]::GetRelativePath($archive, $candidate.FullName).Split([System.IO.Path]::DirectorySeparatorChar)
    if (-not ($relativeParts -contains 'node_modules')) {
        [void]$archivedItems.Add($candidate)
    }
}
$archivedAppsRoot = Join-Path $archive 'projects\chaosatlas-apps'
if (Test-Path -LiteralPath $archivedAppsRoot) {
    $dependencyCandidates = @(Get-ChildItem -LiteralPath $archivedAppsRoot -Directory -Recurse -Force -Filter 'node_modules' -ErrorAction SilentlyContinue | Sort-Object { $_.FullName.Length })
    foreach ($candidate in $dependencyCandidates) {
        $relative = [System.IO.Path]::GetRelativePath($archive, $candidate.FullName)
        if ($relative.Split([System.IO.Path]::DirectorySeparatorChar).Where({ $_ -eq 'node_modules' }).Count -eq 1) {
            [void]$archivedItems.Add($candidate)
        }
    }
}

$records = [System.Collections.Generic.List[object]]::new()
foreach ($archivedItem in @($archivedItems | Sort-Object FullName -Unique)) {
    $relative = [System.IO.Path]::GetRelativePath($archive, $archivedItem.FullName).Replace('\', '/')
    $summary = Get-TreeSummary -Path $archivedItem.FullName
    $classification = if ($relative -eq '.email-notify-outbox') {
        'legacy_notification_queue_do_not_send'
    } elseif ($relative.EndsWith('/node_modules')) {
        'regenerable_dependency'
    } elseif ($relative -eq '.runs' -or $relative.StartsWith('ChaosAtlas-evidence')) {
        'bulk_experiment_output'
    } else {
        'local_generated_state'
    }
    $records.Add([ordered]@{
        source = $relative
        destination = $relative
        classification = $classification
        files = $summary.files
        bytes = $summary.bytes
        sha256_tree = $summary.sha256_tree
        hash_complete = $summary.hash_complete
        read_errors = $summary.read_errors
    })
    Write-Host "Indexed $relative ($($summary.files) files, complete=$($summary.hash_complete))"
}

$manifest = [ordered]@{
    schema_version = 1
    created_at = (Get-Date).ToUniversalTime().ToString('o')
    source_repository = $repo
    source_commit = $commit
    archive_root = $archive
    notification_policy = 'Legacy pending notification records are audit-only and must not be copied into the active pending queue.'
    restore = 'Copy an item from this archive back to its source-relative path only after confirming that the destination does not exist.'
    items = @($records)
}
$manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $archive 'MANIFEST.json') -Encoding utf8

$restore = @(
    '# ChaosAtlas Local Archive Restore Guide',
    '',
    "Source commit: $commit",
    '',
    'Each item keeps its repository-relative path below this directory. Restore only one exact item at a time, and only when its original destination is absent.',
    '',
    'The `.email-notify-outbox` tree is historical audit data. Do not copy its JSON files into the active email queue because doing so may send stale notifications.',
    '',
    'Verify restored content by regenerating its tree digest and comparing it with `MANIFEST.json`.'
)
$restore | Set-Content -LiteralPath (Join-Path $archive 'RESTORE.md') -Encoding utf8
Write-Host "Archive complete: $archive"
