# Dell OS10 query validation

Fixture version: SmartFabric OS10 10.6.1.3P1, build 10.6.1.3P1.6, S5224F-VM. The query matrix below covers default and LAB VRFs with text and structured output.

Apply `startup.cfg` from configuration mode. Connect separate BGP peers to `ethernet1/1/1` and `ethernet1/1/2`. Management SSH uses `mgmt1/1/1`; retain its configured address and credentials.

| Context | Interface | Device addresses | Peer addresses | Advertised prefixes | Origin AS |
|---|---|---|---|---|---|
| default | `ethernet1/1/1` | `10.250.1.1/24`, `fd00:250:1::1/64` | `10.250.1.2`, `fd00:250:1::2` | `1.0.0.0/24`, `2606:4700:4700::/48` | 13335 |
| LAB | `ethernet1/1/2` | `10.250.2.1/24`, `fd00:250:2::1/64` | `10.250.2.2`, `fd00:250:2::2` | `198.51.100.0/24`, `2001:db8:100::/48` | 64497 |

OS10 uses AS65030. Each peer uses AS65000 and one IPv4 BGP session carrying both address families. Set the advertised next hop to the corresponding peer address. Advertise community `65000:777` and MED 42. Confirm one received prefix per family with `show ip bgp [vrf LAB] [ipv6 unicast] summary`.

Configure Hyperglass with `platform: dell_os10`. Set `attrs.source4` and `attrs.source6` to the context's device addresses. Set `vrf: LAB` on the LAB entry. Both output modes use the following SSH timing settings:

```yaml
driver_config:
  fast_cli: false
  global_delay_factor: 1
  conn_timeout: 30
  banner_timeout: 60
  auth_timeout: 60
  read_timeout_override: 90
```

Wait for OS10 services to finish starting before checking admin login. The validated configuration cancels zero-touch deployment with `ztd cancel` and saves with `copy running-configuration startup-configuration`.

## Query matrix

Test seven cases per context and output mode: IPv4/IPv6 prefix queries, one community query covering both families, IPv4/IPv6 ping and IPv4/IPv6 traceroute. Assert exact prefixes, AS paths, next hops, peer IDs, communities, best-path state, metric, local preference, weight, VRF labels and populated traceroute hops. Check route tables, community menus, traceroute tables and native text in the browser.

Confirm cross-VRF prefix queries return no routes. Command captures and their manifest are in `hyperglass/plugins/tests/fixtures/dell-os10-live/`.

## Restricted-table profile

For a restricted-table profile, cap the default VRF at 10,000 prefixes per address family and retain one prefix per family in LAB. Include separate control prefixes carrying community `65000:777` for bounded community searches.

For slow CLI session initialization, set `request_timeout: 240` in `config.yaml` and `driver_config.read_timeout_override: 180` on the device. These settings allow session initialization and command execution to finish within the browser request timeout.

Repeat the query matrix against the restricted feed. The small-table captures remain the regression fixtures.

## Coverage limits

Application diagnostics target each context's own interface address. Traceroute validates one-hop execution and parsing, not remote routed forwarding. Community summaries remain text. AS-path searches use custom directives with configured filter lists. Fixture replay does not establish sustained full-table capacity.
