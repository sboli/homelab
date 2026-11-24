# K3s manifests

Put shared manifests in `base/` and list them in its `kustomization.yaml`. Put settings specific to the `blackbox` cluster in `overlays/blackbox/`. The overlay deploys namespaced resources into `homelab`.

From the repo root, render the manifests locally.

```sh
kustomize build k8s/overlays/blackbox
```

After pushing changes to `main`, run this on `blackbox`.

```sh
git -C "$HOME/pgit/homelab" pull --ff-only &&
  sudo k3s kubectl apply --server-side --field-manager=homelab \
    -k "$HOME/pgit/homelab/k8s/overlays/blackbox"
```
