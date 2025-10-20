#!python

from importlib.metadata import version
from dataclasses import dataclass
from signal import SIGINT
import time
from typing import Callable
import click
from easyecs.cloudformation.stack.create import create_stack
from easyecs.cloudformation.stack.delete import delete_stack
from easyecs.cloudformation.stack.update import update_stack
from easyecs.cloudformation.template import create_template
from easyecs.cloudformation.fetch import (
    fetch_aws_account,
    fetch_containers,
    fetch_is_stack_created,
    fetch_load_balancer_dns,
)
from easyecs.command import (
    run_nc_commands,
    create_port_forwards,
    execute_command,
    popen_procs_port_forward,
    popen_procs_exec_command,
    run_sftp_commands,
    threads,
    event_handlers,
)
from easyecs.docker import build_docker_image
from easyecs.helpers.color import Color
from easyecs.helpers.common import check_credentials
from easyecs.helpers.loader import Loader

from easyecs.helpers.settings import (
    compute_hash_ecs_file,
    delete_hash,
    ecs_file_to_yaml,
    load_settings,
    read_ecs_file,
    save_hash,
)


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


@dataclass(frozen=True)
class Options:
    no_docker_build: Callable = click.option(
        "--no-docker-build",
        is_flag=True,
        default=False,
        show_default=True,
        help=(
            "If used, easyecs will not build and push docker image of containers if"
            " there is one to build."
        ),
    )
    force_redeployment: Callable = click.option(
        "--force-redeployment",
        is_flag=True,
        default=False,
        show_default=True,
        help=(
            "If used, and only when there's no update on the cloudformation stack,"
            " easyecs will force a new deployment of the task."
        ),
    )
    show_docker_logs: Callable = click.option(
        "--show-docker-logs",
        is_flag=True,
        default=False,
        show_default=True,
        help="If used, it will show the docker build and push logs",
    )

    auto_install_nc: Callable = click.option(
        "--auto-install-nc",
        is_flag=True,
        default=False,
        show_default=True,
        help="If used, it will automatically install nc on the container",
    )
    auto_install_sftp: Callable = click.option(
        "--auto-install-sftp",
        is_flag=True,
        default=False,
        show_default=True,
        help="If used, it will automatically install sftp on the container",
    )
    file_name: Callable = click.option(
        "--file-name",
        default="ecs.yml",
        help="Name of the file in current directory to be used for easyecs",
    )


options = Options()


def step_docker_build_and_push(
    no_docker_build,
    ecs_manifest,
    stack_name,
    aws_account_id,
    aws_region,
    vpc_id,
    subnet_ids,
    azs,
    show_docker_logs,
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
        build_docker_image(ecs_manifest, show_docker_logs)
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
        popen_proc.send_signal(SIGINT)
        popen_proc.wait()

    for thread in threads:
        thread.stop()
        thread.join()

    for popen_proc in popen_procs_exec_command:
        popen_proc.stdin.write("exit\x03\x04".encode("utf8"))
        popen_proc.stdin.flush()
        popen_proc.wait()


def has_ecs_file_changed(cache_settings, file_name: str):
    hash_sha256 = compute_hash_ecs_file(file_name)
    return hash_sha256 != cache_settings["sha256"]


def step_bring_up_stack(
    cache_settings,
    no_docker_build,
    ecs_manifest,
    stack_name,
    aws_account_id,
    aws_region,
    vpc_id,
    subnet_ids,
    azs,
    force_redeployment,
    aws_account,
    show_docker_logs,
    run,
    file_name,
):
    print()
    if has_ecs_file_changed(cache_settings, file_name) or force_redeployment:
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
            show_docker_logs,
            run,
        )
        step_create_or_update_stack(stack_name, force_redeployment)
        save_hash(aws_account, file_name)
    else:
        print(f"{Color.YELLOW}No updates are to be performed.{Color.END}")


def action_run(
    file_name: str = "ecs.yml",
    no_docker_build: bool = False,
    force_redeployment: bool = False,
    show_docker_logs: bool = False,
):
    aws_account = fetch_aws_account()
    cache_settings = load_settings(aws_account)
    ecs_manifest = read_ecs_file(file_name)
    app_name = ecs_manifest.metadata.appname
    user = ecs_manifest.metadata.user
    aws_region = cache_settings["aws_region"]
    aws_account_id = cache_settings["aws_account_id"]
    vpc_id = cache_settings["vpc_id"]
    subnet_ids = cache_settings["subnet_ids"]
    azs = cache_settings["azs"]
    stack_name = f"{user}-{app_name}"

    step_bring_up_stack(
        cache_settings,
        no_docker_build,
        ecs_manifest,
        stack_name,
        aws_account_id,
        aws_region,
        vpc_id,
        subnet_ids,
        azs,
        force_redeployment,
        aws_account,
        show_docker_logs,
        run=True,
        file_name=file_name,
    )
    parsed_containers = fetch_containers(user, app_name)
    print()
    create_port_forwards(ecs_manifest, aws_region, aws_account, parsed_containers)
    step_idle_keyboard()

    step_clean_exit()

    exit(0)


