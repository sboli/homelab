#!/bin/sh
set -eu

config_dir=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd -P)
exec sudo nixos-rebuild switch -I "nixos-config=$config_dir/configuration.nix"
