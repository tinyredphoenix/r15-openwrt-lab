# Management service test boundary

The first integrated test runs on the already booted stock kernel. It is not a
custom boot. Start only explicitly selected foreground daemons in a private
RAM filesystem, using a separate ubus socket and management-address listeners.
Wired stock access must remain independently usable before any radio handoff.
No generic rcS, /sbin/init, shutdown, sysupgrade or boot acknowledgement is part
of this management test.

Pinned procd source has two distinct behaviors. /sbin/init installs shutdown
handlers and performs boot setup. Non-PID1 procd skips boot setup and its own
shutdown signal handlers, but upstream still registers system.reboot, watchdog,
signal and sysupgrade on ubus. A private socket or chroot alone does not make
those methods harmless to the running host.

Our patch retains only system.board and system.info when procd is not PID 1.
Both the dispatched method table and its advertised ubus object type are restricted.
PID 1 retains the original method table; this is not proof that an R15 custom
boot or its update implementation works. The host regression test patches the
actual pinned source, compiles its registration function/method tables with
inert adapters, and checks both modes against an unmodified negative control.
The collector also requires the compiled guard marker. Before exposing a device
test web session, independently inspect its live system object and require only
board/info methods. Do not infer live enforcement from marker presence alone.

The test root must not expose flash/device-update tools. It must use private
credentials, separate process ownership, bounded cleanup and no stock service
adoption. A chroot is not isolation for networking or kernel calls. Authentication
and read-only inspection precede any networking takeover. UCI profile edits and
radio apply remain separate observations in the same consolidated test phase.

Source reference: OpenWrt procd commit
2cfc26f8456a4d5ba3836c914a742f3d00bad781, initd/init.c, procd.c, signal.c,
ubus.c and system.c. The actual system.c source fixture retains its original
GPL notice and is used by tests/test_procd_guard.py. No hardware was contacted
by these checks.
