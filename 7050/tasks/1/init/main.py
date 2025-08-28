import os
import sys

print("--- Running mock init script ---")
print(f"LAB_TASK_ID: {os.getenv('LAB_TASK_ID')}")
print(f"K8S_CLUSTER_ID: {os.getenv('K8S_CLUSTER_ID')}")
print(f"LAB_ACTION: {os.getenv('LAB_ACTION')}")
print("--- Mock init script finished ---")

# You can add logic here to simulate a failure
# For example:
# if os.getenv('LAB_TASK_ID') == "999":
#    sys.exit(1)
