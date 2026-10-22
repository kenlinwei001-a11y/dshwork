# WorkDSH 一键部署（Windows 入口）—— 部署在 WSL2，浏览器在 Windows
#
# 用法（普通 PowerShell 即可）：
#   powershell -ExecutionPolicy Bypass -File deploy\bootstrap-windows.ps1
#   powershell -ExecutionPolicy Bypass -File deploy\bootstrap-windows.ps1 -Ref main -Port 18989
#   powershell -ExecutionPolicy Bypass -File deploy\bootstrap-windows.ps1 -Install     # 顺带装 Ubuntu
#   powershell -ExecutionPolicy Bypass -File deploy\bootstrap-windows.ps1 -PortProxy   # 需管理员
#
# 做三件事：1) 检查 WSL2/Ubuntu；2) 在 WSL 里跑 deploy/bootstrap-wsl.sh；3) 从 Windows 侧验证并打开浏览器。
param(
  [string]$Distro = "Ubuntu",
  [string]$Dir = "~/workdsh",
  [int]$Port = 18989,
  [string]$Ref = "",
  [int]$Heap = 0,
  [switch]$Install,
  [switch]$PortProxy,
  [switch]$NoStart,
  [switch]$WithSessions,
  [switch]$NoOpen
)

$ErrorActionPreference = "Stop"
function Say($m) { Write-Host $m }
function Ok($m) { Write-Host "  [OK] $m" -ForegroundColor Green }
function Warn($m) { Write-Host "  [WARN] $m" -ForegroundColor Yellow }
function Fail($m) { Write-Host "  [FAIL] $m" -ForegroundColor Red; exit 1 }

Say "=== WorkDSH Windows 部署（WSL2 运行 + Windows 浏览器访问）==="

$build = [int](Get-ItemProperty "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion").CurrentBuildNumber
if ($build -lt 19041) { Fail "Windows 版本过低（build $build）。WSL2 需要 Windows 10 2004+ 或 Windows 11。" }
Ok "Windows build $build"

if (-not (Get-Command wsl.exe -ErrorAction SilentlyContinue)) {
  if ($Install) {
    Say "未安装 WSL，执行：wsl --install -d $Distro"
    wsl.exe --install -d $Distro
    Say "安装可能要求重启。重启后再执行本脚本。"
    exit 0
  }
  Fail "未安装 WSL。管理员运行：wsl --install -d $Distro（或加 -Install 让脚本代跑），重启后重试。"
}
$distros = @()
try { $distros = (& wsl.exe -l -q) 2>$null | ForEach-Object { $_.Trim() } | Where-Object { $_ } } catch {}
if (-not ($distros -contains $Distro)) {
  if ($Install) {
    Say "安装发行版 $Distro ..."
    wsl.exe --install -d $Distro
    Say "首次启动需要设置 Linux 用户名和密码；完成后重跑本脚本。"
    exit 0
  }
  Warn "未找到发行版 $Distro。已安装：$($distros -join ', ')"
  Fail "先安装：wsl --install -d $Distro（或加 -Install），首次启动初始化完成后再执行。"
}
Ok "WSL 发行版：$Distro"

$dirB = $Dir
if ($dirB.StartsWith("~")) { $dirB = '$HOME' + $dirB.Substring(1) }
$dirB = $dirB.Replace('"', '')

$flags = @("--port $Port")
if ($Ref) { $flags += "--ref $Ref" }
if ($NoStart) { $flags += "--no-start" }
if ($WithSessions) { $flags += "--with-sessions" }
if ($Heap -gt 0) { $flags += "--heap $Heap" }
$flagStr = $flags -join ' '

$inner = 'set -e; D="' + $dirB + '"; ' +
         'if [ ! -d "$D/.git" ]; then mkdir -p "$(dirname "$D")"; git clone https://github.com/kenlinwei001-a11y/dshwork.git "$D"; fi; ' +
         'cd "$D"; bash deploy/bootstrap-wsl.sh ' + $flagStr

Say "在 WSL($Distro) 中执行引导（首次约 5-20 分钟）..."
wsl.exe -d $Distro -- bash -lc $inner
if ($LASTEXITCODE -ne 0) { Warn "引导脚本返回非零（看上面的 WSL 输出），继续做 Windows 侧验证。" }

if ($NoStart) {
  Say "已按 -NoStart 跳过启动验证。稍后手动启动：wsl -d $Distro -- bash -lc cd $dirB && bash deploy/bootstrap-wsl.sh"
  exit 0
}

$url = "http://127.0.0.1:$Port/"
$okHttp = $false
for ($i = 0; $i -lt 30; $i++) {
  try {
    $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 3
    if ([int]$r.StatusCode -ge 200 -and [int]$r.StatusCode -lt 500) { $okHttp = $true; break }
  } catch {
    if ($_.Exception.Response -and [int]$_.Exception.Response.StatusCode -ge 200 -and [int]$_.Exception.Response.StatusCode -lt 500) { $okHttp = $true; break }
  }
  Start-Sleep -Seconds 2
}

if ($okHttp) {
  Ok "Windows 浏览器可访问：$url"
  if (-not $NoOpen) { Start-Process $url | Out-Null }
  exit 0
}

Warn "Windows 侧访问失败，开始诊断"
$ip = ""
try { $ip = (& wsl.exe -d $Distro -- hostname -I) 2>$null; $ip = ($ip -split '\s+')[0] } catch {}
if ($ip) { Say "  WSL IP: $ip" }
Say "  WSL 内自检：wsl -d $Distro -- curl -s -o /dev/null -w %{http_code} http://127.0.0.1:$Port/"
Say "  端口占用：netstat -ano | findstr :$Port"
if (-not $ip) { Fail "拿不到 WSL IP。先在 WSL 里运行 hostname -I 确认网络。" }

if ($PortProxy) {
  $admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
  if (-not $admin) { Fail "-PortProxy 需要管理员 PowerShell。" }
  Say "设置端口代理 127.0.0.1:$Port -> $ip : $Port"
  netsh interface portproxy delete v4tov4 listenport=$Port listenaddress=127.0.0.1 2>$null | Out-Null
  netsh interface portproxy add v4tov4 listenport=$Port listenaddress=127.0.0.1 connectport=$Port connectaddress=$ip
  netsh advfirewall firewall add rule name="WorkDSH $Port" dir=in action=allow protocol=TCP localport=$Port 2>$null | Out-Null
  Start-Sleep -Seconds 2
  try {
    $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 5
    Ok "端口代理生效：$url"
    if (-not $NoOpen) { Start-Process $url | Out-Null }
    exit 0
  } catch {
    Fail "端口代理后仍不可访问。看 WSL 日志：~/.workdsh/preview/logs/"
  }
}

Say ""
Say "下一步二选一："
Say "  A) 管理员 PowerShell 重跑并加 -PortProxy（自动转发，推荐）"
Say "  B) 检查 %UserProfile%\.wslconfig，确保包含："
Say "       [wsl2]"
Say "       localhostForwarding=true"
Say "     然后 wsl --shutdown，再跑本脚本"
exit 1
