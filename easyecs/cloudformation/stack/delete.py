import boto3
from easyecs.helpers.color import Color

from easyecs.helpers.loader import Loader


def delete_stack(stack_name):
    """
    Deletes a CloudFormation stack with a given stack_name
    """
    client = boto3.client("cloudformation")

    # Initialize the loader with appropriate messages
    loader = Loader(
        "Deleting CloudFormation stack:",
        "Deleting CloudFormation stack: \u2705",
        "Deleting CloudFormation stack: \u274c",
        0.05,
    )
    loader.start()

    try:
        # Attempt to delete the CloudFormation stack
        client.delete_stack(StackName=stack_name)

        # Initialize a waiter for the 'stack_delete_complete' event
        waiter = client.get_waiter("stack_delete_complete")
        waiter.wait(StackName=stack_name)
        loader.stop()  # Stop the loader when the stack deletion is complete

    except client.exceptions.StackNotFoundException:
        # If the stack doesn't exist, stop the loader with an error and print a message
        loader.stop_error()
        print(f"{Color.RED}The CloudFormation stack does not exist!{Color.END}")
        exit(-1)
