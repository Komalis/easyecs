import os
import re
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, computed_field, field_validator, model_validator
from pathlib import Path

from easyecs.helpers.exceptions import FileNotFoundException


class EcsFileMetadataModel(BaseModel):
    appname: str
    user: str = os.environ["USER"]
    auto_destruction: Optional[int] = None


class EcsFileStatementModel(BaseModel):
    sid: str
    resources: List[str]
    actions: List[str]
    effect: str


class EcsFileRoleModel(BaseModel):
    arn: Optional[str] = None
    managed_policies: List[str] = []
    statements: List[EcsFileStatementModel] = []

    @field_validator("arn")
    def set_arn(cls, arn):
        arn_pattern: str = r"^arn:aws:iam::\d{0,12}:role\/[\w\d_\/.-]*$"
        assert re.match(
            arn_pattern, arn
        ), f"Role ARN does not respect arn pattern : {arn}"
        return arn

    @field_validator("statements")
    def validate_unique_sid(cls, statements):
        seen = set()
        for statement in statements:
            if statement.sid in seen:
                raise ValueError(f"Duplicate sid {statement.sid} found in statements.")
            seen.add(statement.sid)
        return statements


class EcsFileLimitsModel(BaseModel):
    cpu: int
    memory: int


class EcsFileResourcesModel(BaseModel):
    limits: EcsFileLimitsModel


class EcsFileBuildModel(BaseModel):
    dockerfile: str = "Dockerfile"
    target: Optional[str] = None
    args: Dict[str, str] = {}
    context: str = "."


class EcsFileEnvModel(BaseModel):
    name: str
    value: str
    active: bool = True


class EcsFileSecretModel(BaseModel):
    name: str
    arn: str
    field: str
    active: bool = True


class EcsFileSecretModelV2(BaseModel):
    name: str
    valueFrom: str


class EcsFileVolumeModel(BaseModel):
    name: str
    id: str
    mount_point: str

    @field_validator("id")
    def set_id(cls, id):
        assert id.startswith("fs-"), f"EFS ID should start with fs- instead got {id}"
        return id


class EcsFileContainerHealthCheckModel(BaseModel):
    command: Union[List[str], str]
    interval: int
    retries: int
    start_period: int
    timeout: int


class EcsSftpConfig(BaseModel):
    port: int = 2312
    user: str = "root"
    password: str = "root"


class EcsFileContainerModel(BaseModel):
    name: str
    image: str
    user: str = "root"
    tty: bool = False
    essential: bool = True
    entry_point: Union[Optional[str], Optional[List[str]]] = None
    command: Union[Optional[str], Optional[List[str]]] = None
    resources: EcsFileResourcesModel
    build: Optional[EcsFileBuildModel] = None
    port_forward: List[str] = []
    env: List[EcsFileEnvModel] | Dict[str, Any] | None = None
    secrets: List[EcsFileSecretModel] | List[EcsFileSecretModelV2] = []
    efs_volumes: List[EcsFileVolumeModel] = []
    volumes: List[str] = []
    volumes_excludes: List[str] = []
    healthcheck: Optional[EcsFileContainerHealthCheckModel] = None
    depends_on: Optional[Dict[str, Dict[str, str]]] = None
    ports: Optional[List[str]] = []
    sftp_config: EcsSftpConfig = EcsSftpConfig()

    @field_validator("volumes")
    def validate_volumes(cls, volumes):
        resolved_volumes = []
        for volume in volumes:
            _from, _to = volume.split(":")
            if not os.path.exists(_from):
                raise FileNotFoundException(f"{_from} does not exists!")
            resolved_from_dir = Path(_from).parent.resolve()
            resolved_from_file = Path(_from).name
            resolved_volumes.append(f"{resolved_from_dir}/{resolved_from_file}:{_to}")
        return resolved_volumes

    @field_validator("volumes_excludes")
    def validate_volumes_excludes(cls, volumes):
        resolved_volumes = []
        for volume in volumes:
            if not os.path.exists(volume):
                raise FileNotFoundException(f"{volume} does not exists!")
            resolved_from_dir = Path(volume).parent.resolve()
            resolved_from_file = Path(volume).name
            resolved_volumes.append(f"{resolved_from_dir}/{resolved_from_file}")
        return resolved_volumes


class EcsTaskDefinitionModel(BaseModel):
    resources: EcsFileResourcesModel
    containers: List[EcsFileContainerModel]
    ephemeral_storage: Optional[int] = None

    @field_validator("ephemeral_storage")
    def validate_ephemeral_storage(cls, value):
        if value is not None and (value < 21 or value > 200):
            raise ValueError(
                f"Ephemeral storage must be between 21 and 200 GiB, got {value}"
            )
        return value

    @field_validator("containers")
    def validate_single_tty(cls, containers):
        tty_containers = [container.name for container in containers if container.tty]
        if len(tty_containers) > 1:
            raise ValueError(
                "More than one container has tty set to true:"
                f" {', '.join(tty_containers)}."
            )
        return containers

    @computed_field(return_type=List[EcsFileVolumeModel])
    @property
    def efs_volumes(self) -> List[EcsFileVolumeModel]:
        efs_volumes = [
            volume for container in self.containers for volume in container.efs_volumes
        ]
        return efs_volumes


class SecurityGroupRule(BaseModel):
    name: str
    port: int
    cidr: Optional[str] = None
    prefix_list: Optional[str] = None
    security_group_id: Optional[str] = None

    @model_validator(mode="after")
    def validate_cidr(self):
        has_at_least_two_true = lambda lst: sum(lst) >= 2  # noqa: E731
        if has_at_least_two_true(
            [
                self.prefix_list is not None,
                self.cidr is not None,
                self.security_group_id is not None,
            ]
        ):
            raise ValueError(
                "A rule is either a CIDR, a security group id or a prefix list!"
            )
        if (
            self.prefix_list is None
            and self.cidr is None
            and self.security_group_id is None
        ):
            raise ValueError(
                "A rule is either a CIDR, a security group id or a prefix list, not"
                " none!"
            )
        return self


class SecurityGroupRules(BaseModel):
    egress: List[SecurityGroupRule] = []
    ingress: List[SecurityGroupRule] = []


class EcsLoadBalancerModel(BaseModel):
    listener_port: int
    target_group_port: int
    subnets: list[str] = []
    load_balancer_name: Optional[str] = None
    arn: Optional[str] = None
    security_group_id: Optional[str] = None
    security_group_rules: Optional[SecurityGroupRules] = None
    idle_timeout: Optional[int] = None

    @field_validator("idle_timeout")
    def validate_idle_timeout(cls, value):
        if value is not None and (value < 1 or value > 4000):
            raise ValueError(
                f"Idle timeout must be between 1 and 4000 seconds, got {value}"
            )
        return value

    @model_validator(mode="after")
    def validate_subnets(self):
        if len(self.subnets) == 0 and self.arn is None:
            raise ValueError(
                "If you do not provide an ARN of a NetworkLoadBalancer, please provide"
                " a subnets list to create one"
            )
        return self


class EcsFileModel(BaseModel):
    metadata: EcsFileMetadataModel
    role: EcsFileRoleModel
    execution_role: EcsFileRoleModel
    task_definition: EcsTaskDefinitionModel
    load_balancer: Optional[EcsLoadBalancerModel] = None
    security_group_id: Optional[str] = None
    auto_install_override: list[list[str]] = []
    copy_method: str = "nc"
