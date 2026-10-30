#!/bin/sh
# Adds AgentPROV to this user's application menu (freedesktop desktop entry and hicolor icons), pointing at the
# AgentPROV executable beside this script. Writes only under ${XDG_DATA_HOME:-~/.local/share}; needs no root.
#   ./install-desktop-entry.sh             add or update the entry
#   ./install-desktop-entry.sh --remove    remove it again
set -eu
here=$(cd "$(dirname "$0")" && pwd -P)
data=${XDG_DATA_HOME:-$HOME/.local/share}
entry="$data/applications/org.agentprov.gui.desktop"
sizes="16x16 24x24 32x32 48x48 64x64 128x128 256x256 512x512 scalable"

if [ "${1:-}" = "--remove" ]; then
    rm -f "$entry"
    for size in $sizes; do rm -f "$data/icons/hicolor/$size/apps/agentprov.png" "$data/icons/hicolor/$size/apps/agentprov.svg"; done
    echo "AgentPROV removed from the application menu."
    exit 0
fi

case "$here" in
    *[\"\`\$\\%]* | *'
'*) echo "This folder's path has a character a desktop entry cannot quote (\" \` \$ \\ % or a newline): $here" >&2
        exit 1 ;;
esac
[ -x "$here/AgentPROV" ] || { echo "AgentPROV executable not found beside this script" >&2; exit 1; }

for size in $sizes; do
    src="$here/_internal/share/icons/hicolor/$size/apps"
    [ -d "$src" ] || continue
    mkdir -p "$data/icons/hicolor/$size/apps"
    cp "$src"/agentprov.* "$data/icons/hicolor/$size/apps/"
done
mkdir -p "$data/applications"
AGENTPROV_EXEC="\"$here/AgentPROV\"" awk '/^Exec=/ { print "Exec=" ENVIRON["AGENTPROV_EXEC"]; next } { print }' \
    "$here/org.agentprov.gui.desktop" > "$entry"
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$data/applications" || true
command -v gtk-update-icon-cache >/dev/null 2>&1 && gtk-update-icon-cache -q -t "$data/icons/hicolor" || true
echo "AgentPROV added to the application menu ($entry)."
