# Router output fixtures

These fixtures originate from lab captures. Synthetic cases remain in separate tests. Traceroute upstream addresses and hostnames use documentation ranges and example domains; timing, MPLS annotations and responder counts remain unchanged. Public query destinations remain unchanged.

## Provenance

- `arista_aspath.json`, `arista_live_route.json`, `arista_large_community.json`, `arista_vrf_local_route.json`, `arista-live/` and `arista_traceroute.txt`: cEOS 4.36.3M, captured on 27–28 October 2026. JSON responses use the built-in BGP commands, including `detail` for communities.
- `bird-live/` and `bird_traceroute.txt`: BIRD 2.17.2, captured on 27–28 October 2026. Route output uses `birdc show route ... all`. Bulk fixtures keep every path of the first five returned prefixes.
- `frr-live/` and `frr_route_*.json`: FRRouting 10.2.2, captured on 28 October 2026. BGP commands use `vtysh -c 'show bgp <family> unicast ... json'`. Community detail fixtures use `json detail`.
- `huawei-vrp/` and `huawei-vrpv8-live/`: CE12800 V200R005C10SPC607B607, running VRP 8.180. Captured on 28–30 October 2026. Huawei brief community output omits AS paths; brief AS-path output omits communities. BGP `valid` is not an RPKI result. The VPN-instance fixture is an anonymized user capture from a VRPv8 NE router.
- `juniper-live/`: vJunos-router 26.2R1.7, captured on 29–30 October 2026. BGP commands use `show route protocol bgp ... detail | display xml`. The OTC fixture retains two prefixes and exercises repeated `bgp-path-attributes` blocks.
- `mikrotik-live/`: RouterOS 7.16.2 raw responses captured on 28 October 2026. JSON wrappers retain timestamps and query metadata. Traceroute fixtures retain intermediate screen updates and use the cleanup plugin before parsing.
- `openbgpd-live/` and `openbgpd_traceroute.txt`: OpenBGPD 8.8, captured on 27–28 October 2026. BGP commands use `bgpctl -j show rib detail ...`. Bulk fixtures retain the first five RIB entries.
- `vyos-live/` and `vyos_traceroute.txt`: VyOS 1.5 stream with FRRouting 9.1.3, captured on 27–28 October 2026. IPv4 bulk fixtures retain the first five returned prefixes.
- `cisco-ios-live/`: Cisco IOL 17.18.02, captured on 29 October 2026. BGP commands use `show bgp <family> unicast ...`. The route fixture removes `pathid:` and `Epoch` lines through the command's output filter.
- `cisco-iosv-live/`: IOSv 15.9(3)M6, captured on 29 October and 1 November 2026. Policy fixtures retain complete dual-stack AS-path responses, including wrapped IPv6 prefixes. Only trailing whitespace is removed from BGP output.
- `cisco-nxos-live/`: Nexus 9300v Lite, NX-OS 10.4(8), captured on 29 October 2026.
- `cisco-xr-live/`: XRd 24.2.11, captured on 29 October 2026.

## Test routes

The core advertises `1.0.0.0/24` and `2606:4700:4700::/48` with AS path `64999 13335`, community `65000:777` and large community `65000:777:1`. The Cisco companion probe advertises `1.1.1.0/24` and `2606:4700::/44` with AS path `65000 13335` and community `37195:302`.

Tests preserve fields omitted by a device. They do not infer missing communities or treat protocol validity as RPKI validation.
