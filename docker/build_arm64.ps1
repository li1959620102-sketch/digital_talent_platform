# 国产化 A 方案：构建 arm64 镜像（鲲鹏/飞腾 + 麒麟/统信）
# 依据：用户决策"国产化选 A（轻）"——国产 OS+CPU 可跑即可，数据库保持开源兼容(MySQL/PG)。
# python:3.11-slim 为多架构镜像，无需改 Dockerfile 即可构建 arm64。
param(
    [string]$Tag = "digital-talent-backend:arm64",
    [string]$Platform = "linux/arm64"
)

$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..")

# 1) 确保 buildx 多架构构建器可用
docker buildx create --name multiarch --use 2>$null
docker buildx inspect multiarch --bootstrap 2>$null | Out-Null

# 2) 构建 arm64 镜像（--load 仅单平台时可用；多平台请用 --push 推到镜像仓库）
Set-Location $root
Write-Host "构建 $Tag ($Platform) ..."
docker buildx build --platform $Platform -f backend/Dockerfile -t $Tag . --load

if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ 已构建 $Tag ($Platform)，可在国产 arm64 服务器(麒麟/统信 + 鲲鹏/飞腾)直接运行" -ForegroundColor Green
    Write-Host "   注意：MySQL/PostgreSQL/Redis/Milvus 亦需选用 arm64 镜像（docker-compose 已可加 platform: linux/arm64）" -ForegroundColor Yellow
} else {
    Write-Host "❌ 构建失败，请检查 Dockerfile 与网络" -ForegroundColor Red
}
