"""
Kubernetes semantic conventions for OpenTelemetry.

This module provides Kubernetes semantic convention attributes for tracing
when running in a Kubernetes environment (e.g., AKS).

See: https://opentelemetry.io/docs/specs/semconv/resource/k8s/
See: https://opentelemetry.io/docs/specs/semconv/resource/cloud/
"""

import os
from typing import Any, Dict

from opentelemetry.trace import Span


class K8sAttributes:
    """OpenTelemetry Kubernetes semantic convention attribute names.

    See: https://opentelemetry.io/docs/specs/semconv/resource/k8s/
    """

    # Cluster attributes
    CLUSTER_UID = "k8s.cluster.uid"
    CLUSTER_NAME = "k8s.cluster.name"

    # Node attributes
    NODE_NAME = "k8s.node.name"
    NODE_UID = "k8s.node.uid"

    # Namespace attributes
    NAMESPACE_NAME = "k8s.namespace.name"

    # Pod attributes
    POD_NAME = "k8s.pod.name"
    POD_UID = "k8s.pod.uid"

    # Container attributes
    CONTAINER_NAME = "k8s.container.name"

    # Deployment attributes
    DEPLOYMENT_NAME = "k8s.deployment.name"
    DEPLOYMENT_UID = "k8s.deployment.uid"

    # ReplicaSet attributes
    REPLICASET_NAME = "k8s.replicaset.name"
    REPLICASET_UID = "k8s.replicaset.uid"


class CloudAttributes:
    """OpenTelemetry Cloud semantic convention attribute names.

    See: https://opentelemetry.io/docs/specs/semconv/resource/cloud/
    """

    PROVIDER = "cloud.provider"
    PLATFORM = "cloud.platform"
    REGION = "cloud.region"
    AVAILABILITY_ZONE = "cloud.availability_zone"
    RESOURCE_ID = "cloud.resource_id"
    ACCOUNT_ID = "cloud.account.id"


def get_k8s_attributes() -> Dict[str, Any]:
    """Get Kubernetes attributes from environment variables.

    Environment variables are injected by the Kubernetes deployment via
    the Downward API and custom environment variables.

    Environment variables expected:
    - CLUSTER_NAME: Kubernetes cluster name
    - NODE_NAME: Node name (via fieldRef: spec.nodeName)
    - POD_NAMESPACE: Pod namespace (via fieldRef: metadata.namespace)
    - POD_NAME: Pod name (via fieldRef: metadata.name)
    - POD_UID: Pod UID (via fieldRef: metadata.uid)
    - CONTAINER_NAME: Container name
    - DEPLOYMENT_NAME: Deployment name (optional, derived from POD_NAME)

    Returns:
        Dict of K8s attribute names to values (only non-empty values included)
    """
    attrs: Dict[str, Any] = {}

    # Kubernetes cluster attributes
    cluster_name = os.getenv("CLUSTER_NAME")
    if cluster_name:
        attrs[K8sAttributes.CLUSTER_NAME] = cluster_name

    # Node attributes
    node_name = os.getenv("NODE_NAME")
    if node_name:
        attrs[K8sAttributes.NODE_NAME] = node_name

    # Namespace attributes
    namespace = os.getenv("POD_NAMESPACE")
    if namespace:
        attrs[K8sAttributes.NAMESPACE_NAME] = namespace

    # Pod attributes
    pod_name = os.getenv("POD_NAME")
    if pod_name:
        attrs[K8sAttributes.POD_NAME] = pod_name

    pod_uid = os.getenv("POD_UID")
    if pod_uid:
        attrs[K8sAttributes.POD_UID] = pod_uid

    # Deployment name - can be set explicitly or derived from pod name
    deployment_name = os.getenv("DEPLOYMENT_NAME")
    # Extract deployment name from pod name if not set
    # In Kubernetes, pod names follow the pattern: <deployment-name>-<replicaset-hash>-<pod-hash>
    # e.g., my-deployment-5d8c7b6f9-abc123 -> my-deployment
    if pod_name and not deployment_name:
        parts = pod_name.rsplit("-", 2)
        if len(parts) >= 3:
            deployment_name = parts[0]
    if deployment_name:
        attrs[K8sAttributes.DEPLOYMENT_NAME] = deployment_name

    # Container attributes
    container_name = os.getenv("CONTAINER_NAME")
    if container_name:
        attrs[K8sAttributes.CONTAINER_NAME] = container_name

    return attrs


def get_cloud_attributes() -> Dict[str, Any]:
    """Get cloud provider attributes from environment variables.

    Environment variables expected:
    - CLOUD_PROVIDER: Cloud provider (e.g., "azure", "aws", "gcp")
    - CLOUD_PLATFORM: Cloud platform (e.g., "azure_aks", "aws_eks", "gcp_gke")
    - CLOUD_REGION: Cloud region (e.g., "eastus2", "us-west-2")
    - CLUSTER_RESOURCE_ID: Azure AKS resource ID (for Azure)

    Returns:
        Dict of cloud attribute names to values (only non-empty values included)
    """
    attrs: Dict[str, Any] = {}

    cloud_provider = os.getenv("CLOUD_PROVIDER")
    if cloud_provider:
        attrs[CloudAttributes.PROVIDER] = cloud_provider

    cloud_platform = os.getenv("CLOUD_PLATFORM")
    if cloud_platform:
        attrs[CloudAttributes.PLATFORM] = cloud_platform

    cloud_region = os.getenv("CLOUD_REGION")
    if cloud_region:
        attrs[CloudAttributes.REGION] = cloud_region

    # Azure-specific: AKS resource ID
    cluster_resource_id = os.getenv("CLUSTER_RESOURCE_ID")
    if cluster_resource_id:
        attrs[CloudAttributes.RESOURCE_ID] = cluster_resource_id

    return attrs


def get_all_resource_attributes() -> Dict[str, Any]:
    """Get all Kubernetes and cloud attributes.

    Returns:
        Combined dict of K8s and cloud attribute names to values
    """
    attrs = get_k8s_attributes()
    attrs.update(get_cloud_attributes())
    return attrs


def set_k8s_attributes(span: Span) -> None:
    """Set Kubernetes attributes on a span.

    Args:
        span: The OpenTelemetry span to set attributes on
    """
    for attr_name, attr_value in get_k8s_attributes().items():
        span.set_attribute(attr_name, attr_value)


def set_cloud_attributes(span: Span) -> None:
    """Set cloud provider attributes on a span.

    Args:
        span: The OpenTelemetry span to set attributes on
    """
    for attr_name, attr_value in get_cloud_attributes().items():
        span.set_attribute(attr_name, attr_value)


def set_all_resource_attributes(span: Span) -> None:
    """Set all Kubernetes and cloud attributes on a span.

    Args:
        span: The OpenTelemetry span to set attributes on
    """
    for attr_name, attr_value in get_all_resource_attributes().items():
        span.set_attribute(attr_name, attr_value)


def is_running_in_kubernetes() -> bool:
    """Check if the application is running in a Kubernetes environment.

    Returns:
        True if running in Kubernetes (POD_NAME is set), False otherwise
    """
    return bool(os.getenv("POD_NAME") or os.getenv("KUBERNETES_SERVICE_HOST"))
