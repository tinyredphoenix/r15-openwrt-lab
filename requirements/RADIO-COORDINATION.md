# Same-radio startup and recovery policy

The retained stock kernel/vendor drivers passed bounded routed repeater tests on both bands using compiled station/DHCP/DNS tools and OEM AP services. This does not qualify the new coordinator, custom hostapd startup, netifd/procd integration, PID 1 or a bootable firmware.

A real 2.4 GHz failure motivates the controller: an AP restart with automatic channel selection chose a different channel from the upstream. A phone authenticated and received DHCP but had no Internet. The station still reported COMPLETED while Linux reported carrier 0. Matching the AP to the upstream channel and reassociating restored actual traffic.

## Controller contract

Same-radio profiles use one procd instance owning two foreground children, hostapd and wpa_supplicant. Separate independently respawning AP/station instances cannot safely coordinate an AP restart. Cross-radio profiles retain the earlier independent workers, now with a carrier check before uplink attachment.

The same-radio coordinator:

1. Requires wired `mgmt` up, existing board-created netdevs and the existing board-startup validation prerequisite. It does not create that prerequisite or initialize hardware.
2. Defaults to automatic SSID discovery. It filters fresh WPA2-PSK/CCMP ESS candidates by exact supplicant-encoded SSID, or uses an optional explicit BSSID lock. An associated station with carrier must match the configured SSID/security and network ID before its negotiated frequency is accepted. Matching BSS records aged at most 30 seconds may supply scan frequency.
3. Keeps the uplink detached while channels disagree. It regenerates only a private RAM AP configuration with a numeric channel, restarts only its own foreground AP child and waits for the AP to report ENABLED on that frequency.
4. Explicitly disconnects the station, confirms DISCONNECTED and requests reassociation after an AP change. Cached COMPLETED is insufficient.
5. Attaches only `wwan` after expected BSSID, COMPLETED, carrier and matching AP frequency are present. `ifup` is asynchronous, so DHCP pending is not readiness.
6. Sets an informational ready flag only after netifd reports up and an interface-bound learned-gateway ping passes. Three consecutive gateway-probe failures detach only the uplink and schedule a fresh scan/reassociation. DHCP and firewall3 may permit packets before this informational flag; it is not a separate packet-filter gate.
7. Bounds AP alignment waiting and owned-child termination. Failure to stop an owned process prevents a competing replacement. Lost management stops uplink attachment; no management restart or global radio/network command is issued.

The private link-state file is diagnostic. It must not acknowledge/commit a boot bank or serve as the sole watchdog/readiness test; a SIGKILL or crash can leave a stale file. Shutdown writes ready=0 when cleanup runs. Full boot health must check live processes and actual management/data independently.

## Reviewed limits

- IPv4 routed repeating with WPA2-PSK/CCMP; transparent bridging is not provided.
- Same-radio AP/VXD pairs are limited to `wlan1`/`wlan1-vxd` or `wlan0`/`wlan0-vxd`.
- Candidate frequency conversion supports 2.4 GHz channels 1–13 and 5 GHz channels 36/40/44/48. The renderer's initial AP channels remain conservative. Hostapd/driver country and regulatory checks still apply; DFS/high-band operation is not implemented by this coordinator.
- SSID discovery and changed-BSSID association are implemented offline. Hidden-network discovery, arbitrary upstream/security interoperability, roaming quality and driver scan behavior remain unqualified.
- Gateway ICMP is a provisional health policy, not proof of Internet access. Gateways that block ICMP require a reviewed alternative.
- Runtime DHCP subnet-collision rejection, board/switch/MAC/calibration startup, secure admin access, custom cold boot, watchdog/bank acknowledgement, updates and independent restoration remain unqualified.
- Existing stock daemons are not adopted or terminated by this component. It is not a RAM installer for a running stock system.

## Validation

Offline shell scenarios reproduce channel mismatch, stale COMPLETED/no carrier, stale/wrong BSS entries, DHCP delay, probe failure, management loss and bounded alignment failure. Renderer tests check a single same-radio owner, safe profile validation and absence of radio services in wired-first output.

The cached Linux build's management checks now include target BusyBox syntax and a target-jsonfilter gateway-selection fixture. Those new target checks are prepared, not claimed executed by host tests. Hardware execution of this coordinator remains a separate next gate.

## Phase-2 subnet guard update

The same-radio coordinator now checks the learned IPv4 connected subnet against renderer-generated management and client subnets before readiness/probing. Missing, malformed, multiple-address or overlapping lease data stops this controller and detaches only wwan. `r15-subnet-check` uses pure range arithmetic and returns 0 (disjoint), 1 (overlap) or 2 (invalid policy/data). The renderer includes exactly two normalized local networks in `radio-config/protected-subnets`.

This is not atomic DHCP route prevention: netifd may install routes before rejection; supplied classless routes are not audited; cross-radio workers do not invoke this guard yet. Management/data routing isolation still needs completion. The new revision has host tests; prior successful cloud reports apply to their recorded commits, not these later changes until a new build passes.

Final automatic SSID/channel requirements and optional PPPoE are specified in [FEATURE-COMPATIBILITY.md](FEATURE-COMPATIBILITY.md). SSID-only selection is now implemented offline; limited channels, regulatory handling and hardware behavior still leave the final requirements partially open.

## Pre-publication DHCP integration

The next build revision stages `r15-dhcp.script` at OpenWrt's existing DHCP event path, preserving the exact hash-pinned original as `/usr/libexec/r15-openwrt-dhcp.script`. WWAN bound/renew events first run `r15-dhcp-guard`. It rejects conflicting connected subnets, malformed masks/addresses, protected off-link gateways and classless routes intersecting management/client ranges. An unsafe renewal delegates `deconfig`, withdrawing the old accepted lease rather than publishing the new one. Other interfaces/events keep the original OpenWrt behavior. No DHCP process or event script is executed by build staging.

This moves validation before `proto_send_update`; `/etc/udhcpc.user` would run too late. It is intended to close the earlier post-lease rejection window when correctly deployed. That behavior is host-tested, not yet proved against target netifd/udhcpc. The original script must match `build/dhcp-script-manifest.json` exactly. A missing policy/helper rejects the WWAN lease. Current guard scope requires ordinary unicast IPv4 leases and rejects unchecked CUSTOMROUTES; IPv6/6rd, custom-route configuration and other protocol capabilities require separate integration review.

The build stores a staging report and runs target BusyBox syntax checks without starting DHCP. Review bundles include wrappers and policy inputs but remain non-installable. Existing router RAM tests and immutable checkpoints were not modified.
