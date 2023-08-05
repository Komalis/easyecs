from dataclasses import dataclass, field
import json
import subprocess
from unittest.mock import MagicMock

from botocore.client import ClientError
import pytest

from easyecs.cli import action_dev, action_run
from easyecs.command import generate_ssm_cmd

# Those tests are checking if cloudformation is called in different use cases.
# It also checks if waiters are called to wait for the stack to be completed.
# And moreover checks if the errors are handled correctly.


@dataclass
class Context:
    obj: dict = field(default_factory=dict)


@pytest.fixture
def setup_mocker(mocker):
    mocker.patch("easyecs.cli.load_settings")
    mocker.patch("easyecs.cli.read_ecs_file")
    mocker.patch("easyecs.cli.step_import_aws_cdk")
    mocker.patch("easyecs.cli.step_docker_build_and_push")
    mocker.patch("easyecs.cli.fetch_containers")
    mocker.patch("easyecs.cli.fetch_aws_account")
    mocker.patch("easyecs.cli.create_port_forwards")
    mocker.patch("easyecs.cli.run_nc_commands")
    mocker.patch("easyecs.cli.run_sync_thread")
    mocker.patch("easyecs.cli.execute_command")
    mocker.patch("easyecs.cli.step_idle_keyboard")
    mocker.patch("easyecs.cli.step_clean_exit")
    mocker.patch("easyecs.cli.save_hash")
    mocker.patch("easyecs.cli.has_ecs_file_changed", return_value=True)


def create_context():
    return Context(
        obj={
            "no_docker_build": False,
            "force_redeployment": False,
            "show_docker_logs": False,
        }
    )


def run_action(action, ctx):
    try:
        action(ctx)
    except SystemExit:
        pass


actions = [action_dev, action_run]


@pytest.mark.parametrize("action", actions)
def test_cloudformation_create_stack_is_called(action, setup_mocker, mocker):
    mocker.patch("easyecs.cli.fetch_is_stack_created", return_value=False)
    mocker.patch("easyecs.cloudformation.stack.create.load_template", return_value={})

    mock = MagicMock()
    mocker.patch(
        "easyecs.cloudformation.stack.create.get_client_cloudformation",
        return_value=mock,
    )

    ctx = create_context()
    run_action(action, ctx)

    mock.create_stack.assert_called_once()


@pytest.mark.parametrize("action", actions)
def test_cloudformation_create_stack_is_not_called_stack_created(
    action, setup_mocker, mocker
):
    mocker.patch("easyecs.cli.fetch_is_stack_created", return_value=True)
    mocker.patch("easyecs.cloudformation.stack.update.update_cloudformation_stack")
    mocker.patch("easyecs.cloudformation.stack.update.wait_for_stack_update")
    mocker.patch("easyecs.cloudformation.stack.update.load_template", return_value={})

    mock = MagicMock()
    mocker.patch(
        "easyecs.cloudformation.stack.create.get_client_cloudformation",
        return_value=mock,
    )

    ctx = create_context()
    run_action(action, ctx)

    mock.create_stack.assert_not_called()


@pytest.mark.parametrize("action", actions)
def test_cloudformation_update_stack_is_called_stack_created(
    action, setup_mocker, mocker
):
    mocker.patch("easyecs.cli.fetch_is_stack_created", return_value=True)
    mocker.patch("easyecs.cloudformation.stack.update.load_template", return_value={})

    mock = MagicMock()
    mocker.patch(
        "easyecs.cloudformation.stack.update.get_client_cloudformation",
        return_value=mock,
    )

    ctx = create_context()
    run_action(action, ctx)

    mock.update_stack.assert_called_once()


@pytest.mark.parametrize("action", actions)
def test_cloudformation_update_stack_is_called_stack_created_no_update(
    action, setup_mocker, mocker
):
    mocker.patch("easyecs.cli.fetch_is_stack_created", return_value=True)
    mocker.patch("easyecs.cloudformation.stack.update.load_template", return_value={})

    error_response = {
        "Error": {"Code": None, "Message": "No updates are to be performed."}
    }
    mocker.patch(
        "easyecs.cloudformation.stack.update.wait_for_stack_update",
        side_effect=ClientError(
            error_response=error_response, operation_name="stack_rollback_complete"
        ),
    )

    mock = MagicMock()
    mocker.patch(
        "easyecs.cloudformation.stack.update.get_client_cloudformation",
        return_value=mock,
    )

    ctx = create_context()
    run_action(action, ctx)

    mock.update_stack.assert_called_once()


