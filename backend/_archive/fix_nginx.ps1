$f = 'C:\nginx\conf\nginx.conf'
Copy-Item $f "$f.bak" -Force
$c = Get-Content $f -Raw
if ($c -notmatch 'location = /index\.html') {
    $old = '        # SPA 路由回退（BrowserRouter：/talents /positions 等刷新不 404）'
    $new = @'
        # index.html 禁止缓存（vite build 生成新 hash JS，须每次拉最新 index.html）
        location = /index.html {
            add_header Cache-Control "no-cache, no-store, must-revalidate";
            add_header Pragma "no-cache";
            expires 0;
        }

        # SPA 路由回退（BrowserRouter：/talents /positions 等刷新不 404）
'@
    $c = $c.Replace($old, $new)
    Set-Content -Path $f -Value $c -NoNewline -Encoding UTF8
    $t = & C:\nginx\nginx.exe -t -p C:\nginx 2>&1
    if ($LASTEXITCODE -eq 0) {
        & C:\nginx\nginx.exe -s reload -p C:\nginx 2>&1
        Write-Host "NGINX: config updated + reloaded"
    } else {
        Copy-Item "$f.bak" $f -Force
        Write-Host "NGINX: -t failed, restored backup: $t"
    }
} else {
    Write-Host "NGINX: already has index.html no-cache block, skip"
}
