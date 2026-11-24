#!/bin/sh
set -eu

config_dir=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd -P)
sudo nixos-rebuild switch -I "nixos-config=$config_dir/configuration.nix"

exec sudo install -m 0644 -- \
    "$config_dir/hardware-configuration.nix" \
    "$config_dir/configuration.nix" \
    /etc/nixos/