@pytest.mark.parametrize("action", actions)
def test_cloudformation_cancel_update_is_called_stack_created_no_update_update_in_progress(  # noqa: E501
    action, setup_mocker, mocker
):
    mocker.patch("easyecs.cli.fetch_is_stack_created", return_value=True)
    mocker.patch("easyecs.cloudformation.stack.update.get_client_cloudformation")
    mocker.patch("easyecs.cloudformation.stack.update.load_template", return_value={})

    error_response = {"Error": {"Code": None, "Message": "UPDATE_IN_PROGRESS"}}
    mocker.patch(
        "easyecs.cloudformation.stack.update.wait_for_stack_update",
        side_effect=ClientError(
            error_response=error_response, operation_name="stack_rollback_complete"
        ),
    )

    mock = MagicMock()
    mocker.patch(
        "easyecs.cloudformation.stack.update.boto3.resource", return_value=mock
    )

    ctx = create_context()
    run_action(action, ctx)

    mock.Stack().cancel_update.assert_called_once


@pytest.mark.parametrize("action", actions)
def test_cloudformation_waiter_stack_rollback_complete_is_called_stack_created_no_update_update_in_progress(  # noqa: E501
    action, setup_mocker, mocker
):
    mocker.patch("easyecs.cli.fetch_is_stack_created", return_value=True)
    mocker.patch("easyecs.cloudformation.stack.update.boto3.resource")
    mocker.patch("easyecs.cloudformation.stack.update.load_template", return_value={})

    error_response = {"Error": {"Code": None, "Message": "UPDATE_IN_PROGRESS"}}
    mocker.patch(
        "easyecs.cloudformation.stack.update.wait_for_stack_update",
        side_effect=ClientError(
            error_response=error_response, operation_name="stack_rollback_complete"
        ),
    )

    mock = MagicMock()
    mocker.patch(
        "easyecs.cloudformation.stack.update.get_client_cloudformation",
        return_value=mock,
    )

    ctx = create_context()
    run_action(action, ctx)

    mock.get_waiter.assert_called_once_with("stack_rollback_complete")


@pytest.mark.parametrize("action", actions)
def test_cloudformation_waiter_stack_rollback_complete_is_called_stack_created_no_update_rollback_in_progress(  # noqa: E501
    action, setup_mocker, mocker
):
    mocker.patch("easyecs.cli.fetch_is_stack_created", return_value=True)
    mocker.patch("easyecs.cloudformation.stack.update.boto3.resource")
    mocker.patch("easyecs.cloudformation.stack.update.load_template", return_value={})

    error_response = {"Error": {"Code": None, "Message": "ROLLBACK_IN_PROGRESS"}}
    mocker.patch(
        "easyecs.cloudformation.stack.update.wait_for_stack_update",
        side_effect=ClientError(
            error_response=error_response, operation_name="stack_rollback_complete"
        ),
    )

    mock = MagicMock()
    mocker.patch(
        "easyecs.cloudformation.stack.update.get_client_cloudformation",
        return_value=mock,
    )

    ctx = create_context()
    run_action(action, ctx)

    mock.get_waiter.assert_called_once_with("stack_rollback_complete")


@pytest.mark.parametrize("action", actions)
def test_cloudformation_waiter_stack_rollback_complete_is_called_stack_created_no_update_create_in_progress(  # noqa: E501
    action, setup_mocker, mocker
):
    mocker.patch("easyecs.cli.fetch_is_stack_created", return_value=True)
    mocker.patch("easyecs.cloudformation.stack.update.boto3.resource")
    mocker.patch("easyecs.cloudformation.stack.update.load_template", return_value={})

    error_response = {"Error": {"Code": None, "Message": "CREATE_IN_PROGRESS"}}
    mocker.patch(
        "easyecs.cloudformation.stack.update.wait_for_stack_update",
        side_effect=ClientError(
            error_response=error_response, operation_name="stack_create_complete"
        ),
    )

    mock = MagicMock()
    mocker.patch(
        "easyecs.cloudformation.stack.update.get_client_cloudformation",
        return_value=mock,
    )

    ctx = create_context()
    run_action(action, ctx)

    mock.get_waiter.assert_called_once_with("stack_create_complete")


