#!/bin/sh
# Show lab containers and BGP session state.
cd "$(dirname "$0")"
echo "== containers =="
docker ps --format '{{.Names}}\t{{.Status}}' | grep clab-hyperglass | sort
echo
echo "== core BGP sessions =="
docker exec clab-hyperglass-core gobgp neighbor 2>/dev/null || echo "core not running"
