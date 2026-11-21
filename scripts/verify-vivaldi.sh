#!/usr/bin/env bash
# Exercise the actual browser UI on an isolated headless Sway desktop.
set -euo pipefail
repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
use_flatpak=0
if [[ ${1:-} == --flatpak ]]; then
    use_flatpak=1
    shift
fi
if [[ ${1:-} == --help || $# -gt 1 ]]; then
    printf 'Usage: %s [--flatpak] [evidence-directory]\nRequires Sway, Python 3, Node 20.10+, and Vivaldi.\n' "$0"
    exit 0
fi
for tool in sway python3 node setsid; do command -v "$tool" >/dev/null; done
node --experimental-websocket -e 'if(typeof WebSocket!=="function") throw new Error("Node 20.10+ required")'
mkdir -p "${XDG_CACHE_HOME:-$HOME/.cache}"
scratch=$(mktemp -d "${XDG_CACHE_HOME:-$HOME/.cache}/dotfiles-vivaldi-test.XXXXXXXX")
output=${1:-"$scratch/evidence"}
mkdir -p "$output" "$scratch/runtime" "$scratch/profile/Default" "$scratch/css"
output=$(cd "$output" && pwd)
chmod 700 "$scratch/runtime"
cp "$repo_dir"/vivaldi/*.css "$scratch/css/"
browser_pid=
sway_pid=
cleanup() {
    if [[ -n $browser_pid ]] && kill -0 "$browser_pid" 2>/dev/null; then
        kill -TERM -- "-$browser_pid" 2>/dev/null || true
    fi
    if [[ -n $sway_pid ]] && kill -0 "$sway_pid" 2>/dev/null; then
        kill -TERM "$sway_pid" 2>/dev/null || true
    fi
    printf 'Evidence: %s\nTest profile and logs: %s\n' "$output" "$scratch"
}
trap cleanup EXIT
printf 'output HEADLESS-1 resolution 1280x800\noutput * bg #222222 solid_color\nseat seat0 fallback true\ndefault_border none\nxwayland disable\n' > "$scratch/sway.conf"
python3 - "$scratch" <<'PY'
import json, pathlib, sys
p = pathlib.Path(sys.argv[1])
(p/'profile/Default/Preferences').write_text(json.dumps({'vivaldi': {'appearance': {'css_ui_mods_directory': str(p/'css'), 'density': True}, 'windows': {'use_native_decoration': False}}}))
(p/'profile/Local State').write_text(json.dumps({'browser': {'enabled_labs_experiments': ['vivaldi-css-mods@1']}}))
PY
env XDG_RUNTIME_DIR="$scratch/runtime" WLR_BACKENDS=headless WLR_RENDERER=pixman WLR_LIBINPUT_NO_DEVICES=1 \
    sway --config "$scratch/sway.conf" > "$scratch/sway.log" 2>&1 &
sway_pid=$!
wayland_socket=
for ((i=0; i<100; i++)); do
    for socket in "$scratch"/runtime/wayland-*; do
        if [[ -S $socket ]]; then wayland_socket=$socket; break; fi
    done
    [[ -n $wayland_socket ]] && break
    kill -0 "$sway_pid" 2>/dev/null || { cat "$scratch/sway.log" >&2; exit 1; }
    sleep 0.1
done
[[ -n $wayland_socket ]] || { printf 'Headless Sway did not create a Wayland socket\n' >&2; exit 1; }
browser=()
if [[ $use_flatpak == 1 ]]; then
    browser=(flatpak run "--filesystem=$scratch" com.vivaldi.Vivaldi)
elif command -v vivaldi >/dev/null; then
    browser=(vivaldi)
elif command -v vivaldi-stable >/dev/null; then
    browser=(vivaldi-stable)
else
    printf 'Vivaldi not found; use --flatpak for the Flatpak installation.\n' >&2
    exit 1
fi
WAYLAND_DISPLAY="$wayland_socket" setsid "${browser[@]}" --ozone-platform=wayland \
    "--user-data-dir=$scratch/profile" --no-first-run --no-default-browser-check \
    --disable-background-networking --remote-debugging-address=127.0.0.1 \
    --remote-debugging-port=0 --debug-packed-apps about:blank > "$scratch/vivaldi.log" 2>&1 &
browser_pid=$!
for ((i=0; i<200; i++)); do
    [[ -s $scratch/profile/DevToolsActivePort ]] && break
    kill -0 "$browser_pid" 2>/dev/null || { cat "$scratch/vivaldi.log" >&2; exit 1; }
    sleep 0.1
done
[[ -s $scratch/profile/DevToolsActivePort ]] || { cat "$scratch/vivaldi.log" >&2; exit 1; }
read -r port < "$scratch/profile/DevToolsActivePort"
node --experimental-websocket "$repo_dir/scripts/verify-vivaldi.mjs" "$port" "$repo_dir" "$output"
