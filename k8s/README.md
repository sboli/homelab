# K3s manifests

Put shared manifests in `base/` and list them in its `kustomization.yaml`. Put settings specific to the `blackbox` cluster in `overlays/blackbox/`. The overlay deploys namespaced resources into `homelab`.

From the repo root, render the manifests locally.

```sh
kustomize build k8s/overlays/blackbox
```

After pushing changes to `main`, run this on `blackbox`.

```sh
git -C "$HOME/pgit/homelab" pull --ff-only &&
  kubectl apply --server-side --field-manager=homelab \
    -k "$HOME/pgit/homelab/k8s/overlays/blackbox"
```

## Cloudflare Tunnel

The `cloudflared` deployment on `blackbox` uses a remotely managed tunnel. Its application routes are configured in the Cloudflare dashboard. On a fresh cluster, create the `homelab` namespace and provide the tunnel token from an SSH session on `blackbox` before applying the overlay.

```bash
read -rsp 'Tunnel token: ' tunnel_token
printf '\n'
printf '%s' "$tunnel_token" |
  kubectl -n homelab create secret generic cloudflared-tunnel \
    --from-file=token=/dev/stdin --dry-run=client -o yaml |
  kubectl apply --server-side --field-manager=homelab-secrets -f -
unset tunnel_token
```

After rotating the token in Cloudflare and updating the Secret, run `kubectl -n homelab rollout restart deployment/cloudflared`. Use `kubectl -n homelab rollout status deployment/cloudflared` to verify connector readiness.

## MetalLB

MetalLB reserves `192.168.1.210` for Traefik and automatically assigns `192.168.1.211` through `192.168.1.240` to other `LoadBalancer` services. On a fresh `blackbox` installation, run `nixos/rebuild.sh` to disable K3s ServiceLB before installing MetalLB.

From the repo root on `blackbox`, apply the controller and speakers, then apply the Layer 2 pools and Traefik's IP request once they are ready.

```sh
kubectl apply --server-side --field-manager=homelab -k k8s/infrastructure/metallb &&
  kubectl -n metallb-system rollout status deployment/controller --timeout=5m &&
  kubectl -n metallb-system rollout status daemonset/speaker --timeout=5m &&
  kubectl apply --server-side --field-manager=homelab -k k8s/overlays/blackbox/metallb &&
  kubectl apply --server-side --field-manager=homelab -k k8s/overlays/blackbox/traefik
```

## Pi-hole

Pi-hole uses the host network to serve DNS over TCP and UDP at `192.168.1.200:53`. Its admin UI is available through Traefik at `http://pihole.home.stephenbolivar.com/admin/`.

Pi-hole stores `/etc/pihole` in `/mnt/bigdata/pvcs/pihole`. The persistent volume mounts `192.168.1.201:/volume1/media/pvcs/pihole` directly and retains the data if the claim is deleted. Pi-hole uses SQLite rollback journaling on NFS and runs with the UID and GID used by the NAS export.

For a fresh cluster, create the data directory on the mounted NAS, then create the `homelab` namespace and generate the admin password before applying the overlay. Run these commands from the repo root on `blackbox`.

```sh
mkdir -p -m 0700 /mnt/bigdata/pvcs/pihole
kubectl apply --server-side --field-manager=homelab -f k8s/base/namespace.yaml
od -An -N24 -tx1 /dev/urandom | tr -d '[:space:]' | \
  kubectl -n homelab create secret generic pihole --from-file=web-password=/dev/stdin
```

Read the admin password from its Kubernetes Secret.

```sh
kubectl -n homelab get secret pihole -o jsonpath='{.data.web-password}' | base64 -d
printf '\n'
```

## Jellyfin

Jellyfin is available at `http://jellyfin.home.stephenbolivar.com/`. The [Jellyfin overlay](overlays/blackbox/jellyfin/) manages storage, ingress, network settings, and SQLite settings. On startup Jellyfin reconciles the server settings and named libraries in `settings.json`. The initial administrator is `boli` and the Movies and TV Shows folders are mounted read-only. Newly added media is discovered by Jellyfin's scheduled scans.

The database, user accounts, watch history, and cache live on the NAS under `/mnt/bigdata/pvcs/jellyfin`. The deployment runs one replica and configures SQLite rollback journaling for NFS. Jellyfin recommends local storage for its SQLite database.

On a fresh `blackbox` cluster, create the NAS directory and admin secret before applying the overlay. Run these commands from the repo root.

