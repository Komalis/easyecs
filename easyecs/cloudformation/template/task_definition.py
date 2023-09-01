def create_task_definition(
    stack, service_name, task_role, execution_role, log_group, ecs_data, run=False
):
    from aws_cdk.aws_ecs import (
        LogDriver,
    )

    # Create task definition
    task_definition = create_fargate_task_definition(
        stack, service_name, task_role, execution_role, ecs_data
    )

    # Add EFS volumes to task definition
    add_volumes_to_task_definition(task_definition, ecs_data)

    # Configure logging for containers
    log_configuration = LogDriver.aws_logs(stream_prefix="ecs", log_group=log_group)

    # Add containers to task definition
    dict_container_definitions = add_containers_to_task_definition(
        stack, task_definition, ecs_data, log_configuration, run
    )

    # Add dependencies between containers
    add_container_dependencies(dict_container_definitions)

    return task_definition


def create_fargate_task_definition(
    stack, service_name, task_role, execution_role, ecs_data
):
    from aws_cdk.aws_ecs import (
        FargateTaskDefinition,
    )

    """Create a Fargate task definition."""
    task_definition_name = f"{service_name}-task-definition"
    resource_limits = ecs_data.task_definition.resources.limits
    cpu_limit = resource_limits.cpu * 1024
    memory_limit = resource_limits.memory

    return FargateTaskDefinition(
        stack,
        task_definition_name,
        task_role=task_role,
        execution_role=execution_role,
        cpu=cpu_limit,
        memory_limit_mib=memory_limit,
    )


def add_volumes_to_task_definition(task_definition, ecs_data):
    from aws_cdk.aws_ecs import (
        EfsVolumeConfiguration,
    )

    """Add EFS volumes to the task definition."""
    for volume in ecs_data.task_definition.efs_volumes:
        efs_volume_configuration = EfsVolumeConfiguration(file_system_id=volume.id)
        task_definition.add_volume(
            name=volume.name, efs_volume_configuration=efs_volume_configuration
        )


def add_containers_to_task_definition(
    stack, task_definition, ecs_data, log_configuration, run
):
    """Add containers to the task definition."""
    container_definitions = ecs_data.task_definition.containers
    dict_container_definitions = {}

    for container_definition in container_definitions:
        container_config = extract_container_config(
            stack, container_definition, log_configuration, run
        )
        container = task_definition.add_container(**container_config)
        add_mount_points_to_container(container, container_definition.efs_volumes)
        dict_container_definitions[container_definition.name] = {
            "container": container,
            "container_definition": container_definition,
        }

    return dict_container_definitions


def extract_container_config(stack, container_definition, log_configuration, run):
    from aws_cdk.aws_ecs import (
        ContainerImage,
    )

    """Extract container configuration from its definition."""
    name = container_definition.name
    image = container_definition.image
    user = container_definition.user
    essential = container_definition.essential
    resource_limits = container_definition.resources.limits
    tty = container_definition.tty
    cpu = resource_limits.cpu * 1024
    memory = resource_limits.memory
    entry_point = split_if_str(container_definition.entry_point)
    command = split_if_str(container_definition.command)

    if tty and not run:
        command = ["sleep", "infinity"]

    environment = {
        env_definition.name: env_definition.value
        for env_definition in container_definition.env
        if env_definition.active
    }

    secrets = extract_secrets(stack, container_definition.secrets, name)

    health_check = extract_health_check(container_definition.healthcheck)

    return {
        "id": name,
        "container_name": name,
        "image": ContainerImage.from_registry(image),
        "command": command,
        "logging": log_configuration,
        "environment": environment,
        "secrets": secrets,
        "cpu": cpu,
        "memory_limit_mib": memory,
        "user": user,
        "entry_point": entry_point,
        "health_check": health_check,
        "essential": essential,
    }


def split_if_str(value):
    """Split the value if it's a string."""
    return value.split(" ") if isinstance(value, str) else value


def extract_secrets(stack, secret_definitions, container_name):
    from aws_cdk.aws_secretsmanager import Secret
    from aws_cdk.aws_ecs import (
        Secret as ECSSecret,
    )

    """Extract container secrets from its definition."""
    secrets = {}
    for secret_definition in secret_definitions:
        secret_name = secret_definition.name
        secret = Secret.from_secret_complete_arn(
            stack, f"{secret_name}_{container_name}", secret_definition.arn
        )
        ecs_secret = ECSSecret.from_secrets_manager(secret, secret_definition.field)
        secrets[secret_name] = ecs_secret
    return secrets


def extract_health_check(raw_healthcheck):
    from aws_cdk.aws_ecs import (
        HealthCheck,
    )
    from aws_cdk import Duration

    """Extract health check from container definition."""
    if not raw_healthcheck:
        return None

    healthcheck_command = split_if_str(raw_healthcheck.command)

    return HealthCheck(
        command=healthcheck_command,
        interval=Duration.seconds(raw_healthcheck.interval),
        retries=raw_healthcheck.retries,
        start_period=Duration.seconds(raw_healthcheck.start_period),
        timeout=Duration.seconds(raw_healthcheck.timeout),
    )


def add_mount_points_to_container(container, volumes):
    from aws_cdk.aws_ecs import (
        MountPoint,
    )

    """Add mount points to a container."""
    for volume in volumes:
        mount_point = MountPoint(
            container_path=volume.mount_point,
            read_only=False,
            source_volume=volume.name,
        )
        container.add_mount_points(mount_point)


def add_container_dependencies(dict_container_definitions):
    from aws_cdk.aws_ecs import (
        ContainerDependency,
    )

    """Add dependencies between containers."""
    for dict_container in dict_container_definitions.values():
        container = dict_container["container"]
        container_definition = dict_container["container_definition"]

        if container_definition.depends_on:
            for key, value in container_definition.depends_on.items():
                dependency_container = dict_container_definitions[key]["container"]
                container_dependency_condition = map_dependency_condition(
                    value["condition"]
                )
                container_dependency = ContainerDependency(
                    container=dependency_container,
                    condition=container_dependency_condition,
                )
                container.add_container_dependencies(container_dependency)


def map_dependency_condition(condition_str):
    from aws_cdk.aws_ecs import ContainerDependencyCondition

    """Map a dependency condition to the appropriate AWS CDK condition."""
    if condition_str == "service_completed_successfully":
        return ContainerDependencyCondition.COMPLETE
    elif condition_str == "service_healthy":
        return ContainerDependencyCondition.HEALTHY
    else:
        raise ValueError(f"Unrecognized dependency condition: {condition_str}")
