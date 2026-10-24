# R15 radio lifecycle components

These are research inputs for a future retained-kernel OpenWrt userspace build. They are not installers or a complete boot framework. No component initializes the board, writes firmware or creates the board-startup verification prerequisite.

## Independent wired management

Before starting radios, the future platform startup must initialize and validate the reserved wired management interface, firewall, DHCP and authenticated admin access. A marker file is only an explicit missing prerequisite; touching it does not qualify board startup. `wired-first` rendering includes no radio service.

## Cross-radio worker

`r15-radio-worker` supervises one AP or station process. For station mode it now requires both COMPLETED and carrier before handing the existing VXD to netifd. Disconnect removes only `wwan`; management and AP are not restarted. The two cross-radio instances remain separate.

## Same-radio coordinator

`r15-radio-coordinator` owns both foreground children in a single procd instance. It selects the upstream frequency from an associated station with carrier or a fresh matching selected-BSSID scan result. On mismatch it detaches the uplink, regenerates a private RAM AP configuration, restarts only its AP child, waits for channel alignment, invalidates stale station state and requests reassociation. DHCP waits for association, carrier and AP alignment; readiness additionally waits for netifd and an interface-bound gateway probe.

This implements offline-tested policy for the actual AP-channel/carrier failure observed during stock-kernel tests. It has not run against the target drivers or netifd/procd. It cannot be called a completed boot integration. See [policy, limits and remaining gates](../../requirements/RADIO-COORDINATION.md).

| Input | Future location |
|---|---|
| `runtime/r15-radio-worker` | `/usr/libexec/r15-radio-worker` |
| `runtime/r15-radio-coordinator` | `/usr/libexec/r15-radio-coordinator` |
| `runtime/r15-radio.init` | `/etc/init.d/r15-radio` |
| `radio-config/hostapd.conf` | `/etc/r15/hostapd.conf` (private template) |
| `radio-config/wpa_supplicant.conf` | `/etc/r15/wpa_supplicant.conf` (private) |

Review bundles deliberately store scripts as non-executable inputs. They do not enable `/etc/rc.d` entries or write marker files. The future renderer/service packaging must preserve that boundary until board startup, custom AP execution and secure management have been qualified.

`profile.same-radio.example.json` contains example credentials and a synthetic BSSID, never owner data. Selection defaults to SSID discovery, with optional BSSID locking, and channel support is bounded; it does not imply arbitrary roaming or DFS support.

Tests run fake shell adapters and never contact the router. Target BusyBox/jsonfilter checks are separately defined in the Linux build; host tests do not execute them.

The same-radio lease guard also requires `/usr/libexec/r15-subnet-check` and the renderer's `radio-config/protected-subnets` at `/etc/r15/protected-subnets`. It rejects connected-subnet overlaps after DHCP; it does not eliminate the route-installation window or inspect classless routes. See the phase-2 update in RADIO-COORDINATION.md.

Automatic mode also requires `radio-config/upstream-ssid` at `/etc/r15/upstream-ssid`. This is a literal encoded SSID line, never sourced or evaluated. Bootstrap AP channels are internal defaults; actual same-radio operation follows fresh scan/negotiated frequency.

The pre-publication DHCP wrapper and `r15-dhcp-guard` are staged by `build/stage-dhcp-guard.py`, preserving the exact pinned original DHCP script. They run no services during build staging. Missing policy rejects a WWAN lease; the correct private policy must be provisioned by future packaging. Host tests cover valid/invalid bound and renew dispatch; target runtime integration remains untested.

### UCI service entry

Same-radio procd startup/reload uses `r15-radio-launch`. It renders one validated
UCI snapshot in a private RAM directory, starts one owned controller and removes
the snapshot after exit. An invalid/disabled profile starts no radio controller.
The controller still requires the independently established board-startup marker,
existing interfaces and wired management; the launcher cannot create that marker.
It neither adopts nor kills stock services. The actual integrated device run is
pending. Cross-radio profiles retain their earlier direct worker template.

## Stock-assisted boot integration

`r15-stock-management` adds key-only SSH and pinned HTTPS after OEM board startup,
maintaining the reserved wired address and its route. An explicitly enabled private
radio UCI profile can dispatch `r15-network-handoff`. The handoff uses the existing
ubus and a separate process ledger, preserves external ownership of wired bridges,
and scopes cleanup to network services and its own mounts. It must never call the
broad chroot cleanup while management is running. Automatic handoff startup is a
new private-image experiment; manually dispatched coexistence has passed on the
first flashed management image.

`r15-stage-inactive` is a narrow, explicitly invoked experimental bank writer, not
a web updater. Trial environment guards prevent known stock auto-commit paths; an
operator-only copy of the stock environment tool is retained for deliberate bank
selection. No source-only helper qualifies recovery or a release by itself.
