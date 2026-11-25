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
