# Build the Windows ARM64 bundle inside a clone of the Windows base (D-867), as .github/workflows/bundles.yml does on a
# runner. Runs as SYSTEM through UTM's guest agent; the harness, not part of what is tested.
#   powershell -File win_build.ps1 C:\g5\in C:\g5\out
# C:\g5\in holds uv.zip and checkout.tar.gz (a git archive). Downloads (the user's yes): uv's CPython 3.14 and the
# locked GUI environment from PyPI. No key, no .env.
param([string]$InDir, [string]$OutDir)
$ErrorActionPreference = 'Continue'
New-Item -ItemType Directory -Force -Path $OutDir, C:\g5\uv, C:\g5\src | Out-Null
# short paths for uv's cache and interpreters: LongPathsEnabled stays off in the base (P-5)
$env:UV_CACHE_DIR = 'C:\g5\uvc'; $env:UV_PYTHON_INSTALL_DIR = 'C:\g5\py'
Expand-Archive -Path "$InDir\uv.zip" -DestinationPath C:\g5\uv -Force
$env:Path = "C:\g5\uv;$env:Path"
tar -xzf "$InDir\checkout.tar.gz" -C C:\g5\src
Set-Location C:\g5\src
uv --version *> "$OutDir\uv-version.txt"
uv sync --locked --project gui *> "$OutDir\uv-sync.log"
uv run --project gui python gui/tools/gen_notices.py *> "$OutDir\gen-notices.log"
uv run --project gui python gui/tools/build_bundle.py --out C:\g5\build --source-archive "$InDir\checkout.tar.gz" *> "$OutDir\build-bundle.log"
$status = $LASTEXITCODE
Copy-Item C:\g5\build\bundle-report.json, C:\g5\build\pyinstaller.log -Destination $OutDir -ErrorAction SilentlyContinue
Copy-Item C:\g5\build\AgentPROV-*.zip -Destination $OutDir -ErrorAction SilentlyContinue
Set-Content -Path "$OutDir\done.txt" -Value $status
