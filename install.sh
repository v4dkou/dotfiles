#!/usr/bin/env bash
# Fedora packages first; setup.sh then applies the preferences from GitHub.
set -euo pipefail

if [[ $(id -u) == 0 ]]; then
    printf 'Run the installer as your desktop user, not root.\n' >&2
    exit 1
fi
native_vivaldi_installed() {
    rpm -q --quiet vivaldi-stable
}

install_requirements() {
    local release_file=${DOTFILES_OS_RELEASE:-/etc/os-release}
    local os_id
    os_id=$(. "$release_file"; printf '%s' "$ID")
    if [[ $os_id != fedora ]]; then
        printf 'This pack is tested on Fedora Sway and Fedora Sway Atomic only.\n' >&2
        return 1
    fi

    local packages=(sway sway-config-fedora foot rofi-wayland
        swaybg swaylock swayidle grim slurp grimshot wf-recorder wl-clipboard jq
        python3-evdev pavucontrol NetworkManager bluez xdg-utils util-linux
        procps-ng gsettings-desktop-schemas xdg-desktop-portal-wlr xdg-desktop-portal-gtk
        pulseaudio-utils cmus qt5-qtbase-gui qt6-qtbase-gui)
    local tool
    for tool in git python3 curl; do
        command -v "$tool" >/dev/null || packages+=("$tool")
    done
    if ! native_vivaldi_installed; then
        packages+=(flatpak)
    fi
    local package missing=()
    for package in "${packages[@]}"; do
        rpm -q --quiet "$package" || missing+=("$package")
    done
    if (( ${#missing[@]} )); then
        printf 'Installing the Fedora packages used by this pack.\n'
        if [[ -e ${DOTFILES_OSTREE_BOOTED:-/run/ostree-booted} ]]; then
            sudo rpm-ostree install --assumeyes --idempotent --apply-live "${missing[@]}"
        else
            sudo dnf install -y "${missing[@]}"
        fi
    fi

    if ! native_vivaldi_installed && ! flatpak info com.vivaldi.Vivaldi >/dev/null 2>&1; then
        printf 'Installing Vivaldi from Flathub.\n'
        flatpak remote-add --user --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo
        flatpak install --user --assumeyes flathub com.vivaldi.Vivaldi
    fi

    local login_user
    login_user=$(id -un)
    if ! getent group input >/dev/null; then
        sudo groupadd --system input
    fi
    if ! id -nG "$login_user" | tr ' ' '\n' | grep -qx input; then
        sudo usermod -aG input "$login_user"
        export DOTFILES_INPUT_GROUP_ADDED=1
    fi
}

# Sourceable for package-plan tests; the downloaded entry point runs everything.
if [[ ${BASH_SOURCE[0]:-$0} != "$0" ]]; then
    return
fi
install_requirements

repo_url=${DOTFILES_REPO_URL:-https://github.com/v4dkou/dotfiles.git}
ref=${DOTFILES_REF:-master}
data_dir="${XDG_DATA_HOME:-$HOME/.local/share}/dotfiles"
repository="$data_dir/repository.git"
git check-ref-format "refs/heads/$ref" >/dev/null
mkdir -p "$data_dir/checkouts"

if [[ ! -e $repository ]]; then
    git clone --bare "$repo_url" "$repository"
fi
if [[ $(git --git-dir="$repository" remote get-url origin) != "$repo_url" ]]; then
    printf 'Existing installer repository has a different origin: %s\n' "$repository" >&2
    exit 1
fi
git --git-dir="$repository" fetch --no-tags origin \
    "+refs/heads/$ref:refs/remotes/origin/$ref"
revision=$(git --git-dir="$repository" rev-parse --verify "refs/remotes/origin/$ref^{commit}")
checkout="$data_dir/checkouts/$revision"

# Keep the installed source on disk so configuration symlinks remain valid.
# Each revision gets a worktree; existing checkouts and edits are preserved.
if [[ ! -e $checkout ]]; then
    git --git-dir="$repository" worktree add --detach "$checkout" "$revision"
fi
if [[ $(git -C "$checkout" rev-parse HEAD) != "$revision" ]] ||
    [[ -n $(git -C "$checkout" status --porcelain --untracked-files=all) ]]; then
    printf 'Installed checkout has local changes; preserved it at %s\n' "$checkout" >&2
    exit 1
fi
git -C "$checkout" merge-base --is-ancestor "refs/remotes/origin/$ref" HEAD
printf 'Applying dotfiles from GitHub (%s).\n' "${revision:0:12}"
exec bash "$checkout/setup.sh"
