from __future__ import annotations

from fastapi import HTTPException
from kubernetes import client, config
from kubernetes.client.rest import ApiException

from .config import NAMESPACE_ALLOWLIST
from .models import ServiceOption


def load_k8s() -> None:
    try:
        config.load_incluster_config()
    except config.ConfigException:
        config.load_kube_config()


def cluster_namespaces() -> list[str]:
    try:
        load_k8s()
        names = [item.metadata.name for item in client.CoreV1Api().list_namespace().items]
        return sorted(name for name in names if not NAMESPACE_ALLOWLIST or name in NAMESPACE_ALLOWLIST)
    except Exception:
        return sorted(NAMESPACE_ALLOWLIST)


def namespace_ingresses(namespace: str) -> list[str]:
    if namespace not in cluster_namespaces():
        raise HTTPException(status_code=400, detail="Namespace is not allowed")
    try:
        load_k8s()
        items = client.NetworkingV1Api().list_namespaced_ingress(namespace).items
        return sorted(item.metadata.name for item in items if item.metadata and item.metadata.name)
    except ApiException as exc:
        raise HTTPException(status_code=exc.status or 500, detail=f"Unable to list ingresses in namespace {namespace}: {exc.reason}") from exc


def namespace_services(namespace: str) -> list[ServiceOption]:
    if namespace not in cluster_namespaces():
        raise HTTPException(status_code=400, detail="Namespace is not allowed")
    try:
        load_k8s()
        items = client.CoreV1Api().list_namespaced_service(namespace).items
        return [ServiceOption(name=item.metadata.name, ports=sorted({port.port for port in item.spec.ports or []})) for item in items if item.metadata and item.metadata.name]
    except ApiException as exc:
        raise HTTPException(status_code=exc.status or 500, detail=f"Unable to list services in namespace {namespace}: {exc.reason}") from exc


def ensure_service(item: dict) -> str:
    if not item.get("create_service"):
        return "Skipped"
    load_k8s()
    api = client.CoreV1Api()
    name = item["service_name"]
    namespace = item["namespace"]
    try:
        api.read_namespaced_service(name, namespace)
        return "Already Exists"
    except ApiException as exc:
        if exc.status != 404:
            raise
    service = client.V1Service(
        metadata=client.V1ObjectMeta(name=name, labels={"app": item["repository_name"], "managed-by": "devops-portal"}),
        spec=client.V1ServiceSpec(selector={"app": item["repository_name"]}, ports=[client.V1ServicePort(name="http", port=item["service_port"], target_port=item["service_port"])], type="ClusterIP"),
    )
    api.create_namespaced_service(namespace, service)
    return "Completed"


def validate_existing_service(item: dict) -> None:
    load_k8s()
    api = client.CoreV1Api()
    try:
        service = api.read_namespaced_service(item["service_name"], item["namespace"])
    except ApiException as exc:
        if exc.status == 404:
            raise RuntimeError(f"Service {item['service_name']} does not exist in namespace {item['namespace']}") from exc
        raise
    ports = sorted({port.port for port in service.spec.ports or []})
    if item["service_port"] not in ports:
        raise RuntimeError(f"Service {item['service_name']} does not expose port {item['service_port']}; available ports: {', '.join(map(str, ports))}")


def ensure_ingress_path(item: dict) -> dict[str, str]:
    ingress_name = (item.get("ingress_name") or "").strip()
    if not ingress_name:
        raise RuntimeError("No ingress resource was selected by DevOps")
    if not item.get("service_name"):
        raise RuntimeError("Select a Kubernetes service for ingress provisioning")
    if not item.get("create_service"):
        validate_existing_service(item)
    load_k8s()
    api = client.NetworkingV1Api()
    ingress = api.read_namespaced_ingress(ingress_name, item["namespace"])
    rules = ingress.spec.rules or []
    target_rule = next((rule for rule in rules if rule.http is not None), None)
    if target_rule is None:
        raise RuntimeError(f"Ingress {ingress_name} does not contain an HTTP rule")
    path_value = item["ingress_path"] if item["ingress_path"].startswith("/") else f"/{item['ingress_path']}"
    if not path_value.endswith("(/|$)(.*)"):
        path_value = f"{path_value}(/|$)(.*)"
    paths = target_rule.http.paths or []
    backend = client.V1IngressBackend(service=client.V1IngressServiceBackend(name=item["service_name"], port=client.V1ServiceBackendPort(number=item["service_port"])))
    existing = next((path for path in paths if path.path == path_value), None)
    if existing:
        existing.backend = backend
        action = "Updated existing path"
    else:
        paths.append(client.V1HTTPIngressPath(path=path_value, path_type="ImplementationSpecific", backend=backend))
        action = "Added path"
    target_rule.http.paths = paths
    ingress.spec.rules = rules
    api.replace_namespaced_ingress(ingress_name, item["namespace"], ingress)
    mode = "existing service" if not item.get("create_service") else "service"
    return {"status": "Completed", "message": f"{action} {path_value} in ingress {ingress_name} using {mode} {item['service_name']}:{item['service_port']}"}
