from easyecs.cloudformation.template.task_definition import create_task_definition
from easyecs.model.ecs import EcsFileModel


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
    listener = None
    lb_security_group = None

    subnet_selection = SubnetSelection(subnets=subnets)
    if ecs_manifest.load_balancer:
        listener, lb_security_group = create_load_balancer(stack, ecs_manifest, vpc)
    task_role = create_task_role(stack, service_name, ecs_manifest)
    execution_task_role = create_execution_task_role(stack, service_name, ecs_manifest)
    ecs_cluster = create_ecs_cluster(stack, service_name, vpc)
    log_group = create_log_group(stack, service_name)
    sg = create_security_group(
        stack,
        service_name,
        vpc,
        ecs_manifest,
        lb_security_group,
        ecs_manifest.security_group_id,
    )
    task_definition = create_task_definition(
        stack,
        service_name,
        task_role,
        execution_task_role,
        log_group,
        ecs_manifest,
        run,
    )
    service = create_ecs_service(
        stack, service_name, ecs_cluster, task_definition, subnet_selection, sg
    )
    if ecs_manifest.load_balancer and listener is not None:
        from aws_cdk import Duration

        add_targets_kwargs = {
            "port": ecs_manifest.load_balancer.target_group_port,
            "targets": [service],
        }

        if isinstance(ecs_manifest.load_balancer.idle_timeout, int):
            add_targets_kwargs["deregistration_delay"] = Duration.seconds(
                ecs_manifest.load_balancer.idle_timeout
            )

        listener.add_targets("NlbTarget", **add_targets_kwargs)

    if ecs_manifest.metadata.auto_destruction is not None:
        assert isinstance(
            ecs_manifest.metadata.auto_destruction, int
        ), "auto_destruction must be an Integer (minutes)"
        create_autodestroy(stack, ecs_manifest.metadata.auto_destruction)

    app.synth()


def create_load_balancer(stack, ecs_manifest: EcsFileModel, vpc):
    from aws_cdk.aws_ec2 import SecurityGroup, Peer, Port, Subnet, SubnetSelection
    from aws_cdk.aws_elasticloadbalancingv2 import NetworkLoadBalancer

    if ecs_manifest.load_balancer:
        if ecs_manifest.load_balancer.security_group_id:
            lb_security_group = SecurityGroup.from_security_group_id(
                stack,
                "nlb_security_group",
                security_group_id=ecs_manifest.load_balancer.security_group_id,
                allow_all_outbound=False,
            )
        else:
            lb_security_group = SecurityGroup(
                stack, "nlb_security_group", vpc=vpc, description="NLB Security Group"
            )
        if ecs_manifest.load_balancer.arn:
            lb = NetworkLoadBalancer.from_network_load_balancer_attributes(
                stack, "nlb", load_balancer_arn=ecs_manifest.load_balancer.arn, vpc=vpc
            )
        else:
            subnets = [
                Subnet.from_subnet_id(stack, f"Subnet{i}", subnet_id)
                for i, subnet_id in enumerate(ecs_manifest.load_balancer.subnets)
            ]
            lb = NetworkLoadBalancer(
                stack,
                "nlb",
                vpc=vpc,
                load_balancer_name=ecs_manifest.load_balancer.load_balancer_name,
                internet_facing=False,
                vpc_subnets=SubnetSelection(subnets=subnets),
                security_groups=[lb_security_group],
            )
        if ecs_manifest.load_balancer.security_group_rules:
            if ecs_manifest.load_balancer.security_group_rules.egress:
                for (
                    egress_rule
                ) in ecs_manifest.load_balancer.security_group_rules.egress:
                    if egress_rule.cidr:
                        lb_security_group.add_egress_rule(
                            peer=(
                                Peer.ipv4(egress_rule.cidr)
                                if egress_rule != "0.0.0.0/0"
                                else Peer.any_ipv4()
                            ),
                            connection=(
                                Port.tcp(egress_rule.port)
                                if egress_rule.port != -1
                                else Port.all_traffic()
                            ),
                            description=egress_rule.name,
                        )
                    elif egress_rule.prefix_list:
                        lb_security_group.add_egress_rule(
                            peer=Peer.prefix_list(egress_rule.prefix_list),
                            connection=(
                                Port.tcp(egress_rule.port)
                                if egress_rule.port != -1
                                else Port.all_traffic()
                            ),
                            description=egress_rule.name,
                        )
                    elif egress_rule.security_group_id:
                        lb_security_group.add_egress_rule(
                            peer=SecurityGroup.from_security_group_id(
                                stack,
                                "egress_rule_sg",
                                security_group_id=egress_rule.security_group_id,
                            ),
                            connection=(
                                Port.tcp(egress_rule.port)
                                if egress_rule.port != -1
                                else Port.all_traffic()
                            ),
                            description=egress_rule.name,
                        )
            if ecs_manifest.load_balancer.security_group_rules.ingress:
                for (
                    ingress_rule
                ) in ecs_manifest.load_balancer.security_group_rules.ingress:
                    if ingress_rule.cidr:
                        lb_security_group.add_ingress_rule(
                            peer=(
                                Peer.ipv4(ingress_rule.cidr)
                                if ingress_rule != "0.0.0.0/0"
                                else Peer.any_ipv4()
                            ),
                            connection=(
                                Port.tcp(ingress_rule.port)
                                if ingress_rule.port != -1
                                else Port.all_traffic()
                            ),
                            description=ingress_rule.name,
                        )
                    elif ingress_rule.prefix_list:
                        lb_security_group.add_ingress_rule(
                            peer=Peer.prefix_list(ingress_rule.prefix_list),
                            connection=(
                                Port.tcp(ingress_rule.port)
                                if ingress_rule.port != -1
                                else Port.all_traffic()
                            ),
                            description=ingress_rule.name,
                        )
                    elif ingress_rule.security_group_id:
                        lb_security_group.add_ingress_rule(
                            peer=SecurityGroup.from_security_group_id(
                                stack,
                                "ingress_rule_sg",
                                security_group_id=ingress_rule.security_group_id,
                            ),
                            connection=(
                                Port.tcp(ingress_rule.port)
                                if ingress_rule.port != -1
                                else Port.all_traffic()
                            ),
                            description=ingress_rule.name,
                        )
        listener = lb.add_listener(
            "NlbListener", port=ecs_manifest.load_balancer.listener_port
        )
        return listener, lb_security_group


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


