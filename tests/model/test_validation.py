import os
from typing import Union
import pytest
from pydantic import ValidationError
from easyecs.model.ecs import (
    EcsFileModel,
    EcsFileMetadataModel,
    EcsFileRoleModel,
    EcsFileStatementModel,
    EcsFileLimitsModel,
    EcsFileResourcesModel,
    EcsFileContainerModel,
    EcsTaskDefinitionModel,
)  # Replace 'your_module' with the actual module name


def test_unique_sid_validation():
    with pytest.raises(ValidationError) as exc_info:
        statement1 = EcsFileStatementModel(
            sid="test_sid", resources=["*"], actions=["*"], effect="allow"
        )
        statement2 = EcsFileStatementModel(
            sid="test_sid", resources=["*"], actions=["*"], effect="allow"
        )
        role = EcsFileRoleModel(
            managed_policies=[], statements=[statement1, statement2]
        )
        EcsFileModel(
            metadata=EcsFileMetadataModel(appname="test_app"),
            role=role,
            execution_role=role,
            task_definition=EcsTaskDefinitionModel(
                resources=EcsFileResourcesModel(
                    limits=EcsFileLimitsModel(cpu=1024, memory=2048)
                ),
                containers=[],
            ),
        )
    error_message = exc_info.value.errors()[0]["msg"]
    assert "Duplicate sid" in error_message


def test_single_tty_validation():
    with pytest.raises(ValidationError) as exc_info:
        container1 = EcsFileContainerModel(
            name="container1",
            image="image1",
            user="root",
            tty=True,
            resources=EcsFileResourcesModel(
                limits=EcsFileLimitsModel(cpu=1024, memory=2048)
            ),
        )
        container2 = EcsFileContainerModel(
            name="container2",
            image="image2",
            user="root",
            tty=True,
            resources=EcsFileResourcesModel(
                limits=EcsFileLimitsModel(cpu=1024, memory=2048)
            ),
        )
        task_definition = EcsTaskDefinitionModel(
            resources=EcsFileResourcesModel(
                limits=EcsFileLimitsModel(cpu=1024, memory=2048)
            ),
            containers=[container1, container2],
        )
        EcsFileModel(
            metadata=EcsFileMetadataModel(appname="test_app"),
            role=EcsFileRoleModel(managed_policies=[], statements=[]),
            execution_role=EcsFileRoleModel(managed_policies=[], statements=[]),
            task_definition=task_definition,
        )
    error_message = exc_info.value.errors()[0]["msg"]
    assert "More than one container has tty set to true" in error_message


@pytest.mark.parametrize(
    "test_input,expected",
    [
        (
            "arn:aws:sqs:us-east-1:123456789012:XYZ",
            ValidationError,
        ),
        (
            "arn:aws:iam::123456789012:role/S3Access",
            "arn:aws:iam::123456789012:role/S3Access",
        ),
        (
            "arn:aws:iam::123456789012:role/{{.USER}}",
            "arn:aws:iam::123456789012:role/" + os.getenv("USER"),
        ),
    ],
)
def test_arn_validation(test_input: str, expected: Union[str, ValidationError]):
    if expected == ValidationError:
        with pytest.raises(expected) as exc_info:
            EcsFileRoleModel(arn=test_input)
        error_message = exc_info.value.errors()[0]["msg"]
        assert (
            "Role ARN does not respect arn pattern" in error_message
        ), f"Expected: {expected}, Got: {error_message}"
    else:
        fm = EcsFileRoleModel(arn=test_input)
        assert fm.arn == expected, f"Expected: {expected}, Got: {fm.arn}"
