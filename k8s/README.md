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

MetalLB advertises `LoadBalancer` service IPs on the LAN from `192.168.1.210` through `192.168.1.240`. On a fresh `blackbox` installation, run `nixos/rebuild.sh` to disable K3s ServiceLB before installing MetalLB.

From the repo root on `blackbox`, apply the controller and speakers, then apply the Layer 2 pool once they are ready.

```sh
kubectl apply --server-side --field-manager=homelab -k k8s/infrastructure/metallb &&
  kubectl -n metallb-system rollout status deployment/controller --timeout=5m &&
  kubectl -n metallb-system rollout status daemonset/speaker --timeout=5m &&
  kubectl apply --server-side --field-manager=homelab -k k8s/overlays/blackbox/metallb
```
