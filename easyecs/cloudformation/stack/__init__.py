from easyecs.cloudformation.client import get_client_cloudformation


def wait_for_stack_status(stack_name: str, stack_status: str):
    """
    Waits for the CloudFormation stack to be rolled back.
    """
    client = get_client_cloudformation()
    waiter = client.get_waiter(stack_status)
    waiter.wait(StackName=stack_name)
