import json
import os
import random
import time
from typing import Dict
import boto3
import socket
from botocore.exceptions import UnauthorizedSSOTokenError

from easyecs.helpers.color import Color


def load_template(stack_name: str) -> Dict:
    """
    Loads the CloudFormation template from a JSON file.
    """
    with open(f".cloudformation/{stack_name}.template.json") as f:
        return json.load(f)


def parse_dict_with_env_var(build_args):
    for key, value in build_args.items():
        if value.startswith("{{.") and value.endswith("}}"):
            env_var_name = value[3:][:-2]
            new_value = os.environ.get(env_var_name)
            if new_value is None:
                print(
                    f"{Color.RED}Environment variable {env_var_name} does not"
                    f" exist{Color.END}"
                )
            build_args[key] = new_value
    return build_args


def convert_tags_to_dict(tags):
    return {tag["Key"]: tag["Value"] for tag in tags}


def convert_containers_to_dict(containers):
    parsed_containers = {}
    for container in containers:
        container_name = container["name"]
        # We give him a target id so it's easier to use it with ssm start session
        runtime_id = container["runtimeId"]
        task_id = runtime_id.split("-")[0]
        target_id = f"{task_id}_{runtime_id}"
        container["targetId"] = target_id
        parsed_containers[container_name] = container
    return parsed_containers


def is_port_in_use(port: int) -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.connect(("127.0.0.1", int(port)))
        s.shutdown(2)
        return True
    except Exception:
        return False


def check_credentials() -> None:
    client = boto3.client("s3")
    try:
        client.list_buckets()
    except UnauthorizedSSOTokenError:
        print(
            f"{Color.RED}You should refresh your credentials or connect to your aws"
            f" account (aws sso login){Color.END}"
        )
        exit(-1)


def generate_random_port():
    random_port = random.randint(1024, 65535)
    while is_port_in_use(random_port):
        random_port = random.randint(1024, 65535)
        time.sleep(0.1)
    random_port = str(random_port)
    return random_port
