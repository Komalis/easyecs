import json
from typing import Dict

from botocore.waiter import WaiterError
from easyecs.cloudformation.client import get_client_cloudformation
from easyecs.cloudformation.fetch import fetch_stack_url
from easyecs.cloudformation.stack.delete import delete_stack

from easyecs.helpers.color import Color
from easyecs.helpers.common import load_template
from easyecs.helpers.loader import Loader


def create_cloudformation_stack(stack_name: str, template_body: Dict):
    """
    Sends a request to AWS to create a CloudFormation stack.
    """
    client = get_client_cloudformation()
    client.create_stack(
        StackName=stack_name,
        TemplateBody=json.dumps(template_body),
        Capabilities=["CAPABILITY_NAMED_IAM"],
    )


def wait_for_stack_creation(stack_name: str):
    """
    Waits for the CloudFormation stack to be created.
    Throws an exception if the creation fails.
    """
    client = get_client_cloudformation()
    waiter = client.get_waiter("stack_create_complete")
    waiter.wait(StackName=stack_name)


def handle_stack_creation_failure(e: WaiterError, stack_name: str):
    """
    Handles a CloudFormation stack creation failure.
    Prints the reason for the failure, deletes the stack, and exits the program.
    """
    reason = e.kwargs["reason"]
    print(f"{Color.RED}{reason}{Color.END}")
    delete_stack(stack_name)
    exit(-1)


def create_stack(stack_name: str):
    """
    Creates a CloudFormation stack with the given name.
    """
    loader = Loader(
        "Creating CloudFormation stack:",
        "Creating CloudFormation stack: \u2705",
        "Creating CloudFormation stack: \u274c",
        0.05,
    )
    loader.start()

    try:
        cloudformation_template = load_template(stack_name)
        create_cloudformation_stack(stack_name, cloudformation_template)
        loader.set_metadata(f"Cloudformation URL: {fetch_stack_url(stack_name)}")
        wait_for_stack_creation(stack_name)
    except WaiterError as e:
        handle_stack_creation_failure(e, stack_name)

    loader.stop()
