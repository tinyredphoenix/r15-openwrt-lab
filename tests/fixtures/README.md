# Pinned source fixture

procd-system-2cfc26f.c is the unmodified GPL-2.0-or-later source from
https://github.com/openwrt/procd/blob/2cfc26f8456a4d5ba3836c914a742f3d00bad781/system.c
with its original copyright/license notice retained.

SHA-256: 7930b94fcb21d9962768fa61cc88e862432a496e8ecb2caa4e243fead75230cb

The guard test applies our patch to this actual registration function and method
tables, compiles them with inert adapters, and checks PID 1 and ordinary-process
registrations. The unmodified source is a negative control. No daemon, reboot,
process signal, watchdog or network call runs.

The two nixio Makefile fixtures are unmodified Apache-2.0 LuCI sources from
https://github.com/openwrt/luci/tree/e4c46338b196e486a88b1a75b78e283708c82bc4/libs/luci-lib-nixio
with original notices retained.

- Makefile SHA-256: b683210c70cec4db1b103271839353e9803bedea832ef3d4d603f56dd35eff76
- src/Makefile SHA-256: cd4696fbdc9d05d29d736afe9cdc302a27fcb8053001f88a9b4d37d44ecce1f6

The test dry-runs the actual child recipe before and after our patch, with the
SDK variable reset reproduced by an inert include. No compiler or target runs.
