from easyecs.cloudformation.client import get_client_cloudformation


def wait_for_stack_update(stack_name: str):
    """
    Waits for the CloudFormation stack to be updated.
    Throws an exception if the update fails.
    """
    client = get_client_cloudformation()
    waiter = client.get_waiter("stack_update_complete")
    waiter.wait(StackName=stack_name)


def wait_for_stack_rollback(stack_name: str):
    """
    Waits for the CloudFormation stack to be rolled back.
    """
    client = get_client_cloudformation()
    waiter = client.get_waiter("stack_rollback_complete")
    waiter.wait(StackName=stack_name)


def wait_for_stack_create(stack_name: str):
    """
    Waits for the CloudFormation stack to be created.
    """
    client = get_client_cloudformation()
    waiter = client.get_waiter("stack_create_complete")
    waiter.wait(StackName=stack_name)


def wait_for_stack_delete(stack_name: str):
    """
    Waits for the CloudFormation stack to be deleted.
    """
    client = get_client_cloudformation()
    waiter = client.get_waiter("stack_delete_complete")
    waiter.wait(StackName=stack_name)
