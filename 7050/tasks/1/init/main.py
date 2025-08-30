import asyncio
from http.client import HTTPException
from http import HTTPStatus
import os
import logging
import json
from kubernetes_asyncio import client, config
from kubernetes_asyncio.client.api_client import ApiClient
from kubernetes_asyncio.client.exceptions import ApiException

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# --- Configuration ---
K8S_CLUSTER_ID = os.getenv("K8S_CLUSTER_ID")
AGGREGATED_KUBECONFIG_PATH = os.getenv("AGGREGATED_KUBECONFIG_PATH")
LAB_OWNER = os.getenv("LAB_OWNER")


async def _get_k8s_client(cluster_context_name: str) -> ApiClient:
    """
    Configures and returns an async Kubernetes API client using an aggregated kubeconfig.
    """
    try:
        # Load the aggregated kubeconfig file
        await config.load_kube_config(
            config_file=str(AGGREGATED_KUBECONFIG_PATH), context=cluster_context_name
        )

        return client.ApiClient()

    except Exception as e:
        print(f"Error loading K8s config for context '{cluster_context_name}': {e}")
        raise HTTPException(
            status_code=HTTPStatus.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to connect to Kubernetes cluster via context '{cluster_context_name}'.",
        )


async def main():
    namespace = f"{LAB_OWNER}-nginx"
    api_client = await _get_k8s_client(K8S_CLUSTER_ID)

    v1 = client.CoreV1Api(api_client)
    apps_v1 = client.AppsV1Api(api_client)
    networking_v1 = client.NetworkingV1Api(api_client)

    # Default status
    overall_status = "success"

    try:
        deployments = await apps_v1.list_namespaced_deployment(namespace=namespace)
        if not deployments.items:
            overall_status = "fail"
    except ApiException:
        overall_status = "fail"

    try:
        services = await v1.list_namespaced_service(namespace=namespace)
        if not services.items:
            overall_status = "fail"
    except ApiException:
        overall_status = "fail"

    try:
        ingresses = await networking_v1.list_namespaced_ingress(namespace=namespace)
        if not ingresses.items:
            overall_status = "fail"
    except ApiException:
        overall_status = "fail"

    print(json.dumps({"status": overall_status}, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
