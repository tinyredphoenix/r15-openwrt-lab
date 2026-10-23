# R15 A1 offline configuration prototype

This is an executable configuration renderer, **not firmware or an installable overlay**. It makes the management/repeater separation reviewable before a kernel or image is built. It never connects to a router, runs networking commands, or writes flash. Do not copy the rendered files onto stock firmware.

The current target is a vendor Linux 4.4.140 / OpenWrt userspace research route. Configuration syntax is scoped to OpenWrt 21.02 and firewall3, following the related Mercusys integration pattern. This is not a choice of a maintained production release; userspace/kernel compatibility and package builds remain work to do. A modern RTL960X port is still a separate route.

## Generate and check locally

From the workspace root:

```sh
python3 -m unittest discover -s prototype -v
python3 prototype/r15_repeater.py --profile prototype/profile.example.json --stage wired-first --output prototype/generated/wired-first-review-v2
python3 prototype/r15_repeater.py --profile prototype/profile.example.json --stage repeater --output prototype/generated/repeater-review-v2
```

Output must be a new directory. All generated files are private, and the manifest records their hashes and unresolved prerequisites. PSKs remain secrets even though plaintext passphrases are not emitted. Example credentials are placeholders. Public examples contain no owner credentials. Actual runtime test inputs stay private in the owner workspace.

The `unverified0/1/2` names **are placeholders**, not discovered R15 interfaces. The example has no SSH public key, so its manifest explicitly reports that login would be unavailable. A real owner Ed25519 public key and tested mappings are prerequisites for a future boot test.

## Management invariant

Both stages reserve a wired interface for `mgmt`, with a candidate fixed address `192.168.77.1/24`. The corresponding laptop fallback is `192.168.77.2/24` without a gateway. DHCP is proposed as a convenience; static access must also work. The final subnet must be checked against the actual upstream network.

- SSH binds to `mgmt`; authorized keys belong to the owner. Management configuration does not depend on upstream Wi-Fi association or radio credentials.
- The management port cannot be consumed by either radio role. The Wi-Fi roles have their own downstream network and uplink.
- The management firewall zone has no forwarding from the Wi-Fi uplink. No gateway is learned on the management interface. The management DHCP service has its own dnsmasq instance/lease file and does not advertise itself as the laptop's Internet gateway/DNS. Static IP and SSH access must work even if DHCP fails.
- `wired-first` renders without reading any radio configuration. A broken SSID or unavailable Tenda cannot prevent that stage from rendering.
- `repeater` emits WPA2/CCMP hostapd and supplicant configurations using hex SSIDs and derived PSKs. Both cross-radio and same-radio designs use IPv4 NAT, so clients receive a separate subnet. Transparent bridging and WDS are not implemented. The paired controller follows the discovered upstream channel within the current conservative channel scope.
- The radio lifecycle worker now implements external-device attachment to netifd, disconnect handling and reattachment after association, with separate procd instances for AP and client. Realtek interface bring-up, per-unit MAC/calibration loading, hostapd association replies and hardware validation remain unfinished. No generic `iw ... interface add` call is used. See [runtime details](runtime/README.md).

The renderer is an offline aid; these invariants do **not** prove that the kernel, switch, SSH daemon or DHCP server will run on the hardware. See [the recovery requirements](../README.md#what-still-blocks-firmware) for what must be established before a first flash. No firmware-update handler, recovery-button handler or bootloader changes are supplied here.

A second example, `profile.stock-observed.example.json`, uses the stock netdev names recovered from the owner log. Review bundles under `generated/*-stock-review-v3` include those names; they remain non-installable and have no owner SSH key.

## Radio settings through UCI

Same-radio rendering now emits a private `r15_radio` UCI package with one named
`repeater` section. `r15-radio-config.lua` reads it without committing settings,
starting services or changing interfaces. It validates India/WPA2-CCMP, the band,
optional BSSID and credentials. SSIDs are hex-encoded bytes so quotes, newlines
and UTF-8 round-trip through UCI without becoming configuration directives.
Derived keys are secrets and receive the same private-file protection as passwords.
There is no manual channel option: discovery selects the upstream channel.

This is the configuration adapter only. The current procd template still uses
its rendered files. Transactional service reload, a LuCI form and actual radio
apply remain pending; copying the UCI package does not apply settings yet.
