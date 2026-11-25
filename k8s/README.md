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

For a fresh cluster, create the `homelab` namespace and generate the admin password before applying the overlay. Run these commands from the repo root on `blackbox`.

```sh
kubectl apply --server-side --field-manager=homelab -f k8s/base/namespace.yaml
od -An -N24 -tx1 /dev/urandom | tr -d '[:space:]' | \
  kubectl -n homelab create secret generic pihole --from-file=web-password=/dev/stdin
```

Read the admin password from its Kubernetes Secret.

```sh
kubectl -n homelab get secret pihole -o jsonpath='{.data.web-password}' | base64 -d
printf '\n'
```
