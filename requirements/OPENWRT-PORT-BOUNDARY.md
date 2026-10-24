# R15 OpenWrt port boundary

The deliverable is an OpenWrt port, not an independent router distribution. The
owner clarified this explicitly on 24 October 2026. Retaining a vendor kernel is
an available compatibility route; it must not be confused with mainline R15
support or with the temporary stock-assisted diagnostic image.

| Component | Diagnostic prototype today | Port target |
|---|---|---|
| PID1 and boot | OEM BusyBox init; nested OpenWrt services | OpenWrt init/procd, generic preinit and inittab |
| Services | Explicit experiment process records | procd service instances and OpenWrt rc.common |
| Networking | Actual netifd/UCI with temporary handoff | Standard network configuration and netifd, R15 board/driver adapter |
| DHCP, DNS, routing | Compiled dnsmasq and legacy iptables qualified | OpenWrt dnsmasq/firewall services and their normal configuration |
| Persistent settings | Volatile configuration in the diagnostic image | Standard OpenWrt overlay/fstools/UCI if compatible with the retained kernel |
| Management | Key SSH and HTTPS qualified; GUI password login deferred | OpenWrt Dropbear, uhttpd, rpcd and LuCI |
| Updating | Narrow direct inactive-bank experiment writer | Validated R15 platform upgrade hooks and recovery procedure |
| Wi-Fi | Pre-created vendor netdevs; reviewed hostapd/supplicant | Existing vendor-port integration adapted to exact R15 radios |

## Concrete reference, not a board-image transplant

The locally retained [MR1500X port](https://github.com/adaasch/mr1500x-openwrt/tree/a07e5f0dbaa57ac2f9d166e11d2f9d775ab9db3d)
uses OpenWrt 21.02.7 userspace with a vendor 4.4 kernel, normal OpenWrt preinit,
procd, LuCI, UCI and a persistent overlay. Its build script compiles overlayfs as a
module against its vendor kernel because that kernel has overlayfs disabled.
This gives a concrete route to investigate before inventing a settings store.

Its Ethernet, kernel modules, NAND/NOR layout and radio initialization cannot be
copied onto the R15. That board is little-endian RTL8197F/NOR; this R15 is
big-endian RTL8198D/SPI-NAND with a dual-bank UBI layout. In particular, its NOR
rootfs_data partition module is not an R15 partition recipe.

Its safe wireless integration also demonstrates why unmodified generic
mac80211 setup cannot simply be enabled: the vendor drivers use pre-created
interfaces, and that port replaces interface-creation operations with a
reporting adapter and connects its hardware service to LuCI apply. Reuse the
integration pattern, not unsupported hardware commands.

## Work started

`build/stage-openwrt-base.py` verifies the exact OpenWrt 21.02.7 generic base-files
by SHA256 and Git blob identity, resolves build templates and emits a deterministic
offline tar. It includes standard preinit/inittab and console metadata, excludes
SDK board overrides, and explicitly remains non-flashable. The cache-backed build
adds standard fstools, UBI utilities, fwtool and opkg; the base tar is exported
separately until R15 platform composition is validated.

The R15 GPL configuration also disables overlayfs and module version CRCs. Neither
this configuration nor a matching vermagic alone establishes full ABI safety.
Building a matching overlay module, validating it against the running kernel,
choosing a preservation-safe upper filesystem and integrating the standard
mount_root path remain open. No new partition or formatting is authorized by the
existence of this source-only foundation.

## Reuse the evidence

Both-band radio/client/load/reconnect results, native tools, NAND geometry and
backups, wired management, guarded custom-filesystem boot and original-bank
fallback remain useful. They do not need to be repeated merely because standard
boot files are added offline. Test new PID1/board/storage integration when it is
concrete. Automatic radio startup in the temporary OEM-assisted image remains
unqualified; association fails after early AP/channel transitions. That failure
must not be reported as a failure of a completed native OpenWrt port.
