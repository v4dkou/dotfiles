#!/usr/bin/env python3
"""Record real Vivaldi and Foot windows on an isolated 1368x800 Sway display."""
import json
import os
from pathlib import Path
import signal
import socket
import struct
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ROOT / "docs/demo.gif"
SCRATCH = Path(tempfile.mkdtemp(prefix="dotfiles-demo-"))
RUNTIME = SCRATCH / "runtime"
RUNTIME.mkdir(mode=0o700)
HOME_DIR = SCRATCH / "home"
HOME_DIR.mkdir()
ENV = {**os.environ, "HOME": str(HOME_DIR), "XDG_CONFIG_HOME": str(HOME_DIR / ".config"),
       "XDG_RUNTIME_DIR": str(RUNTIME), "GTK_THEME": "Adwaita-dark", "WLR_BACKENDS": "headless",
       "WLR_RENDERER": "pixman", "WLR_LIBINPUT_NO_DEVICES": "1"}
processes = []
fifo_handles = []


class VirtualPointer:
    """A pointer device on this private Wayland socket, never the user's seat."""
    def __init__(self, display):
        self.socket = socket.socket(socket.AF_UNIX)
        self.socket.settimeout(3)
        self.socket.connect(str(display))
        self.send(1, 1, struct.pack("<I", 2))  # wl_display.get_registry
        data = b""
        manager = None
        while manager is None:
            data += self.socket.recv(65536)
            while len(data) >= 8:
                obj, header = struct.unpack_from("<II", data)
                size, opcode = header >> 16, header & 65535
                if len(data) < size:
                    break
                payload, data = data[8:size], data[size:]
                if obj == 2 and opcode == 0:
                    name, length = struct.unpack_from("<II", payload)
                    interface = payload[8:8 + length - 1].decode()
                    if interface == "zwlr_virtual_pointer_manager_v1":
                        manager = name
        interface = b"zwlr_virtual_pointer_manager_v1\0"
        encoded = struct.pack("<I", len(interface)) + interface
        encoded += b"\0" * (-len(interface) % 4)
        self.send(2, 0, struct.pack("<I", manager) + encoded + struct.pack("<II", 1, 3))
        self.send(3, 0, struct.pack("<II", 0, 4))
        time.sleep(.2)

    def send(self, obj, opcode, payload=b""):
        self.socket.sendall(struct.pack("<II", obj, ((8 + len(payload)) << 16) | opcode) + payload)

    def timestamp(self):
        return int(time.monotonic() * 1000) & 0xffffffff

    def move(self, x, y):
        self.send(4, 1, struct.pack("<IIIII", self.timestamp(), round(x), round(y), 1368, 800))
        self.send(4, 4)

    def click(self, button):
        if button in ["button4", "button5"]:
            direction = -1 if button == "button4" else 1
            self.send(4, 5, struct.pack("<I", 0))
            self.send(4, 7, struct.pack("<IIii", self.timestamp(), 0, direction * 15 * 256, direction))
            self.send(4, 4)
        else:
            code = {"button1": 0x110, "button2": 0x112, "button3": 0x111}[button]
            for state in [1, 0]:
                self.send(4, 2, struct.pack("<III", self.timestamp(), code, state))
                self.send(4, 4)


def launch(args, name, env=ENV):
    log = (SCRATCH / (name + ".log")).open("w")
    p = subprocess.Popen(args, env=env, stdout=log, stderr=log, start_new_session=True)
    processes.append(p)
    return p


def run(args, env=ENV):
    return subprocess.run(args, env=env, text=True, capture_output=True, check=True).stdout


def ipc(command):
    result = json.loads(run(["swaymsg", "-s", ENV["SWAYSOCK"], command]))
    if any(not r.get("success") for r in result):
        raise RuntimeError(f"Sway rejected {command}: {result}")


def windows():
    d = json.loads(run(["swaymsg", "-s", ENV["SWAYSOCK"], "-t", "get_tree"]))
    found = []
    def visit(n, parent=None):
        if n.get("app_id"):
            n["_parent_rect"] = parent["rect"] if parent else n["rect"]
            found.append(n)
        for c in n.get("nodes", []) + n.get("floating_nodes", []):
            visit(c, n)
    visit(d)
    return found


def wait_for(test, seconds=15):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        value = test()
        if value:
            return value
        time.sleep(.1)
    raise RuntimeError(f"Demo did not become ready; logs: {SCRATCH}")


def browser(expression, kind="ui"):
    return json.loads(run(["node", "--experimental-websocket", str(ROOT / "scripts/demo-browser.mjs"), str(port), kind, expression]))


def chapter(text):
    browser(f"document.querySelector('#chapter').textContent={json.dumps(text)}", "pages")


def cursor(x, y):
    pointer.move(x, y)


def click(x, y, button="button1"):
    cursor(x, y)
    time.sleep(.05)
    pointer.click(button)


