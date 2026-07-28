# Samsung Appliance Daily Review — 자동 시작 스크립트
# 실행: start.bat 더블클릭

$ROOT = Split-Path -Parent $MyInvocation.MyCommand.Path
$PORT = 8765
$LOG  = "$env:TEMP\cf_tunnel.log"

# 실제 Python 경로 (Microsoft Store 스텁 회피). 없으면 py → python 순으로 대체.
$PY = "C:\Users\cjscn\AppData\Local\Python\bin\python.exe"
if (-not (Test-Path $PY)) {
    if (Get-Command py -ErrorAction SilentlyContinue) { $PY = "py" } else { $PY = "python" }
}

# cloudflared 는 설치돼 있을 때만 터널을 연다.
$CF = "C:\Users\cjscn\AppData\Local\Microsoft\WinGet\Packages\Cloudflare.cloudflared_Microsoft.Winget.Source_8wekyb3d8bbwe\cloudflared.exe"

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
Write-Host "[2/3] FastAPI 뷰어 시작 중... (python: $PY)" -ForegroundColor Yellow
$viewer = Start-Process -FilePath $PY `
    -ArgumentList "-m viewer.app" `
    -WorkingDirectory $ROOT `
    -NoNewWindow -PassThru
Start-Sleep -Seconds 6

$viewerOk = $false
try {
    $r = Invoke-WebRequest -Uri "http://localhost:$PORT" -UseBasicParsing -TimeoutSec 5
    Write-Host "      뷰어 OK (HTTP $($r.StatusCode))" -ForegroundColor Green
    $viewerOk = $true
} catch {
    Write-Host "      뷰어 응답 없음 — 잠시 후 브라우저에서 새로고침 해보세요" -ForegroundColor Red
}

# 브라우저 자동 열기 (더블클릭만으로 화면이 뜨도록)
Start-Process "http://localhost:$PORT"

# 3. Cloudflare 터널 (설치돼 있을 때만)
$url = $null
if (Test-Path $CF) {
    Write-Host "[3/3] Cloudflare 터널 연결 중..." -ForegroundColor Yellow
    Remove-Item $LOG -ErrorAction SilentlyContinue
    $tunnel = Start-Process -FilePath $CF `
        -ArgumentList "tunnel --url http://localhost:$PORT" `
        -RedirectStandardError $LOG `
        -NoNewWindow -PassThru

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
} else {
    Write-Host "[3/3] cloudflared 미설치 — 외부 터널 건너뜀 (로컬만 사용)" -ForegroundColor Gray
}

# 결과 출력
Write-Host ""
Write-Host "======================================" -ForegroundColor Cyan
Write-Host "  로컬  : http://localhost:$PORT" -ForegroundColor White
if ($url) {
    Write-Host "  외부  : $url" -ForegroundColor Green
    $url | Set-Clipboard
    Write-Host "  (URL 클립보드 복사 완료)" -ForegroundColor Gray
} elseif (Test-Path $CF) {
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
        $viewer = Start-Process -FilePath $PY `
            -ArgumentList "-m viewer.app" `
            -WorkingDirectory $ROOT `
            -NoNewWindow -PassThru
    }
}