@pytest.mark.parametrize("action", actions)
def test_cloudformation_waiter_stack_update_complete_is_called_stack_created(  # noqa: E501
    action, setup_mocker, mocker
):
    mocker.patch("easyecs.cli.fetch_is_stack_created", return_value=True)
    mocker.patch("easyecs.cloudformation.stack.update.boto3.resource")
    mocker.patch("easyecs.cloudformation.stack.update.load_template", return_value={})

    mock = MagicMock()
    mocker.patch(
        "easyecs.cloudformation.stack.update.get_client_cloudformation",
        return_value=mock,
    )

    ctx = create_context()
    run_action(action, ctx)

    mock.get_waiter.assert_called_once_with("stack_update_complete")


@pytest.mark.parametrize("action", actions)
def test_cloudformation_waiter_stack_create_complete_is_called_stack_not_created(  # noqa: E501
    action, setup_mocker, mocker
):
    mocker.patch("easyecs.cli.fetch_is_stack_created", return_value=False)
    mocker.patch("easyecs.cloudformation.stack.create.load_template", return_value={})

    mock = MagicMock()
    mocker.patch(
        "easyecs.cloudformation.stack.create.get_client_cloudformation",
        return_value=mock,
    )

    ctx = create_context()
    run_action(action, ctx)

    mock.get_waiter.assert_called_once_with("stack_create_complete")


@pytest.mark.parametrize("action", actions)
def test_cloudformation_waiter_stack_no_create_or_update_if_hash_same(  # noqa: E501
    action, setup_mocker, mocker
):
    mocker.patch("easyecs.cli.has_ecs_file_changed", return_value=False)

    mocks = [
        mocker.patch("easyecs.cli.step_import_aws_cdk"),
        mocker.patch("easyecs.cli.step_docker_build_and_push"),
        mocker.patch("easyecs.cli.step_create_or_update_stack"),
        mocker.patch("easyecs.cli.save_hash"),
    ]

    ctx = create_context()
    run_action(action, ctx)

    for mock in mocks:
        mock.assert_not_called()


@pytest.mark.parametrize("action", actions)
def test_cloudformation_waiter_stack_create_or_update_if_hash_same_force_redeployment(  # noqa: E501
    action, setup_mocker, mocker
):
    mocker.patch("easyecs.cli.has_ecs_file_changed", return_value=False)

    mocks = [
        mocker.patch("easyecs.cli.step_import_aws_cdk"),
        mocker.patch("easyecs.cli.step_docker_build_and_push"),
        mocker.patch("easyecs.cli.step_create_or_update_stack"),
        mocker.patch("easyecs.cli.save_hash"),
    ]

    ctx = create_context()
    ctx.obj["force_redeployment"] = True
    run_action(action, ctx)

    for mock in mocks:
        mock.assert_called_once()


@pytest.mark.parametrize("action", [action_dev])
def test_run_nc_when_dev_with_synchronize(action, mocker):  # noqa: E501
    mocker.patch("easyecs.cli.fetch_aws_account", return_value="aws_account")
    cache_settings = MagicMock()
    cache_settings.aws_region = "eu-west-1"
    mocker.patch("easyecs.cli.load_settings", return_value=cache_settings)
    ecs_manifest = MagicMock()
    container = MagicMock()
    container.synchronize = True
    ecs_manifest.task_definition.containers = [container]
    mocker.patch("easyecs.cli.read_ecs_file", return_value=ecs_manifest)
    mocker.patch("easyecs.cli.step_bring_up_stack")
    parsed_containers = MagicMock()
    mocker.patch("easyecs.cli.fetch_containers", return_value=parsed_containers)
    mocker.patch("easyecs.cli.create_port_forwards")
    mocker.patch("easyecs.cli.run_sync_thread")
    mocker.patch("easyecs.cli.execute_command")
    mocker.patch("easyecs.cli.step_idle_keyboard")
    mocker.patch("easyecs.cli.step_clean_exit")
    mocker.patch("easyecs.command.check_nc_command", return_value=True)
    mocker.patch("easyecs.command.generate_random_port", return_value=8000)
    mocker.patch("easyecs.command.port_forward")
    mocker.patch("easyecs.command.boto3.client")
    ssm_cmd = MagicMock()
    mocker.patch("easyecs.command.generate_ssm_cmd", return_value=ssm_cmd)
    proc_nc_server = mocker.patch("easyecs.command.subprocess.Popen")
    mocker.patch("easyecs.command.json.dumps")

    ctx = create_context()
    run_action(action, ctx)

    proc_nc_server.assert_called_once_with(
        ssm_cmd,
        start_new_session=True,
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
    )


