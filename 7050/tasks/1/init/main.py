import asyncio
import os
import logging
import json
from http import HTTPStatus
from kubernetes_asyncio import client, config
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


async def _get_k8s_client(cluster_context_name: str) -> client.ApiClient:
    """
    Configures and returns an async Kubernetes API client using an aggregated kubeconfig.
    """
    try:
        await config.load_kube_config(
            config_file=str(AGGREGATED_KUBECONFIG_PATH), context=cluster_context_name
        )
        return client.ApiClient()
    except Exception as e:
        logger.error(
            f"Error loading K8s config for context '{cluster_context_name}': {e}"
        )
        raise RuntimeError(
            f"Failed to connect to Kubernetes cluster via context '{cluster_context_name}'."
        )


async def main():
    namespace = f"{LAB_OWNER}-nginx"

    # Ensure api_client is closed properly
    async with await _get_k8s_client(K8S_CLUSTER_ID) as api_client:
        v1 = client.CoreV1Api(api_client)
        apps_v1 = client.AppsV1Api(api_client)
        networking_v1 = client.NetworkingV1Api(api_client)

        overall_status = "success"

        try:
            # Run all checks
            checks = [
                await apps_v1.list_namespaced_deployment(namespace=namespace),
                await v1.list_namespaced_service(namespace=namespace),
                await networking_v1.list_namespaced_ingress(namespace=namespace),
            ]

            # If any resource list is empty -> fail
            if any(not c.items for c in checks):
                overall_status = "fail"

        except ApiException as e:
            logger.error(f"K8s API error: {e}")
            overall_status = "fail"
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            overall_status = "fail"

        print(json.dumps({"status": overall_status}, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
