import pytest
from easyecs.cloudformation.template import create_template
from unittest.mock import MagicMock


@pytest.mark.parametrize(
    "depends_on",
    [
        ({}),
        (
            {
                "args1": {
                    "container": MagicMock(),
                    "container_definition": MagicMock(
                        depends_on={
                            "args2": {"condition": "service_completed_successfully"}
                        }
                    ),
                },
                "args2": {
                    "container": MagicMock(),
                    "container_definition": MagicMock(),
                },
            }
        ),
        (
            {
                "args1": {
                    "container": MagicMock(),
                    "container_definition": MagicMock(
                        depends_on={
                            "args2": {"condition": "service_completed_successfully"},
                            "args3": {"condition": "service_healthy"},
                        }
                    ),
                },
                "args2": {
                    "container": MagicMock(),
                    "container_definition": MagicMock(),
                },
                "args3": {
                    "container": MagicMock(),
                    "container_definition": MagicMock(),
                },
            }
        ),
    ],
)
def test_depends_on_container_has_depends_on(depends_on, mocker):
    mocker.patch("aws_cdk.App")
    mocker.patch("aws_cdk.BootstraplessSynthesizer")
    mocker.patch("aws_cdk.Stack")
    mocker.patch("aws_cdk.aws_ec2.Vpc.from_vpc_attributes")
    mocker.patch("aws_cdk.aws_ec2.Subnet.from_subnet_id")
    mocker.patch("aws_cdk.aws_ec2.SubnetSelection")
    mocker.patch("easyecs.cloudformation.template.create_task_role")
    mocker.patch("easyecs.cloudformation.template.create_execution_task_role")
    mocker.patch("easyecs.cloudformation.template.create_ecs_cluster")
    mocker.patch("easyecs.cloudformation.template.create_log_group")
    mocker.patch("easyecs.cloudformation.template.create_security_group")
    mocker.patch("easyecs.cloudformation.template.create_ecs_service")
    mocker.patch("aws_cdk.aws_secretsmanager.Secret.from_secret_complete_arn")
    mocker.patch("aws_cdk.aws_ecs.ContainerImage.from_registry")
    mocker.patch("aws_cdk.aws_ecs.LogDriver.aws_logs")
    mocker.patch("aws_cdk.aws_ecs.EfsVolumeConfiguration")
    mocker.patch("aws_cdk.aws_ecs.MountPoint")
    mocker.patch("aws_cdk.aws_ecs.Secret.from_secrets_manager")
    mocker.patch("aws_cdk.aws_ecs.HealthCheck")
    mocker.patch(
        "easyecs.cloudformation.template.task_definition.add_containers_to_task_definition",  # noqa: E501
        return_value=depends_on,
    )
    mocker.patch("aws_cdk.Duration")

    mocker.patch("aws_cdk.aws_ecs.FargateTaskDefinition")
    ecs_data = MagicMock()
    container = MagicMock()
    container.depends_on = depends_on
    ecs_data.task_definition.containers = [container]

    create_template(
        "test_service",
        "123456789012",
        "us-west-2",
        "vpc-0123456789abcdef0",
        ["subnet-0123456789abcdef0", "subnet-0123456789abcdef1"],
        ["us-west-2a", "us-west-2b"],
        ecs_data,
    )

    for _, value in depends_on.items():
        container = value["container"]
        container_definitions = value["container_definition"]
        depends_on = container_definitions.get("depends_on", {})
        assert container.add_container_dependencies().call_count == len(
            depends_on.keys()
        )