def test_generate_cmd_nc_server(mocker):  # noqa: E501
    ssm_nc_server = {}
    target = "ecs:test"
    aws_region = "eu-west-1"
    aws_account = "test-account"
    test_cmd = [
        "session-manager-plugin",
        json.dumps({}),
        aws_region,
        "StartSession",
        aws_account,
        json.dumps(dict(Target=target)),
        f"https://ssm.{aws_region}.amazonaws.com",
    ]
    generated_cmd = generate_ssm_cmd(ssm_nc_server, aws_region, aws_account, target)
    assert test_cmd == generated_cmd


@pytest.mark.parametrize("action", [action_dev])
def test_no_run_nc_when_dev_without_synchronize(action, mocker):  # noqa: E501
    mocker.patch("easyecs.cli.fetch_aws_account", return_value="aws_account")
    cache_settings = MagicMock()
    cache_settings.aws_region = "eu-west-1"
    mocker.patch("easyecs.cli.load_settings", return_value=cache_settings)
    ecs_manifest = MagicMock()
    container = MagicMock()
    container.synchronize = False
    ecs_manifest.task_definition.containers = [container]
    mocker.patch("easyecs.cli.read_ecs_file", return_value=ecs_manifest)
    mocker.patch("easyecs.cli.step_bring_up_stack")
    parsed_containers = MagicMock()
    mocker.patch("easyecs.cli.fetch_containers", return_value=parsed_containers)
    mocker.patch("easyecs.cli.create_port_forwards")
    mocker.patch("easyecs.cli.run_sync_thread")
    mocker.patch("easyecs.cli.execute_command")
    mocker.patch("easyecs.cli.step_idle_keyboard")
    mocker.patch("easyecs.cli.step_clean_exit")
    mocker.patch("easyecs.command.check_nc_command", return_value=True)
    mocker.patch("easyecs.command.generate_random_port", return_value=8000)
    mocker.patch("easyecs.command.port_forward")
    mocker.patch("easyecs.command.boto3.client")
    proc_nc_server = mocker.patch("easyecs.command.subprocess.Popen")
    mocker.patch("easyecs.command.json.dumps")

    ctx = create_context()
    run_action(action, ctx)

    proc_nc_server.assert_not_called()


@pytest.mark.parametrize("action", [action_dev])
def test_no_run_nc_when_dev_with_synchronize_without_nc(action, mocker):  # noqa: E501
    mocker.patch("easyecs.cli.fetch_aws_account", return_value="aws_account")
    cache_settings = MagicMock()
    cache_settings.aws_region = "eu-west-1"
    mocker.patch("easyecs.cli.load_settings", return_value=cache_settings)
    ecs_manifest = MagicMock()
    container = MagicMock()
    container.synchronize = False
    ecs_manifest.task_definition.containers = [container]
    mocker.patch("easyecs.cli.read_ecs_file", return_value=ecs_manifest)
    mocker.patch("easyecs.cli.step_bring_up_stack")
    parsed_containers = MagicMock()
    mocker.patch("easyecs.cli.fetch_containers", return_value=parsed_containers)
    mocker.patch("easyecs.cli.create_port_forwards")
    mocker.patch("easyecs.cli.run_sync_thread")
    mocker.patch("easyecs.cli.execute_command")
    mocker.patch("easyecs.cli.step_idle_keyboard")
    mocker.patch("easyecs.cli.step_clean_exit")
    mocker.patch("easyecs.command.check_nc_command", return_value=False)
    mocker.patch("easyecs.command.generate_random_port", return_value=8000)
    mocker.patch("easyecs.command.port_forward")
    mocker.patch("easyecs.command.boto3.client")
    proc_nc_server = mocker.patch("easyecs.command.subprocess.Popen")
    mocker.patch("easyecs.command.json.dumps")

    ctx = create_context()
    run_action(action, ctx)

    proc_nc_server.assert_not_called()


