import json

import boto3
from botocore.client import ClientError
from botocore.waiter import WaiterError
from easyecs.command import run_force_new_deployment
from easyecs.helpers.color import Color
from easyecs.helpers.loader import Loader


def create_stack(stack_name):
    loader = Loader(
        "Creating CloudFormation stack:",
        "Creating CloudFormation stack: \u2705",
        "Creating CloudFormation stack: \u274c",
        0.05,
    )
    loader.start()
    cloudformation_template = json.load(
        open(f".cloudformation/{stack_name}.template.json")
    )
    client = boto3.client("cloudformation")
    client.create_stack(
        StackName=stack_name,
        TemplateBody=json.dumps(cloudformation_template),
        Capabilities=["CAPABILITY_NAMED_IAM"],
    )
    waiter = client.get_waiter("stack_create_complete")
    try:
        waiter.wait(StackName=stack_name)
        loader.stop()
    except WaiterError as e:
        loader.stop_error()
        reason = e.kwargs["reason"]
        print(f"{Color.RED}{reason}{Color.END}")
        delete_stack(stack_name)
        exit(-1)


def update_stack(stack_name, force_redeployment):
    loader = Loader(
        "Updating CloudFormation stack:",
        "Updating CloudFormation stack: \u2705",
        "Updating CloudFormation stack: \u274c",
        0.05,
    )
    loader.start()
    cloudformation_template = json.load(
        open(f".cloudformation/{stack_name}.template.json")
    )
    client = boto3.client("cloudformation")
    while True:
        try:
            client.update_stack(
                StackName=stack_name,
                TemplateBody=json.dumps(cloudformation_template),
                Capabilities=["CAPABILITY_NAMED_IAM"],
            )
            waiter = client.get_waiter("stack_update_complete")
            waiter.wait(StackName=stack_name)
            loader.stop()
            break
        except ClientError as e:
            message = e.response["Error"]["Message"]
            if message == "No updates are to be performed.":
                loader.stop()
                print(f"{Color.YELLOW}No updates are to be performed.{Color.END}")
                if force_redeployment:
                    run_force_new_deployment(stack_name)
                break
            elif "UPDATE_IN_PROGRESS" in message:
                cloudformation = boto3.resource("cloudformation")
                stack = cloudformation.Stack(stack_name)
                stack.cancel_update()
                waiter = client.get_waiter("stack_rollback_complete")
                waiter.wait(StackName=stack_name)
            elif "ROLLBACK_IN_PROGRESS" in message:
                waiter = client.get_waiter("stack_rollback_complete")
                waiter.wait(StackName=stack_name)
            else:
                loader.stop_error()
                print(e)
                break


def delete_stack(stack_name):
    loader = Loader(
        "Deleting CloudFormation stack:",
        "Deleting CloudFormation stack: \u2705",
        "Deleting CloudFormation stack: \u274c",
        0.05,
    )
    loader.start()
    client = boto3.client("cloudformation")
    try:
        client.delete_stack(StackName=stack_name)
    except client.exceptions.AlreadyExistsException:
        loader.stop_error()
        print(f"{Color.RED}The CloudFormation stack already exists!{Color.END}")
        exit(-1)
    waiter = client.get_waiter("stack_delete_complete")
    waiter.wait(StackName=stack_name)
    loader.stop()
