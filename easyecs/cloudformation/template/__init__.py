from easyecs.cloudformation.template.task_definition import create_task_definition


def create_template(
    service_name,
    aws_account_id,
    aws_region,
    vpc_id,
    subnet_ids,
    azs,
    ecs_manifest,
    run=False,
):
    from aws_cdk import App, BootstraplessSynthesizer, Environment, Stack
    from aws_cdk.aws_ec2 import Subnet, SubnetSelection, Vpc

    app = App(outdir="./.cloudformation")
    bootstrapless_synthesizer = BootstraplessSynthesizer()
    stack = Stack(
        app,
        service_name,
        synthesizer=bootstrapless_synthesizer,
        env=Environment(account=aws_account_id, region=aws_region),
    )

    vpc = Vpc.from_vpc_attributes(stack, "vpc", vpc_id=vpc_id, availability_zones=azs)

    subnets = [
        Subnet.from_subnet_id(stack, id=f"container_{i}", subnet_id=subnet_id)
        for i, subnet_id in enumerate(subnet_ids)
    ]

    subnet_selection = SubnetSelection(subnets=subnets)
    task_role = create_task_role(stack, service_name, ecs_manifest)
    execution_task_role = create_execution_task_role(stack, service_name, ecs_manifest)
    ecs_cluster = create_ecs_cluster(stack, service_name, vpc)
    log_group = create_log_group(stack, service_name)
    sg = create_security_group(stack, service_name, vpc)
    task_definition = create_task_definition(
        stack,
        service_name,
        task_role,
        execution_task_role,
        log_group,
        ecs_manifest,
        run,
    )
    create_ecs_service(
        stack, service_name, ecs_cluster, task_definition, subnet_selection, sg
    )

    app.synth()


def create_task_role(stack, service_name, ecs_manifest):
    from aws_cdk.aws_iam import (
        Effect,
        ManagedPolicy,
        PolicyDocument,
        PolicyStatement,
        ServicePrincipal,
        Role,
    )

    if ecs_manifest.role.arn:
        return Role.from_role_arn(
            scope=stack, id=ecs_manifest.role.arn, role_arn=ecs_manifest.role.arn
        )
    else:
        role_name = f"{service_name}-task-role"
        policy_name = f"{service_name}-task-role-policy"
        assumed_by = ServicePrincipal("ecs-tasks.amazonaws.com")
        managed_policies_raw = ecs_manifest.role.managed_policies
        managed_policies = [
            ManagedPolicy.from_aws_managed_policy_name(managed_policy)
            for managed_policy in managed_policies_raw
        ]
        policy_statements_raw = ecs_manifest.role.statements
        policy_statements = [
            PolicyStatement(
                sid=policy_statement.sid,
                actions=policy_statement.actions,
                resources=policy_statement.resources,
                effect=(
                    Effect.ALLOW if policy_statement.effect == "Allow" else Effect.DENY
                ),
            )
            for policy_statement in policy_statements_raw
        ]
        inline_policies = PolicyDocument(statements=policy_statements)
        role: Role = Role(
            stack,
            role_name,
            assumed_by=assumed_by,
            inline_policies={policy_name: inline_policies},
            managed_policies=managed_policies,
        )
        role.without_policy_updates()
        return role


def create_execution_task_role(stack, service_name, ecs_manifest):
    from aws_cdk.aws_iam import (
        Effect,
        ManagedPolicy,
        PolicyDocument,
        PolicyStatement,
        ServicePrincipal,
        Role,
    )

    if ecs_manifest.execution_role.arn:
        return Role.from_role_arn(
            scope=stack,
            id=ecs_manifest.execution_role.arn,
            role_arn=ecs_manifest.execution_role.arn,
        )
    else:
        role_name = f"{service_name}-execution-task-role"
        policy_name = f"{service_name}-execution-task-role-policy"
        assumed_by = ServicePrincipal("ecs-tasks.amazonaws.com")
        managed_policies_raw = ecs_manifest.execution_role.managed_policies
        managed_policies = [
            ManagedPolicy.from_aws_managed_policy_name(managed_policy)
            for managed_policy in managed_policies_raw
        ]
        policy_statements_raw = ecs_manifest.execution_role.statements
        policy_statements = [
            PolicyStatement(
                sid=policy_statement.sid,
                actions=policy_statement.actions,
                resources=policy_statement.resources,
                effect=(
                    Effect.ALLOW if policy_statement.effect == "Allow" else Effect.DENY
                ),
            )
            for policy_statement in policy_statements_raw
        ]
        inline_policies = PolicyDocument(statements=policy_statements)
        role: Role = Role(
            stack,
            role_name,
            assumed_by=assumed_by,
            inline_policies={policy_name: inline_policies},
            managed_policies=managed_policies,
        )
        role.without_policy_updates()
        return role


def create_ecs_cluster(stack, service_name, vpc):
    from aws_cdk.aws_ecs import Cluster

    cluster_name = f"{service_name}-cluster"
    return Cluster(stack, cluster_name, cluster_name=cluster_name, vpc=vpc)


def create_log_group(stack, service_name):
    from aws_cdk.aws_logs import LogGroup

    log_group_name = f"{service_name}-log"
    return LogGroup(stack, log_group_name)


def create_security_group(stack, service_name, vpc):
    from aws_cdk.aws_ec2 import ISecurityGroup, SecurityGroup

    sg_name = f"{service_name}-sg"
    sg: ISecurityGroup = SecurityGroup(stack, sg_name, vpc=vpc, allow_all_outbound=True)
    return sg


def create_ecs_service(
    stack, service_name, cluster, task_definition, subnets, security_group
):
    from aws_cdk.aws_ecs import FargateService

    service_name = f"{service_name}-service"
    return FargateService(
        stack,
        service_name,
        service_name=service_name,
        cluster=cluster,
        task_definition=task_definition,
        vpc_subnets=subnets,
        security_groups=[security_group],
        enable_execute_command=True,
        min_healthy_percent=0,
    )
