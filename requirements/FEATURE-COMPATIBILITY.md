# Feature compatibility and automatic upstream discovery

Use standard OpenWrt services and packages wherever the retained Linux 4.4.140 kernel and board interfaces allow them. Keep the first installed configuration focused on repeating; optional features should remain buildable where their dependencies are satisfied. No claim of every OpenWrt feature is justified by a userspace version check.

## Required automatic channel behavior

The owner configures an upstream SSID and security credentials, not its channel. On cold start, upstream reboot, channel optimization and lost link, discover that SSID again using fresh driver scan results and the negotiated association state. Select a matching security-compatible BSS in the intended band; do not join an unrelated BSS solely because it is stronger. BSSID pinning may be an optional advanced setting, not a mandatory normal setup input.

For same-radio repeating, the local AP must follow the selected upstream channel. A stale COMPLETED state without carrier is not success. Revalidate carrier, channel, DHCP and data after AP changes. Handle country restrictions, unsupported channels and DFS explicitly; never invent a channel, bypass regulatory checks, or require the upstream administrator to disable automatic channel optimization.

The current coordinator now implements SSID-only discovery using exact supplicant-encoded SSID text, fresh BSS records, WPA2-PSK/CCMP filtering and association status validation. A BSSID lock is optional; an initial AP bootstrap channel is supplied internally when omitted. Negotiated channel changes and upstream reboot/reappearance are covered by offline tests. Channel support remains limited to 2.4 GHz 1–13 and 5 GHz 36/40/44/48; regulatory/DFS handling outside that subset and actual target execution remain **not complete**.

Reuse supplicant's network selection and OpenWrt's existing services where compatible. The adapter is needed because the observed vendor AP/VXD behavior and custom startup are not yet qualified through standard netifd wireless management. Do not duplicate OpenWrt routing/DHCP/firewall logic without evidence that an adapter is necessary.

## Feature matrix

| Feature | Intended treatment | Current evidence / gap |
|---|---|---|
| Both-band repeating | Required, automatic upstream channel following | Bounded stock-kernel RAM paths passed; SSID discovery implemented offline; target execution and final custom startup remain open |
| Wired administration, DHCP/DNS, routing/firewall | Required using OpenWrt services | Compiled tools and runtime subsets passed; integrated secure boot/service order unqualified |
| PPPoE | Retain as optional future build capability; do not enable in repeater mode | Supplied vendor kernel .config enables PPP/PPPOE; exact binary/userspace/plugin/protocol integration is not qualified. Owner explicitly defers live PPPoE testing |
| LuCI, VLANs, VPNs, QoS, IPv6 and other optional packages | Preserve where kernel, driver, storage and package dependencies can be met | Assess individually; do not silently exclude them or claim compatibility from package availability |
| Modern OpenWrt kernel features | Separate porting route | Retained 4.4 kernel cannot be assumed to implement current kernel APIs or missing drivers |

For PPPoE, audit the OpenWrt PPP daemon, PPPoE plugin and netifd protocol script together with the retained kernel ABI. Generic kmod IPKs built for another kernel must not be loaded. Keep runtime status explicitly untested until a future owner-authorized validation; package inclusion is not connection proof.

All new hardware validation belongs to the consolidated project phase 3, not to each small change.
