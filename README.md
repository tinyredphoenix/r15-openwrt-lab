# D-Link R15 A1 OpenWrt research

Current direction: **port the normal OpenWrt system**, using the proven vendor
kernel/driver compatibility where necessary. The flashed OEM-PID1/chroot image is
a diagnostic prototype, not the finished port. See
[the port boundary](requirements/OPENWRT-PORT-BOUNDARY.md). Generic OpenWrt
base-files/preinit/inittab and standard fstools/UBI/package-management builds are
now being integrated; no replacement configuration framework is being developed.

Work toward a minimal routed wireless repeater for the Indian R15 A1, with wired management independent of the Wi-Fi uplink. **This public repository contains research source, not a downloadable installation image. A private, unit-specific stock-assisted image has booted on the owner’s R15.**

Observed stock firmware 1.06.10 uses RTL8198D, big-endian MIPS interAptiv, Linux 4.4.140; RTL8852AE (`wlan0`, PCI 10ec:8852) and RTL8192FE (`wlan1`, PCI 10ec:818c). Both create VXD client interfaces. The running stock kernel reports 256 MiB physical RAM (about 238.8 MiB MemTotal). These observations do not establish OpenWrt driver compatibility.

## What is implemented

- A local configuration renderer with separate wired management, SSH keys and DHCP that does not replace the laptop's Internet route.
- Radio lifecycle components: separate workers for cross-radio operation and a single paired controller for same-radio channel alignment, carrier/reassociation handling and netifd readiness. The controller has passed bounded native 5 GHz RAM integration on the retained OEM kernel/drivers; it uses interface-specific netifd calls without a global network reload.
- A read-only health probe for uptime, memory, Ethernet/Wi-Fi packet counters, exposed LED devices and voltage sensors. Missing sensors remain unknown; LED control and antenna-chain testing still require board verification.
- A read-only checker for the observed decrypted stock image's inner record lengths and checksums. It rejects corruption without claiming authenticity or flash compatibility; it always reports `flashable: false`.
- A pinned Linux SDK build for patched wireless tools and the management foundation: BusyBox, procd, ubus, UCI, netifd, Dropbear, dnsmasq and jsonfilter.
- Firewall3 and legacy IPv4/IPv6 iptables are selected for the generated routing/NAT policy. Their kernel dependencies are recorded as unverified requirements; SDK kernel modules are excluded. Version/help checks alone cannot establish filtering. Separately, retained-kernel RAM tests exercised temporary IPv4 filtering/NAT and DNS/DHCP; they do not qualify the generated firewall or custom boot.
- GitHub Actions caches the SDK/compiler and dependency build tree. The compiler is the official OpenWrt 21.02.7 `realtek/generic` MIPS big-endian userspace SDK, **not an R15 board target**.

The build verifies SDK SHA-256, configuration retention, ELF32 big-endian MIPS output, the compiled association-response marker, and tool version execution using QEMU user emulation. It checks the radio worker with target BusyBox ash syntax parsing and exercises Ed25519 key generation, parses the rendered management UCI files, and checks dnsmasq syntax with default-route/DNS advertising disabled. Test keys are temporary and never published. No SSH or DHCP server is started by these checks. It produces IPKs, source archives with the distribution package recipes/patches, and a partial userspace tree. **QEMU version tests do not test Wi-Fi, Ethernet, booting or recovery.** Kernel modules, router image packaging and the SDK target's unrelated board base-files are excluded. The partial tree lacks the R15 boot framework. The new coordinator is a source-level integration component, not target-tested boot code.

The old userspace baseline is an integration experiment with a vendor 4.4 kernel, not a maintained production release. No credentials, settings exports, owner logs, calibration tables or stock/vendor binaries belong in this repository or Actions cache.

## Run

Local logic checks (Python 3.9+):

```sh
python3 -m unittest discover -s prototype -v
python3 -m unittest discover -s tests -v
```

Build on x86-64 Linux, or run **Actions → R15 userspace research → Run workflow**:

```sh
bash build/build-userspace.sh
```

The SDK download is about 82 MiB; expanded compiler, dependencies and sources need additional disk space. The workflow uses a standard Ubuntu 24.04 runner and caches `.cache/`; no self-hosted runner, secret or paid runner is required. Download artifacts from the completed Actions run. Artifacts remain research-only even if all build checks pass.

For a small local download, run **Actions → Export compact research runtime** with a successful userspace run ID. It verifies the selected files against that run's checksum manifest on the cloud runner and exports only runtime packages, the userspace tarball and reports. Large source archives remain in the original build artifact; provenance links to that run. The compact output is also non-flashable.

## Boot integration and remaining release work

A private guarded bank1 image has booted from NAND using the exact OEM kernel,
drivers, PID1 and board initialization, with OpenWrt management under
`/opt/r15-openwrt`. Key-only SSH authenticated as root and certificate-pinned HTTPS
responded. Late OEM startup removed the management subnet route while keeping its
address; explicitly restoring that route fixed access. The bootstrap source now
maintains both the address and return route.