def tabs():
    return browser("[...document.querySelectorAll('#tabs-container .tab')].map(t=>({rect:t.getBoundingClientRect().toJSON(),filter:getComputedStyle(t.querySelector('.favicon img')).filter}))")


def terminal(number, subtitle):
    fifo = SCRATCH / f"terminal-{number}.fifo"
    os.mkfifo(fifo)
    handle = os.open(fifo, os.O_RDWR)
    fifo_handles.append(handle)
    scene = SCRATCH / f"terminal-{number}.sh"
    scene.write_text(f'''printf '\\033[2J\\033[H\\n  {subtitle}\\n\\n'
bash {str(ROOT / 'time.sh')!r}
while IFS= read -r line; do
    printf '\\033[38;5;108m$ \\033[0m'
    python3 -c 'import sys,time; [(print(c,end="",flush=True),time.sleep(.025)) for c in sys.argv[1]]' "$line"
    printf '\\n'
    eval "$line"
    printf '\\n'
done < {str(fifo)!r}
''')
    launch(["foot", "-c", str(ROOT / ".config/foot/foot.ini"), "-f", "monospace:size=13",
            "-a", f"dotfiles-demo-terminal-{number}", "-T", f"terminal {number}", "bash", str(scene)], f"foot-{number}")
    node = wait_for(lambda: next((n for n in windows() if n.get("app_id") == f"dotfiles-demo-terminal-{number}"), None))
    return node, handle


def type_command(handle, command):
    os.write(handle, (command + "\n").encode())


def decoration(node):
    n = next(n for n in windows() if n["id"] == node["id"])
    r, d = n["_parent_rect"], n["deco_rect"]
    return r["x"] + d["x"] + d["width"] / 2, r["y"] + d["y"] + max(1, d["height"] / 2)


