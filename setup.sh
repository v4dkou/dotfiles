#!/bin/bash

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET="$HOME/.config/sway"
SOURCE="$REPO_DIR/.config/sway"

if [ -e "$TARGET" ] && [ ! -L "$TARGET" ]; then
    mv "$TARGET" "$TARGET.backup"
    echo "Backed up the existing sway config folder"
fi

if [ ! -L "$TARGET" ]; then
    ln -s "$SOURCE" "$TARGET"
    swaymsg reload
    echo "Applied sway config"
else
    echo "Sway config was already set up correctly, skipping"
fi

