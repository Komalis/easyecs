from unittest.mock import MagicMock

from easyecs.docker import docker_build_cmd


def test_docker_command():
    build = MagicMock()
    build.dockerfile = "Dockerfile.dev"
    build.target = "dev"
    build.args = {"ARG1": "VALUE1", "ARG2": "VALUE2"}
    image_name = "test_image"

    expected_command = (
        "docker buildx build -t test_image -f Dockerfile.dev --target dev --build-arg"
        ' ARG1="VALUE1" --build-arg ARG2="VALUE2" --platform=linux/amd64 .'
    )
    assert docker_build_cmd(build, image_name) == expected_command


def test_docker_command_without_target():
    build = MagicMock()
    build.dockerfile = "Dockerfile.dev"
    build.target = None
    build.args = {"ARG1": "VALUE1", "ARG2": "VALUE2"}
    image_name = "test_image"

    # Test when target is not specified
    build.target = None
    expected_command = (
        'docker buildx build -t test_image -f Dockerfile.dev --build-arg ARG1="VALUE1"'
        ' --build-arg ARG2="VALUE2" --platform=linux/amd64 .'
    )
    assert docker_build_cmd(build, image_name) == expected_command


def test_docker_command_without_dockerfile():
    build = MagicMock()
    build.dockerfile = None
    build.target = "dev"
    build.args = {"ARG1": "VALUE1", "ARG2": "VALUE2"}
    image_name = "test_image"

    expected_command = (
        'docker buildx build -t test_image --target dev --build-arg ARG1="VALUE1" --build-arg'
        ' ARG2="VALUE2" --platform=linux/amd64 .'
    )
    assert docker_build_cmd(build, image_name) == expected_command


def test_docker_command_without_args():
    build = MagicMock()
    build.dockerfile = "Dockerfile.dev"
    build.args = {}
    build.target = "dev"
    image_name = "test_image"

    expected_command = "docker buildx build -t test_image -f Dockerfile.dev --target dev --platform=linux/amd64 ."
    assert docker_build_cmd(build, image_name) == expected_command
