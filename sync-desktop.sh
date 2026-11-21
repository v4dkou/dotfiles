#!/usr/bin/env bash
# Apply locally, or send just the desktop-theme/Vivaldi files over SSH.
set -euo pipefail
repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

if [[ ${1:-} == --help || $# -gt 1 ]]; then
    printf 'Usage: %s [user@host]\nRun with Vivaldi closed to also update its CSS preferences.\n' "$0"
    exit 0
fi

if [[ $# == 0 ]]; then
    exec python3 "$repo_dir/scripts/install-desktop.py" "$repo_dir"
fi

host=$1
if [[ $host == -* || ! $host =~ ^[a-zA-Z0-9_.@:-]+$ ]]; then
    printf 'Invalid SSH destination: %s\n' "$host" >&2
    exit 1
fi

# A deployment snapshot keeps the remote Git checkout and its local changes intact.
tar -C "$repo_dir" -cf - desktop-theme vivaldi scripts/install-desktop.py \
    scripts/verify-vivaldi.sh scripts/verify-vivaldi.mjs sync-desktop.sh README.md |
    ssh -o BatchMode=yes -o GSSAPIAuthentication=no -o PreferredAuthentications=publickey \
        -o ControlPath=none -o ConnectTimeout=10 "$host" '
        set -eu
        dest="$HOME/.local/share/dotfiles-desktop"
        mkdir -p "$dest/releases"
        release=$(mktemp -d "$dest/releases/release.XXXXXXXX")
        tar -xf - -C "$release"
        python3 "$release/scripts/install-desktop.py" "$release"
    '
