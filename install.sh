#!/usr/bin/env bash
# Install or update preferences from GitHub; setup.sh applies the checked-out files.
set -euo pipefail

if [[ $(id -u) == 0 ]]; then
    printf 'Run the installer as your desktop user, not root.\n' >&2
    exit 1
fi
for tool in git python3; do
    command -v "$tool" >/dev/null || { printf 'Install %s first.\n' "$tool" >&2; exit 1; }
done

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