def create_security_group(
    stack,
    service_name,
    vpc,
    ecs_manifest,
    lb_security_group,
    security_group_id: str = None,
):
    from aws_cdk.aws_ec2 import ISecurityGroup, SecurityGroup, Port

    sg_name = f"{service_name}-sg"
    if security_group_id:
        sg = SecurityGroup.from_security_group_id(
            stack, sg_name, security_group_id=security_group_id
        )
    else:
        sg: ISecurityGroup = SecurityGroup(
            stack, sg_name, vpc=vpc, allow_all_outbound=True
        )
    if ecs_manifest.load_balancer:
        sg.add_ingress_rule(
            peer=lb_security_group,
            connection=Port.tcp(ecs_manifest.load_balancer.target_group_port),
            description="Allow Port from Load Balancer",
        )
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


def create_autodestroy(stack, deployment_timeout: int):
    from pathlib import Path
    from aws_cdk.aws_events import Rule, Schedule
    from aws_cdk.aws_events_targets import LambdaFunction
    from aws_cdk.aws_iam import PolicyStatement
    from aws_cdk import aws_lambda, Duration

    lambdaDeleteStackPolicy = PolicyStatement(
        actions=["cloudformation:DeleteStack", "lambda:RemovePermission"],
        resources=["*"],
    )

    lambda_function_file = str(
        Path(__file__).parent.parent / "auto_destruction/harakiri.py"
    )
    harakiri = aws_lambda.Function(
        stack,
        "AutoDestroy",
        code=aws_lambda.Code.from_inline(open(lambda_function_file).read()),
        handler="index.handler",
        timeout=Duration.seconds(300),
        environment={"StackName": stack.artifact_id},
        runtime=aws_lambda.Runtime.PYTHON_3_11,
    )
    harakiri.add_to_role_policy(lambdaDeleteStackPolicy)

    lambda_rule = Rule(
        stack,
        "TimeToDestroy",
        schedule=Schedule.rate(Duration.minutes(deployment_timeout)),
    )
    lambda_rule.add_target(LambdaFunction(handler=harakiri))
