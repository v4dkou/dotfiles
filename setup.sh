#!/bin/bash
set -e

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_CONFIG="$REPO_DIR/.config"
REPO_LOCAL_BIN="$REPO_DIR/.local/bin"
HOME_CONFIG="${XDG_CONFIG_HOME:-$HOME/.config}"
HOME_LOCAL_BIN="$HOME/.local/bin"
INPUT_GROUP_ADDED=${DOTFILES_INPUT_GROUP_ADDED:-0}
BROWSER_DEFERRED=0

if [ "$(id -u)" -eq 0 ]; then
    echo "Run setup.sh as your login user, not as root." >&2
    exit 1
fi

backup_target() {
    local target="$1"
    local label="$2"
    local backup="$target.backup.$(date +%s%N)"

    mv "$target" "$backup"
    echo "Backed up existing $label to $backup"
}

link_path() {
    local source="$1"
    local target="$2"
    local label="$3"

    if [ -L "$target" ] && [ "$(readlink "$target")" = "$source" ]; then
        echo "$label already linked, skipping"
        return
    fi

    if [ -e "$target" ] || [ -L "$target" ]; then
        backup_target "$target" "$label"
    fi

    ln -s "$source" "$target"
    echo "Applied $label"
}

install_local_bins() {
    [ -d "$REPO_LOCAL_BIN" ] || return

    mkdir -p "$HOME_LOCAL_BIN"

    for SOURCE in "$REPO_LOCAL_BIN"/*; do
        [ -f "$SOURCE" ] || continue

        NAME="$(basename "$SOURCE")"
        TARGET="$HOME_LOCAL_BIN/$NAME"

        link_path "$SOURCE" "$TARGET" "$NAME"
    done

    link_path "$REPO_DIR/time.sh" "$HOME_LOCAL_BIN/dotfiles-time" "terminal clock"
}

install_local_bins
python3 "$REPO_DIR/scripts/install-desktop.py" "$REPO_DIR" || {
    result=$?
    if [ "$result" -ne 3 ]; then
        exit "$result"
    fi
    BROWSER_DEFERRED=1
}
mkdir -p "$HOME_CONFIG"

for SOURCE in "$REPO_CONFIG"/*; do
    [ -d "$SOURCE" ] || continue

    NAME="$(basename "$SOURCE")"
    TARGET="$HOME_CONFIG/$NAME"

    link_path "$SOURCE" "$TARGET" "$NAME config"
done

if command -v swaymsg >/dev/null 2>&1 && [ -n "${SWAYSOCK:-}" ]; then
    swaymsg reload || echo "Could not reload Sway; reload it manually after setup" >&2
else
    echo "Sway is not running in this shell; config will load on next Sway start"
fi

if [ "$INPUT_GROUP_ADDED" -eq 1 ]; then
    echo "Log out completely and log back in before sway-mouse-flick can read input devices."
fi

if [ "$BROWSER_DEFERRED" -eq 1 ]; then
    echo "Close Vivaldi and rerun the installer to finish applying browser preferences." >&2
    exit 3
fi
