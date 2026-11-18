#!/bin/sh
# Build the lab images: core, the Linux routers and hyperglass from this repo.
set -eu
cd "$(dirname "$0")/.."
for i in core frr bird openbgpd; do
  docker build -t "hyperglass-lab/$i:latest" "images/$i"
done
docker build -t hyperglass-lab/hyperglass:dev ..
