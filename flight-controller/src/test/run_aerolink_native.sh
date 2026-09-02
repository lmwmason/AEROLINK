#!/bin/sh
set -eu
fc_root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
repo_root=$(CDPATH= cd -- "$fc_root/.." && pwd)
cc -std=c11 -Wall -Wextra -Werror -DAEROLINK_NATIVE_TEST -DUSE_AEROLINK -I"$fc_root/src/main" \
  "$fc_root/src/main/io/aerolink.c" "$fc_root/src/test/unit/aerolink_native_test.c" \
  -o /tmp/aerolink_native_test
/tmp/aerolink_native_test "$repo_root/raspberry-pi/tests/vectors/uart_v1.json"
cc -std=c11 -Wall -Wextra -Werror -DAEROLINK_NATIVE_TEST -I"$fc_root/src/main" -c "$fc_root/src/main/io/aerolink.c" \
  -o /tmp/aerolink_disabled.o
