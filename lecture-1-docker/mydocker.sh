#!/bin/bash
set -euo pipefail

cg=/sys/fs/cgroup/lab1-api
sudo mkdir -p "$cg"
echo "success mkdir '$cg'"
echo 268435456 | sudo tee "$cg/memory.max" >/dev/null
echo 0 | sudo tee "$cg/memory.swap.max" >/dev/null
echo '50000 100000' | sudo tee "$cg/cpu.max" >/dev/null
echo 64 | sudo tee "$cg/pids.max" >/dev/null

api=$(cd "$(dirname "$0")/api" && pwd)

unshare --user --map-root-user --pid --fork --mount --mount-proc --net --uts --ipc \
  bash -c "
    for i in \$(seq 1 50); do
      ip link show veth-api >/dev/null 2>&1 && break
      sleep 0.1
    done
    ip addr add 10.0.0.2/24 dev veth-api
    ip link set veth-api up
    exec /usr/sbin/capsh --drop=cap_sys_time -- -c \"cd '$api' && exec go run .\"
  " &
ns_pid=$!
sudo ip link add veth-lab type veth peer name veth-api
for i in $(seq 1 50); do
  sudo ip link set veth-api netns "$ns_pid" && break
  sleep 0.1
done
sudo ip addr add 10.0.0.1/24 dev veth-lab
sudo ip link set veth-lab up
api_pid=
for i in $(seq 1 100); do
  for cand in $(pgrep -f '/exe/api' || true); do
    if [ "$(readlink "/proc/$cand/ns/net")" = "$(readlink "/proc/$ns_pid/ns/net")" ]; then
      api_pid=$cand
      break
    fi
  done
  [ -n "$api_pid" ] && break
  sleep 0.1
done
echo "$api_pid" | sudo tee "$cg/cgroup.procs" >/dev/null
wait "$ns_pid"