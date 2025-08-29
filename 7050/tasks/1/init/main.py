import os
import asyncio
import json
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
        print(
            json.dumps(
                {"status": "error", "message": "K8S_CLUSTER_ID not set. Exiting."}
            )
        )
        exit(1)

    result = {
        "namespace_status": "in_progress",
        "deployment_status": "in_progress",
        "service_status": "in_progress",
        "ingress_status": "in_progress",
        "final_status": "failed",
    }

    async with await _get_k8s_client(K8S_CLUSTER_ID) as api_client:
        core_v1 = client.CoreV1Api(api_client)
        apps_v1 = client.AppsV1Api(api_client)
        networking_v1 = client.NetworkingV1Api(api_client)

        try:
            # Step 1: Create Namespace
            try:
                namespace_body = client.V1Namespace(
                    metadata=client.V1ObjectMeta(name=NAMESPACE_NAME)
                )
                await core_v1.create_namespace(body=namespace_body)
                result["namespace_status"] = "created"
            except client.ApiException as e:
                if e.status == 409:
                    result["namespace_status"] = "already_exists"
                else:
                    raise

            # Step 2: Create Deployment
            try:
                deployment_body = client.V1Deployment(
                    metadata=client.V1ObjectMeta(
                        name="nginx-deployment", namespace=NAMESPACE_NAME
                    ),
                    spec=client.V1DeploymentSpec(
                        replicas=1,
                        selector=client.V1LabelSelector(
                            match_labels={"app": "nginx-demo"}
                        ),
                        template=client.V1PodTemplateSpec(
                            metadata=client.V1ObjectMeta(labels={"app": "nginx-demo"}),
                            spec=client.V1PodSpec(
                                containers=[
                                    client.V1Container(
                                        name="nginx",
                                        image="nginx:latest",
                                        ports=[
                                            client.V1ContainerPort(container_port=80)
                                        ],
                                    )
                                ]
                            ),
                        ),
                    ),
                )
                await apps_v1.create_namespaced_deployment(
                    namespace=NAMESPACE_NAME, body=deployment_body
                )
                result["deployment_status"] = "created"
            except client.ApiException as e:
                if e.status == 409:
                    result["deployment_status"] = "already_exists"
                else:
                    raise

            # Step 3: Create Service
            try:
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
                result["service_status"] = "created"
            except client.ApiException as e:
                if e.status == 409:
                    result["service_status"] = "already_exists"
                else:
                    raise

            # Step 4: Create Ingress
            try:
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
                                                ),
                                            ),
                                        ),
                                    ]
                                ),
                            )
                        ],
                    ),
                )
                await networking_v1.create_namespaced_ingress(
                    namespace=NAMESPACE_NAME, body=ingress_body
                )
                result["ingress_status"] = "created"
            except client.ApiException as e:
                if e.status == 409:
                    result["ingress_status"] = "already_exists"
                else:
                    raise

            result["final_status"] = "success"
            result["message"] = f"Lab resources created for task {LAB_TASK_ID}."
            result["access_url"] = f"http://{INGRESS_DOMAIN}"

        except Exception as e:
            result["final_status"] = "error"
            result["message"] = f"Script failed with an error: {e}"
        finally:
            print(json.dumps(result, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
