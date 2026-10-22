# Requirements before any R15 firmware flash

These requirements come from the owner's explicit request. They are acceptance criteria, not a claim that the functions have been implemented or tested. Current decision: **NO-GO for persistent flashing**.

| Required capability | Acceptance evidence needed | Current state |
|---|---|---|
| Wired management | Known physical LAN socket, static address and authenticated SSH work after cold boot with both radios unavailable | Stock LAN access observed; custom boot untested |
| Firmware access/update | Owner can inspect/change settings and transfer a candidate; installer checks board, lengths, integrity and protected partitions before any write | Userspace build in progress; installer absent |
| Linux failsafe | A verified physical trigger starts immutable minimal wired management without saved configuration or radio services | Button mapping and early switch startup unverified |
| Emergency return to stock | Exact A1 bootloader recovery entry, address and accepted original image tested on the actual unit, including after a nonbooting candidate | Vendor GPL recipe found; restore not demonstrated |
| Per-unit preservation | Verified bootloader/environment/factory/calibration backups, with appropriate NAND bad-block/ECC/OOB handling | Web configuration export is not these backups |
| Power and watchdog health | Startup watchdog ownership, boot acknowledgement, reboot reason where available, cold starts and power interruption tests | Boot-health string identified; behavior unverified |
| Power supply checks | Identify any voltage/brownout sensing; expose supported readings without treating missing sensors as a healthy supply | No supply monitor established; software cannot prove external power quality |
| LEDs | Identify exact board LED controls, polarity and reset/shared-pin hazards; distinguish startup, management-ready, uplink loss, fault and rescue states | GPIO/LED support exists in stock sources; mapping unverified |
| Ethernet | Test all physical sockets, link/speed, packet RX/TX, switching/isolation and management access with upstream absent | Stock netdev mapping observed; replacement initialization untested |
| Wi-Fi RX/TX and antennas | Preserve per-unit RF data and board-specific RFE50 tables; test both radios/chains, receive/transmit, signal, reconnection and regulatory limits | Radios/PCI IDs observed; custom RF execution untested |
| Scanning and client mode | Scan/join ordinary APs, handle wrong key/missing AP/channel change and recover without resetting management | Supplicant configuration and reconnect worker implemented; hardware untested |
| Broadcasting | Validate SSID beacons, downstream association, DHCP, forwarding and reconnect under sustained load | Patched hostapd compiled; hardware untested |
| Wi-Fi security | WPA2-PSK with CCMP/AES initially; no open/WEP/TKIP fallback or default WPS; private credentials, owner authentication, firewall and isolation checks | Config renderer and patch builds checked; over-air security untested |
| Failed settings/update | Invalid radio settings leave wired access intact; interrupted writes never destroy the independent recovery path | Configuration separation implemented; physical fault tests absent |

## Recovery boundaries

Linux failsafe cannot rescue a kernel or Ethernet driver that does not boot. Bootloader recovery must work independently of the replacement operating system. A downloaded stock image is not a backup of per-unit calibration or bootloader data. C1/C2 configuration records do not establish dual firmware slots or rollback.

The first boot test should be nonpersistent RAM boot only if the installed bootloader and compatible kernel loading method are verified. No such method is established here. Do not assume an external initrd works: the reference kernel config disables CONFIG_BLK_DEV_INITRD.

No first flash is permitted by this project's readiness decision until the wired and independent-restore tests are demonstrated. There is no current flash writer or image packer in this repository.

## Status behavior to implement after board mapping

Use the available LEDs to distinguish booting, wired-management-ready, upstream-disconnected, repeater-active, recovery and fault. Patterns/colors are proposals until the actual LED wiring is established. A steady light or a hardware timer continuing to blink is not proof that Linux/networking remains healthy. Do not guess GPIO numbers or write arbitrary GPIOs: reset and power-control signals may share the controller.

The read-only health probe reports uptime, memory, link and packet counters, LED device availability and exposed voltage readings. Missing readings remain unknown. Netdev packet counters do not prove physical antenna-chain performance, and uptime cannot distinguish every power-loss cause.

WPA3, transparent bridging/WDS and same-radio AP+STA need separate driver/capability verification; the initial cross-radio WPA2 design does not claim them. The vendor 4.4 kernel / OpenWrt 21.02 baseline is an old integration route; passing these tests is not a security audit of that code.
