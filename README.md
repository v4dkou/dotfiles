# dotfiles

Install or update these preferences on a Linux PC with one command:

```sh
curl -fsSL https://raw.githubusercontent.com/v4dkou/dotfiles/master/install.sh | bash
```

Run as your desktop user. Requires Bash, curl, Git and Python 3. The same command
fetches the latest version and reapplies it when run again. Source checkouts stay
on disk under `~/.local/share/dotfiles` so configuration links survive logout and
reboot. Existing Git clones and local edits are preserved.

The installer runs `setup.sh`, which applies:

- Sway configuration, keyboard shortcuts, mouse flick, Foot and Waybar.
- GTK 3/4 dark mode, the desktop/portal dark preference, and Qt's GTK integration.
- Shell startup hooks for Bash and existing/installed Zsh.
- Vivaldi CSS preferences for native and Flatpak installations, including hiding
  the entire header with one unstacked top tab without flicker on Vivaldi 8.3.

Vivaldi itself is installed separately. Close it before the first setup so its
preferences can be updated safely. An already configured browser can stay open
on later runs; restart it after CSS changes. Log out and back in after the first
installation so the whole desktop inherits the theme and input-group changes.

Existing configuration files and links are backed up before replacement. Theme,
shell and browser backups are under `~/.local/state/dotfiles-desktop/backups`;
replaced Sway, Foot and Waybar links/directories get adjacent `.backup.*` names.
Unrelated shell commands, GTK settings and browser profile data are preserved.
Privileged dependency/group steps print a warning if sudo is unavailable and
configuration installation continues.

From an existing checkout, the same installer step is:

```sh
bash setup.sh
```

## Checking the Vivaldi CSS

These checks use a separate browser profile on a headless Sway desktop:

```sh
./scripts/verify-vivaldi.sh /tmp/vivaldi-evidence
./scripts/verify-vivaldi.sh --flatpak /tmp/vivaldi-evidence
```

Requires Sway, Python 3, Node 20.10+ and Vivaldi. Screenshots and frame measurements
compare the original and fixed rules, including loading the CSS at startup and
repeatedly opening/closing a second tab. The fixed states must have zero header
visibility changes. Verified on native Vivaldi 7.7 and Flatpak Vivaldi 8.3.
