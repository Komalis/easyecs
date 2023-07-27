from easyecs.helpers.color import Color


def verify_ecs_manifest(ecs_manifest):
    verify_tty(ecs_manifest)


def verify_tty(ecs_manifest):
    containers = ecs_manifest["task_definition"]["containers"]
    tty = 0
    for container in containers:
        tty += 1 if container.get("tty", False) else 0
    if tty > 1:
        print(
            f"{Color.RED}Error parsing ecs.yml, you can activate tty flag for one"
            f" container only{Color.END}"
        )
        exit(-1)