try:
    bus = subprocess.run(["dbus-daemon", "--session", "--fork", "--print-address=1", "--print-pid=1"], env=ENV, text=True, capture_output=True, check=True).stdout.splitlines()
    ENV["DBUS_SESSION_BUS_ADDRESS"] = bus[0]
    bus_pid = int(bus[1])
    config = SCRATCH / "sway.conf"
    mouse_bindings = "\n".join(line for line in (ROOT / ".config/sway/config.d/custom.conf").read_text().splitlines() if line.startswith("bindsym --border "))
    config.write_text(f'''output HEADLESS-1 resolution 1368x800
output * bg #121212 solid_color
seat seat0 fallback true
xwayland disable
font pango:monospace 10
default_border pixel 1
default_floating_border normal
hide_edge_borders smart
client.focused #384537 #384537 #e8e8e6 #384537 #384537
client.unfocused #121212 #121212 #999999 #121212 #121212
{mouse_bindings}
workspace 1
''')
    launch(["sway", "--config", str(config)], "sway")
    sock = wait_for(lambda: next(RUNTIME.glob("sway-ipc.*.sock"), None))
    ENV["SWAYSOCK"] = str(sock)
    display = wait_for(lambda: next((p for p in RUNTIME.glob("wayland-*") if p.is_socket()), None))
    ENV["WAYLAND_DISPLAY"] = str(display)
    pointer = VirtualPointer(display)
    profile = SCRATCH / "browser"
    (profile / "Default").mkdir(parents=True)
    prefs = json.loads((ROOT / "vivaldi/preferences.json").read_text())
    prefs["vivaldi"]["appearance"]["css_ui_mods_directory"] = str(ROOT / "vivaldi")
    (profile / "Default/Preferences").write_text(json.dumps(prefs))
    (profile / "Local State").write_text(json.dumps({"browser": {"enabled_labs_experiments": ["vivaldi-css-mods@1"]}}))
    launch(["/usr/bin/vivaldi", "--ozone-platform=wayland", "--force-dark-mode", "--disable-gpu",
            f"--user-data-dir={profile}", "--no-first-run", "--no-default-browser-check", "--disable-background-networking",
            "--remote-debugging-port=0", "--debug-packed-apps", "about:blank"], "vivaldi")
    active_port = wait_for(lambda: (profile / "DevToolsActivePort") if (profile / "DevToolsActivePort").exists() else None)
    port = active_port.read_text().splitlines()[0]
    time.sleep(2)
    url = (ROOT / "docs/demo/index.html").as_uri()
    browser(f"new Promise(r=>chrome.tabs.update({{url:{json.dumps(url+'?topic=Docs')}}},()=>r(true)))")
    time.sleep(1)
    cursor(1200, 680)
    capture = SCRATCH / "capture.mp4"
    recorder = launch(["wf-recorder", "--no-dmabuf", "--no-damage", "-r", "10", "-o", "HEADLESS-1", "-c", "libx264", "-p", "crf=18", "-f", str(capture)], "recorder")
    time.sleep(2)
    chapter("02 / More tabs bring the header back.")
    for topic in ["Notes", "Mail"]:
        browser(f"new Promise(r=>chrome.tabs.create({{url:{json.dumps(url+'?topic='+topic)}}},t=>r(t.id)))")
    time.sleep(1)
    chapter("03 / Away: grayscale. Hover: full color.")
    cursor(1200, 680)
    time.sleep(1)
    before = tabs()
    assert all(t["filter"] == "grayscale(1)" for t in before), before
    target = before[1]["rect"]
    # Empty tab-strip space reveals color without opening a tab-preview tooltip.
    hover_x = before[-1]["rect"]["right"] + 160
    hover_y = target["y"] + target["height"] / 2
    cursor(hover_x, hover_y)
    time.sleep(1.5)
    hovered = tabs()
    assert all(t["filter"] == "none" for t in hovered), hovered
    chapter("04 / Scroll to switch. Middle-click to close.")
    for index in [0, 2]:
        r = tabs()[index]["rect"]
        click(r["x"] + 45, r["y"] + r["height"] / 2)
        cursor(hover_x, hover_y)
        time.sleep(.35)
    old_active = browser("new Promise(r=>chrome.tabs.query({active:true,currentWindow:true},t=>r(t[0].id)))")
    click(target["x"] + 45, target["y"] + target["height"] / 2, "button4")
    cursor(hover_x, hover_y)
    time.sleep(.8)
    assert browser("new Promise(r=>chrome.tabs.query({active:true,currentWindow:true},t=>r(t[0].id)))") != old_active
    for _ in range(2):
        r = tabs()[-1]["rect"]
        click(r["x"] + 45, r["y"] + r["height"] / 2, "button2")
        time.sleep(.6)
    assert len(tabs()) == 1
    chapter("05 / Sway tabs use the same click, scroll and middle-click gestures.")
    one, handle = terminal(1, "Tools, only when you need them.")
    type_command(handle, "command -v pavucontrol nmcli bluetoothctl")
    time.sleep(1.5)
    ipc(f'[con_id={one["id"]}] splitv')
    two, second_handle = terminal(2, "Another window. Another tab.")
    ipc(f'[con_id={two["id"]}] layout tabbed')
    type_command(second_handle, "echo 'Click / wheel / middle-click'")
    time.sleep(1.5)
    click(*decoration(one))
    time.sleep(.7)
    assert next(n["id"] for n in windows() if n.get("focused")) == one["id"]
    click(*decoration(two))
    time.sleep(.7)
    assert next(n["id"] for n in windows() if n.get("focused")) == two["id"]
    focused_before_scroll = next(n["id"] for n in windows() if n.get("focused"))
    click(*decoration(two), "button4")
    time.sleep(.7)
    assert next(n["id"] for n in windows() if n.get("focused")) != focused_before_scroll
    click(*decoration(two), "button2")
    time.sleep(.7)
    assert not any(n["id"] == two["id"] for n in windows())
    chapter("06 / No workspace bar. You keep the map.")
    ipc("workspace 2")
    three, third_handle = terminal(3, "Workspace 2 / keep the workspace map yourself.")
    type_command(third_handle, "nmcli -g STATE general")
    time.sleep(2)
    ipc("workspace 1")
    time.sleep(1)
    ipc(f'[con_id={one["id"]}] kill')
    chapter("01 / One tab. The page gets the whole window.")
    cursor(1200, 680)
    time.sleep(1)
    recorder.send_signal(signal.SIGINT)
    cursor(1205, 680)
    recorder.wait(timeout=20)
    if recorder.returncode:
        raise RuntimeError((SCRATCH / "recorder.log").read_text())
    OUT.parent.mkdir(parents=True, exist_ok=True)
    run(["ffmpeg", "-y", "-i", str(capture), "-filter_complex",
         "fps=8,split[a][b];[a]palettegen=stats_mode=full[p];[b][p]paletteuse=dither=none:diff_mode=rectangle",
         "-loop", "0", str(OUT)])
    (SCRATCH / "verification.json").write_text(json.dumps({"display": [1368, 800], "before_hover": before, "during_hover": hovered, "wheel_switched_browser_tab": True, "wheel_switched_sway_tab": True, "middle_click_closed_sway_tab": True}, indent=2))
    print(f"Recorded {OUT} ({OUT.stat().st_size:,} bytes); source capture and checks: {SCRATCH}")
finally:
    for handle in fifo_handles:
        os.close(handle)
    for p in reversed(processes):
        if p.poll() is None:
            os.killpg(p.pid, signal.SIGTERM)
            try:
                p.wait(timeout=4)
            except subprocess.TimeoutExpired:
                os.killpg(p.pid, signal.SIGKILL)
    if "bus_pid" in globals():
        try:
            os.kill(bus_pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
