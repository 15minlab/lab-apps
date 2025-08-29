# main.py
# This script patches an existing Ingress resource to add the ingressClassName field.

import os
import asyncio
from kubernetes_asyncio import client, config
from kubernetes_asyncio.client.api_client import ApiClient

# --- Configuration ---
K8S_CLUSTER_ID = os.getenv("K8S_CLUSTER_ID")
LAB_TASK_ID = os.getenv("LAB_TASK_ID")
NAMESPACE_NAME = "demo"
INGRESS_NAME = "nginx-ingress"
INGRESS_CLASS_NAME = "nginx"


# --- Kubernetes Client Helper ---
async def _get_k8s_client(cluster_context_name: str) -> ApiClient:
    """
    Configures and returns an async Kubernetes API client.
    This function is a placeholder that should match your controller's logic.
    """
    kubeconfig_path = os.getenv("AGGREGATED_KUBECONFIG_PATH")
    if not kubeconfig_path:
        raise ValueError("AGGREGATED_KUBECONFIG_PATH environment variable not set.")

    await config.load_kube_config(
        config_file=kubeconfig_path, context=cluster_context_name
    )
    return client.ApiClient()


# --- Main Script Logic ---
async def main():
    """
    Main function to update Kubernetes resources.
    """
    if not K8S_CLUSTER_ID:
        print("K8S_CLUSTER_ID not set. Exiting.")
        return

    async with await _get_k8s_client(K8S_CLUSTER_ID) as api_client:
        networking_v1 = client.NetworkingV1Api(api_client)

        print(
            f"--- Updating Ingress '{INGRESS_NAME}' in Namespace '{NAMESPACE_NAME}' ---"
        )

        # Define the patch body. Only include the fields you want to change.
        patch_body = {"spec": {"ingressClassName": INGRESS_CLASS_NAME}}

        try:
            # Use the patch_namespaced_ingress method to apply the update
            await networking_v1.patch_namespaced_ingress(
                name=INGRESS_NAME, namespace=NAMESPACE_NAME, body=patch_body
            )
            print(
                f"Ingress '{INGRESS_NAME}' successfully patched with ingressClassName: '{INGRESS_CLASS_NAME}'."
            )
        except client.ApiException as e:
            if e.status == 404:
                print(f"Ingress '{INGRESS_NAME}' not found. Cannot update.")
                exit(1)
            else:
                raise

        print(f"\nLab resources for task {LAB_TASK_ID} successfully updated.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"Script failed with an error: {e}")
        exit(1)
