#!python

import time
import click
from easyecs.cloudformation.stack.create import create_stack
from easyecs.cloudformation.stack.delete import delete_stack
from easyecs.cloudformation.stack.update import update_stack
from easyecs.cloudformation.template import create_template
from easyecs.cloudformation.fetch import (
    fetch_aws_account,
    fetch_containers,
    fetch_is_stack_created,
)
from easyecs.command import (
    run_nc_commands,
    create_port_forwards,
    execute_command,
    run_sync_thread,
    popen_procs_port_forward,
    popen_procs_exec_command,
    threads,
)
from easyecs.docker import build_docker_image
from easyecs.helpers.common import check_credentials
from easyecs.helpers.loader import Loader

from easyecs.helpers.settings import load_settings, read_ecs_file


def step_import_aws_cdk():
    loader_import = Loader(
        "Importing CloudFormation:",
        "Importing CloudFormation: \u2705",
        "Importing CloudFormation: \u274c",
        0.05,
    )
    loader_import.start()
    # It takes time to import CDK so we show it to the user!
    import aws_cdk  # noqa: F401

    loader_import.stop()


def step_docker_build_and_push(
    no_docker_build,
    ecs_manifest,
    stack_name,
    aws_account_id,
    aws_region,
    vpc_id,
    subnet_ids,
    azs,
    run,
):
    if not no_docker_build:
        loader_docker = Loader(
            "Building and pushing docker images:",
            "Building and pushing docker images: \u2705",
            "Building and pushing docker images: \u274c",
            0.05,
        )
        loader_docker.start()
        build_docker_image(ecs_manifest)
        loader_docker.stop()

    loader = Loader(
        "Creating CloudFormation template:",
        "Creating CloudFormation template: \u2705",
        "Creating CloudFormation template: \u274c",
        0.05,
    )
    loader.start()
    create_template(
        stack_name,
        aws_account_id,
        aws_region,
        vpc_id,
        subnet_ids,
        azs,
        ecs_manifest,
        run,
    )
    loader.stop()


def step_create_or_update_stack(stack_name, force_redeployment):
    if not fetch_is_stack_created(stack_name):
        create_stack(stack_name)
    else:
        update_stack(stack_name, force_redeployment)


def step_idle_keyboard():
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Quitting...")
        pass


def step_clean_exit():
    for popen_proc in popen_procs_port_forward:
        popen_proc.kill()

    for thread in threads:
        thread.stop()

    for popen_proc in popen_procs_exec_command:
        popen_proc.stdin.write("exit\x03\x04".encode("utf8"))
        popen_proc.stdin.flush()
        popen_proc.wait()


def action_run(ctx):
    no_docker_build = ctx.obj["no_docker_build"]
    force_redeployment = ctx.obj["force_redeployment"]
    aws_account = fetch_aws_account()
    cache_settings = load_settings(aws_account)
    ecs_manifest = read_ecs_file()
    app_name = ecs_manifest.metadata.appname
    user = ecs_manifest.metadata.user
    aws_region = cache_settings["aws_region"]
    aws_account_id = cache_settings["aws_account_id"]
    vpc_id = cache_settings["vpc_id"]
    subnet_ids = cache_settings["subnet_ids"]
    azs = cache_settings["azs"]
    stack_name = f"{user}-{app_name}"

    print()
    step_import_aws_cdk()
    step_docker_build_and_push(
        no_docker_build,
        ecs_manifest,
        stack_name,
        aws_account_id,
        aws_region,
        vpc_id,
        subnet_ids,
        azs,
        True,
    )
    step_create_or_update_stack(stack_name, force_redeployment)
    parsed_containers = fetch_containers(user, app_name)
    print()
    create_port_forwards(ecs_manifest, aws_region, aws_account, parsed_containers)
    step_idle_keyboard()

    step_clean_exit()

    exit(0)


def action_dev(ctx):
    no_docker_build = ctx.obj["no_docker_build"]
    force_redeployment = ctx.obj["force_redeployment"]
    aws_account = fetch_aws_account()
    cache_settings = load_settings(aws_account)
    ecs_manifest = read_ecs_file()
    app_name = ecs_manifest.metadata.appname
    user = ecs_manifest.metadata.user
    aws_region = cache_settings["aws_region"]
    aws_account_id = cache_settings["aws_account_id"]
    vpc_id = cache_settings["vpc_id"]
    subnet_ids = cache_settings["subnet_ids"]
    azs = cache_settings["azs"]
    stack_name = f"{user}-{app_name}"

    print()
    step_import_aws_cdk()
    step_docker_build_and_push(
        no_docker_build,
        ecs_manifest,
        stack_name,
        aws_account_id,
        aws_region,
        vpc_id,
        subnet_ids,
        azs,
        False,
    )
    step_create_or_update_stack(stack_name, force_redeployment)
    parsed_containers = fetch_containers(user, app_name)
    print()
    create_port_forwards(ecs_manifest, aws_region, aws_account, parsed_containers)
    run_nc_commands(parsed_containers, aws_region, aws_account, ecs_manifest)
    run_sync_thread(parsed_containers, ecs_manifest)
    print()

    found_tty = execute_command(
        ecs_manifest,
        parsed_containers,
        aws_region,
        aws_account,
    )

    if not found_tty:
        step_idle_keyboard()
    step_clean_exit()
    exit(0)


def action_delete(_):
    ecs_manifest = read_ecs_file()
    app_name = ecs_manifest.metadata.appname
    user = ecs_manifest.metadata.user
    stack_name = f"{user}-{app_name}"
    delete_stack(stack_name)


@click.group()
@click.pass_context
def entrypoint(ctx):
    ctx.ensure_object(dict)
    check_credentials()


@entrypoint.command(name="run", help="Run a stack")
@click.option(
    "--no-docker-build",
    is_flag=True,
    default=False,
    show_default=True,
    help=(
        "If used, easyecs will not build and push docker image of containers if there"
        " is one to build."
    ),
)
@click.option(
    "--force-redeployment",
    is_flag=True,
    default=False,
    show_default=True,
    help=(
        "If used, and only when there's no update on the cloudformation stack, easyecs"
        " will force a new deployment of the task."
    ),
)
@click.pass_context
def click_run(ctx, no_docker_build, force_redeployment):
    ctx.obj["no_docker_build"] = no_docker_build
    ctx.obj["force_redeployment"] = force_redeployment
    action_run(ctx)


@entrypoint.command(name="dev", help="Run a stack in development mode")
@click.option(
    "--no-docker-build",
    is_flag=True,
    default=False,
    show_default=True,
    help=(
        "If used, easyecs will not build and push docker image of containers if there"
        " is one to build."
    ),
)
@click.option(
    "--force-redeployment",
    is_flag=True,
    default=False,
    show_default=True,
    help=(
        "If used, and only when there's no update on the cloudformation stack, easyecs"
        " will force a new deployment of the task."
    ),
)
@click.pass_context
def click_dev(ctx, no_docker_build, force_redeployment):
    ctx.obj["no_docker_build"] = no_docker_build
    ctx.obj["force_redeployment"] = force_redeployment
    action_dev(ctx)


@entrypoint.command(name="delete", help="Delete a stack")
@click.pass_context
def click_delete(ctx):
    action_delete(ctx)


if __name__ == "__main__":
    entrypoint()
