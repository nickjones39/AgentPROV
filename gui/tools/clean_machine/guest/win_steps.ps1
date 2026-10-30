# The G5 §3 steps inside a Windows guest (D-862, D-867), run as the auto-logged-on user by a scheduled task (the
# window, the screenshot and the user's Credential Manager need the interactive session). The harness, not part of
# what is tested.
#   powershell -File win_steps.ps1 -Level V|W -Arch arm64|x64 -InDir C:\g5\in -OutDir C:\g5\out
# C:\g5\in holds the bundle zip, mini.tar.gz and, for level W, uv.zip and checkout.tar.gz. Each step appends one JSON
# line to OutDir\steps.jsonl; level W keeps each command's output under OutDir\w\. Step 5 stores a fixed dummy value
# (never a key) in this throwaway guest's Credential Manager and deletes it. done.txt is written last.
param([string]$Level = 'V', [string]$Arch = 'arm64', [switch]$LiveRuns, [string]$InDir = 'C:\g5\in',
      [string]$OutDir = 'C:\g5\out')
$ErrorActionPreference = 'Continue'
New-Item -ItemType Directory -Force -Path $OutDir, "$OutDir\w", C:\g5\run | Out-Null
$steps = "$OutDir\steps.jsonl"

function Tail([string]$s) { if ($null -eq $s) { '' } elseif ($s.Length -gt 2048) { $s.Substring($s.Length - 2048) } else { $s } }
function Record([int]$n, [string]$lvl, [bool]$pass, [datetime]$t, [hashtable]$evidence) {
  $line = [ordered]@{ step = $n; level = $lvl; pass = $pass; seconds = [math]::Round(((Get-Date) - $t).TotalSeconds, 2) }
  foreach ($k in $evidence.Keys) { $line[$k] = $evidence[$k] }
  Add-Content -Path $steps -Value ($line | ConvertTo-Json -Compress -Depth 8) -Encoding utf8
}
function Run([string]$name, [string]$exe, [string[]]$argv, [string]$stdin = $null, [int]$timeout = 900) {
  $out = "$OutDir\w\$name.stdout"; $err = "$OutDir\w\$name.stderr"
  # Start-Process joins ArgumentList with spaces and quotes nothing: an argument with a space must be quoted here
  $quoted = @($argv | ForEach-Object { if ($_ -match '[\s"]') { '"' + ($_ -replace '"', '\"') + '"' } else { $_ } })
  $p = @{ FilePath = $exe; ArgumentList = $quoted; RedirectStandardOutput = $out; RedirectStandardError = $err;
          NoNewWindow = $true; PassThru = $true }
  if ($null -ne $stdin) { Set-Content -Path "$OutDir\w\$name.stdin" -Value $stdin -NoNewline -Encoding ascii
                          $p.RedirectStandardInput = "$OutDir\w\$name.stdin" }
  $proc = Start-Process @p
  $null = $proc.Handle  # without the handle cached, a -PassThru process with redirection reports no ExitCode
  if (-not $proc.WaitForExit($timeout * 1000)) { $proc.Kill(); $code = -1 } else { $proc.WaitForExit(); $code = $proc.ExitCode }
  [pscustomobject]@{ code = $code; out = (Get-Content $out -Raw -ErrorAction SilentlyContinue);
                     err = (Get-Content $err -Raw -ErrorAction SilentlyContinue) }
}
function Json([string]$s) { try { $s | ConvertFrom-Json } catch { $null } }

