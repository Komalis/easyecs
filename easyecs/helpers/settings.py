import hashlib
import json
import os
import re
import yaml
from jinja2 import Environment, FileSystemLoader

from easyecs.cloudformation.fetch import (
    fetch_account_id,
    fetch_availability_zones,
    fetch_container_subnet_ids,
    fetch_region,
    fetch_vpc_id,
)
from easyecs.helpers.color import Color
from easyecs.model.ecs import EcsFileModel


def backport_old_format_to_new_format(data: str) -> str:
    # This function will be deprecated in the future.
    old_format_pattern = r"{{ ?\.(\w+) ?}}"
    matches = re.findall(old_format_pattern, data)
    for match in matches:
        print(
            f"{Color.RED}Old template format has been found {{{{.{match}}}}}, please"
            f" update it to {{{{ {match} }}}}, it will be deprecated in a near"
            f" future.{Color.END}"
        )
    new_data = re.sub(old_format_pattern, r"{{ \1 }}", data)
    return new_data


def ecs_file_to_yaml(file_name: str) -> str:
    env = Environment(loader=FileSystemLoader("."))
    with open(file_name) as f:
        data = f.read()
        data = backport_old_format_to_new_format(data)
        template = env.from_string(data)
        rendered_template = template.render(**os.environ)
    return rendered_template


def read_ecs_file(file_name: str) -> EcsFileModel:
    rendered_template = ecs_file_to_yaml(file_name)
    rendered_data = yaml.safe_load(rendered_template)
    return EcsFileModel(**rendered_data)


def compute_hash_ecs_file(file_name: str):
    hash_sha256 = hashlib.sha256()
    with open(file_name, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_sha256.update(chunk)
    return hash_sha256.hexdigest()


def save_hash(aws_account, file_name: str):
    hash_sha256 = compute_hash_ecs_file(file_name)
    with open(".tmp/easyecs.tmp", "r") as f:
        cache_configuration = json.load(f)
    cache_configuration[aws_account]["sha256"] = hash_sha256
    with open(".tmp/easyecs.tmp", "w") as f:
        json.dump(cache_configuration, f)


def delete_hash(aws_account):
    with open(".tmp/easyecs.tmp", "r") as f:
        cache_configuration = json.load(f)
    cache_configuration[aws_account]["sha256"] = None
    with open(".tmp/easyecs.tmp", "w") as f:
        json.dump(cache_configuration, f)


def load_settings(aws_account):
    try:
        os.makedirs(".tmp", exist_ok=True)
        with open(".tmp/easyecs.tmp", "r") as f:
            cache_configuration = json.load(f)
    except FileNotFoundError:
        cache_configuration = {}

    account_cache_configuration = cache_configuration.get(aws_account, {})

    aws_region = account_cache_configuration.get("aws_region", None)
    if not aws_region:
        aws_region = fetch_region()
    azs = account_cache_configuration.get("azs", None)
    if not azs:
        azs = fetch_availability_zones(aws_region)
    aws_account_id = account_cache_configuration.get("aws_account_id", None)
    if not aws_account_id:
        aws_account_id = fetch_account_id()
    vpc_id = account_cache_configuration.get("vpc_id", None)
    if not vpc_id:
        vpc_id = fetch_vpc_id()
    subnet_ids = account_cache_configuration.get("subnet_ids", None)
    if not subnet_ids:
        subnet_ids = fetch_container_subnet_ids(vpc_id)

    hash_sha256 = account_cache_configuration.get("sha256", None)

    cache_configuration[aws_account] = {
        "aws_region": aws_region,
        "aws_account_id": aws_account_id,
        "vpc_id": vpc_id,
        "subnet_ids": subnet_ids,
        "azs": azs,
        "sha256": hash_sha256,
    }

    print(
        "Selected aws account:"
        f" {Color.BOLD}{Color.GREEN}{aws_account}{Color.END} \u2705"
    )
    print(f"Selected region: {Color.BOLD}{Color.GREEN}{aws_region}{Color.END} \u2705")
    print(f"Selected vpc_id: {Color.BOLD}{Color.GREEN}{vpc_id}{Color.END} \u2705")
    print(
        "Selected subnet_ids:"
        f" {Color.BOLD}{Color.GREEN}{','.join(subnet_ids)}{Color.END} \u2705"
    )
    print(
        "Selected availability zones:"
        f" {Color.BOLD}{Color.GREEN}{','.join(azs)}{Color.END} \u2705"
    )

    os.makedirs(".tmp", exist_ok=True)
    with open(".tmp/easyecs.tmp", "w") as f:
        json.dump(cache_configuration, f)

    return cache_configuration[aws_account]
