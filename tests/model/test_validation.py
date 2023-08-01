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