The original bank0 remains committed. Trial selection reset to its inactive
sentinel during boot; the default environment writer and known boot-acknowledgement
script are guarded against automatic commitment. The original environment tool is
preserved at an explicit operator path. These guards cover known vendor paths,
not every possible vendor write. The narrow inactive-bank writer validates identity,
current bank, volume geometry, existing contents, image hashes and readback; it does
not select a bank, reboot, format UBI, or write raw NAND.

A scoped network handoff has run alongside the flashed management services:
5 GHz association, DHCP, initial automatic channel alignment and interface-bound
Internet probes passed while SSH and HTTPS remained reachable. Its shutdown
restored stock services without stopping management. Earlier independent 5 GHz and
2.4 GHz phone tests retain their qualification; this integration does not repeat or
replace their load/reconnect evidence. The next private image adds automatic network
startup; that new startup path still requires its own first boot.

Remaining release work includes persistent owner settings/apply, automatic startup
qualification, live upstream channel changes, stability, a tested stock restoration
upload and a distributable installer/update path. No mainline kernel, Wi-Fi 6 AP,
full OpenWrt PID1 takeover or complete recovery guarantee is claimed. Private image,
credential, calibration, backup and device-log artifacts stay outside this repository.

The [boot integration audit](requirements/BOOT-INTEGRATION.md),
[recovery requirements](requirements/RECOVERY-AND-HARDWARE.md) and
[stock boot mechanisms](requirements/STOCK-BOOT-MECHANISM.md) retain the detailed
research history; the current status here supersedes their older pending labels.

## References and licensing

- [Official SDK and checksum](https://downloads.openwrt.org/releases/21.02.7/targets/realtek/generic/)
- [Pinned OpenWrt 21.02.7 source](https://github.com/openwrt/openwrt/tree/57a6d97ddf8f6541a52e0f8fad8c6f47685a1bc3)
- [Mercusys vendor-kernel/OpenWrt userspace port](https://github.com/adaasch/mr1500x-openwrt), including the related `rtl8192cd` association-response integration. Its router images are incompatible with the R15.
- [RTL960X OpenWrt platform work](https://github.com/jameywine/openwrt/tree/rtl9607c-dev), relevant to a future modern-kernel route; not proof of R15 radio support.

Original project glue is MIT licensed; imported hostapd patch retains BSD-3-Clause terms. See `LICENSE` and `patches/NOTICE.md`. Downloaded OpenWrt sources and packages retain their own licenses. This project is not affiliated with D-Link, Realtek, OpenWrt or the reference port's authors.

## Radio integration status

Private owner-authorized tests separately qualified bounded 5 GHz and 2.4 GHz routed repeating on the stock kernel/vendor drivers, using compiled station and DHCP/DNS tools with OEM AP services. An AP restart exposed a channel-selection/carrier failure, corrected manually in that experiment. The [same-radio coordinator](requirements/RADIO-COORDINATION.md) now models that recovery in code and renders a single-owner service. No private credentials, router captures or calibration data are included here. The production coordinator has since passed bounded 5 GHz RAM execution with our AP and station daemons, UCI rendering, initial automatic channel alignment, netifd DHCP and radio-bound Internet traffic. A phone received DHCP/DNS and forwarded Internet traffic through our AP and compiled iptables rules. The stock-assisted management filesystem has since booted; full OpenWrt PID1 takeover remains untested.

Final management direction: [OpenWrt administration](requirements/OPENWRT-MANAGEMENT.md) replaces the OEM interface. LuCI/RPC/HTTPS and optional PPPoE are being added to the cached build; radio UI integration and actual target startup remain unqualified. No private administrative credentials are published.

## Native integration status (2026-10-24)

The 5 GHz RAM experiment now uses our hostapd, supplicant, production UCI/coordinator,
netifd, dnsmasq and legacy iptables, with the exact stock kernel, radio drivers and
stock board initialization retained. Initial SSID-based channel alignment, WPA2/CCMP,
uplink DHCP, ten radio-bound Internet ping replies and a phone's DHCP/DNS/NAT path
passed. Three upstream reconnect cycles each passed ten interface-bound ping replies.
A phone completed 100 MB download and 100 MB upload with mobile data disabled;
R15 forwarding counters corroborated the radio path. Wired management remained
accessible and cleanup restored stock services. The client runner ended on a
termination signal, so these individual checks are recorded separately from its exit status.
The private evidence and per-unit settings are kept off this repository.

This is a bounded integration result, not an R15 firmware image or a modern-kernel
port. The test AP used 20 MHz 802.11n; 802.11ac/ax AP operation, live upstream channel
migration, multi-day stability and custom boot remain
separate qualifications. The 2.4 GHz production coordinator/client path has also passed phone WPA2
authentication, DHCP and a reported 100 MB transfer in each direction, corroborated
by forwarding counters. Three upstream reconnect cycles each passed ten interface-bound ping replies;
full cleanup returned zero and restored the stock AP and DHCP service. In-place AP
password reload was unreliable; a fresh controller session with the selected key
worked. Live settings application remains a separate qualification.

Key-only SSH passed after staging `/etc/shells`. GUI password authentication is
currently deferred, not removed or exposed without authentication. The account
collector now writes accepted login shells. Radio workers use only the WWAN ubus
up/down methods because the generic `ifup` wrapper reloads all network configuration.
