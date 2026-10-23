# Stock boot selection and inner-record integrity

Offline findings from the R15 A1 1.06.10 artifacts, 2026-10-23. No stock executable was run, and no router flash, environment or watchdog interface was opened. These findings do not change the **NO-GO for flashing** decision.

## Logical sections and boot selection

The stock `libupgbuf.so` exported `flash_sec_name` function contains a jump table. Decoding its entries and checking their return instructions gives these names:

| Logical section ID | Name |
|---|---|
| 1 | boot |
| 3 | ODM |
| 5 / 6 | Config0 / Config1 |
| 9 / 10 | ubi_k0 / ubi_k1 |
| 11 / 12 | ubi_r0 / ubi_r1 |
| 13 | Storage |
| 14 | ubi_mydlink |
| 15 | ODM2 |
| 16 / 17 / 18 | linux / rootfs / tclinux |

This is a software section-name table. It is **not** the owner's live partition map, a list of flash offsets, or proof that all named sections exist. The same library searches `/proc/mtd` at runtime to resolve a section name into a device, rather than establishing its physical range from this table.

Static decoding of `flash_cur_rootfs_secid` shows a read of up to 511 bytes from `/proc/cmdline`, followed by substring checks for ` root=31:9 ` and ` root=31:11 `. It returns section 11 or 12 respectively; its companion kernel function returns section 9 or 10 for those same command-line matches. Read/open failures or unmatched strings return an error. This describes the shipped parser, not the observed boot arguments of the owner's router.

`flashboot_chg_boot_part` maps rootfs section 11 to `sw_tryactive=0`, and section 12 to `sw_tryactive=1`. The commander routine around address `0x403d8c` checks the current rootfs section and conditionally updates `sw_commit` to the corresponding 0/1 value. Two direct calls to that routine were identified at `0x4036dc` and `0x403814`; their enclosing startup paths and timing still require analysis.

The library getter builds `fw_printenv -n <name>` and reads its output through `popen`; its setter formats a value and invokes `fw_setenv` through the stock command helper. These strings are evidence of persistent environment dependencies, **not commands to run**. The GPL environment-tool header compiles in redundant environment candidates `/dev/mtd1` and `/dev/mtd2`, each with size 0x20000 and offset zero; both device names also occur in the shipped utility. Actual device sizes, redundancy state and erase geometry must be verified on the unit before any use. Do not use an example `fw_env.config` to write boot state.

Together, these establish paired-bank support in the stock software. They do not establish bootloader retry counts, automatic rollback, the effect of missing acknowledgement, power-loss atomicity or a safe inactive-bank update procedure. Config0/Config1 remain separate from the paired kernel/rootfs sections.

## Read-only inner-record checker

`build/inspect-stock-records.py` supports the single observed **already decrypted** MH01 layout: 16 initial bytes, three 80-byte record headers plus their payloads, and 256 remaining bytes. It does not decrypt the downloaded stock image or create another image.

The observed records are mydlink, kernel and rootfs, with record kind bytes 9, 4 and 8, and ROM ID `DLK6E7001001`. Payload length is at header offset 44, payload checksum at offset 14, and kind at offset 70. The stock `icksum` routine uses big-endian 16-bit addition with end-around carry, without complementing the result; an odd final byte is padded with 0xff. The observed complete header sum is 0xffff.

The checker verifies those header and payload checksums, lengths, order and the observed ROM ID. All three records in the local stock artifact pass. It rejects damaged payloads/headers, unexpected kinds or ROM IDs, truncation and unexpected trailing length. Synthetic fixtures cover these rejection cases without publishing firmware data.

**Checksums are not authentication.** The 16-byte container header and 256-byte trailer are not validated beyond layout/magic/length constraints; signatures, bootloader acceptance, board compatibility, calibration and flash layout are unverified. Every successful report retains `flashable: false`. Never upload this decrypted input or an inspector report as router firmware.

## Evidence identity and remaining gates

- Stock library SHA-256: `1715afb2671e40aa2a6794bf82e6c93ab7e8bfd1dd08ce68b3c5620d1729391f`.
- Commander SHA-256: `224773a610a51f91a25f0ca216bb47ffc652166f70772cbccb6d6fdb04f3476d`.
- Local decrypted artifact SHA-256: `91672b85fb73b4aeacc84fbb331e6793a490c3317876c89e5bc52549dff99da8`.
- Method: ELF dynamic symbol/GOT/relocation inspection, Capstone 5.0.6 instruction decoding, manual branch/delay-slot review, and checksum comparison against all three observed records. Static inspection does not establish execution or successful writes.

Remaining gates include the actual MTD/UBI map and per-unit backups; complete board startup, LEDs and radio calibration; verified wired management without radios; and successful independent restoration to stock. See [the acceptance requirements](RECOVERY-AND-HARDWARE.md).
