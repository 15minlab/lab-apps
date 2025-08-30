import os
import shutil
import asyncio
import logging
import redis
import json
from pathlib import Path
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from kubernetes_asyncio import client, config
from kubernetes_asyncio.client.api_client import ApiClient
from kubernetes_asyncio.client.exceptions import ApiException

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Load environment variables from the .env file
load_dotenv()

# --- Redis Configuration ---
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_DB = int(os.getenv("REDIS_DB", 0))

try:
    r = redis.Redis(
        host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=True
    )
    r.ping()
    logger.info("Successfully connected to Redis.")
except redis.exceptions.ConnectionError as e:
    logger.error(f"Could not connect to Redis: {e}")
    r = None

# Directory to store the cloned repos. Must be a shared volume.
CACHE_DIR = Path(os.getenv("CACHE_DIR", "/data/lab_repo_cache"))

# Ensure the cache directory exists
os.makedirs(CACHE_DIR, exist_ok=True)

# --- GitHub PAT Configuration ---
GITHUB_PAT = os.getenv("GITHUB_PAT")
if not GITHUB_PAT:
    logger.warning(
        "GITHUB_PAT environment variable not set. Cloning will fail for private repositories."
    )

# --- Kubernetes Client Cache ---
_k8s_client_cache = {}


# --- Pydantic Model and Router ---
class LabRequest(BaseModel):
    lab_template_source: str
    lab_template_revision: str
    lab_template_path: str
    action: str
    k8s_cluster_id: str
    lab_owner: str = Field(..., description="The owner/user of the lab template.")
    task_id: int = Field(..., description="A unique identifier for the lab task.")


router = APIRouter(
    prefix="/lab",
    tags=["Lab Controller"],
)


async def _run_subprocess(command: list, cwd: Path = None, env: dict = None):
    """
    Asynchronously runs a subprocess and handles stdout/stderr.
    Returns the stdout and stderr as strings.
    Raises a RuntimeError on a non-zero exit code.
    """
    logger.info(f"Executing command: {' '.join(command)}")
    proc = await asyncio.create_subprocess_exec(
        *command,
        cwd=cwd,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    stdout_str = stdout.decode()
    stderr_str = stderr.decode()
    if proc.returncode != 0:
        logger.error(f"Command failed with exit code {proc.returncode}")
        logger.error(f"Stdout:\n{stdout_str}")
        logger.error(f"Stderr:\n{stderr_str}")
        raise RuntimeError(
            f"Command failed with exit code {proc.returncode}. Stderr: {stderr_str}"
        )
    return stdout_str, stderr_str


async def _get_repo_path(source: str, revision: str) -> Path:
    """
    Clones or updates a git repository using non-blocking I/O and Redis for caching.
    Includes robust path validation.
    """
    if not r:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Caching service is unavailable. Please check the Redis connection.",
        )

    # Sanitize the source URL for a valid Redis key and directory name
    safe_source = (
        source.replace("https://", "")
        .replace("http://", "")
        .replace("git@", "")
        .replace(":", "_")
        .replace("/", "_")
        .replace(".", "_")
    )
    repo_key = f"lab_repo:{safe_source}:{revision}"

    repo_path_str = r.get(repo_key)
    repo_path = CACHE_DIR / f"{safe_source}_{revision}"

    if repo_path_str and Path(repo_path_str).exists():
        # --- Cache Hit ---
        repo_path = Path(repo_path_str)
        logger.info(f"Cache hit for {source}:{revision}. Updating repository...")
        try:
            # Use async subprocess to pull latest changes
            await _run_subprocess(["git", "pull"], cwd=repo_path)
            logger.info("Repository updated successfully.")
            return repo_path
        except RuntimeError as e:
            logger.error(f"Error updating repository: {e}")
            # Invalidate cache and fall through to re-clone
            r.delete(repo_key)
            logger.info("Cache invalidated. Attempting to re-clone...")

    # --- Cache Miss or Update Failure ---
    logger.info(f"Cache miss for {source}:{revision}. Cloning new repository...")

    # Robustly remove the old directory if it exists before cloning
    if repo_path.exists() and repo_path.is_dir():
        logger.info(f"Destination path {repo_path} already exists. Removing...")
        shutil.rmtree(repo_path)

    # Prepare authenticated source URL
    if GITHUB_PAT and "github.com" in source:
        auth_source = source.replace("https://", f"https://oauth2:{GITHUB_PAT}@")
    else:
        auth_source = source

    try:
        # Use async subprocess to clone
        await _run_subprocess(
            [
                "git",
                "clone",
                "--depth",
                "1",
                "--branch",
                revision,
                auth_source,
                str(repo_path),
            ]
        )
        r.set(repo_key, str(repo_path))
        r.expire(repo_key, 86400)
        logger.info(f"Repository cloned and added to Redis cache with key {repo_key}.")
        return repo_path
    except RuntimeError as e:
        logger.error(f"Error cloning repository: {e}")
        error_detail = "Failed to clone repository. Check URL and credentials, and ensure the specified branch/revision exists."
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=error_detail
        )


