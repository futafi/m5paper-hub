#!/bin/sh
# Deploy the hub and the sample feeds to a Linux machine over SSH.
#
#   hub/deploy.sh user@host                 install or update, then restart
#   hub/deploy.sh --pull-config user@host   copy the deployed config.toml back
#   SSH_KEY=~/.ssh/id_x hub/deploy.sh ...   use a specific key
#
# The target needs Python 3.11+ and systemd; no sudo and no pip. Pillow is
# fetched here (with uv) into hub/vendor for the target's Python and copied
# over. The deployed config.toml is never overwritten.
set -eu
cd "$(dirname "$0")/.."
SSH="ssh -o BatchMode=yes${SSH_KEY:+ -i $SSH_KEY}"
DEST=.local/share/m5paper-hub

if [ "${1:-}" = "--pull-config" ]; then
    [ -n "${2:-}" ] || { echo "usage: $0 --pull-config user@host" >&2; exit 2; }
    $SSH "$2" "cat $DEST/config.toml" > hub/config.deployed.toml
    echo "Saved hub/config.deployed.toml"
    exit 0
fi
[ -n "${1:-}" ] || { echo "usage: $0 user@host" >&2; exit 2; }
TARGET=$1

PYVER=$($SSH "$TARGET" 'python3 -c "import sys; print(\"%d.%d\" % sys.version_info[:2])"')
ARCH=$($SSH "$TARGET" 'uname -m')
if [ ! -f "hub/vendor/.python-$PYVER-$ARCH" ]; then
    rm -rf hub/vendor
    uv pip install --quiet --target hub/vendor --python-version "$PYVER" \
        --python-platform "$ARCH-manylinux_2_28" --only-binary :all: pillow
    touch "hub/vendor/.python-$PYVER-$ARCH"
fi
mkdir -p hub/fonts
for font in NotoSansCJK-Regular.ttc NotoSansCJK-Bold.ttc; do
    if [ ! -f "hub/fonts/$font" ]; then
        if [ -f "/usr/share/fonts/opentype/noto/$font" ]; then
            cp "/usr/share/fonts/opentype/noto/$font" hub/fonts/
        else
            echo "warning: $font not found here; put it in hub/fonts/ for Japanese text" >&2
        fi
    fi
done

$SSH "$TARGET" "mkdir -p $DEST/hub $DEST/feeds .config/systemd/user"
rsync -a --delete -e "$SSH" --exclude __pycache__ --exclude 'config*.toml' --exclude 'test_*' \
    hub/ "$TARGET:$DEST/hub/"
rsync -a --delete -e "$SSH" --exclude __pycache__ feeds/ "$TARGET:$DEST/feeds/"
$SSH "$TARGET" "cat > $DEST/config.example.toml" < hub/config.example.toml
$SSH "$TARGET" "cat > .config/systemd/user/m5paper-hub.service" < hub/m5paper-hub.service
$SSH "$TARGET" "cat > .config/systemd/user/m5paper-sysmon.service" < feeds/m5paper-sysmon.service
$SSH "$TARGET" "
    [ -f $DEST/config.toml ] || cp $DEST/config.example.toml $DEST/config.toml
    systemctl --user daemon-reload
    systemctl --user enable --quiet m5paper-hub.service m5paper-sysmon.service
    systemctl --user restart m5paper-hub.service m5paper-sysmon.service
    sleep 2
    systemctl --user --no-pager --lines=5 status m5paper-hub.service | head -12
"
echo "For the units to survive logout and reboot: loginctl enable-linger (once, on the target)."
