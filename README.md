<div align="center">
  <br/>
  <img src="https://res.cloudinary.com/hyperglass/image/upload/v1593916013/logo-light.svg" width=300></img>
  <br/>
  <h3>The network looking glass that tries to make the internet better.</h3>
  <br/>  
  A looking glass is implemented by network operators as a way of providing customers, peers, or the general public with a way to easily view elements of, or run tests from the provider's network.
</div>

<hr/>

> ### Fork notice
>
> This repository is a maintained fork of [**thatmattlove/hyperglass**](https://github.com/thatmattlove/hyperglass). The upstream project has been quiet for an extended period, so this fork carries production-oriented fixes that hadn't landed upstream as of v2.0.4.
>
> **Container images** are published to GHCR on every push to `main` and on tag pushes:
>
> | Tag | Updated by | Use case |
> | --- | --- | --- |
> | `ghcr.io/jsenecal/hyperglass:2.0.4-jsenecal.2` | tag push | immutable, recommended for production |
> | `ghcr.io/jsenecal/hyperglass:sha-<short>` | every build | per-commit immutable |
> | `ghcr.io/jsenecal/hyperglass:main` | every push to `main` | rolling HEAD |
> | `ghcr.io/jsenecal/hyperglass:latest` | every build | rolling whatever's freshest |
>
> **Maintained by** Jonathan Senecal &lt;jonathan.senecal@metrooptic.com&gt;. **Issues** belong in the [fork's tracker](https://github.com/jsenecal/hyperglass/issues), not upstream's.

#### Changes from upstream v2.0.4

- **[#356](https://github.com/thatmattlove/hyperglass/issues/356)** — Worker count is now cgroup- and affinity-aware (`os.process_cpu_count` / `sched_getaffinity`), capped at 8 by default, and overridable via the new `HYPERGLASS_WORKERS` env var. Stops containerized deployments on high-core hosts from OOM-killing themselves at startup.
- **[#354](https://github.com/thatmattlove/hyperglass/pull/354) / [#318](https://github.com/thatmattlove/hyperglass/issues/318)** — Pass `request_timeout` to netmiko's `send_command()` so long-running commands like traceroute don't fail at the 10s default.
- **[#341](https://github.com/thatmattlove/hyperglass/issues/341) / [#348](https://github.com/thatmattlove/hyperglass/issues/348)** — Pin `click<8.2` so fresh Docker / `pip install -e .` installs don't pick up a click release that's incompatible with `typer 0.9.0` and crash on startup.
- **[#330](https://github.com/thatmattlove/hyperglass/issues/330)** — Make the `Device.http` field optional so the existing "platform: http but no http params" validator branch is actually reachable.
- **[#334](https://github.com/thatmattlove/hyperglass/issues/334)** — Targeted CVE patches: bump Next.js to 13.5.11, Pillow ≥10.4, httpx ≥0.27, h11 ≥0.16, base image to rolling `python:3.12-alpine` with `apk upgrade`, setuptools ≥78.1.1.
- **CI** — Tag- and push-triggered multi-tag GHCR publish workflow (lifted from upstream's never-merged `docker-build` branch).

<hr/>

<div align="center">

[**Documentation**](https://hyperglass.dev)&nbsp;&nbsp;&nbsp;|&nbsp;&nbsp;&nbsp;[**Live Demo**](https://demo.hyperglass.dev/)

[![Frontend Tests](https://img.shields.io/github/actions/workflow/status/thatmattlove/hyperglass/frontend.yml?label=Frontend%20Tests&style=for-the-badge)](https://github.com/thatmattlove/hyperglass/actions/workflows/frontend.yml)
[![Backend Tests](https://img.shields.io/github/actions/workflow/status/thatmattlove/hyperglass/backend.yml?label=Backend%20Tests&style=for-the-badge)](https://github.com/thatmattlove/hyperglass/actions/workflows/backend.yml)

<br/>

hyperglass is intended to make implementing a looking glass too easy not to do, with the lofty goal of improving the internet community at large by making looking glasses more common across autonomous systems of any size.

</div>

### [Changelog](https://hyperglass.dev/changelog)

## Features

- BGP Route, BGP Community, BGP AS Path, Ping, & Traceroute, or [add your own commands](https://hyperglass.dev/configuration/directives).
- Full IPv6 support
- Customizable everything: features, theme, UI/API text, error messages, commands
- Built-in support for:
  - Arista EOS
  - BIRD
  - Cisco IOS
  - Cisco NX-OS
  - Cisco IOS-XR
  - FRRouting
  - Huawei VRP
  - Juniper Junos
  - Mikrotik
  - Nokia SR OS
  - OpenBGPD
  - TNSR
  - VyOS
- Configurable support for any other [supported platform](https://hyperglass.dev/platforms)
- Optionally access devices via an SSH proxy/jump server
- Access-list/prefix-list style query control to whitelist or blacklist query targets
- REST API with automatic, configurable OpenAPI documentation
- Modern, responsive UI built on [ReactJS](https://reactjs.org/), with [NextJS](https://nextjs.org/) & [Chakra UI](https://chakra-ui.com/), written in [TypeScript](https://www.typescriptlang.org/)
- Query multiple devices simultaneously
- Browser-based DNS-over-HTTPS resolution of FQDN queries

*To request support for a specific platform, please [submit a Github Issue](https://github.com/thatmattlove/hyperglass/issues/new) with the **feature** label.*

### [Get Started →](https://hyperglass.dev/installation)

## Community

- [Slack](https://netdev.chat/)
- [Telegram](https://t.me/hyperglasslg)

Any users, potential users, or contributors of hyperglass are welcome to join and discuss usage, feature requests, bugs, and other things.

**hyperglass is developed with the express intention of being free to the networking community**.

*However, if you're feeling particularly helpful or generous, small donations are welcome.*

[![Donate](https://img.shields.io/badge/Donate-blue.svg?logo=paypal&style=for-the-badge)](https://www.paypal.com/cgi-bin/webscr?cmd=_s-xclick&hosted_button_id=ZQFH3BB2B5M3E&source=url)

## Acknowledgements

hyperglass is built entirely on open-source software. Here are some of the awesome libraries used, check them out too!

- [Netmiko](https://github.com/ktbyers/netmiko)
- [Litestar](https://litestar.dev)
- [Pydantic](https://docs.pydantic.dev/latest/)
- [Chakra UI](https://chakra-ui.com/)

[![GitHub](https://img.shields.io/github/license/thatmattlove/hyperglass?color=330036&style=for-the-badge)](https://github.com/thatmattlove/hyperglass/blob/main/LICENSE)
