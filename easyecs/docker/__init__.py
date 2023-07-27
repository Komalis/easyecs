import subprocess
from easyecs.helpers.common import parse_dict_with_env_var


def build_docker_image(ecs_manifest):
    containers = ecs_manifest["task_definition"]["containers"]
    for container in containers:
        image_name = container.get("image")
        build = container.get("build", None)
        if build:
            dockerfile = build.get("dockerfile", "Dockerfile")
            if dockerfile:
                dockerfile = f"-f {dockerfile}"
            target = build.get("target", None)
            if target:
                target = f"--target {target}"
            build_args = build.get("args", {})
            build_args = parse_dict_with_env_var(build_args)
            build_args_str = " ".join(
                [f'--build-arg {key}="{value}"' for key, value in build_args.items()]
            )
            build_cmd = (
                f"docker build -t {image_name} {dockerfile} {target} {build_args_str} ."
            )
            res = subprocess.Popen(
                build_cmd,
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            res.wait()
            if res.poll() != 0:
                raise Exception("There was an issue building the docker image")
            push_docker_image(image_name)


def push_docker_image(image_name):
    push_cmd = f"docker push {image_name}"
    res = subprocess.Popen(
        push_cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    res.wait()
