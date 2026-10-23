# D-Link R15 A1 OpenWrt research

Work toward a minimal cross-radio wireless repeater for the Indian R15 A1, with wired management independent of the Wi-Fi uplink. **No bootable or flashable R15 firmware is available here. Do not upload these artifacts to a router.**

Observed stock firmware 1.06.10 uses RTL8198D, big-endian MIPS interAptiv, Linux 4.4.140; RTL8852AE (`wlan0`, PCI 10ec:8852) and RTL8192FE (`wlan1`, PCI 10ec:818c). Both create VXD client interfaces. Physical RAM capacity is not established. These observations do not establish OpenWrt driver compatibility.

## What is implemented

- A local configuration renderer with separate wired management, SSH keys and DHCP that does not replace the laptop's Internet route.
- A radio worker with separate AP and supplicant supervision, netifd uplink attachment after association, disconnect cleanup and reconnect handling. It does not restart wired management.
- A read-only health probe for uptime, memory, Ethernet/Wi-Fi packet counters, exposed LED devices and voltage sensors. Missing sensors remain unknown; LED control and antenna-chain testing still require board verification.
- A read-only checker for the observed decrypted stock image's inner record lengths and checksums. It rejects corruption without claiming authenticity or flash compatibility; it always reports `flashable: false`.
- A pinned Linux SDK build for patched wireless tools and the management foundation: BusyBox, procd, ubus, UCI, netifd, Dropbear, dnsmasq and jsonfilter.
- Firewall3 and legacy IPv4/IPv6 iptables are selected for the generated routing/NAT policy. Their kernel dependencies are recorded as unverified requirements; SDK kernel modules are excluded. Version/help checks cannot establish packet filtering on the R15.
- GitHub Actions caches the SDK/compiler and dependency build tree. The compiler is the official OpenWrt 21.02.7 `realtek/generic` MIPS big-endian userspace SDK, **not an R15 board target**.

The build verifies SDK SHA-256, configuration retention, ELF32 big-endian MIPS output, the compiled association-response marker, and tool version execution using QEMU user emulation. It checks the radio worker with target BusyBox ash syntax parsing and exercises Ed25519 key generation, parses the rendered management UCI files, and checks dnsmasq syntax with default-route/DNS advertising disabled. Test keys are temporary and never published. No SSH or DHCP server is started by these checks. It produces IPKs, source archives with the distribution package recipes/patches, and a partial userspace tree. **QEMU version tests do not test Wi-Fi, Ethernet, booting or recovery.** Kernel modules, router image packaging and the SDK target's unrelated board base-files are excluded. The partial tree lacks the R15 boot framework.

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

## What still blocks firmware

The runtime includes five hash-pinned generic OpenWrt shell helpers used by init scripts and hotplug, with BusyBox syntax checks. These provide service plumbing only. Boot entrypoints, filesystem mounts and R15 switch initialization remain unimplemented; SDK board base-files, generic wireless startup and firmware upgraders are excluded.

The [recovery and hardware acceptance requirements](requirements/RECOVERY-AND-HARDWARE.md) track wired failsafe, independent restoration to stock, safe firmware updates, power/watchdog behavior, LEDs, Ethernet, radio RX/TX, scanning, broadcasting and Wi-Fi security. These are pre-flash requirements, not completed hardware tests.

The [stock boot-mechanism findings](requirements/STOCK-BOOT-MECHANISM.md) document paired logical kernel/rootfs sections, `sw_tryactive`/`sw_commit`, and the inner-record integrity checker. Bootloader rollback and the live flash layout remain unverified.

R15 board initialization and per-unit MAC/calibration handling; complete runtime flash/UBI map; kernel/driver/userspace compatibility; watchdog boot acknowledgement; actual wired management boot testing; owner SSH provisioning; and independently verified bootloader recovery. D-Link's GPL README provides a recovery-entry recipe, but restoration on the actual unit has not been demonstrated. No firmware write is implemented by this project.

## References and licensing

- [Official SDK and checksum](https://downloads.openwrt.org/releases/21.02.7/targets/realtek/generic/)
- [Pinned OpenWrt 21.02.7 source](https://github.com/openwrt/openwrt/tree/57a6d97ddf8f6541a52e0f8fad8c6f47685a1bc3)
- [Mercusys vendor-kernel/OpenWrt userspace port](https://github.com/adaasch/mr1500x-openwrt), including the related `rtl8192cd` association-response integration. Its router images are incompatible with the R15.
- [RTL960X OpenWrt platform work](https://github.com/jameywine/openwrt/tree/rtl9607c-dev), relevant to a future modern-kernel route; not proof of R15 radio support.

Original project glue is MIT licensed; imported hostapd patch retains BSD-3-Clause terms. See `LICENSE` and `patches/NOTICE.md`. Downloaded OpenWrt sources and packages retain their own licenses. This project is not affiliated with D-Link, Realtek, OpenWrt or the reference port's authors.
