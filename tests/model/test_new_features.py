"""Test new features: ephemeral_storage and idle_timeout"""

import pytest
from pydantic import ValidationError
from easyecs.model.ecs import (
    EcsFileMetadataModel,
    EcsFileRoleModel,
    EcsTaskDefinitionModel,
    EcsFileResourcesModel,
    EcsFileLimitsModel,
    EcsFileContainerModel,
    EcsLoadBalancerModel,
    EcsFileModel,
)


def test_ephemeral_storage_valid():
    """Test valid ephemeral storage values"""
    # Test minimum value
    task_def = EcsTaskDefinitionModel(
        ephemeral_storage=21,
        resources=EcsFileResourcesModel(limits=EcsFileLimitsModel(cpu=1, memory=512)),
        containers=[
            EcsFileContainerModel(
                name="test",
                image="test:latest",
                resources=EcsFileResourcesModel(
                    limits=EcsFileLimitsModel(cpu=1, memory=512)
                ),
            )
        ],
    )
    assert task_def.ephemeral_storage == 21

    # Test maximum value
    task_def = EcsTaskDefinitionModel(
        ephemeral_storage=200,
        resources=EcsFileResourcesModel(limits=EcsFileLimitsModel(cpu=1, memory=512)),
        containers=[
            EcsFileContainerModel(
                name="test",
                image="test:latest",
                resources=EcsFileResourcesModel(
                    limits=EcsFileLimitsModel(cpu=1, memory=512)
                ),
            )
        ],
    )
    assert task_def.ephemeral_storage == 200

    # Test None (default)
    task_def = EcsTaskDefinitionModel(
        resources=EcsFileResourcesModel(limits=EcsFileLimitsModel(cpu=1, memory=512)),
        containers=[
            EcsFileContainerModel(
                name="test",
                image="test:latest",
                resources=EcsFileResourcesModel(
                    limits=EcsFileLimitsModel(cpu=1, memory=512)
                ),
            )
        ],
    )
    assert task_def.ephemeral_storage is None


def test_ephemeral_storage_invalid():
    """Test invalid ephemeral storage values"""
    # Test below minimum
    with pytest.raises(ValidationError, match="between 21 and 200"):
        EcsTaskDefinitionModel(
            ephemeral_storage=20,
            resources=EcsFileResourcesModel(
                limits=EcsFileLimitsModel(cpu=1, memory=512)
            ),
            containers=[
                EcsFileContainerModel(
                    name="test",
                    image="test:latest",
                    resources=EcsFileResourcesModel(
                        limits=EcsFileLimitsModel(cpu=1, memory=512)
                    ),
                )
            ],
        )

    # Test above maximum
    with pytest.raises(ValidationError, match="between 21 and 200"):
        EcsTaskDefinitionModel(
            ephemeral_storage=201,
            resources=EcsFileResourcesModel(
                limits=EcsFileLimitsModel(cpu=1, memory=512)
            ),
            containers=[
                EcsFileContainerModel(
                    name="test",
                    image="test:latest",
                    resources=EcsFileResourcesModel(
                        limits=EcsFileLimitsModel(cpu=1, memory=512)
                    ),
                )
            ],
        )


def test_idle_timeout_valid():
    """Test valid idle timeout values"""
    # Test minimum value
    lb = EcsLoadBalancerModel(
        listener_port=443,
        target_group_port=8080,
        subnets=["subnet-123"],
        idle_timeout=1,
    )
    assert lb.idle_timeout == 1

    # Test maximum value
    lb = EcsLoadBalancerModel(
        listener_port=443,
        target_group_port=8080,
        subnets=["subnet-123"],
        idle_timeout=4000,
    )
    assert lb.idle_timeout == 4000

    # Test None (default)
    lb = EcsLoadBalancerModel(
        listener_port=443, target_group_port=8080, subnets=["subnet-123"]
    )
    assert lb.idle_timeout is None


def test_idle_timeout_invalid():
    """Test invalid idle timeout values"""
    # Test below minimum
    with pytest.raises(ValidationError, match="between 1 and 4000"):
        EcsLoadBalancerModel(
            listener_port=443,
            target_group_port=8080,
            subnets=["subnet-123"],
            idle_timeout=0,
        )

    # Test above maximum
    with pytest.raises(ValidationError, match="between 1 and 4000"):
        EcsLoadBalancerModel(
            listener_port=443,
            target_group_port=8080,
            subnets=["subnet-123"],
            idle_timeout=4001,
        )
