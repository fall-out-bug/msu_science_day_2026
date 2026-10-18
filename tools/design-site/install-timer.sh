#!/usr/bin/env bash
set -euo pipefail
root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
state=${SD2026_DESIGN_STATE_DIR:-"$HOME/.local/share/science-day/design-site"}
python=${SD2026_DESIGN_PYTHON:-"$root/.venv/bin/python"}
"$python" -c 'import markdown; assert markdown.__version__ == "3.11"'
test -f "$state/published/current/manifest.json"
curl --fail --silent --show-error --max-time 15 http://192.168.50.12:8080/design/manifest.json >/dev/null
mkdir -p "$state" "$HOME/.config/systemd/user"
# Keep the scheduler independent of work-in-progress changes in the checkout.
install -m 755 "$root/tools/design-site/publish.py" "$state/publisher.py"
cat > "$HOME/.config/systemd/user/science-day-design-publish.service" <<EOF
[Unit]
Description=Publish Science Day design documents from main
After=network-online.target

[Service]
Type=oneshot
ExecStart="$python" "$state/publisher.py" --repo "$root" --sync-main --state "$state" --verify-base http://192.168.50.12:8080
TimeoutStartSec=5min
UMask=0022
NoNewPrivileges=yes
EOF
cat > "$HOME/.config/systemd/user/science-day-design-publish.timer" <<'EOF'
[Unit]
Description=Check Science Day main for design updates

[Timer]
OnStartupSec=30s
OnUnitInactiveSec=2min
AccuracySec=10s
Unit=science-day-design-publish.service

[Install]
WantedBy=timers.target
EOF
systemctl --user daemon-reload
systemctl --user enable --now science-day-design-publish.timer
systemctl --user start science-day-design-publish.service
systemctl --user show science-day-design-publish.service -p Result -p ExecMainStatus
