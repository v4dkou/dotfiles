#!/usr/bin/env bash
# One clock per user, owned by the first terminal that starts it.
run_clock() {
    [[ -t 1 ]] || return 0
    local lock_dir=${XDG_RUNTIME_DIR:-${XDG_CACHE_HOME:-$HOME/.cache}}
    mkdir -p "$lock_dir"
    umask 077
    exec 9>"$lock_dir/dotfiles-time.lock"
    flock -n 9 || return 0

    # Recognize a manually started copy of the old time.sh too.
    local pid args script_arg
    for pid in $(pgrep -u "$(id -u)" -f '(^|[ /])time\.sh([[:space:]]|$)' || true); do
        [[ $pid == "$BASHPID" || $pid == "$$" || $pid == "$PPID" ]] && continue
        [[ -r /proc/$pid/cmdline ]] || continue
        mapfile -d '' -t args < "/proc/$pid/cmdline" || continue
        script_arg=${args[1]:-}
        if [[ ${args[0]##*/} =~ ^(bash|sh|zsh)$ && ${script_arg##*/} == time.sh ]]; then
            return 0
        fi
    done

    trap 'exit 0' HUP INT TERM
    while printf '\033]0;%s%s\007' \
        "$(date '+%H:%M:%S')" \
        "$(df -h --output=avail /home /tmp | awk 'NR > 1 { printf " / %s", $1 }')"; do
        sleep 1 9>&-
    done
}

if [[ ${1:-} == --foreground ]]; then
    run_clock
else
    ( run_clock & )
fi
