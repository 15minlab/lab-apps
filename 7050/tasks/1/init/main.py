import os
import asyncio
import json
import logging
from kubernetes_asyncio import client, config
from kubernetes_asyncio.client.api_client import ApiClient
from kubernetes_asyncio.client.exceptions import ApiException

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# --- Configuration (from environment variables) ---
# The controller now passes these values directly to the script's environment.
K8S_CLUSTER_ID = os.getenv("K8S_CLUSTER_ID")
LAB_TASK_ID = os.getenv("LAB_TASK_ID")
LAB_OWNER = os.getenv("LAB_OWNER")
NAMESPACE_NAME = "demo"
INGRESS_DOMAIN = "demo.15minlab.com"

if not all([K8S_CLUSTER_ID, LAB_OWNER, LAB_TASK_ID]):
    logger.error("Required environment variables not set. Exiting.")
    print(
        json.dumps(
            {
                "status": "error",
                "message": "Required environment variables (K8S_CLUSTER_ID, LAB_OWNER, LAB_TASK_ID) not set.",
            }
        )
    )
    exit(1)


# --- Kubernetes Client Helper ---
async def _get_k8s_client(cluster_context_name: str) -> ApiClient:
    """
    Configures and returns an async Kubernetes API client using an aggregated kubeconfig.
    This function is a placeholder and should match the one in your controller.
    """
    try:
        await config.load_kube_config(context=cluster_context_name)
        return client.ApiClient()
    except Exception as e:
        logger.error(
            f"Failed to load kubeconfig for context '{cluster_context_name}': {e}"
        )
        raise


# --- Main Script Logic ---
async def main():
    """
    Main function to create and manage Kubernetes resources with a prefix.
    """
    result = {
        "namespace_status": "in_progress",
        "deployment_status": "in_progress",
        "service_status": "in_progress",
        "final_status": "failed",
        "message": "",
        "access_url": "",
    }

    try:
        async with await _get_k8s_client(K8S_CLUSTER_ID) as api_client:
            core_v1 = client.CoreV1Api(api_client)
            apps_v1 = client.AppsV1Api(api_client)
            networking_v1 = client.NetworkingV1Api(api_client)

            # Use a consistent prefix for all resources
            prefix = f"{LAB_OWNER}-{LAB_TASK_ID}"
            logger.info(f"Using prefix: {prefix}")

            # The namespace name is also prefixed to avoid conflicts
            prefixed_namespace = f"{prefix}-{NAMESPACE_NAME}"
            prefixed_deployment_name = f"{prefix}-nginx-deployment"
            prefixed_service_name = f"{prefix}-nginx-service"
            prefixed_ingress_name = f"{prefix}-nginx-ingress"
            prefixed_ingress_host = f"{prefix}.{INGRESS_DOMAIN}"

            logger.info(f"Creating Namespace: {prefixed_namespace}")
            # Step 1: Create Namespace
            try:
                namespace_body = client.V1Namespace(
                    metadata=client.V1ObjectMeta(name=prefixed_namespace)
                )
                await core_v1.create_namespace(body=namespace_body)
                result["namespace_status"] = "created"
            except ApiException as e:
                if e.status == 409:
                    result["namespace_status"] = "already_exists"
                    logger.warning(f"Namespace {prefixed_namespace} already exists.")
                else:
                    raise

            logger.info(f"Creating Deployment: {prefixed_deployment_name}")
            # Step 2: Create Deployment
            try:
                deployment_body = client.V1Deployment(
                    metadata=client.V1ObjectMeta(
                        name=prefixed_deployment_name, namespace=prefixed_namespace
                    ),
                    spec=client.V1DeploymentSpec(
                        replicas=1,
                        selector=client.V1LabelSelector(
                            match_labels={"app": "nginx-demo", "lab_owner": LAB_OWNER}
                        ),
                        template=client.V1PodTemplateSpec(
                            metadata=client.V1ObjectMeta(
                                labels={"app": "nginx-demo", "lab_owner": LAB_OWNER}
                            ),
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
                    namespace=prefixed_namespace, body=deployment_body
                )
                result["deployment_status"] = "created"
            except ApiException as e:
                if e.status == 409:
                    result["deployment_status"] = "already_exists"
                    logger.warning(
                        f"Deployment {prefixed_deployment_name} already exists."
                    )
                else:
                    raise

            logger.info(f"Creating Service: {prefixed_service_name}")
            # Step 3: Create Service
            try:
                service_body = client.V1Service(
                    metadata=client.V1ObjectMeta(
                        name=prefixed_service_name, namespace=prefixed_namespace
                    ),
                    spec=client.V1ServiceSpec(
                        selector={"app": "nginx-demo", "lab_owner": LAB_OWNER},
                        ports=[client.V1ServicePort(port=80, target_port=80)],
                        type="ClusterIP",
                    ),
                )
                await core_v1.create_namespaced_service(
                    namespace=prefixed_namespace, body=service_body
                )
                result["service_status"] = "created"
            except ApiException as e:
                if e.status == 409:
                    result["service_status"] = "already_exists"
                    logger.warning(f"Service {prefixed_service_name} already exists.")
                else:
                    raise

            logger.info(f"Creating Ingress: {prefixed_ingress_name}")
            # Step 4: Create Ingress
            try:
                ingress_body = client.V1Ingress(
                    metadata=client.V1ObjectMeta(
                        name=prefixed_ingress_name, namespace=prefixed_namespace
                    ),
                    spec=client.V1IngressSpec(
                        rules=[
                            client.V1IngressRule(
                                host=prefixed_ingress_host,
                                http=client.V1HTTPIngressRuleValue(
                                    paths=[
                                        client.V1HTTPIngressPath(
                                            path="/",
                                            path_type="Prefix",
                                            backend=client.V1IngressBackend(
                                                service=client.V1IngressServiceBackend(
                                                    name=prefixed_service_name,
                                                    port=client.V1ServiceBackendPort(
                                                        number=80
                                                    ),
                                                ),
                                            ),
                                        ),
                                    ],
                                ),
                            )
                        ],
                    ),
                )
                await networking_v1.create_namespaced_ingress(
                    namespace=prefixed_namespace, body=ingress_body
                )
                result["ingress_status"] = "created"
            except ApiException as e:
                if e.status == 409:
                    result["ingress_status"] = "already_exists"
                    logger.warning(f"Ingress {prefixed_ingress_name} already exists.")
                else:
                    raise

            result["final_status"] = "success"
            result["message"] = f"Lab resources created for task {LAB_TASK_ID}."
            result["access_url"] = f"http://{prefixed_ingress_host}"

    except Exception as e:
        logger.error(f"Script failed with an unhandled exception: {e}", exc_info=True)
        result["final_status"] = "error"
        result["message"] = f"Script failed with an error: {e}"
        result["traceback"] = str(e)  # Add traceback for debugging
    finally:
        # The script must print the final result as a JSON string to standard output.
        # The controller will read this and send it back to the API caller.
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
