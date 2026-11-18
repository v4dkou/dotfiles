#!/bin/bash
set -e

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_CONFIG="$REPO_DIR/.config"
REPO_LOCAL_BIN="$REPO_DIR/.local/bin"
HOME_CONFIG="$HOME/.config"
HOME_LOCAL_BIN="$HOME/.local/bin"
CURRENT_USER="${USER:-$(id -un)}"
INPUT_GROUP_ADDED=0

if [ "$(id -u)" -eq 0 ]; then
    echo "Run setup.sh as your login user, not as root." >&2
    exit 1
fi

backup_target() {
    local target="$1"
    local label="$2"
    local backup="$target.backup.$(date +%s)"

    mv "$target" "$backup"
    echo "Backed up existing $label to $backup"
}

link_path() {
    local source="$1"
    local target="$2"
    local label="$3"

    if [ -e "$target" ] && [ ! -L "$target" ]; then
        backup_target "$target" "$label"
    fi

    if [ -L "$target" ]; then
        if [ "$(readlink "$target")" = "$source" ]; then
            echo "$label already linked, skipping"
        else
            ln -sfn "$source" "$target"
            echo "Updated $label link"
        fi
    else
        ln -s "$source" "$target"
        echo "Applied $label"
    fi
}

install_python_evdev() {
    if python3 -c "import evdev" >/dev/null 2>&1; then
        echo "python-evdev already installed"
        return
    fi

    echo "Installing python-evdev dependency"

    # Atomic (ostree) systems may still ship a dnf binary that refuses to install
    if [ -e /run/ostree-booted ] && command -v rpm-ostree >/dev/null 2>&1; then
        sudo rpm-ostree install --idempotent --apply-live python3-evdev
    elif command -v dnf >/dev/null 2>&1; then
        sudo dnf install -y python3-evdev
    elif command -v apt-get >/dev/null 2>&1; then
        sudo apt-get update
        sudo apt-get install -y python3-evdev
    elif command -v pacman >/dev/null 2>&1; then
        sudo pacman -S --needed python-evdev
    elif command -v zypper >/dev/null 2>&1; then
        sudo zypper install -y python3-evdev
    else
        echo "Could not find a supported package manager for python-evdev" >&2
        echo "Install python-evdev manually before using sway-mouse-flick" >&2
    fi
}

ensure_input_group() {
    if ! getent group input >/dev/null 2>&1; then
        echo "No input group found; skipping input group membership setup" >&2
        return
    fi

    if id -nG "$CURRENT_USER" | tr ' ' '\n' | grep -qx input; then
        echo "$CURRENT_USER already belongs to the input group"
        return
    fi

    sudo usermod -aG input "$CURRENT_USER" || return 1
    INPUT_GROUP_ADDED=1
    echo "Added $CURRENT_USER to the input group"
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
}

# Root-requiring steps are non-fatal so config links still apply without sudo
install_python_evdev || echo "Skipped python-evdev install; sway-mouse-flick will not work until it is installed" >&2
ensure_input_group || echo "Skipped input group setup; sway-mouse-flick needs it to read input devices" >&2
install_local_bins
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