# ------------------------------------------------------------------ level V: the bundle only (steps 1-3)
$zip = Get-ChildItem "$InDir\AgentPROV-windows-*.zip" | Select-Object -First 1
Expand-Archive -Path $zip.FullName -DestinationPath C:\g5\run\bundle -Force
$exe = 'C:\g5\run\bundle\AgentPROV\AgentPROV.exe'
tar -xzf "$InDir\mini.tar.gz" -C C:\g5\run
$partial = Get-ChildItem C:\g5\run -Directory | Where-Object Name -like '*.partial' | Select-Object -First 1
$corpus = Join-Path C:\g5\run ($partial.Name -replace '\.partial$', '')
$os = Get-CimInstance Win32_OperatingSystem
@{ caption = $os.Caption; version = $os.Version; build = $os.BuildNumber; arch = $env:PROCESSOR_ARCHITECTURE; tested_arch = $Arch;
   long_paths = (Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem').LongPathsEnabled;
   activation = (Get-CimInstance SoftwareLicensingProduct -Filter "PartialProductKey IS NOT NULL AND Name LIKE 'Windows%'" |
                 Select-Object -First 1).LicenseStatus } | ConvertTo-Json | Set-Content "$OutDir\guest.json" -Encoding utf8

$t = Get-Date; $env:QT_QPA_PLATFORM = 'offscreen'
$r = Run 'step1' $exe @('--smoke') -timeout 120
Remove-Item Env:QT_QPA_PLATFORM
Record 1 'V' ($r.code -eq 0) $t @{ exit = $r.code; stderr_tail = (Tail $r.err) }

$t = Get-Date
$gui = Start-Process -FilePath $exe -ArgumentList "`"$corpus`"" -PassThru -RedirectStandardError "$OutDir\step2-gui.stderr"
$found = $false; $deadline = (Get-Date).AddSeconds(30)
while ((Get-Date) -lt $deadline -and -not $gui.HasExited) {
  $gui.Refresh(); if ($gui.MainWindowTitle -like 'AgentPROV*') { $found = $true; break }; Start-Sleep 1 }
if ($found) { Start-Sleep 10 }
$alive = -not $gui.HasExited
Add-Type -AssemblyName System.Windows.Forms, System.Drawing
$b = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
$bmp = New-Object System.Drawing.Bitmap $b.Width, $b.Height
[System.Drawing.Graphics]::FromImage($bmp).CopyFromScreen($b.Location, [System.Drawing.Point]::Empty, $b.Size)
$bmp.Save("$OutDir\screenshot.png", [System.Drawing.Imaging.ImageFormat]::Png)
$title = $gui.MainWindowTitle
if ($alive) { [void]$gui.CloseMainWindow(); if (-not $gui.WaitForExit(15000)) { $gui.Kill() } }
Record 2 'V' ($found -and $alive) $t @{ platform_plugin = 'windows'; window_found = $found; window_title = $title;
  alive_after_load = $alive; executions = 'count on the screenshot (D-864)';
  stderr_tail = (Tail (Get-Content "$OutDir\step2-gui.stderr" -Raw -ErrorAction SilentlyContinue)) }

$t = Get-Date
New-Item -ItemType Directory -Force -Path C:\g5\run\preview-home | Out-Null
$r = Run 'step3' $exe @('--preview-helper', 'C:\g5\run\preview-home') -stdin '' -timeout 5
Record 3 'V' ($r.code -eq 0) $t @{ exit = $r.code; stderr_tail = (Tail $r.err) }

if ($Level -eq 'W') {
  # ---------------------------------------------------------------- level W: the checkout (steps 4-9)
  $env:UV_CACHE_DIR = 'C:\g5\uvc'; $env:UV_PYTHON_INSTALL_DIR = 'C:\g5\py'; $env:AGENTPROV_HOME = 'C:\g5\home'
  New-Item -ItemType Directory -Force -Path C:\g5\uv, C:\g5\src | Out-Null
  Expand-Archive -Path "$InDir\uv.zip" -DestinationPath C:\g5\uv -Force
  $env:Path = "C:\g5\uv;$env:Path"
  tar -xzf "$InDir\checkout.tar.gz" -C C:\g5\src
  Set-Location C:\g5\src
  function Ap([string]$name, [string[]]$argv, [string]$stdin = $null, [int]$timeout = 900) {
    Run $name 'uv' (@('run', '--no-sync', 'agentprov') + $argv) $stdin $timeout }

  $t = Get-Date
  $core = Run '4-sync-core' 'uv' @('sync', '--locked') -timeout 3600
  $guiSync = Run '4-sync-gui' 'uv' @('sync', '--locked', '--project', 'gui') -timeout 3600
  $info = Ap '4-info' @('info')
  $ok4 = ($core.code -eq 0 -and $guiSync.code -eq 0 -and $info.code -eq 0)
  Record 4 'W' $ok4 $t @{ sync_core = $core.code; sync_gui = $guiSync.code; info_exit = $info.code;
    python = @{ core = (Run '4-py-core' 'uv' @('run', '--no-sync', 'python', '-V')).out.Trim();
                gui = (Run '4-py-gui' 'uv' @('run', '--no-sync', '--project', 'gui', 'python', '-V')).out.Trim() };
    stderr_tail = $(if ($ok4) { '' } else { Tail ($core.err + $guiSync.err + $info.err) }) }

  if ($ok4) {
    $t = Get-Date
    $status = Json (Ap '5-status' @('keys', 'status', '--format', 'json')).out
    $names = Json (Ap '5-list0' @('keys', 'list', '--format', 'json')).out
    $name = if ($names) { $names.keys[0].name } else { $null }
    $set = Ap '5-set' @('keys', 'set', $name, '--stdin') -stdin "g5-dummy-value-not-a-key`n"
    $after = Json (Ap '5-list1' @('keys', 'list', '--format', 'json')).out
    $del = Ap '5-delete' @('keys', 'delete', $name, '--yes')
    $gone = Json (Ap '5-list2' @('keys', 'list', '--format', 'json')).out
    $stored = @(($after.keys | Where-Object name -eq $name).stored, ($gone.keys | Where-Object name -eq $name).stored)
    Record 5 'W' ($status.allowed -eq $true -and $set.code -eq 0 -and $del.code -eq 0 -and $stored[0] -eq $true -and
                  $stored[1] -eq $false) $t @{ status = $status; key_name = $name; set_exit = $set.code;
      delete_exit = $del.code; stored_after_set_then_delete = $stored; dummy_value = 'fixed test text, not a key' }

    $t = Get-Date
    Set-Content -Path C:\g5\src\tools\g5_sleeper.py -Encoding ascii -Value @'
import signal, sys, time
signal.signal(signal.SIGTERM, lambda *a: sys.exit(130))
print("started", flush=True)
time.sleep(float(sys.argv[-1]))
'@
    function Started([string]$name) { $d = Json (Ap $name (@('jobs', 'start', '--format', 'json') + $args)).out; $d }
    function Ended([string]$dir, [int]$s = 60) { $e = Join-Path $dir 'ended.json'; $end = (Get-Date).AddSeconds($s)
      while ((Get-Date) -lt $end) { if (Test-Path $e) { return (Get-Content $e -Raw | ConvertFrom-Json) }; Start-Sleep 1 }
      $null }
    $info = Started '6-start-info' '--' 'info'; $infoEnd = if ($info) { Ended $info.directory } else { $null }
    $sleeper = Started '6-start-sleeper' '--tool' 'tools/g5_sleeper.py' '--' '120'
    Start-Sleep 3
    $kill = Ap '6-kill' @('jobs', 'kill', '--yes', $sleeper.job_id); $killEnd = Ended $sleeper.directory
    # user decision 2026-10-28 (D-867): on Windows a graceful stop exists only through an agentprov job's control file
    # (P-2), and no offline agentprov command runs long enough to stop; info and kill decide the step
    Record 6 'W' ($infoEnd.outcome -eq 'ok' -and $killEnd.outcome -eq 'killed') $t @{
      ended = @{ info = $infoEnd; kill = $killEnd }; kill_exit = $kill.code;
      stop = 'not exercised on Windows (D-867); the control-file stop is covered by tests/jobs/test_jobs_windows_paths.py';
      harness = 'tools/g5_sleeper.py written into the guest checkout copy' }
    # the job folders (job.json, supervisor.txt, ended.json, stdout/stderr) are the evidence when a job misbehaves
    Copy-Item -Recurse -Force C:\g5\home\jobs "$OutDir\w\jobs" -ErrorAction SilentlyContinue

    if (-not $LiveRuns) {
      # user decisions 2026-10-28 and 2026-10-29 (D-867): live runs are not applicable on Windows in v0.1. ARM64: the
      # AgentDojo backend cannot be installed (torch has no win_arm64 wheel). x64: it builds, but the scripted cell's
      # worker dies and its reason is discarded. -LiveRuns runs steps 7-8 anyway (diagnosis only)
      $why = @{ arm64 = 'the AgentDojo backend cannot be installed on Windows ARM64';
                x64 = 'the backend builds on Windows x64 but its worker dies in the scripted cell' }[$Arch]
      foreach ($n in 7, 8) { Record $n 'W' $false (Get-Date) @{ applicable = $false;
        reason = "live runs need macOS or Linux in v0.1: $why (D-867)" } }
    } else {
      $t = Get-Date
      $build = Ap '7-backends-build' @('backends', 'build', 'agentdojo', '--allow-network') -timeout 5400
      $marker = Get-ChildItem C:\g5\home\envs\agentdojo-*\AGENTPROV_ENV.json -ErrorAction SilentlyContinue | Select-Object -First 1
      $m = if ($marker) { Get-Content $marker.FullName -Raw | ConvertFrom-Json } else { $null }
      $ok7 = ($build.code -eq 0 -and $m.status -eq 'complete' -and $m.sandbox_status -eq 'not_applicable')
      Record 7 'W' $ok7 $t @{ exit = $build.code; marker_status = $m.status; sandbox_status = $m.sandbox_status;
        stderr_tail = $(if ($ok7) { '' } else { Tail $build.err }) }

      $t = Get-Date
      $script = "$OutDir\w\script.json"
      Set-Content -Path $script -Encoding ascii -Value '[{"reply": "tool_calls", "calls": [{"name": "get_most_recent_transactions", "args": {"n": 100}, "id": "call_1"}]}, {"reply": "text", "content": "You spent 1050 in March 2022."}]'
      $run = Ap '8-run-scripted' @('run', 'agentdojo', '--corpus', 'C:\g5\home\corpora\g5-dev', '--campaign', 'g5',
        '--suite', 'banking', '--user-tasks', 'user_task_1', '--benign', 'only', '--model-display-name', 'Scripted Model',
        '--llm-script', $script, '--max-attempts', '1', '--keep-staging', '--json', '--progress', 'off') -timeout 1800
      $val = Ap '8-validate' @('validate', '--corpus', 'C:\g5\home\corpora\g5-dev.partial') -timeout 900
      if ($run.code -ne 0 -or $val.code -ne 0) {
        # the working corpus (manifest, register, sessions) says why a cell was inconclusive
        Copy-Item -Recurse -Force C:\g5\home\corpora\g5-dev.partial "$OutDir\w\corpus" -ErrorAction SilentlyContinue
        # the worker's own stderr is deleted with its staging folder, so the backend environment's interpreter imports
        # the heavy modules one by one: a native crash shows as an NTSTATUS exit code (0xC000001D illegal instruction)
        $envPy = Get-ChildItem C:\g5\home\envs\agentdojo-*\Scripts\python.exe -ErrorAction SilentlyContinue | Select-Object -First 1
        $diag = [ordered]@{}
        if ($envPy) {
          foreach ($m in 'numpy', 'torch', 'agentdojo', 'agentdojo.agent_pipeline', 'agentprov_backend.worker') {
            $d = Run "8-import-$m" $envPy.FullName @('-I', '-c', "import $m") -timeout 600
            $diag[$m] = @{ exit = $d.code; hex = ('0x{0:X8}' -f [BitConverter]::ToUInt32([BitConverter]::GetBytes([int32]$d.code), 0)); stderr_tail = (Tail $d.err) }
          }
        }
        Set-Content -Path "$OutDir\w\8-imports.json" -Value ($diag | ConvertTo-Json -Depth 6) -Encoding utf8
      }
      Record 8 'W' ($run.code -eq 0 -and $val.code -eq 0) $t @{ run_exit = $run.code; validate_exit = $val.code;
        counters = (Json $run.out).counters; stderr_tail = $(if ($run.code -eq 0 -and $val.code -eq 0) { '' } else {
        Tail ($run.err + $val.err) }) }

    }

    $t = Get-Date
    $probe = 'import json; from agentprov_gui.live.runspec import containment_choices, containment_line; print(json.dumps({c: containment_line(c) for c in containment_choices()}))'
    $c = Run '9-containment' 'uv' @('run', '--no-sync', '--project', 'gui', 'python', '-c', $probe)
    $offered = Json $c.out
    $keys = if ($offered) { @($offered.PSObject.Properties.Name | Sort-Object) } else { @() }
    Record 9 'W' (($keys -join ',') -eq 'dedicated-user,vm') $t @{ offered = $offered; expected = @('dedicated-user', 'vm');
      note = 'read from runspec.containment_choices (P-4), not by driving the Run Live dialog' }
  }
}
Set-Content -Path "$OutDir\done.txt" -Value 'done'