@pytest.mark.parametrize(
    "action, ports",
    [
        (action_dev, ["8000:8000"]),
        (action_run, ["8000:8000"]),
        (action_dev, ["8000:8000", "8001:8001"]),
        (action_run, ["8000:8000", "8001:8001"]),
    ],
)
def test_run_port_forward(action, ports, mocker):  # noqa: E501
    mocker.patch("easyecs.cli.fetch_aws_account", return_value="aws_account")
    cache_settings = MagicMock()
    cache_settings.aws_region = "eu-west-1"
    mocker.patch("easyecs.cli.load_settings", return_value=cache_settings)
    ecs_manifest = MagicMock()
    container = MagicMock()
    container.port_forward = ports
    ecs_manifest.task_definition.containers = [container]
    mocker.patch("easyecs.cli.read_ecs_file", return_value=ecs_manifest)
    mocker.patch("easyecs.cli.step_bring_up_stack")
    parsed_containers = MagicMock()
    mocker.patch("easyecs.cli.fetch_containers", return_value=parsed_containers)
    mocker.patch("easyecs.cli.run_sync_thread")
    mocker.patch("easyecs.cli.execute_command")
    mocker.patch("easyecs.cli.step_idle_keyboard")
    mocker.patch("easyecs.cli.step_clean_exit")
    mocker.patch("easyecs.cli.run_nc_commands")
    ssm_cmd = MagicMock()
    mocker.patch("easyecs.command.generate_ssm_cmd", return_value=ssm_cmd)
    mocker.patch("easyecs.command.boto3.client")
    mocker.patch("easyecs.command.is_port_in_use", return_value=False)

    process = mocker.patch("easyecs.command.subprocess.Popen")

    ctx = create_context()
    run_action(action, ctx)

    if len(ports) == 1:
        process.assert_called_once_with(
            ssm_cmd,
            start_new_session=True,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
        )
    else:
        assert process.call_count == len(ports)


@pytest.mark.parametrize(
    "action, ports",
    [
        (action_dev, ["8000:8000"]),
        (action_run, ["8000:8000"]),
        (action_dev, ["8000:8000", "8001:8001"]),
        (action_run, ["8000:8000", "8001:8001"]),
    ],
)
def test_no_run_port_forward_port_in_use(action, ports, mocker):  # noqa: E501
    mocker.patch("easyecs.cli.fetch_aws_account", return_value="aws_account")
    cache_settings = MagicMock()
    cache_settings.aws_region = "eu-west-1"
    mocker.patch("easyecs.cli.load_settings", return_value=cache_settings)
    ecs_manifest = MagicMock()
    container = MagicMock()
    container.port_forward = ports
    ecs_manifest.task_definition.containers = [container]
    mocker.patch("easyecs.cli.read_ecs_file", return_value=ecs_manifest)
    mocker.patch("easyecs.cli.step_bring_up_stack")
    parsed_containers = MagicMock()
    mocker.patch("easyecs.cli.fetch_containers", return_value=parsed_containers)
    mocker.patch("easyecs.cli.run_sync_thread")
    mocker.patch("easyecs.cli.execute_command")
    mocker.patch("easyecs.cli.step_idle_keyboard")
    mocker.patch("easyecs.cli.step_clean_exit")
    mocker.patch("easyecs.cli.run_nc_commands")
    ssm_cmd = MagicMock()
    mocker.patch("easyecs.command.generate_ssm_cmd", return_value=ssm_cmd)
    mocker.patch("easyecs.command.boto3.client")
    mocker.patch("easyecs.command.is_port_in_use", return_value=True)

    process = mocker.patch("easyecs.command.subprocess.Popen")

    ctx = create_context()
    run_action(action, ctx)

    process.assert_not_called()
