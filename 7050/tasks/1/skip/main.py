import os
import asyncio
import json
import sys
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
    Main function to update Kubernetes resources and return a JSON status.
    """
    if not K8S_CLUSTER_ID:
        print(
            json.dumps(
                {"status": "error", "message": "K8S_CLUSTER_ID not set. Exiting."}
            )
        )
        sys.exit(1)

    async with await _get_k8s_client(K8S_CLUSTER_ID) as api_client:
        networking_v1 = client.NetworkingV1Api(api_client)

        try:
            # Define the patch body. Only include the fields you want to change.
            patch_body = {"spec": {"ingressClassName": INGRESS_CLASS_NAME}}

            # Use the patch_namespaced_ingress method to apply the update
            await networking_v1.patch_namespaced_ingress(
                name=INGRESS_NAME, namespace=NAMESPACE_NAME, body=patch_body
            )

            # Return success message as a JSON object to standard output
            print(
                json.dumps(
                    {
                        "status": "success",
                        "message": f"Ingress '{INGRESS_NAME}' successfully patched with ingressClassName: '{INGRESS_CLASS_NAME}'.",
                    }
                )
            )
        except client.ApiException as e:
            # Handle specific Kubernetes API errors and return a JSON failure message
            if e.status == 404:
                print(
                    json.dumps(
                        {
                            "status": "failed",
                            "message": f"Ingress '{INGRESS_NAME}' not found. Cannot update.",
                        }
                    )
                )
                sys.exit(1)
            else:
                raise


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print(
            json.dumps(
                {"status": "error", "message": f"Script failed with an error: {e}"}
            )
        )
        sys.exit(1)
