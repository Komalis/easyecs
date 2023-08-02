from dataclasses import dataclass, field
from unittest.mock import MagicMock

from botocore.client import ClientError
import pytest

from easyecs.cli import action_dev, action_run

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


def create_context():
    return Context(obj={"no_docker_build": False, "force_redeployment": False})


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
