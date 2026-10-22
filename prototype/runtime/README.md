# R15 radio worker — research component

`r15-radio-worker` implements the process and uplink lifecycle for a future OpenWrt userspace build. It is not a stock-firmware installer. The renderer includes this worker and a procd service in repeater review bundles; `wired-first` has neither.

Two independent procd instances run the downstream hostapd process and the upstream supplicant worker. Their failures are restarted with bounded retries. No `iw interface add`, global process kill, network restart, switch write, module loading or flash command is used.

The upstream worker waits for `wpa_state=COMPLETED`, attaches the existing VXD device with netifd's `add_device`, and starts only `wwan`. On disconnect it stops only `wwan` and detaches that device. The supplicant remains running to reconnect; re-association attaches the interface again. Failed attachment or DHCP startup is retried on later polls. Repeated successful status polls do not continually restart DHCP. The AP process is separate from this uplink state machine.

Only the observed cross-radio pairs are accepted:

| Upstream | Downstream |
|---|---|
| `wlan0-vxd` (5 GHz) | `wlan1` (2.4 GHz) |
| `wlan1-vxd` (2.4 GHz) | `wlan0` (5 GHz) |

Before starting, the worker requires an existing `mgmt` interface reporting up, both board-created radio netdevs, and `/etc/r15/board-startup-verified`. **No code here creates that marker.** It represents a missing board bring-up and validation step; creating an empty file is not a substitute for testing switch/MAC/calibration initialization. The worker does not configure management or claim to verify SSH access.

Future packaging locations (not implemented):

| Review input | Target path |
|---|---|
| `runtime/r15-radio-worker` | `/usr/libexec/r15-radio-worker` (executable) |
| `runtime/r15-radio.init` | `/etc/init.d/r15-radio` (executable) |
| `radio-config/hostapd.conf` | `/etc/r15/hostapd.conf` (private) |
| `radio-config/wpa_supplicant.conf` | `/etc/r15/wpa_supplicant.conf` (private) |

The generated UCI `lan` bridge must already be available for hostapd. The 2.4 GHz AP requires the association-response driver integration identified in the driver audit. Module ordering, per-unit RF/MAC data, ABI compatibility, watchdog boot acknowledgement, live DHCP subnet collision rejection and update/recovery remain unresolved. Dynamic command behavior is tested against mocks only; actual OpenWrt/netifd/procd and R15 driver behavior are untested.

`profile.stock-observed.example.json` uses interface names seen in the owner log. Its management device is a candidate based on that log, not a validated replacement-kernel physical port map. Credentials remain example values and it has no owner SSH key.

Tests: `python3 -m unittest discover -s prototype -v` — 18 passing tests including reconnect, attachment/DHCP failure, absent uplink and management loss. The tests run fake commands in a temporary directory and never contact the router.
