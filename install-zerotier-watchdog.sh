#!/usr/bin/env bash
set -euo pipefail

sudo install -m 0755 /dev/stdin /usr/local/bin/zerotier-watchdog.sh <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

STATUS="$(zerotier-cli info 2>/dev/null | awk '{print $5}' || true)"

if [[ "$STATUS" == "OFFLINE" ]]; then
    logger -t zerotier-watchdog "ZeroTier offline, restarting zerotier-one.service"
    systemctl restart zerotier-one.service
fi
EOF

sudo tee /etc/systemd/system/zerotier-watchdog.service >/dev/null <<'EOF'
[Unit]
Description=Restart ZeroTier if offline

[Service]
Type=oneshot
ExecStart=/usr/local/bin/zerotier-watchdog.sh
EOF

sudo tee /etc/systemd/system/zerotier-watchdog.timer >/dev/null <<'EOF'
[Unit]
Description=Run ZeroTier watchdog every 30 seconds

[Timer]
OnBootSec=30s
OnUnitActiveSec=30s
AccuracySec=5s

[Install]
WantedBy=timers.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now zerotier-watchdog.timer
sudo systemctl restart zerotier-watchdog.timer

echo "Installed ZeroTier watchdog timer."
systemctl list-timers zerotier-watchdog.timer --no-pager
