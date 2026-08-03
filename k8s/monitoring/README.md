# Monitoring dashboard Kubernetes notes

The monitoring dashboard is served by the existing DevOps Portal frontend and backend deployments. It does not require a separate Kubernetes Deployment or ServiceAccount.

The backend continues to use the ServiceAccount already configured in the MS setup backend manifest:

```yaml
serviceAccountName: devops-portal-backend
```

The first monitoring release reads:

- Kubernetes inventory from the configured shared inventory JSON file.
- DevOps Portal request and provisioning status from the existing request storage.

No additional cluster-wide permissions are introduced by this feature. Remote cluster data continues to be supplied through the inventory file, while local-cluster access continues to use the permissions already assigned to `devops-portal-backend`.

Required backend route:

```text
GET /monitoring/summary
```

The route is restricted to authenticated DevOps users.
