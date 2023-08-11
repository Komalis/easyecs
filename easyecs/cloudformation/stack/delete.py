import boto3
from botocore.utils import ClientError
from easyecs.cloudformation.client import get_client_cloudformation
from easyecs.cloudformation.fetch import fetch_stack_url
from easyecs.cloudformation.stack.waiter import (
    wait_for_stack_create,
    wait_for_stack_delete,
    wait_for_stack_rollback,
)
from easyecs.helpers.color import Color

from easyecs.helpers.loader import Loader


def handle_delete_error(e: ClientError, stack_name: str, loader: Loader):
    """
    Handles a CloudFormation stack update failure.
    Depending on the error, either waits for a rollback, cancels an update,
    or prints the error and breaks the loop.
    """
    message = e.response["Error"]["Message"]
    if "UPDATE_IN_PROGRESS" in message:
        cloudformation = boto3.resource("cloudformation")
        stack = cloudformation.Stack(stack_name)
        stack.cancel_update()
        wait_for_stack_rollback(stack_name)
        delete_cloudformation_stack(stack_name)
        loader.stop()
    elif "CREATE_FAILED" in message:
        print(f"{Color.RED}Creation failed, please check CloudFormation.{Color.END}")
        loader.stop()
    elif "ROLLBACK_FAILED" in message:
        print(f"{Color.RED}Rollback failed, please check CloudFormation.{Color.END}")
        loader.stop()
    elif "ROLLBACK_IN_PROGRESS" in message:
        wait_for_stack_rollback(stack_name)
        loader.stop()
    elif "CREATE_IN_PROGRESS" in message:
        wait_for_stack_create(stack_name)
        loader.stop()
    else:
        loader.stop_error()
        print(e)


def delete_cloudformation_stack(stack_name: str):
    client = get_client_cloudformation()
    client.delete_stack(StackName=stack_name)


def delete_stack(stack_name):
    """
    Deletes a CloudFormation stack with a given stack_name
    """
    # Initialize the loader with appropriate messages
    loader = Loader(
        "Deleting CloudFormation stack:",
        "Deleting CloudFormation stack: \u2705",
        "Deleting CloudFormation stack: \u274c",
        0.05,
    )
    loader.start()

    try:
        loader.set_metadata(f"Cloudformation URL: {fetch_stack_url(stack_name)}")
        delete_cloudformation_stack(stack_name)
        wait_for_stack_delete(stack_name)
        loader.stop()
    except ClientError as e:
        handle_delete_error(e, stack_name, loader)
