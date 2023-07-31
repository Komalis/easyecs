#!python

import time
import inotify.adapters
import boto3
import click
from easyecs.cloudformation.template import create_template
from easyecs.cloudformation.fetch import (
    fetch_containers,
    fetch_is_stack_created,
)
from easyecs.cloudformation.stack import (
    create_stack,
    delete_stack,
    update_stack,
)
from easyecs.cloudformation.template.verify import verify_ecs_manifest
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


def action_run(no_docker_build, force_redeployment):
    aws_account = boto3.client("iam").list_account_aliases()["AccountAliases"][0]
    cache_settings = load_settings(aws_account)
    aws_region = cache_settings["aws_region"]
    aws_account_id = cache_settings["aws_account_id"]
    vpc_id = cache_settings["vpc_id"]
    subnet_ids = cache_settings["subnet_ids"]
    azs = cache_settings["azs"]

    ecs_manifest = read_ecs_file()
    app_name = ecs_manifest.metadata.appname
    user = ecs_manifest.metadata.user
    stack_name = f"{user}-{app_name}"

    verify_ecs_manifest(ecs_manifest)

    print()

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
        run=True,
    )
    loader.stop()

    if not fetch_is_stack_created(stack_name):
        create_stack(stack_name)
    else:
        update_stack(stack_name, force_redeployment)

    print()

    parsed_containers = fetch_containers(user, app_name)

    create_port_forwards(ecs_manifest, aws_region, aws_account, parsed_containers)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Quitting...")
        pass

    for popen_proc in popen_procs_port_forward:
        popen_proc.kill()

    for thread in threads:
        thread.stop()

    exit(0)


def action_dev(no_docker_build, force_redeployment):
    aws_account = boto3.client("iam").list_account_aliases()["AccountAliases"][0]
    cache_settings = load_settings(aws_account)
    aws_region = cache_settings["aws_region"]
    aws_account_id = cache_settings["aws_account_id"]
    vpc_id = cache_settings["vpc_id"]
    subnet_ids = cache_settings["subnet_ids"]
    azs = cache_settings["azs"]

    ecs_manifest = read_ecs_file()
    app_name = ecs_manifest.metadata.appname
    user = ecs_manifest.metadata.user
    stack_name = f"{user}-{app_name}"

    verify_ecs_manifest(ecs_manifest)

    print()

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
    )
    loader.stop()

    if not fetch_is_stack_created(stack_name):
        create_stack(stack_name)
    else:
        update_stack(stack_name, force_redeployment)

    print()

    parsed_containers = fetch_containers(user, app_name)

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
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("Quitting...")
            pass

    for popen_proc in popen_procs_port_forward:
        popen_proc.kill()

    for popen_proc in popen_procs_exec_command:
        popen_proc.stdin.write("exit\x03\x04".encode("utf8"))
        popen_proc.stdin.flush()
        popen_proc.wait()

    for thread in threads:
        thread.stop()

    exit(0)


def action_delete():
    ecs_manifest = read_ecs_file()
    app_name = ecs_manifest.metadata.appname
    user = ecs_manifest.metadata.user
    stack_name = f"{user}-{app_name}"
    delete_stack(stack_name)


def action_debug():
    sync_events = set(["IN_CLOSE_WRITE"])
    i = inotify.adapters.Inotify()
    i.add_watch(".")
    for event in i.event_gen(yield_nones=False):
        (_, type_names, path, filename) = event
        if set(type_names).issubset(sync_events):
            print(
                "PATH=[{}] FILENAME=[{}] EVENT_TYPES={}".format(
                    path, filename, type_names
                )
            )


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
    action_run(no_docker_build, force_redeployment)


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
    action_dev(no_docker_build, force_redeployment)


@entrypoint.command(name="delete", help="Delete a stack")
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
def click_delete(ctx, force_redeployment):
    action_delete()


if __name__ == "__main__":
    entrypoint()
