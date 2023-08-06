from easyecs.cloudformation.template import create_template
from unittest.mock import MagicMock


def _setup_mocks(mocker):
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
    magic_mock_image = mocker.patch("aws_cdk.aws_ecs.ContainerImage.from_registry")
    mock_log_group = MagicMock()
    mocker.patch("aws_cdk.aws_ecs.LogDriver.aws_logs", return_value=mock_log_group)
    mocker.patch("aws_cdk.aws_ecs.EfsVolumeConfiguration")
    mocker.patch("aws_cdk.aws_ecs.MountPoint")
    mocker.patch("aws_cdk.aws_ecs.Secret.from_secrets_manager")
    mock_health_check = mocker.patch("aws_cdk.aws_ecs.HealthCheck")
    mocker.patch("aws_cdk.Duration")
    mocker_container = mocker.patch("aws_cdk.aws_ecs.FargateTaskDefinition")

    return magic_mock_image, mock_log_group, mocker_container, mock_health_check


def _create_mock_container():
    container = MagicMock()
    container.name = "test"
    container.image = "test"
    container.user = "test"
    container.resources.limits.cpu = 1
    container.resources.limits.memory = 1024
    container.command = "/bin/bash"
    container.env = []
    container.secrets = []

    return container


def _create_mock_ecs_data(container):
    ecs_data = MagicMock()
    ecs_data.task_definition.containers = [container]
    return ecs_data


def test_command_is_always_sleep_when_tty(mocker):
    magic_mock_image, mock_log_group, mocker_container, mock_health_check = (
        _setup_mocks(mocker)
    )

    container = _create_mock_container()
    ecs_data = _create_mock_ecs_data(container)

    create_template(
        "test_service",
        "123456789012",
        "us-west-2",
        "vpc-0123456789abcdef0",
        ["subnet-0123456789abcdef0", "subnet-0123456789abcdef1"],
        ["us-west-2a", "us-west-2b"],
        ecs_data,
        run=False,
    )

    mocker_container().add_container.assert_called_once_with(
        id=container.name,
        container_name=container.name,
        image=magic_mock_image(container.image),
        command="sleep infinity".split(" "),
        logging=mock_log_group,
        environment={},
        secrets={},
        cpu=1024,
        memory_limit_mib=1024,
        user=container.user,
        essential=container.essential,
        health_check=mock_health_check(),
        entry_point=container.entry_point,
    )


def test_command_is_always_sleep_when_run(mocker):
    magic_mock_image, mock_log_group, mocker_container, mock_health_check = (
        _setup_mocks(mocker)
    )

    container = _create_mock_container()
    container.tty = True
    ecs_data = _create_mock_ecs_data(container)

    create_template(
        "test_service",
        "123456789012",
        "us-west-2",
        "vpc-0123456789abcdef0",
        ["subnet-0123456789abcdef0", "subnet-0123456789abcdef1"],
        ["us-west-2a", "us-west-2b"],
        ecs_data,
        run=True,
    )

    mocker_container().add_container.assert_called_once_with(
        id=container.name,
        container_name=container.name,
        image=magic_mock_image(container.image),
        command=container.command.split(" "),
        logging=mock_log_group,
        environment={},
        secrets={},
        cpu=1024,
        memory_limit_mib=1024,
        user=container.user,
        essential=container.essential,
        health_check=mock_health_check(),
        entry_point=container.entry_point,
    )
