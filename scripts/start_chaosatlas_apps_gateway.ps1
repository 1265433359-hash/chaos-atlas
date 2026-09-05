[CmdletBinding()]
param(
    [string]$MinikubeProfile = 'chaosatlas-apps',
    [string]$ContainerName = 'chaosatlas-apps-gateway',
    [string]$StateRoot = '',
    [string]$Image = 'nginx@sha256:b34848eff6db786b6b1282d3a9c3fd0b5563dfb6d261df4923378b419e0d24f0'
)

$ErrorActionPreference = 'Stop'

if (-not $StateRoot) {
    if ($env:CHAOSATLAS_STATE_ROOT) {
        $StateRoot = [System.IO.Path]::GetFullPath($env:CHAOSATLAS_STATE_ROOT)
    } else {
        $StateRoot = Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'ChaosAtlas'
    }
}

$profileStatus = & minikube status -p $MinikubeProfile --format '{{.Host}}'
if ($LASTEXITCODE -ne 0 -or $profileStatus.Trim() -ne 'Running') {
    throw "Minikube profile is not running: $MinikubeProfile"
}

$networkJson = & docker inspect $MinikubeProfile --format '{{json .NetworkSettings.Networks}}'
if ($LASTEXITCODE -ne 0) {
    throw "Cannot inspect Minikube container: $MinikubeProfile"
}
$networks = $networkJson | ConvertFrom-Json
$networkNames = @($networks.PSObject.Properties.Name)
if ($networkNames.Count -ne 1) {
    throw "Expected exactly one Docker network for $MinikubeProfile"
}
$networkName = $networkNames[0]

$gatewayRoot = Join-Path $StateRoot 'runtime\chaosatlas-apps-gateway'
New-Item -ItemType Directory -Force -Path $gatewayRoot | Out-Null
$configPath = Join-Path $gatewayRoot 'default.conf'
$config = @"
server {
    listen 80;
    server_name immich.local erpnext.local medusa.local rocketchat.local;

    location / {
        proxy_pass http://${MinikubeProfile}:31063;
        proxy_set_header Host `$host;
        proxy_set_header X-Real-IP `$remote_addr;
        proxy_set_header X-Forwarded-For `$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto `$scheme;
        proxy_http_version 1.1;
        proxy_read_timeout 300s;
        client_max_body_size 0;
    }
}
"@
[System.IO.File]::WriteAllText($configPath, $config, [System.Text.UTF8Encoding]::new($false))

$existing = & docker ps -a --filter "name=^/$ContainerName`$" --format '{{.Names}}'
if ($existing -contains $ContainerName) {
    & docker rm -f $ContainerName | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Cannot replace gateway container: $ContainerName"
    }
}

& docker create `
    --name $ContainerName `
    --restart unless-stopped `
    --network $networkName `
    --publish '127.0.0.1:80:80' `
    $Image | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw 'Failed to create the four-application gateway'
}
& docker cp $configPath "${ContainerName}:/etc/nginx/conf.d/default.conf"
if ($LASTEXITCODE -ne 0) {
    throw 'Failed to copy the external gateway configuration'
}
& docker start $ContainerName | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw 'Failed to start the four-application gateway'
}

Start-Sleep -Seconds 2
& docker exec $ContainerName nginx -t
if ($LASTEXITCODE -ne 0) {
    throw 'Gateway Nginx configuration test failed'
}

[pscustomobject]@{
    Status = 'running'
    Container = $ContainerName
    Network = $networkName
    Config = $configPath
    Listen = '127.0.0.1:80'
} | ConvertTo-Json
