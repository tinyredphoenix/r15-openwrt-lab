# Final OpenWrt administration

The owner explicitly authorizes replacing D-Link management in the final product, as well as during grouped tests. Use LuCI, UCI, rpcd, uhttpd and Dropbear. Retaining the vendor kernel/drivers does not require retaining the OEM web UI, commander service, OEM passwords or OEM management configuration.

The build pins LuCI source separately from the retained OpenWrt userspace baseline. It compiles the standard LuCI collection, uhttpd/RPC services, optional PPP/PPPoE packages and HTTPS support. Source hashes and archives are retained; foreign SDK kernel modules remain excluded. Successful compilation is not a live PPPoE, web authentication or cold-boot result.

The profile renderer provides UCI inputs for HTTP/HTTPS bound only to the reserved management IPv4 address, HTTPS redirection, CGI and ubus access. rpcd authenticates against the root password database. Candidate authentication material is provisioned privately; no default or owner credential is included in public recipes/artifacts. Missing root credentials or HTTPS identity remains an explicit unresolved provision/startup condition. No services are enabled by rendering alone.

LuCI's existing generic wireless pages cannot be assumed to configure these vendor AP/VXD interfaces. The Realtek adapter must expose supported radio operations/settings through UCI and report actual association/carrier/channel state. Current paired-controller SSID/channel logic is implemented and tested offline; a complete LuCI-to-radio apply path remains open.

Do not enable a generic SDK board initializer, flash writer or sysupgrade handler for this R15. The final device-specific update path must validate the actual image format and protected regions. Mac recovery HTTP entry is proven; actual restoration is untested and is a strong owner preference, not an owner-imposed absolute gate. Keep recovery limits visible while making autonomous release decisions from actual evidence.

The current build is a pinned legacy userspace integration route for vendor Linux 4.4.140; it is not a current official OpenWrt R15 target. Modern-kernel driver support is a separate unqualified route. Full boot, board initialization, authentication and long-running operation require the grouped device qualification phase.

## Private provisioning helper

`build/provision-management.py` is a local private-build operation, not part of public cloud staging. It verifies an explicit owner public key, SHA-512 crypt password hash, matching HTTPS certificate/private key, management-address SAN and certificate lifetime before changing a fresh filesystem copy. It refuses symlinked destinations or a different existing administrative identity. It provisions both root authorized-key locations; the client private key is never copied. Generated files are private and no service starts.

This does not qualify login behavior, SSH host identity, PID 1, early hardware initialization or update handling. The grouped target session must verify actual SSH/HTTPS/RPC operation. Never publish its output or include owner credentials in Actions artifacts.
