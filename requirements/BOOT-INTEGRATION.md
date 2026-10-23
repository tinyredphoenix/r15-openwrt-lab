# R15 boot integration gaps

These findings compare the compiled procd source (`2cfc26f8456a4d5ba3836c914a742f3d00bad781`), private filesystem inventory and the R15 GPL kernel configuration. They do not establish the running router's exact kernel configuration. No boot code or watchdog operation was executed.

## Management startup

The compiled `/sbin/init` runs early device/mount setup, initializes its watchdog interface, attempts `/sbin/kmodloader /etc/modules-boot.d/`, then runs `/bin/sh /etc/preinit`. When that child exits, `spawn_procd()` executes `/sbin/procd`; it does not reject a failed preinit exit status. Reaching procd therefore does not establish that preinit succeeded.

Procd reads `/etc/inittab`. Its `sysinit` handler dispatches the matching `/etc/rc.d/S*` entries in order. It does not discover and start every file in `/etc/init.d`. The private prototype currently lacks preinit, inittab and an enabled service sequence. Copying service scripts and libraries alone cannot provide a management boot.

Package `Require-User` fields specify identities for ubus, dnsmasq, logd, network and ntp, plus audio/dialout groups. The collector now generates those explicit identities and baseline root/nobody records without executing package installation scripts. Password fields are locked; no shared password or owner SSH key is installed. Package installation scripts are still excluded, so any other installation side effects require separate review.

Before enabling services, establish writable runtime directories and account ownership, host-key generation, owner SSH authorization, and R15 Ethernet initialization. Verify the labelled management socket with both radios unavailable. Do not enable generic wireless startup as part of a management-only test.

The DHCP client and dnsmasq startup also require `/bin/ipcalc.sh`, which comes from base-files rather than their IPKs. This helper is now staged from the pinned source. Target BusyBox checks exercise its embedded AWK against dotted netmasks, CIDR input and the management DHCP range; no DHCP process is started.

## Filesystem assumptions

The supplied GPL kernel configuration disables `CONFIG_OVERLAY_FS` and `CONFIG_BLK_DEV_INITRD`; UBIFS, SquashFS and tmpfs are enabled. An embedded IKCONFIG marker was not found in the extracted stock kernel, so the source configuration cannot be promoted to an exact binary configuration.

A standard OpenWrt overlay or external initramfs cannot be assumed. A future first-test design can use volatile configuration after the actual boot/filesystem interface is verified. Persistent configuration and upgrades require the real UBI/MTD layout and protected per-unit backups first. No partition, mount source or write location is selected here.

## Watchdog assumptions

Procd's watchdog implementation opens `/dev/watchdog`, uses `WDIOC_SETTIMEOUT`, writes keepalives, and passes the open descriptor across the init/procd transition with `WDTFD`. If opening the device fails, initialization returns without a watchdog descriptor.

The GPL configuration instead enables `CONFIG_LUNA_WDT_KTHREAD` and disables generic `CONFIG_WATCHDOG`. The supplied Luna source uses its own kernel threads and `/proc/luna_watchdog` controls. No adapter between this mechanism and procd is present. A running kernel watchdog thread is not proof that Ethernet, SSH or the repeater is healthy. The stock watchdog helper's `/dev/watchdog` strings do not establish that a compatible device exists on the actual router.

Procd also attempts a cgroup2 mount; the supplied GPL configuration disables cgroups. The mount result is not checked in that early-init source. This is an incompatibility to account for, not evidence by itself that procd cannot run.

## Validation boundary

QEMU userspace checks do not execute PID 1, preinit, service startup, mount operations or watchdog code. Actual boot arguments, MTD/UBI geometry, stock interfaces/switch state and private per-unit backups have since been captured. Both radios passed bounded RAM-only repeater tests on the unchanged stock startup. Backup completeness, actual independent restoration and custom wired boot remain open. The new same-radio coordinator addresses channel/carrier policy in offline tests only; see RADIO-COORDINATION.md. There is no bootable image or authorized flash step.

## Channel and lifecycle integration stage

Same-radio review profiles now render one paired controller instead of independently restarting AP and station workers. The controller implements upstream channel alignment, explicit post-AP-restart reassociation, carrier gating, asynchronous DHCP readiness and an interface-bound gateway probe. Cross-radio station workers also gate attachment on carrier. Host logic tests are distinct from target execution; no preinit, inittab, rc.d enablement, board initialization or bank-commit path has been added. Full custom boot remains unqualified.
