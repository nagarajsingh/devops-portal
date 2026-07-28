from __future__ import annotations

from fastapi import HTTPException
from kubernetes import client, config
from kubernetes.client.rest import ApiException

from .config import NAMESPACE_ALLOWLIST
from .logging_config import get_logger
from .models import ServiceOption

logger = get_logger("kubernetes")


def load_k8s() -> None:
    try:
        config.load_incluster_config()
        logger.debug("Loaded in-cluster Kubernetes configuration")
    except config.ConfigException:
        config.load_kube_config()
        logger.debug("Loaded local Kubernetes configuration")


def cluster_namespaces() -> list[str]:
    try:
        load_k8s()
        names = [item.metadata.name for item in client.CoreV1Api().list_namespace().items]
        allowed = sorted(name for name in names if not NAMESPACE_ALLOWLIST or name in NAMESPACE_ALLOWLIST)
        logger.debug("Namespaces loaded count=%s allowed=%s", len(names), len(allowed))
        return allowed
    except Exception:
        logger.exception("Unable to list namespaces; using configured allowlist")
        return sorted(NAMESPACE_ALLOWLIST)


def namespace_ingresses(namespace: str) -> list[str]:
    if namespace not in cluster_namespaces():
        logger.warning("Ingress listing denied namespace=%s", namespace)
        raise HTTPException(status_code=400, detail="Namespace is not allowed")
    try:
        load_k8s()
        items = client.NetworkingV1Api().list_namespaced_ingress(namespace).items
        names = sorted(item.metadata.name for item in items if item.metadata and item.metadata.name)
        logger.info("Ingresses listed namespace=%s count=%s", namespace, len(names))
        return names
    except ApiException as exc:
        logger.exception("Unable to list ingresses namespace=%s", namespace)
        raise HTTPException(status_code=exc.status or 500, detail=f"Unable to list ingresses in namespace {namespace}: {exc.reason}") from exc


def namespace_services(namespace: str) -> list[ServiceOption]:
    if namespace not in cluster_namespaces():
        logger.warning("Service listing denied namespace=%s", namespace)
        raise HTTPException(status_code=400, detail="Namespace is not allowed")
    try:
        load_k8s()
        items = client.CoreV1Api().list_namespaced_service(namespace).items
        services = [ServiceOption(name=item.metadata.name, ports=sorted({port.port for port in item.spec.ports or []})) for item in items if item.metadata and item.metadata.name]
        logger.info("Services listed namespace=%s count=%s", namespace, len(services))
        return services
    except ApiException as exc:
        logger.exception("Unable to list services namespace=%s", namespace)
        raise HTTPException(status_code=exc.status or 500, detail=f"Unable to list services in namespace {namespace}: {exc.reason}") from exc


def ensure_service(item: dict) -> str:
    if not item.get("create_service"):
        logger.info("Kubernetes service creation skipped request_id=%s service=%s namespace=%s", item.get("id"), item.get("service_name"), item.get("namespace"))
        return "Skipped"
    load_k8s()
    api = client.CoreV1Api()
    name = item["service_name"]
    namespace = item["namespace"]
    logger.info("Ensuring Kubernetes service request_id=%s service=%s namespace=%s port=%s", item.get("id"), name, namespace, item.get("service_port"))
    try:
        api.read_namespaced_service(name, namespace)
        logger.info("Kubernetes service already exists request_id=%s service=%s namespace=%s", item.get("id"), name, namespace)
        return "Already Exists"
    except ApiException as exc:
        if exc.status != 404:
            logger.exception("Unable to read Kubernetes service request_id=%s service=%s namespace=%s", item.get("id"), name, namespace)
            raise
    service = client.V1Service(
        metadata=client.V1ObjectMeta(name=name, labels={"app": item["repository_name"], "managed-by": "devops-portal"}),
        spec=client.V1ServiceSpec(selector={"app": item["repository_name"]}, ports=[client.V1ServicePort(name="http", port=item["service_port"], target_port=item["service_port"])], type="ClusterIP"),
    )
    api.create_namespaced_service(namespace, service)
    logger.info("Kubernetes service created request_id=%s service=%s namespace=%s port=%s", item.get("id"), name, namespace, item.get("service_port"))
    return "Completed"


def validate_existing_service(item: dict) -> None:
    load_k8s()
    api = client.CoreV1Api()
    logger.info("Validating existing Kubernetes service request_id=%s service=%s namespace=%s port=%s", item.get("id"), item.get("service_name"), item.get("namespace"), item.get("service_port"))
    try:
        service = api.read_namespaced_service(item["service_name"], item["namespace"])
    except ApiException as exc:
        if exc.status == 404:
            logger.warning("Existing service not found request_id=%s service=%s namespace=%s", item.get("id"), item.get("service_name"), item.get("namespace"))
            raise RuntimeError(f"Service {item['service_name']} does not exist in namespace {item['namespace']}") from exc
        logger.exception("Unable to validate existing service request_id=%s service=%s namespace=%s", item.get("id"), item.get("service_name"), item.get("namespace"))
        raise
    ports = sorted({port.port for port in service.spec.ports or []})
    if item["service_port"] not in ports:
        logger.warning("Existing service port mismatch request_id=%s service=%s requested_port=%s available_ports=%s", item.get("id"), item.get("service_name"), item.get("service_port"), ports)
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
    logger.info("Updating ingress request_id=%s ingress=%s namespace=%s service=%s port=%s", item.get("id"), ingress_name, item.get("namespace"), item.get("service_name"), item.get("service_port"))
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
    logger.info("Ingress updated request_id=%s ingress=%s namespace=%s path=%s action=%s", item.get("id"), ingress_name, item.get("namespace"), path_value, action)
    return {"status": "Completed", "message": f"{action} {path_value} in ingress {ingress_name} using {mode} {item['service_name']}:{item['service_port']}"}
