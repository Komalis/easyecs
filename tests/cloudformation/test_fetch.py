from unittest.mock import MagicMock

from botocore.exceptions import ClientError

from easyecs.cloudformation.fetch import fetch_containers


def test_fetch_containers_returns_empty_when_cluster_not_found(mocker):
    client = MagicMock()
    client.list_tasks.side_effect = ClientError(
        {
            "Error": {
                "Code": "ClusterNotFoundException",
                "Message": "Cluster not found.",
            }
        },
        "ListTasks",
    )
    mocker.patch("easyecs.cloudformation.fetch.boto3.client", return_value=client)

    assert fetch_containers("user", "app") == {}
