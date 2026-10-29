#!/usr/bin/env bash
set -e

IF=can0

# 如果不是 root，就自动用 sudo 重新执行
if [ "$EUID" -ne 0 ]; then
    exec sudo bash "$0" "$@"
fi

ip link set ${IF} down || true

ip link set ${IF} type can \
  bitrate 1000000 sample-point 0.80 \
  dbitrate 5000000 dsample-point 0.75 \
  fd on \
  restart-ms 100

ip link set ${IF} up

ip -details link show ${IF}