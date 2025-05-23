import subprocess
from easyecs.helpers.common import parse_dict_with_env_var


def docker_build_cmd(build, image_name):
    dockerfile = build.dockerfile
    target = build.target
    if target:
        target = f"--target {target}"
    build_args = build.args
    build_args = parse_dict_with_env_var(build_args)
    build_args_str = " ".join(
        [f'--build-arg {key}="{value}"' for key, value in build_args.items()]
    )

    build_cmd_params = [f"docker buildx build -t {image_name}"]
    build_cmd_params += ["-f", dockerfile] if dockerfile else []
    build_cmd_params += [target] if target else []
    build_cmd_params += [build_args_str] if build_args else []
    build_cmd_params += ["--platform=linux/amd64", build.context]

    build_cmd = " ".join(build_cmd_params)

    return build_cmd


def build_docker_image(ecs_manifest, show_docker_logs):
    containers = ecs_manifest.task_definition.containers
    for container in containers:
        image_name = container.image
        build = container.build
        if build:
            build_cmd = docker_build_cmd(build, image_name)
            if show_docker_logs:
                res = subprocess.Popen(
                    build_cmd,
                    shell=True,
                )
            else:
                res = subprocess.Popen(
                    build_cmd,
                    shell=True,
                    stderr=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                )
            res.wait()
            if res.poll() != 0:
                raise Exception(
                    "There was an issue building the docker image. Use"
                    " --show-docker-logs to get more information!"
                )
            push_docker_image(image_name, show_docker_logs)


def push_docker_image(image_name, show_docker_logs):
    push_cmd = f"docker push {image_name}"
    if show_docker_logs:
        res = subprocess.Popen(push_cmd, shell=True)
    else:
        res = subprocess.Popen(
            push_cmd, shell=True, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL
        )
    res.wait()
    if res.poll() != 0:
        raise Exception(
            "There was an issue pushing the docker image. Use --show-docker-logs to get"
            " more information!"
        )