async def _get_k8s_client(cluster_context_name: str) -> ApiClient:
    """
    Configures and returns an async Kubernetes API client from a cache.
    """
    if cluster_context_name in _k8s_client_cache:
        logger.info(
            f"Using cached Kubernetes client for context '{cluster_context_name}'."
        )
        return _k8s_client_cache[cluster_context_name]

    try:
        # Load the kubeconfig file, context is handled by k8s_asyncio
        await config.load_kube_config(context=cluster_context_name)
        client_instance = client.ApiClient()
        _k8s_client_cache[cluster_context_name] = client_instance
        logger.info(
            f"New Kubernetes client created and cached for context '{cluster_context_name}'."
        )
        return client_instance
    except Exception as e:
        logger.error(
            f"Error loading K8s config for context '{cluster_context_name}': {e}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to connect to Kubernetes cluster via context '{cluster_context_name}'.",
        )


async def _execute_script(script_path: Path, request_data: dict):
    """
    Executes the main.py script to get K8s resource definitions and then
    creates them on the cluster, prefixing names with the lab_owner.
    """
    if not script_path.exists():
        raise FileNotFoundError(f"Script not found at: {script_path}")

    # Use _run_subprocess to execute the script and capture its output
    logger.info(f"Executing Python script: {script_path} to get resource definitions")
    try:
        stdout, _ = await _run_subprocess(["python3", str(script_path)])
        resources = json.loads(stdout)
        if not isinstance(resources, list):
            raise ValueError("Script did not return a list of Kubernetes resources.")
    except (RuntimeError, json.JSONDecodeError, ValueError) as e:
        logger.error(f"Script execution failed or returned invalid JSON: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Script failed to return valid Kubernetes resource definitions: {e}",
        )

    # Get the Kubernetes API client
    k8s_client = await _get_k8s_client(request_data["k8s_cluster_id"])
    lab_owner = request_data["lab_owner"]
    created_resources = []

    # Map for API clients based on API version
    api_map = {
        "apps/v1": client.AppsV1Api(k8s_client),
        "core/v1": client.CoreV1Api(k8s_client),
    }

    # Iterate through the resources and create them
    for resource in resources:
        kind = resource.get("kind")
        api_version = resource.get("apiVersion")
        name = resource.get("metadata", {}).get("name")
        namespace = resource.get("metadata", {}).get("namespace", "default")

        if not all([kind, api_version, name]):
            logger.error("Skipping malformed resource: %s", json.dumps(resource))
            continue

        # Prefix the resource name with the lab owner's name
        prefixed_name = f"{lab_owner}-{name}"
        resource["metadata"]["name"] = prefixed_name

        # Add a custom label for easier lookup
        if "labels" not in resource["metadata"]:
            resource["metadata"]["labels"] = {}
        resource["metadata"]["labels"]["lab-owner"] = lab_owner

        # Special handling for related resources (e.g., Deployments with a selector)
        if kind == "Deployment":
            # Update the selector and template labels to match the new prefixed name
            resource["spec"]["selector"]["matchLabels"]["app"] = prefixed_name
            resource["spec"]["template"]["metadata"]["labels"]["app"] = prefixed_name
        elif kind == "Service":
            # Update the service selector to match the new prefixed deployment
            resource["spec"]["selector"]["app"] = prefixed_name

        # Get the correct API client for this resource
        api = api_map.get(api_version)
        if not api:
            logger.warning(
                f"No API client found for apiVersion: {api_version}. Skipping."
            )
            continue

        # Call the appropriate creation method
        try:
            # We use a dictionary to map kind to method call for clarity and safety
            create_methods = {
                "Deployment": api.create_namespaced_deployment,
                "Service": api.create_namespaced_service,
                # Add other resource types here as needed
            }
            create_method = create_methods.get(kind)
            if not create_method:
                logger.warning(f"No creation method found for kind: {kind}. Skipping.")
                continue

            response = await create_method(namespace=namespace, body=resource)
            created_resources.append(f"{kind}/{response.metadata.name}")
            logger.info(f"Successfully created {kind} '{response.metadata.name}'")
        except ApiException as e:
            logger.error(f"Error creating {kind} '{name}': {e.body}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to create {kind} '{name}': {e.body}",
            )

    return {
        "result": "success",
        "message": f"Successfully created the following resources: {', '.join(created_resources)}",
        "details": {"created_resources": created_resources},
    }


@router.post("/")
async def handle_lab_action(request: LabRequest):
    """
    Handles dynamic lab actions based on the request using the provided script path.
    """
    try:
        # 1. Get the local repository path
        repo_local_path = await _get_repo_path(
            request.lab_template_source, request.lab_template_revision
        )

        # 2. Construct the full script path with validation
        sanitized_lab_path = Path(request.lab_template_path)
        sanitized_action = Path(request.action).name

        script_path = (
            repo_local_path
            / sanitized_lab_path
            / str(request.task_id)
            / sanitized_action
            / "main.py"
        )

        # Resolve the final path to ensure it's a child of the repo path
        resolved_path = script_path.resolve()
        if not str(resolved_path).startswith(str(repo_local_path.resolve())):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid script path: Path is not contained within the repository.",
            )

        # 3. Check if the script exists
        if not resolved_path.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Script not found at: {resolved_path}",
            )

        # 4. Execute the script and get its output
        result = await _execute_script(resolved_path, request.dict())

        return {
            "result": "success",
            "message": result["message"],
            "details": result.get("details", {}),
        }

    except HTTPException as e:
        return {"result": "failed", "message": e.detail, "status_code": e.status_code}
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}", exc_info=True)
        return {"result": "error", "message": f"An unexpected error occurred: {e}"}
