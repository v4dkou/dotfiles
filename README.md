# Desktop configuration sync

Apply the shared GTK/Qt dark theme and Vivaldi CSS locally:

```sh
./sync-desktop.sh
```

Apply the same files to the new PC:

```sh
./sync-desktop.sh vadkou@10.111.0.6
```

The script uses SSH and Python 3; it does not need sudo. It preserves unrelated
shell and GTK settings, backs up changed files under
`~/.local/state/dotfiles-desktop/backups/`, and leaves both Git checkouts intact.
Rerunning it does not duplicate shell hooks or rewrite unchanged files. Remote
source snapshots live under `~/.local/share/dotfiles-desktop/releases/`.

The environment is installed for Bash, existing/installed Zsh, systemd user
services, and Fedora's Sway launcher. GTK 3/4 settings and the GNOME/portal dark
preference are also set. Qt uses the installed GTK 3 platform-theme integration
instead of `minimal` or the unavailable `qt5ct` plugin. Log out and back in to
apply the environment to the whole desktop; new login shells pick it up sooner.
Exports in a Sway `exec` command cannot change Sway's own environment; see
[Sway's environment documentation](https://github.com/swaywm/sway/wiki/Setting-Environmental-Variables).

Close Vivaldi before syncing to activate its CSS. If Vivaldi is running, the
script stages the CSS and theme, prints the profile it skipped, and exits 3.
Close the browser and rerun the same command. Both native and Flatpak profiles
are supported, with a read-only Flatpak grant for `~/.config/vivaldi-css`.
Only the CSS-directory preference and CSS experiment flag are changed; existing
profile data is retained.
Once the CSS folder is configured, unchanged reruns also work with Vivaldi open.
Later CSS edits are copied immediately; restart Vivaldi to reload those styles.

With one unstacked top tab, the entire header is hidden and occupies no space.
With two tabs, it returns. The header stays measurable while hidden because
Vivaldi 8.3 removes rendered tabs when `display: none` makes its width zero,
causing the old selector to repeatedly turn itself off and on.

## Visual regression check

Run the real Vivaldi UI on an isolated headless Sway desktop and save screenshots
and frame measurements without touching the normal browser session:

```sh
./scripts/verify-vivaldi.sh /tmp/vivaldi-evidence
# For the new PC's Flatpak installation, run on that PC:
./scripts/verify-vivaldi.sh --flatpak /tmp/vivaldi-evidence
```

Requires Sway, Python 3, Node 20.10+ (built-in WebSocket), and Vivaldi. Each run
creates its own browser profile and compositor. It checks the CSS loaded at
startup, compares the original rule with the fixed source, opens/closes a second tab, repeats that transition,
and checks three seconds of animation frames per state. Screenshots include
browser chrome. `report.json` records the browser version and observed changes;
each scenario also has six PNGs and its raw frame measurements. The old rule
can be stable on 7.7; the fixed states must be stable on both versions.
