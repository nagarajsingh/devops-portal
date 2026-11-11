# Kubernetes Logs

The Kubernetes Logs module is available to both Developer and DevOps portal users.

## Security model

- No namespace is exposed by default.
- DevOps users manage the namespace allowlist from the portal.
- The backend enforces the allowlist for pod listing, viewing and downloads.
- Local-cluster logs use the backend ServiceAccount directly.
- Remote-cluster logs use a read-only per-cluster log agent and a shared NFS broker.
- Remote broker requests are HMAC-signed with a dedicated shared secret.

## Remote cluster installation

The log agent uses the same RWX/NFS PVC pattern as the existing cluster inventory job.

1. Create the shared secret in the remote cluster:

```bash
kubectl -n automation create secret generic devops-portal-log-agent-secret \
  --from-literal=BROKER_SECRET='<same-long-random-secret-used-by-portal-backend>'
```

2. Edit `remote-log-agent.yaml` and set:

```yaml
CLUSTER_NAME: "mashreq-nativemob-safenet-nonprod"
```

The value must exactly match one of the portal `KUBERNETES_TARGETS`.

3. Ensure `devops-portal-inventory-pvc` mounts the same NFS path visible to the portal backend.

4. Apply:

```bash
kubectl apply -f k8s/logs/remote-log-agent.yaml
```

5. Verify:

```bash
kubectl -n automation get pods -l app=devops-portal-log-agent
kubectl -n automation logs deploy/devops-portal-log-agent
```

Repeat for each remote cluster.

## Backend configuration

Set the same secret in `devops-portal-secrets`:

```text
KUBERNETES_LOG_BROKER_SECRET=<same value as remote agents>
```

If `KUBERNETES_LOG_BROKER_DIR` is omitted, the backend derives the broker directory from `KUBERNETES_INVENTORY_FILE` and appends `kubernetes-log-broker`.

When the inventory path and broker are mounted differently, configure it explicitly:

```text
KUBERNETES_LOG_BROKER_DIR=/shared/devops-portal/kubernetes-log-broker
```

## Log history behavior

The portal offers Live, 5m, 10m, 30m, 1h, 5h, 12h, 24h, 3d and 7d windows.

Kubernetes native logs can return:
- current container logs,
- the previous terminated container instance when still available,
- logs from Succeeded/Failed pods that still exist in the cluster.

Kubernetes cannot return logs for pods that have already been deleted/garbage-collected. For guaranteed multi-day history of deleted pods, connect this UI to the organization's centralized log platform (for example Splunk) as a historical provider.
