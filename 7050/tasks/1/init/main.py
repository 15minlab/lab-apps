# main.py
# This script creates a Kubernetes namespace, a deployment, a service,
# and an ingress for an Nginx application.

import os
import asyncio
from kubernetes_asyncio import client, config
from kubernetes_asyncio.client.api_client import ApiClient

# --- Configuration ---
# The script gets its configuration from environment variables set by the API controller.
K8S_CLUSTER_ID = os.getenv("K8S_CLUSTER_ID")
LAB_TASK_ID = os.getenv("LAB_TASK_ID")
NAMESPACE_NAME = "demo"
INGRESS_DOMAIN = "demo.15minlab.com"


# --- Kubernetes Client Helper ---
# This function assumes you have a helper function to load the kubeconfig.
# This is required for the script to be runnable on its own for testing.
async def _get_k8s_client(cluster_context_name: str) -> ApiClient:
    """
    Configures and returns an async Kubernetes API client using an aggregated kubeconfig.
    This function is a placeholder and should match the one in your controller.
    """
    # Placeholder for local testing, assuming an aggregated kubeconfig exists.
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
    Main function to create and manage Kubernetes resources.
    """
    if not K8S_CLUSTER_ID:
        print("K8S_CLUSTER_ID not set. Exiting.")
        return

    async with await _get_k8s_client(K8S_CLUSTER_ID) as api_client:
        core_v1 = client.CoreV1Api(api_client)
        apps_v1 = client.AppsV1Api(api_client)
        networking_v1 = client.NetworkingV1Api(api_client)

        print("--- Step 1: Create Namespace ---")
        try:
            # Create a namespace if it doesn't exist
            namespace_body = client.V1Namespace(
                metadata=client.V1ObjectMeta(name=NAMESPACE_NAME)
            )
            await core_v1.create_namespace(body=namespace_body)
            print(f"Namespace '{NAMESPACE_NAME}' created.")
        except client.ApiException as e:
            if e.status == 409:  # HTTP 409 Conflict means it already exists
                print(f"Namespace '{NAMESPACE_NAME}' already exists.")
            else:
                raise

        print("\n--- Step 2: Create Deployment ---")
        try:
            # Create a deployment for Nginx
            deployment_body = client.V1Deployment(
                metadata=client.V1ObjectMeta(
                    name="nginx-deployment", namespace=NAMESPACE_NAME
                ),
                spec=client.V1DeploymentSpec(
                    replicas=1,
                    selector=client.V1LabelSelector(match_labels={"app": "nginx-demo"}),
                    template=client.V1PodTemplateSpec(
                        metadata=client.V1ObjectMeta(labels={"app": "nginx-demo"}),
                        spec=client.V1PodSpec(
                            containers=[
                                client.V1Container(
                                    name="nginx",
                                    image="nginx:latest",
                                    ports=[client.V1ContainerPort(container_port=80)],
                                )
                            ]
                        ),
                    ),
                ),
            )
            await apps_v1.create_namespaced_deployment(
                namespace=NAMESPACE_NAME, body=deployment_body
            )
            print("Nginx deployment created.")
        except client.ApiException as e:
            if e.status == 409:
                print("Nginx deployment already exists.")
            else:
                raise

        print("\n--- Step 3: Create Service ---")
        try:
            # Create a service to expose the deployment
            service_body = client.V1Service(
                metadata=client.V1ObjectMeta(
                    name="nginx-service", namespace=NAMESPACE_NAME
                ),
                spec=client.V1ServiceSpec(
                    selector={"app": "nginx-demo"},
                    ports=[client.V1ServicePort(port=80, target_port=80)],
                    type="ClusterIP",
                ),
            )
            await core_v1.create_namespaced_service(
                namespace=NAMESPACE_NAME, body=service_body
            )
            print("Nginx service created.")
        except client.ApiException as e:
            if e.status == 409:
                print("Nginx service already exists.")
            else:
                raise

        print("\n--- Step 4: Create Ingress ---")
        try:
            # Create an ingress to expose the service externally
            ingress_body = client.V1Ingress(
                metadata=client.V1ObjectMeta(
                    name="nginx-ingress", namespace=NAMESPACE_NAME
                ),
                spec=client.V1IngressSpec(
                    rules=[
                        client.V1IngressRule(
                            host=INGRESS_DOMAIN,
                            http=client.V1HTTPIngressRuleValue(
                                paths=[
                                    client.V1HTTPIngressPath(
                                        path="/",
                                        path_type="Prefix",
                                        backend=client.V1IngressBackend(
                                            service=client.V1IngressServiceBackend(
                                                name="nginx-service",
                                                port=client.V1ServiceBackendPort(
                                                    number=80
                                                ),
                                            )
                                        ),
                                    )
                                ]
                            ),
                        )
                    ]
                ),
            )
            await networking_v1.create_namespaced_ingress(
                namespace=NAMESPACE_NAME, body=ingress_body
            )
            print("Nginx ingress created.")
        except client.ApiException as e:
            if e.status == 409:
                print("Nginx ingress already exists.")
            else:
                raise

        print(f"\nLab resources created for task {LAB_TASK_ID}.")
        print(f"Access your application at: http://{INGRESS_DOMAIN}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"Script failed with an error: {e}")
        # The exit code is important for the controller to know about failures.
        exit(1)