def action_dev(
    file_name: str = "ecs.yml",
    no_docker_build: bool = False,
    force_redeployment: bool = False,
    show_docker_logs: bool = False,
    auto_install_nc: bool = False,
    auto_install_sftp: bool = False,
):
    aws_account = fetch_aws_account()
    cache_settings = load_settings(aws_account)
    ecs_manifest = read_ecs_file(file_name)
    app_name = ecs_manifest.metadata.appname
    user = ecs_manifest.metadata.user
    auto_install_override = ecs_manifest.auto_install_override
    aws_region = cache_settings["aws_region"]
    aws_account_id = cache_settings["aws_account_id"]
    vpc_id = cache_settings["vpc_id"]
    subnet_ids = cache_settings["subnet_ids"]
    azs = cache_settings["azs"]
    stack_name = f"{user}-{app_name}"

    step_bring_up_stack(
        cache_settings,
        no_docker_build,
        ecs_manifest,
        stack_name,
        aws_account_id,
        aws_region,
        vpc_id,
        subnet_ids,
        azs,
        force_redeployment,
        aws_account,
        show_docker_logs,
        run=False,
        file_name=file_name,
    )
    if ecs_manifest.load_balancer:
        load_balancer_port = ecs_manifest.load_balancer.listener_port
        load_balancer_dns = fetch_load_balancer_dns(stack_name)
        print()
        print(
            "Your service is accessible on this URL:"
            f" http://{load_balancer_dns}:{load_balancer_port}"
        )
    parsed_containers = fetch_containers(user, app_name)
    print()
    create_port_forwards(ecs_manifest, aws_region, aws_account, parsed_containers)
    if ecs_manifest.copy_method == "nc":
        run_nc_commands(
            parsed_containers, aws_region, aws_account, ecs_manifest, auto_install_nc
        )
    elif ecs_manifest.copy_method == "sftp":
        run_sftp_commands(
            parsed_containers,
            aws_region,
            aws_account,
            ecs_manifest,
            auto_install_sftp,
            auto_install_override,
        )
    print()

    for event_handler in event_handlers:
        event_handler.synchronize()
        time.sleep(0.1)

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


def action_delete(file_name: str):
    aws_account = fetch_aws_account()
    ecs_manifest = read_ecs_file(file_name)
    app_name = ecs_manifest.metadata.appname
    user = ecs_manifest.metadata.user
    stack_name = f"{user}-{app_name}"
    delete_stack(stack_name)
    delete_hash(aws_account)


@click.group()
@click.pass_context
def entrypoint(ctx):
    ctx.ensure_object(dict)
    check_credentials()


@entrypoint.command(name="run", help="Run a stack")
@options.no_docker_build
@options.force_redeployment
@options.show_docker_logs
@options.file_name
def click_run(
    no_docker_build: bool,
    force_redeployment: bool,
    show_docker_logs: bool,
    file_name: str,
):
    action_run(file_name, no_docker_build, force_redeployment, show_docker_logs)


@entrypoint.command(name="dev", help="Run a stack in development mode")
@options.no_docker_build
@options.force_redeployment
@options.show_docker_logs
@options.auto_install_nc
@options.auto_install_sftp
@options.file_name
def click_dev(
    no_docker_build: bool,
    force_redeployment: bool,
    show_docker_logs: bool,
    auto_install_nc: bool,
    auto_install_sftp: bool,
    file_name: str,
):
    action_dev(
        file_name,
        no_docker_build,
        force_redeployment,
        show_docker_logs,
        auto_install_nc,
        auto_install_sftp,
    )


@entrypoint.command(name="delete", help="Delete a stack")
@options.file_name
def click_delete(file_name: str):
    action_delete(file_name)


@entrypoint.command(name="version", help="Echo the version of EasyECS")
def click_version() -> None:
    print(version("easyecs"))


@entrypoint.command(name="render", help="Show a rendered ecs file")
@options.file_name
def click_render(file_name: str) -> None:
    print(ecs_file_to_yaml(file_name))


if __name__ == "__main__":
    entrypoint()
