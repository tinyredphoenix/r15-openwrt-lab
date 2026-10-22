#!/usr/bin/env bash
# Compile userspace only. Never build a kernel or a router upgrade image.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
source "$ROOT/build/pins.env"
[[ $(uname -sm) == 'Linux x86_64' ]] || {
    echo 'This pinned SDK requires x86-64 Linux. Use the Actions workflow.' >&2; exit 2;
}
CACHE="$ROOT/.cache"
SDK="$CACHE/sdk"
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
cp -a "$SOURCE/package/." "$SDK/package/"
cp "$ROOT/patches/900-rtl8192cd-sta-assoc-reply.patch" \
    "$SDK/package/network/services/hostapd/patches/"
cp "$ROOT/build/userspace.config" "$SDK/.config"
make -C "$SDK" defconfig
for symbol in CONFIG_PACKAGE_wpad-basic=y CONFIG_PACKAGE_wpa-cli=y \
    CONFIG_PACKAGE_hostapd-utils=y CONFIG_PACKAGE_kmod-cfg80211=y \
    CONFIG_DRIVER_11N_SUPPORT=y CONFIG_DRIVER_11AC_SUPPORT=y; do
    grep -qx "$symbol" "$SDK/.config" || { echo "Missing build setting: $symbol" >&2; exit 1; }
done
# Rebuild patched wpad; retain compiler, downloads and dependency builds in cache.
make -C "$SDK" package/network/services/hostapd/clean
make -C "$SDK" package/toolchain/compile -j2 V=s
make -C "$SDK" package/network/services/hostapd/compile -j2 V=s
python3 "$ROOT/build/collect-userspace.py" "$SDK" "$ROOT/artifacts"
qemu-mips -L "$ROOT/artifacts/rootfs" "$ROOT/artifacts/rootfs/usr/sbin/hostapd" -v \
    > "$ROOT/artifacts/hostapd-version.txt" 2>&1
qemu-mips -L "$ROOT/artifacts/rootfs" "$ROOT/artifacts/rootfs/usr/sbin/wpa_supplicant" -v \
    > "$ROOT/artifacts/supplicant-version.txt" 2>&1
qemu-mips -L "$ROOT/artifacts/rootfs" "$ROOT/artifacts/rootfs/usr/sbin/wpa_cli" -v \
    > "$ROOT/artifacts/wpa-cli-version.txt" 2>&1
cp "$SDK/.config" "$ROOT/artifacts/sdk.config"
cp "$ROOT/build/pins.env" "$ROOT/artifacts/pins.env"
printf '%s\n' 'USERSPACE RESEARCH ONLY. NOT FIRMWARE. DO NOT FLASH.' \
    'QEMU version checks do not test radio drivers, Ethernet, or recovery.' \
    > "$ROOT/artifacts/DO-NOT-FLASH.txt"
tar -czf "$ROOT/artifacts/userspace-research.tar.gz" -C "$ROOT/artifacts/rootfs" .
(cd "$ROOT/artifacts" && find . -type f ! -path './rootfs/*' ! -name SHA256SUMS -print0 |
    sort -z | xargs -0 sha256sum > SHA256SUMS)
