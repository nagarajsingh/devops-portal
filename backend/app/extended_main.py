from __future__ import annotations

import base64
import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from fastapi import Depends, HTTPException
from kubernetes import client
from kubernetes.client.rest import ApiException

from . import main

app = main.app


def azdo_request(method: str, path: str, payload: dict | None = None) -> tuple[int, dict]:
    """Call Azure DevOps and support both JSON and raw repository-item responses."""
    if not main.AZDO_ORG or not main.AZDO_PROJECT or not main.AZDO_PAT:
        raise RuntimeError("Azure DevOps organization, project or PAT is not configured")

    url = (
        f"https://dev.azure.com/{urllib.parse.quote(main.AZDO_ORG)}/"
        f"{urllib.parse.quote(main.AZDO_PROJECT)}/{path}"
    )
    token = base64.b64encode(f":{main.AZDO_PAT}".encode()).decode()
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"Authorization": f"Basic {token}", "Content-Type": "application/json"},
    )

    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            raw = response.read().decode()
            try:
                body = json.loads(raw or "{}")
            except json.JSONDecodeError:
                body = {"content": raw}
            return response.status, body
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode()
        try:
            body = json.loads(raw or "{}")
        except json.JSONDecodeError:
            body = {"message": raw or f"Azure DevOps request failed with HTTP {exc.code}"}
        return exc.code, body


# Existing main.py functions resolve this global dynamically, so replacing it
# also fixes reference file downloads without modifying code during image build.
main.azdo_request = azdo_request


def namespace_services(namespace: str) -> list[dict[str, Any]]:
    if namespace not in main.cluster_namespaces():
        raise HTTPException(status_code=400, detail="Namespace is not allowed")

    try:
        main.load_k8s()
        items = client.CoreV1Api().list_namespaced_service(namespace).items
        services: list[dict[str, Any]] = []
        for item in items:
            if not item.metadata or not item.metadata.name:
                continue
            ports = sorted({port.port for port in (item.spec.ports or []) if port.port})
            services.append({"name": item.metadata.name, "ports": ports})
        return sorted(services, key=lambda item: item["name"])
    except ApiException as exc:
        raise HTTPException(
            status_code=exc.status or 500,
            detail=f"Unable to list services in namespace {namespace}: {exc.reason}",
        ) from exc


@app.get("/services/{namespace}", response_model=list[dict[str, Any]])
def list_services(
    namespace: str,
    _: main.UserContext = Depends(main.require_devops),
) -> list[dict[str, Any]]:
    return namespace_services(namespace)


def ensure_ingress_path(item: dict) -> dict[str, str]:
    ingress_name = (item.get("ingress_name") or "").strip()
    if not ingress_name:
        raise RuntimeError("No ingress resource was selected by DevOps")

    service_name = (item.get("service_name") or "").strip()
    if not service_name:
        raise RuntimeError("Select a Kubernetes service for ingress provisioning")

    service_port = int(item.get("service_port") or 0)
    if service_port < 1 or service_port > 65535:
        raise RuntimeError("Provide a valid Kubernetes service port")

    main.load_k8s()
    core_api = client.CoreV1Api()
    networking_api = client.NetworkingV1Api()
    namespace = item["namespace"]

    # When service creation is disabled, the selected service must already exist
    # and the selected port must be exposed by it.
    if not item.get("create_service"):
        try:
            service = core_api.read_namespaced_service(service_name, namespace)
        except ApiException as exc:
            if exc.status == 404:
                raise RuntimeError(
                    f"Service {service_name} does not exist in namespace {namespace}"
                ) from exc
            raise

        exposed_ports = {port.port for port in (service.spec.ports or []) if port.port}
        if service_port not in exposed_ports:
            available = ", ".join(str(port) for port in sorted(exposed_ports)) or "none"
            raise RuntimeError(
                f"Service {service_name} does not expose port {service_port}; available ports: {available}"
            )

    ingress = networking_api.read_namespaced_ingress(ingress_name, namespace)
    rules = ingress.spec.rules or []
    if not rules:
        raise RuntimeError(f"Ingress {ingress_name} does not contain any rules")

    path_value = item["ingress_path"]
    if not path_value.startswith("/"):
        path_value = f"/{path_value}"
    if not path_value.endswith("(/|$)(.*)"):
        path_value = f"{path_value}(/|$)(.*)"

    target_rule = next((rule for rule in rules if rule.http is not None), None)
    if target_rule is None:
        raise RuntimeError(f"Ingress {ingress_name} does not contain an HTTP rule")

    paths = target_rule.http.paths or []
    existing = next((path for path in paths if path.path == path_value), None)
    backend = client.V1IngressBackend(
        service=client.V1IngressServiceBackend(
            name=service_name,
            port=client.V1ServiceBackendPort(number=service_port),
        )
    )

    if existing:
        existing.backend = backend
        action = "Updated existing path"
    else:
        paths.append(
            client.V1HTTPIngressPath(
                path=path_value,
                path_type="ImplementationSpecific",
                backend=backend,
            )
        )
        action = "Added path"

    target_rule.http.paths = paths
    ingress.spec.rules = rules
    networking_api.replace_namespaced_ingress(ingress_name, namespace, ingress)
    source = "newly created service" if item.get("create_service") else "existing service"
    return {
        "status": "Completed",
        "message": (
            f"{action} {path_value} in ingress {ingress_name} using "
            f"{source} {service_name}:{service_port}"
        ),
    }


# provision() calls main.ensure_ingress_path at runtime, so this replacement
# applies to approval retries and new requests.
main.ensure_ingress_path = ensure_ingress_path
