import boto3
from easyecs.helpers.common import (
    convert_containers_to_dict,
    convert_tags_to_dict,
)

from easyecs.helpers.selector import select_action


def fetch_aws_account():
    aws_account = boto3.client("iam").list_account_aliases()["AccountAliases"][0]
    return aws_account


def fetch_region():
    client = boto3.client("ec2")
    response = client.describe_regions()
    regions = response["Regions"]
    parsed_regions = [region["RegionName"] for region in regions]
    selected_region: str = select_action(parsed_regions, "Select your ECS region")
    return selected_region


def fetch_vpc_id():
    client = boto3.client("ec2")
    response = client.describe_vpcs()
    vpcs = response["Vpcs"]
    vpcs_parsed = {}
    for vpc in vpcs:
        vpc_id = vpc["VpcId"]
        tags = convert_tags_to_dict(vpc.get("Tags", {}))
        vpc_name = tags.get("Name", "Unnamed VPC")
        vpc_key = f"{vpc_id} - {vpc_name}"
        vpcs_parsed[vpc_key] = vpc
    selected_vpc = select_action(vpcs_parsed.keys(), "Select your ECS Task VPC")
    if not selected_vpc:
        raise Exception("You should selected one VPC!")
    return vpcs_parsed[selected_vpc]["VpcId"]


def fetch_container_subnet_ids(vpc_id):
    client = boto3.client("ec2")
    response = client.describe_subnets(
        Filters=[
            {
                "Name": "vpc-id",
                "Values": [
                    vpc_id,
                ],
            }
        ],
    )
    subnets = response["Subnets"]
    subnets_parsed = {}
    for subnet in subnets:
        subnet_id = subnet["SubnetId"]
        tags = convert_tags_to_dict(subnet.get("Tags", {}))
        subnet_name = tags.get("Name", "Unnamed Subnet")
        subnet_key = f"{subnet_id} - {subnet_name}"
        subnets_parsed[subnet_key] = subnet
    selected_subnets = select_action(
        subnets_parsed.keys(), "Select your ECS Task Subnet(s)", multi=True
    )
    if not selected_subnets:
        raise Exception("You should selected at least one subnet!")
    return [
        subnets_parsed[selected_subnet]["SubnetId"]
        for selected_subnet in selected_subnets
    ]


def fetch_availability_zones(aws_region):
    client = boto3.client("ec2")
    response = client.describe_availability_zones(
        Filters=[{"Name": "region-name", "Values": [aws_region]}]
    )
    azs = response["AvailabilityZones"]
    parsed_azs = [az["ZoneName"] for az in azs]
    return parsed_azs


def fetch_account_id():
    client = boto3.client("sts")
    account_id = client.get_caller_identity()["Account"]
    return account_id


def fetch_is_stack_created(stack_name):
    client = boto3.client("cloudformation")
    try:
        client.describe_stacks(StackName=stack_name)
    except client.exceptions.ClientError:
        return False
    return True


def fetch_containers(user, app_name):
    cluster_name = f"{user}-{app_name}-cluster"
    client = boto3.client("ecs")
    res = client.list_tasks(cluster=cluster_name)
    task_arns = res["taskArns"]
    res_task = client.describe_tasks(cluster=cluster_name, tasks=task_arns)
    containers = res_task["tasks"][0]["containers"]
    # This inject the target for easier use with SSM.
    for container in containers:
        runtime_id = container["runtimeId"]
        task_id = runtime_id.split("-")[0]
        target = f"ecs:{cluster_name}_{task_id}_{runtime_id}"
        container["ssm_target"] = target
    parsed_containers = convert_containers_to_dict(containers)
    return parsed_containers


def fetch_session_region():
    my_session = boto3.session.Session()
    region_name = my_session.region_name
    return region_name


def fetch_stack_url(stack_name):
    client = boto3.client("cloudformation")
    res = client.describe_stacks(StackName=stack_name)
    stack_arn = res["Stacks"][0]["StackId"]
    region_name = fetch_session_region()
    url = f"https://{region_name}.console.aws.amazon.com/cloudformation/home?region={region_name}#/stacks/stackinfo?stackId={stack_arn}"  # noqa: E501
    return url
