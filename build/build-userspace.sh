#!/usr/bin/env bash
# Compile userspace only. Never build a kernel or a router upgrade image.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
source "$ROOT/build/pins.env"
[[ $(uname -sm) == 'Linux x86_64' ]] || {
    echo 'This pinned SDK requires x86-64 Linux. Use the Actions workflow.' >&2; exit 2;
}
CACHE="$ROOT/.cache"
SDK="$CACHE/sdk-${SDK_SHA256:0:16}"
SOURCE="$ROOT/.work/openwrt-source"
mkdir -p "$CACHE" "$ROOT/.work" "$ROOT/artifacts"
if [[ ! -f "$CACHE/$SDK_NAME" ]]; then
    curl --fail --location --retry 3 "$SDK_URL" -o "$CACHE/$SDK_NAME.part"
    mv "$CACHE/$SDK_NAME.part" "$CACHE/$SDK_NAME"
fi
printf '%s  %s\n' "$SDK_SHA256" "$CACHE/$SDK_NAME" | sha256sum -c -
if [[ ! -d "$SDK/staging_dir" ]]; then
    mkdir -p "$SDK"
    tar -xJf "$CACHE/$SDK_NAME" --strip-components=1 -C "$SDK"
fi
if [[ ! -d "$SOURCE/.git" ]]; then
    git init -q "$SOURCE"
    git -C "$SOURCE" remote add origin https://github.com/openwrt/openwrt.git
    git -C "$SOURCE" fetch -q --depth 1 origin "$OPENWRT_COMMIT"
    git -C "$SOURCE" checkout -q --detach FETCH_HEAD
fi
[[ $(git -C "$SOURCE" rev-parse HEAD) == "$OPENWRT_COMMIT" ]]
# SDK supplies the compiler and staged headers. Matching source supplies core
# package recipes; no feeds tracking a moving branch are used.
# Preserve mtimes of unchanged recipes so test-only commits do not rebuild them.
rsync -rcpl "$SOURCE/package/" "$SDK/package/"
PATCH_CHANGED=0
PATCH_TARGET="$SDK/package/network/services/hostapd/patches/900-rtl8192cd-sta-assoc-reply.patch"
if ! cmp -s "$ROOT/patches/900-rtl8192cd-sta-assoc-reply.patch" "$PATCH_TARGET"; then
    cp "$ROOT/patches/900-rtl8192cd-sta-assoc-reply.patch" "$PATCH_TARGET"
    PATCH_CHANGED=1
fi
cp "$ROOT/build/userspace.config" "$SDK/.config"
make -C "$SDK" defconfig
for symbol in CONFIG_PACKAGE_wpad-basic=y CONFIG_PACKAGE_wpa-cli=y \
    CONFIG_PACKAGE_hostapd-utils=y CONFIG_PACKAGE_kmod-cfg80211=y \
    CONFIG_DRIVER_11N_SUPPORT=y CONFIG_DRIVER_11AC_SUPPORT=y \
    CONFIG_PACKAGE_busybox=y CONFIG_PACKAGE_procd=y CONFIG_PACKAGE_netifd=y \
    CONFIG_PACKAGE_uci=y CONFIG_PACKAGE_dropbear=y CONFIG_PACKAGE_dnsmasq=y \
    CONFIG_PACKAGE_jsonfilter=y CONFIG_DROPBEAR_ED25519=y \
    CONFIG_PACKAGE_firewall=y CONFIG_PACKAGE_iptables=y CONFIG_PACKAGE_ip6tables=y; do
    grep -qx "$symbol" "$SDK/.config" || { echo "Missing build setting: $symbol" >&2; exit 1; }
done
# Invalidate wpad only when the added patch changes. OpenWrt tracks configuration
# changes itself; the artifact collector independently checks the compiled marker.
if [[ "$PATCH_CHANGED" == 1 ]]; then
    make -C "$SDK" package/network/services/hostapd/clean
fi
make -C "$SDK" package/toolchain/compile -j2 V=s
make -C "$SDK" package/network/services/hostapd/compile -j2 V=s
for package in utils/busybox system/procd system/ubox system/ubus system/uci \
    network/config/netifd network/services/dropbear network/services/dnsmasq \
    utils/jsonfilter network/utils/iptables network/config/firewall; do
    make -C "$SDK" "package/$package/compile" -j2 V=s
done
python3 "$ROOT/build/collect-userspace.py" "$SDK" "$ROOT/artifacts"
python3 "$ROOT/build/stage-common-runtime.py" "$SOURCE/package/base-files/files" \
    "$ROOT/artifacts/rootfs" "$ROOT/artifacts/common-runtime.json"
python3 - "$ROOT/artifacts/build-report.json" "$ROOT/artifacts/common-runtime.json" <<'PY'
import json, sys
from pathlib import Path
path = Path(sys.argv[1])
report = json.loads(path.read_text())
report['common_service_helpers'] = json.loads(Path(sys.argv[2]).read_text())
root = path.parent / 'rootfs'
report['regular_file_bytes'] = sum(p.stat().st_size for p in root.rglob('*')
                                 if p.is_file() and not p.is_symlink())
path.write_text(json.dumps(report, indent=2) + '\n')
PY
# This hostapd version intentionally exits 1 for -v (hostapd/main.c).
# Require both that exact status and its expected output, not a blanket || true.
status=0
qemu-mips -L "$ROOT/artifacts/rootfs" "$ROOT/artifacts/rootfs/usr/sbin/hostapd" -v \
    > "$ROOT/artifacts/hostapd-version.txt" 2>&1 || status=$?
[[ "$status" == 1 ]]
grep -q '^hostapd v' "$ROOT/artifacts/hostapd-version.txt"
qemu-mips -L "$ROOT/artifacts/rootfs" "$ROOT/artifacts/rootfs/usr/sbin/wpa_supplicant" -v \
    > "$ROOT/artifacts/supplicant-version.txt" 2>&1
qemu-mips -L "$ROOT/artifacts/rootfs" "$ROOT/artifacts/rootfs/usr/sbin/wpa_cli" -v \
    > "$ROOT/artifacts/wpa-cli-version.txt" 2>&1
grep -q '^wpa_supplicant v' "$ROOT/artifacts/supplicant-version.txt"
grep -q '^wpa_cli v' "$ROOT/artifacts/wpa-cli-version.txt"
python3 - "$ROOT/artifacts/build-report.json" <<'PY'
import json, sys
from pathlib import Path
p = Path(sys.argv[1])
report = json.loads(p.read_text())
report['qemu_version_checks'] = {'hostapd': 'pass (expected exit 1)',
                                  'wpa_supplicant': 'pass', 'wpa_cli': 'pass'}
p.write_text(json.dumps(report, indent=2) + '\n')
PY
python3 "$ROOT/build/check-management.py" "$ROOT/artifacts/rootfs" "$ROOT/artifacts"
cp "$SDK/.config" "$ROOT/artifacts/sdk.config"
cp "$ROOT/build/pins.env" "$ROOT/artifacts/pins.env"
printf '%s\n' 'USERSPACE RESEARCH ONLY. NOT FIRMWARE. DO NOT FLASH.' \
    'QEMU version checks do not test radio drivers, Ethernet, or recovery.' \
    > "$ROOT/artifacts/DO-NOT-FLASH.txt"
tar -czf "$ROOT/artifacts/userspace-research.tar.gz" -C "$ROOT/artifacts/rootfs" .
(cd "$ROOT/artifacts" && find . -type f ! -path './rootfs/*' ! -name SHA256SUMS -print0 |
    sort -z | xargs -0 sha256sum > SHA256SUMS)
