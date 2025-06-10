import os

import boto3


def handler(event, context):
    client = boto3.client("cloudformation")
    stack_name = os.environ["StackName"]
    response = client.delete_stack(
        StackName=stack_name,
    )
    print(response)

    return {"statusCode": response["ResponseMetadata"]["HTTPStatusCode"]}
