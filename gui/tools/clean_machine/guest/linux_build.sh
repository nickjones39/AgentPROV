#!/bin/sh
# Build the Linux bundle inside a clone of the base (D-865), as .github/workflows/bundles.yml does on a runner.
#   sh linux_build.sh IN_DIR OUT_DIR GLIBC_FLOOR PACKAGES...
# IN_DIR holds uv.tar.gz and checkout.tar.gz (a git archive). Downloads: the packages from Ubuntu's mirrors, uv's
# CPython and the locked GUI environment from PyPI. No key, no .env.
set -eu
in_dir=$1; out_dir=$2; floor=$3; shift 3
mkdir -p "$out_dir" "$HOME/uv" "$HOME/src"
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends "$@" >"$out_dir/apt.log" 2>&1
tar -xzf "$in_dir/uv.tar.gz" -C "$HOME/uv" --strip-components=1
export PATH="$HOME/uv:$PATH"
tar -xzf "$in_dir/checkout.tar.gz" -C "$HOME/src"
cd "$HOME/src"
uv --version >"$out_dir/uv-version.txt"
uv sync --locked --project gui >"$out_dir/uv-sync.log" 2>&1
uv run --project gui python gui/tools/gen_notices.py >"$out_dir/gen-notices.log" 2>&1
status=0
uv run --project gui python gui/tools/build_bundle.py --out "$HOME/g5-build" --glibc-floor "$floor" \
    --source-archive "$in_dir/checkout.tar.gz" \
    >"$out_dir/build-bundle.log" 2>&1 || status=$?
cp "$HOME/g5-build/bundle-report.json" "$HOME/g5-build/pyinstaller.log" "$out_dir/" 2>/dev/null || true
cp "$HOME"/g5-build/AgentPROV-linux-*.tar.gz "$out_dir/" 2>/dev/null || true
exit "$status"
