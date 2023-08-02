import boto3


def get_client_cloudformation():
    return boto3.client("cloudformation")
