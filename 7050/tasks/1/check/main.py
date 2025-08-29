# main.py
# This script checks for the presence of 'ingressClassName: nginx' in a Kubernetes Ingress resource.

import os
import asyncio
from kubernetes_asyncio import client, config
from kubernetes_asyncio.client.api_client import ApiClient

# --- Configuration ---
K8S_CLUSTER_ID = os.getenv("K8S_CLUSTER_ID")
LAB_TASK_ID = os.getenv("LAB_TASK_ID")
NAMESPACE_NAME = "demo"
INGRESS_NAME = "nginx-ingress"
EXPECTED_INGRESS_CLASS_NAME = "nginx"


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
    Main function to check the Ingress resource.
    """
    if not K8S_CLUSTER_ID:
        print("K8S_CLUSTER_ID not set. Exiting.")
        exit(1)

    async with await _get_k8s_client(K8S_CLUSTER_ID) as api_client:
        networking_v1 = client.NetworkingV1Api(api_client)

        print(
            f"--- Checking Ingress '{INGRESS_NAME}' in Namespace '{NAMESPACE_NAME}' ---"
        )

        try:
            # Read the Ingress resource from the cluster
            ingress = await networking_v1.read_namespaced_ingress(
                name=INGRESS_NAME, namespace=NAMESPACE_NAME
            )

            # Check for the ingressClassName field
            if (
                ingress.spec
                and ingress.spec.ingress_class_name == EXPECTED_INGRESS_CLASS_NAME
            ):
                print(
                    f"✅ SUCCESS: Ingress has 'ingressClassName: {EXPECTED_INGRESS_CLASS_NAME}'."
                )
                print("Check complete. Lab is in the correct state.")
                exit(0)  # Exit with code 0 for success
            else:
                current_class = (
                    ingress.spec.ingress_class_name
                    if ingress.spec and ingress.spec.ingress_class_name
                    else "missing"
                )
                print(
                    f"❌ FAILURE: Ingress is present, but 'ingressClassName' is '{current_class}'."
                )
                print(f"Expected: '{EXPECTED_INGRESS_CLASS_NAME}'.")
                print("Check complete. Lab is not in the correct state.")
                exit(1)  # Exit with code 1 for failure

        except client.ApiException as e:
            if e.status == 404:
                print(
                    f"❌ FAILURE: Ingress '{INGRESS_NAME}' not found in namespace '{NAMESPACE_NAME}'."
                )
                exit(1)
            else:
                print(f"An unexpected Kubernetes API error occurred: {e}")
                exit(1)
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
            exit(1)


if __name__ == "__main__":
    asyncio.run(main())
