#!/bin/sh
set -eu

storage=/mnt/bigdata/pvcs/media-stack
test "$(findmnt -rn -M /mnt/bigdata -t nfs,nfs4 -o SOURCE)" = 192.168.1.201:/volume1/media
mkdir -p -m 0700 "$storage" "$storage/postgres" "$storage/prowlarr" "$storage/radarr" "$storage/sonarr" "$storage/seerr"

if test -z "$(kubectl -n homelab get secret media-stack --ignore-not-found -o name)"; then
  {
    printf '{"apiVersion":"v1","kind":"Secret","metadata":{"name":"media-stack","namespace":"homelab"},"stringData":{'
    separator=
    for key in postgres-password prowlarr-db radarr-db sonarr-db seerr-db arr-admin-password prowlarr-api-key radarr-api-key sonarr-api-key; do
      length=24
      case "$key" in *-api-key) length=16 ;; esac
      printf '%s"%s":"%s"' "$separator" "$key" "$(od -An -N"$length" -tx1 /dev/urandom | tr -d '[:space:]')"
      separator=,
    done
    printf '}}\n'
  } | kubectl create -f -
fi

if test -z "$(kubectl -n homelab get secret media-qbittorrent --ignore-not-found -o name)"; then
  config=/mnt/bigdata/pvcs/qbittorrent/qBittorrent/qBittorrent.conf
  key=
  if test -r "$config"; then
    key=$(sed -n 's/^APIKey=\(qbt_[A-Za-z0-9]\{28\}\)$/\1/p' "$config")
  fi
  if test -z "$key"; then
    key=qbt_$(od -An -N14 -tx1 /dev/urandom | tr -d '[:space:]')
  fi
  printf '%s' "$key" |
    kubectl -n homelab create secret generic media-qbittorrent --from-file=api-key=/dev/stdin
fi