```sh
mkdir -p -m 0700 /mnt/bigdata/pvcs/jellyfin
kubectl apply --server-side --field-manager=homelab -f k8s/base/namespace.yaml
od -An -N24 -tx1 /dev/urandom | tr -d '[:space:]' | \
  kubectl -n homelab create secret generic jellyfin-admin --from-file=password=/dev/stdin
```

Retrieve the password on `blackbox`. Keep the Secret and Jellyfin administrator password in sync so the startup configuration can authenticate on later restarts.

```sh
kubectl -n homelab get secret jellyfin-admin -o jsonpath='{.data.password}' | base64 -d
printf '\n'
```

## Homepage

The dashboard is available at `http://homepage.home.stephenbolivar.com/`. Edit [services.yaml](overlays/blackbox/homepage/services.yaml) to add links and health checks, and [settings.yaml](overlays/blackbox/homepage/settings.yaml) to change the layout. Applying the `blackbox` overlay rolls out changes to these files. Homepage uses a memory-backed volume for its runtime configuration.

## qBittorrent

Sign in as `boli` at `http://qbittorrent.home.stephenbolivar.com/`. The [qBittorrent overlay](overlays/blackbox/qbittorrent/) uses host networking and enables UPnP/NAT-PMP for a random TCP/UDP peer port on `192.168.1.200`. The web UI uses port `8089` behind Traefik and has its own UPnP mapping disabled.

Config and resume data live under `/mnt/bigdata/pvcs/qbittorrent`. Downloads go to `/mnt/downloads` on `blackbox`'s local disk. The NixOS configuration creates that directory, and the pod mounts it at the same path.

qBittorrent loads [David Moore's IP filter](https://github.com/DavidMoore/ipfilter/releases/tag/lists) for peers. The init container refreshes the list when the pod starts and falls back to its previous NAS copy if the download fails.

On a fresh cluster, create the config directory on `blackbox` and apply the namespace manifest first.

```sh
mkdir -p -m 0700 /mnt/bigdata/pvcs/qbittorrent
kubectl apply --server-side --field-manager=homelab -f k8s/base/namespace.yaml
```

From the Mac at the repo root, enter the web password to create the hash Secret, then apply the overlay on `blackbox`.

```sh
python3 k8s/overlays/blackbox/qbittorrent/password.py | \
  ssh boli@192.168.1.200 \
    'kubectl -n homelab create secret generic qbittorrent-webui --from-file=password-hash=/dev/stdin'
```

## Media requests and automation

Open Seerr, Prowlarr, Radarr, and Sonarr from Homepage. Seerr uses your Jellyfin credentials. The three Arr apps use the `boli` account and the password in the `media-stack` Secret.

```sh
kubectl -n homelab get secret media-stack -o jsonpath='{.data.arr-admin-password}' | base64 -d
printf '\n'
```

Seerr sends movie requests to Radarr and TV requests to Sonarr. Prowlarr syncs configured indexers to both. Sonarr and Radarr use separate qBittorrent categories under `/mnt/downloads`, import completed files into their respective NAS libraries, and notify Jellyfin to refresh. Add your indexers in Prowlarr.

Prowlarr uses the `flaresolverr` tag to select indexers for its FlareSolverr proxy. Apply the tag to the indexer in Prowlarr when it requires that proxy. FlareSolverr runs on the cluster network and accepts connections from Prowlarr.

The [media overlay](overlays/blackbox/media/) stores app config and PostgreSQL data under `/mnt/bigdata/pvcs/media-stack`. On a fresh cluster, create the namespace and run `sh k8s/overlays/blackbox/media/prepare.sh` on `blackbox` before applying the overlay. The script provisions the database credentials and the qBittorrent API key in Kubernetes Secrets.

## Unmanic

Open Unmanic from Homepage. It scans the Jellyfin Movies and TV Shows folders at startup and daily, with one Intel Quick Sync encode at a time. The profile encodes HEVC at ICQ 20 with the slow preset. It selects progressive 8-bit SDR H.264 in MKV or MP4 up to 1080p and skips low-bitrate files, files over 24 GiB, files less than a day old, and hard-linked files. Audio, subtitles, chapters, and the container are preserved. It replaces a source atomically only after verifying streams and duration and saving at least 15%.

Unmanic keeps its state under `/mnt/bigdata/pvcs/unmanic` and uses temporary local storage for encodes. On a fresh cluster, run `mkdir -p -m 0775 /mnt/bigdata/pvcs/unmanic` on `blackbox` before applying the overlay. To pause the encoder, pause the worker in Unmanic. Worker and scanner settings are reapplied when the pod starts.

The Intel GPU device plugin exposes two allocations of blackbox's integrated GPU so Jellyfin can use Quick Sync for playback transcoding while Unmanic is encoding.
