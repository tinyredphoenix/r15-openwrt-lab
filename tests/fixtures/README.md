# Pinned source fixture

procd-system-2cfc26f.c is the unmodified GPL-2.0-or-later source from
https://github.com/openwrt/procd/blob/2cfc26f8456a4d5ba3836c914a742f3d00bad781/system.c
with its original copyright/license notice retained.

SHA-256: 7930b94fcb21d9962768fa61cc88e862432a496e8ecb2caa4e243fead75230cb

The guard test applies our patch to this actual registration function and method
tables, compiles them with inert adapters, and checks PID 1 and ordinary-process
registrations. The unmodified source is a negative control. No daemon, reboot,
process signal, watchdog or network call runs.
