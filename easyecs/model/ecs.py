import os
from typing import Dict, List, Optional
from pydantic import BaseModel


class EcsFileMetadataModel(BaseModel):
    appname: str
    user: str = os.environ["USER"]


class EcsFileStatementModel(BaseModel):
    sid: str
    resources: List[str]
    actions: List[str]
    effect: str


class EcsFileRoleModel(BaseModel):
    managed_policies: List[str] = []
    statements: List[EcsFileStatementModel]


class EcsFileLimitsModel(BaseModel):
    cpu: int
    memory: int


class EcsFileResourcesModel(BaseModel):
    limits: EcsFileLimitsModel


class EcsFileSynchronizeModel(BaseModel):
    root: str
    exclude: List[str]


class EcsFileBuildModel(BaseModel):
    dockerfile: str = "Dockerfile"
    target: Optional[str] = None
    args: List[Dict[str, str]] = []


class EcsFileEnvModel(BaseModel):
    name: str
    value: str
    active: bool = True


class EcsFileSecretModel(BaseModel):
    name: str
    arn: str
    field: str
    active: bool = True


class EcsFileContainerModel(BaseModel):
    name: str
    image: str
    user: str = "root"
    tty: bool = False
    command: Optional[str] = None
    resources: EcsFileResourcesModel
    build: Optional[EcsFileBuildModel] = None
    synchronize: Optional[EcsFileSynchronizeModel] = None
    port_forward: List[str] = []
    env: List[EcsFileEnvModel] = []
    secrets: List[EcsFileSecretModel] = []


class EcsTaskDefinitionModel(BaseModel):
    resources: EcsFileResourcesModel
    containers: List[EcsFileContainerModel]


class EcsFileModel(BaseModel):
    metadata: EcsFileMetadataModel
    role: EcsFileRoleModel
    execution_role: EcsFileRoleModel
    task_definition: EcsTaskDefinitionModel
