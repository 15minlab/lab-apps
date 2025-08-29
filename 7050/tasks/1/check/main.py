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
    Main function to check the Ingress resource and return a JSON status.
    """
    if not K8S_CLUSTER_ID:
        print(
            json.dumps(
                {"status": "error", "message": "K8S_CLUSTER_ID not set. Exiting."}
            )
        )
        sys.exit(1)

    try:
        async with await _get_k8s_client(K8S_CLUSTER_ID) as api_client:
            networking_v1 = client.NetworkingV1Api(api_client)

            # Read the Ingress resource from the cluster
            ingress = await networking_v1.read_namespaced_ingress(
                name=INGRESS_NAME, namespace=NAMESPACE_NAME
            )

            # Check for the ingressClassName field
            if (
                ingress.spec
                and ingress.spec.ingress_class_name == EXPECTED_INGRESS_CLASS_NAME
            ):
                # Return success message as a JSON object to standard output
                print(
                    json.dumps(
                        {
                            "status": "success",
                            "message": f"Ingress has 'ingressClassName: {EXPECTED_INGRESS_CLASS_NAME}'.",
                        }
                    )
                )
            else:
                current_class = (
                    ingress.spec.ingress_class_name
                    if ingress.spec and ingress.spec.ingress_class_name
                    else "missing"
                )
                # Return failure message as a JSON object to standard output
                print(
                    json.dumps(
                        {
                            "status": "failed",
                            "message": f"Ingress is present, but 'ingressClassName' is '{current_class}'. Expected: '{EXPECTED_INGRESS_CLASS_NAME}'.",
                        }
                    )
                )

    except client.ApiException as e:
        if e.status == 404:
            # Return failure message for a 404 error
            print(
                json.dumps(
                    {
                        "status": "failed",
                        "message": f"Ingress '{INGRESS_NAME}' not found in namespace '{NAMESPACE_NAME}'.",
                    }
                )
            )
            sys.exit(1)
        else:
            # Re-raise for unexpected API errors
            print(
                json.dumps(
                    {
                        "status": "error",
                        "message": f"An unexpected Kubernetes API error occurred: {e}",
                    }
                )
            )
            sys.exit(1)
    except Exception as e:
        # Return a general error message for any other exception
        print(
            json.dumps(
                {"status": "error", "message": f"An unexpected error occurred: {e}"}
            )
        )
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
