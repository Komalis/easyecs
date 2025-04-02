import pytest
from easyecs.cloudformation.template import create_template
from unittest.mock import MagicMock


@pytest.mark.parametrize(
    "efs_volumes, count", [([], 0), ([MagicMock()], 1), ([MagicMock(), MagicMock()], 2)]
)
def test_efs_add_mount_points_if_container_has_efs_volumes(efs_volumes, count, mocker):
    mocker.patch("aws_cdk.App")
    mocker.patch("aws_cdk.BootstraplessSynthesizer")
    mocker.patch("aws_cdk.Stack")
    mocker.patch("aws_cdk.aws_ec2.Vpc.from_vpc_attributes")
    mocker.patch("aws_cdk.aws_ec2.Subnet.from_subnet_id")
    mocker.patch("aws_cdk.aws_ec2.SubnetSelection")
    mocker.patch("aws_cdk.aws_elasticloadbalancingv2.NetworkLoadBalancer")
    mocker.patch("easyecs.cloudformation.template.create_task_role")
    mocker.patch("easyecs.cloudformation.template.create_execution_task_role")
    mocker.patch("easyecs.cloudformation.template.create_ecs_cluster")
    mocker.patch("easyecs.cloudformation.template.create_log_group")
    mocker.patch("easyecs.cloudformation.template.create_security_group")
    mocker.patch("aws_cdk.aws_ec2.SecurityGroup")
    mocker.patch("easyecs.cloudformation.template.create_ecs_service")
    mocker.patch("aws_cdk.aws_secretsmanager.Secret.from_secret_complete_arn")
    mocker.patch("aws_cdk.aws_ecs.ContainerImage.from_registry")
    mocker.patch("aws_cdk.aws_ecs.LogDriver.aws_logs")
    mocker.patch("aws_cdk.aws_ecs.EfsVolumeConfiguration")
    mocker.patch("aws_cdk.aws_ecs.MountPoint")
    mocker.patch("aws_cdk.aws_ecs.Secret.from_secrets_manager")
    mocker.patch("aws_cdk.aws_ecs.HealthCheck")
    mocker.patch("aws_cdk.Duration")

    # Mock the ecs_data object. Here you may need to adjust to your specific case
    mocker_container = mocker.patch("aws_cdk.aws_ecs.FargateTaskDefinition")
    ecs_data = MagicMock()
    ecs_data.task_definition.efs_volumes = [MagicMock(), MagicMock()]
    container = MagicMock()
    container.efs_volumes = efs_volumes
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

    assert mocker_container().add_container().add_mount_points.call_count == count
