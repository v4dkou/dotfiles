#!/usr/bin/env python3
"""Install only the shared desktop theme and Vivaldi CSS, preserving other settings."""
import configparser
import io
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime

SOURCE = Path(sys.argv[1]).resolve()
HOME_DIR = Path.home()
CONFIG = Path(os.environ.get("XDG_CONFIG_HOME", HOME_DIR / ".config"))
STATE = Path(os.environ.get("XDG_STATE_HOME", HOME_DIR / ".local/state")) / "dotfiles-desktop"
BACKUP = STATE / "backups" / datetime.now().strftime("%Y%m%dT%H%M%S.%f")
changed = []


def backup(path):
    if path.exists() or path.is_symlink():
        dest = BACKUP / path.relative_to(HOME_DIR)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dest, follow_symlinks=False)


def write(path, content):
    """Replace a file atomically; never write through a file symlink."""
    if path.exists() and path.read_text() == content:
        return
    # Do not modify a Git checkout indirectly through a linked config directory.
    for parent in path.parents:
        if parent == HOME_DIR:
            break
        if (parent / ".git").exists():
            raise RuntimeError(f"Refusing to modify a Git checkout: {path}")
        if parent.is_symlink():
            raise RuntimeError(f"Refusing to write through a linked directory: {parent}")
    backup(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = path.stat().st_mode & 0o777 if path.exists() else 0o644
    fd, name = tempfile.mkstemp(prefix=".dotfiles-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as f:
            f.write(content)
        os.chmod(name, mode)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)
    changed.append(str(path))
    print(f"Updated {path}")


def run(*args, **kwargs):
    return subprocess.run(args, text=True, capture_output=True, **kwargs)


def install_theme():
    text = (SOURCE / "desktop-theme/environment.conf").read_text()
    values = dict(line.split("=", 1) for line in text.splitlines() if line and not line.startswith("#"))
    write(CONFIG / "environment.d/60-dotfiles-theme.conf", text)
    shell_file = CONFIG / "shell/desktop-theme.sh"
    write(shell_file, "# Managed by dotfiles setup.sh\n" + "".join(f"export {k}={v}\n" for k, v in values.items()))

    marker = "# BEGIN dotfiles desktop theme"
    block = (f'{marker}\n'
             'if [ -r "${XDG_CONFIG_HOME:-$HOME/.config}/shell/desktop-theme.sh" ]; then\n'
             '    . "${XDG_CONFIG_HOME:-$HOME/.config}/shell/desktop-theme.sh"\n'
             'fi\n# END dotfiles desktop theme\n')
    login = next((HOME_DIR / p for p in [".bash_profile", ".bash_login", ".profile"] if (HOME_DIR / p).exists()), HOME_DIR / ".profile")
    shells = {HOME_DIR / ".bashrc", login}
    zsh_dir = Path(os.environ.get("ZDOTDIR", HOME_DIR))
    if shutil.which("zsh") or any((zsh_dir / p).exists() for p in [".zshrc", ".zprofile"]):
        shells.update([zsh_dir / ".zshrc", zsh_dir / ".zprofile"])
    for path in sorted(shells):
        original = path.read_text() if path.exists() else ""
        original = re.sub(r"(?m)^# BEGIN dotfiles desktop theme\n.*?^# END dotfiles desktop theme\n?", "", original, flags=re.S)
        write(path, original.rstrip() + "\n\n" + block)

    for version in ["gtk-3.0", "gtk-4.0"]:
        path = CONFIG / version / "settings.ini"
        original = path.read_text() if path.exists() else ""
        parser = configparser.RawConfigParser()
        parser.optionxform = str
        parser.read_string(original)
        if not parser.has_section("Settings"):
            parser.add_section("Settings")
        parser.set("Settings", "gtk-theme-name", "Adwaita-dark")
        parser.set("Settings", "gtk-application-prefer-dark-theme", "true")
        out = io.StringIO()
        parser.write(out, space_around_delimiters=False)
        write(path, out.getvalue())

    if shutil.which("gsettings") and "org.gnome.desktop.interface" in run("gsettings", "list-schemas").stdout.splitlines():
        old = {}
        for key, value in [("gtk-theme", "Adwaita-dark"), ("color-scheme", "prefer-dark")]:
            previous = run("gsettings", "get", "org.gnome.desktop.interface", key)
            if previous.returncode == 0 and previous.stdout.strip() != repr(value):
                old[key] = previous.stdout.strip()
                BACKUP.mkdir(parents=True, exist_ok=True)
                (BACKUP / "gsettings.json").write_text(json.dumps(old, indent=2) + "\n")
                result = run("gsettings", "set", "org.gnome.desktop.interface", key, value)
                if result.returncode:
                    raise RuntimeError(result.stderr.strip())
                print(f"Set {key}={value}")
    if shutil.which("dbus-update-activation-environment"):
        result = run("dbus-update-activation-environment", "--systemd", *[f"{k}={v}" for k, v in values.items()])
        if result.returncode:
            print("Session bus unavailable; environment will apply at the next login.")


def main_browser_running(profile):
    if not (profile / "SingletonLock").is_symlink():
        return False
    for proc in Path("/proc").iterdir():
        if not proc.name.isdigit():
            continue
        try:
            if proc.stat().st_uid != os.getuid() or not (proc / "comm").read_text().strip().startswith("vivaldi"):
                continue
            raw = (proc / "cmdline").read_bytes().decode(errors="replace")
            args = [a for a in raw.split("\0") if a]
            # Vivaldi rewrites argv into a single, space-separated process title.
            if len(args) == 1:
                try:
                    args = shlex.split(args[0])
                except ValueError:
                    return True
            if any(a.startswith("--type=") for a in args):
                continue
            # Verification browsers always have an isolated --user-data-dir.
            explicit = next((a.split("=", 1)[1] for a in args if a.startswith("--user-data-dir=")), None)
            if "--user-data-dir" in args:
                index = args.index("--user-data-dir")
                explicit = args[index + 1] if index + 1 < len(args) else None
            if explicit is None or str(profile) in raw or str(profile.resolve()) in raw:
                return True
        except (OSError, ProcessLookupError):
            continue
    return False


def install_vivaldi():
    css = CONFIG / "vivaldi-css"
    before = len(changed)
    for source in sorted((SOURCE / "vivaldi").glob("*.css")):
        write(css / source.name, source.read_text())
    css_changed = len(changed) != before
    native = CONFIG / "vivaldi"
    flatpak = HOME_DIR / ".var/app/com.vivaldi.Vivaldi/config/vivaldi"
    available = {
        native: bool(shutil.which("vivaldi") or shutil.which("vivaldi-stable")),
        flatpak: bool(shutil.which("flatpak") and run("flatpak", "info", "com.vivaldi.Vivaldi").returncode == 0),
    }
    deferred = False
    for root in [native, flatpak]:
        if not root.is_dir() and not available[root]:
            continue
        profiles = [p / "Preferences" for p in root.iterdir() if p.name == "Default" or p.name.startswith("Profile ")] if root.is_dir() else []
        profiles = [p for p in profiles if p.is_file()]
        if not profiles and available[root]:
            profiles = [root / "Default/Preferences"]
        if not profiles:
            continue
        if main_browser_running(root):
            configured = all(p.exists() and json.loads(p.read_text()).get("vivaldi", {}).get("appearance", {}).get("css_ui_mods_directory") == str(css) for p in profiles)
            state = root / "Local State"
            labs = json.loads(state.read_text()).get("browser", {}).get("enabled_labs_experiments", []) if state.exists() else []
            override = HOME_DIR / ".local/share/flatpak/overrides/com.vivaldi.Vivaldi"
            granted = root == native or (override.exists() and str(css) + ":ro" in override.read_text())
            if configured and labs.count("vivaldi-css-mods@1") == 1 and not any(x.startswith("vivaldi-css-mods@") and x != "vivaldi-css-mods@1" for x in labs) and granted:
                print("Vivaldi CSS already configured." if not css_changed else "Vivaldi CSS updated; restart Vivaldi to reload the changed styles.")
                continue
            print(f"Vivaldi is running ({root}); close it and rerun this script to activate the staged CSS.")
            deferred = True
            continue
        if root == flatpak:
            if not shutil.which("flatpak"):
                raise RuntimeError("flatpak is required to grant Vivaldi read access to its CSS directory")
            override = HOME_DIR / ".local/share/flatpak/overrides/com.vivaldi.Vivaldi"
            permission = str(css) + ":ro"
            if not override.exists() or permission not in override.read_text():
                backup(override)
                result = run("flatpak", "override", "--user", f"--filesystem={permission}", "com.vivaldi.Vivaldi")
                if result.returncode:
                    raise RuntimeError(result.stderr.strip())
        for path in profiles:
            original = json.loads(path.read_text()) if path.exists() else {}
            data = json.loads(json.dumps(original))
            data.setdefault("vivaldi", {}).setdefault("appearance", {})["css_ui_mods_directory"] = str(css)
            # Avoid formatting-only changes on subsequent runs.
            if original != data:
                write(path, json.dumps(data, separators=(",", ":")) + "\n")
        local_state = root / "Local State"
        data = json.loads(local_state.read_text()) if local_state.exists() else {}
        experiments = data.setdefault("browser", {}).setdefault("enabled_labs_experiments", [])
        enabled = [x for x in experiments if not x.startswith("vivaldi-css-mods@")]
        enabled.append("vivaldi-css-mods@1")
        if experiments != enabled:
            data["browser"]["enabled_labs_experiments"] = enabled
            write(local_state, json.dumps(data, separators=(",", ":")) + "\n")
    return deferred


def main():
    if os.getuid() == 0:
        raise RuntimeError("Run this as your desktop user, not root")
    install_theme()
    deferred = install_vivaldi()
    if BACKUP.exists():
        print(f"Backups: {BACKUP}")
    print(f"Changed {len(changed)} files. Log out and back in for the full desktop environment to inherit the theme.")
    if deferred:
        sys.exit(3)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError, configparser.Error) as error:
        print(f"Error: {error}", file=sys.stderr)
        sys.exit(1)
