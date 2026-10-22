The unmodified `900-rtl8192cd-sta-assoc-reply.patch` comes from
[adaasch/mr1500x-openwrt](https://github.com/adaasch/mr1500x-openwrt/blob/a07e5f0dbaa57ac2f9d166e11d2f9d775ab9db3d/patches/900-rtl8192cd-sta-assoc-reply.patch),
Git blob `4cbfeb9d3b32dd0cec5bcb03da50ce40d39ad76a`.

The reference repository's LICENSE explicitly offers this patch under hostapd's
BSD-3-Clause terms. It is not covered by this project's MIT license. Hostapd's
copyright and license notices remain in the patched upstream source, included
with the downloaded source archives and pinned source references.

The patch supplies an association-response operation for drivers configured with
REPLY_ASSOC_BY_HAPD plus HAVE_AP_SME. The R15 source audit found this combination
in its 2.4 GHz driver. Applying and compiling the patch does not demonstrate
successful association on the R15; that requires a later hardware test.
