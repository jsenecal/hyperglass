# Hyperglass multi-vendor lab

The main topology connects routers to a GoBGP core. Hyperglass queries them through a shared management network. The companion topology runs one optional appliance with a small test feed.

Run commands from `lab/` unless a command gives another directory.

## Requirements

- Docker and Containerlab.
- Python with PyYAML and Netmiko.
- KVM for VM-based appliances.
- Vendor images and licences obtained separately. The repository contains no vendor binaries.

All topology defaults set `privileged: false`. Do not bypass container isolation to run an appliance. Run hardware-dependent appliances in an isolated VM.

## Files

- `hyperglass-lab.clab.yml`: main routers, GoBGP, Redis and two Hyperglass instances.
- `hyperglass-platforms.clab.yml`: optional router appliances.
- `hyperglass-firewalls.clab.yml`: optional firewall appliances; see [setup](configs/firewalls/README.md).
- `configs/hyperglass/`: structured-output configuration.
- `configs/hyperglass-text/`: text-output configuration.
- `images/`: Dockerfiles and wrappers, not vendor images.
- `scripts/`: build, configuration and query helpers.
- `tests/`: integration tests against running devices.

## Build and start

```sh
sh scripts/build-images.sh
./lab-up.sh frr
./lab-status.sh
```

The structured instance listens on `http://127.0.0.1:8001`. The text instance listens on `http://127.0.0.1:8002`. A published image can be selected with `lab-up.sh --image <image>`.

The core starts without a full table. The default fixture advertises `1.0.0.0/24` and `2606:4700:4700::/48`, with AS path `64999 13335`, community `65000:777` and large community `65000:777:1`.

```sh
sh scripts/inject-test-routes.sh
sh scripts/inject-table.sh
```

The full-table helper reads local MRT files from `data/`.

## Optional appliances

```sh
sh platform.sh list
sh platform.sh start iosv
sh platform.sh status
sh platform.sh stop
```

The helper runs one optional appliance and its GoBGP probe. Restarting the same appliance preserves its disk. Selecting another appliance discards the previous appliance-local changes. Store repeatable configuration in startup files.

## Queries

```sh
python3 scripts/smoke-test.py
python3 scripts/test-device.py lab-frr
python3 -m pytest tests/ -k frr -v
HYPERGLASS_LAB_TEXT=1 HYPERGLASS_LAB_API=http://127.0.0.1:8002/api python3 -m pytest tests/ -k frr -v
```

The tests skip unavailable devices. `HYPERGLASS_LAB_API` selects an API endpoint. `HYPERGLASS_LAB_TEXT=1` selects text query expectations.

Run `scripts/verify-policy-matrix.py --help` for structured-policy and RPKI checks. The helper injects fixture routes and can query an external RPKI provider.

## Platform notes

- Cisco IOS and NX-OS IPv6 BGP Route queries require a prefix no longer than `/127`. A bare IPv6 host becomes `/128` and is rejected.
- IOSv IPv6 traceroute accepts only its destination. Its custom lab directive omits the source address.
- Junos forwarding requires an online FPC.
- Huawei VRPv8 uses `huawei_vrpv8`. Configure its routed data port with `scripts/configure-huawei.py`.
- Start one Huawei VM at a time.
- RouterOS 6 requires its IPv6 package for IPv6 queries.
- The Arista and FRR configurations include VRF `LAB`. A VRF is a separate device location with `vrf: LAB`.
- The Arista BGP Summary directive demonstrates fixed-choice query variables.

## Stop

```sh
sh platform.sh stop
./lab-down.sh
```

Built images and input files remain available after teardown.
