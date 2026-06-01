# Samsung Appliance Daily Review — 자동 시작 스크립트
# 실행: start.bat 더블클릭

$ROOT = Split-Path -Parent $MyInvocation.MyCommand.Path
$CF   = "C:\Users\cjscn\AppData\Local\Microsoft\WinGet\Packages\Cloudflare.cloudflared_Microsoft.Winget.Source_8wekyb3d8bbwe\cloudflared.exe"
$LOG  = "$env:TEMP\cf_tunnel.log"
$PORT = 8765

Write-Host ""
Write-Host "======================================" -ForegroundColor Cyan
Write-Host "  Samsung Appliance Review Viewer" -ForegroundColor Cyan
Write-Host "======================================" -ForegroundColor Cyan

# 1. 기존 프로세스 정리
Write-Host "`n[1/3] 기존 프로세스 정리..." -ForegroundColor Yellow
Get-Process cloudflared -ErrorAction SilentlyContinue | Stop-Process -Force
Get-NetTCPConnection -LocalPort $PORT -State Listen -ErrorAction SilentlyContinue |
    ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
Start-Sleep -Seconds 2

# 2. FastAPI 뷰어 시작
Write-Host "[2/3] FastAPI 뷰어 시작 중..." -ForegroundColor Yellow
$viewer = Start-Process -FilePath "python" `
    -ArgumentList "-m viewer.app" `
    -WorkingDirectory $ROOT `
    -NoNewWindow -PassThru
Start-Sleep -Seconds 6

try {
    $r = Invoke-WebRequest -Uri "http://localhost:$PORT" -UseBasicParsing -TimeoutSec 5
    Write-Host "      뷰어 OK (HTTP $($r.StatusCode))" -ForegroundColor Green
} catch {
    Write-Host "      뷰어 응답 없음 — 계속 시도합니다" -ForegroundColor Red
}

# 3. Cloudflare 터널 시작
Write-Host "[3/3] Cloudflare 터널 연결 중..." -ForegroundColor Yellow
Remove-Item $LOG -ErrorAction SilentlyContinue
$tunnel = Start-Process -FilePath $CF `
    -ArgumentList "tunnel --url http://localhost:$PORT" `
    -RedirectStandardError $LOG `
    -NoNewWindow -PassThru

$url = $null
for ($i = 0; $i -lt 20; $i++) {
    Start-Sleep -Seconds 1
    if (Test-Path $LOG) {
        $line = Get-Content $LOG | Where-Object { $_ -match "https://[\w\-]+\.trycloudflare\.com" } | Select-Object -First 1
        if ($line -and $line -match "(https://[\w\-]+\.trycloudflare\.com)") {
            $url = $Matches[1]
            break
        }
    }
}

# 결과 출력
Write-Host ""
Write-Host "======================================" -ForegroundColor Cyan
if ($url) {
    Write-Host "  로컬  : http://localhost:$PORT" -ForegroundColor White
    Write-Host "  외부  : $url" -ForegroundColor Green
    $url | Set-Clipboard
    Write-Host "  (URL 클립보드 복사 완료)" -ForegroundColor Gray
} else {
    Write-Host "  로컬  : http://localhost:$PORT" -ForegroundColor White
    Write-Host "  터널 URL 발급 실패 — 로그: $LOG" -ForegroundColor Red
}
Write-Host "======================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "이 창을 닫으면 뷰어+터널이 종료됩니다." -ForegroundColor Gray
Write-Host ""

# 창 유지 (blocking 없이)
while ($true) {
    Start-Sleep -Seconds 30
    # 뷰어 죽으면 재시작
    if (-not (Get-Process -Id $viewer.Id -ErrorAction SilentlyContinue)) {
        Write-Host "뷰어 재시작 중..." -ForegroundColor Yellow
        $viewer = Start-Process -FilePath "python" `
            -ArgumentList "-m viewer.app" `
            -WorkingDirectory $ROOT `
            -NoNewWindow -PassThru
    }
}
