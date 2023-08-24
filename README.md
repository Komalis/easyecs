# EasyECS

EasyECS is an innovative container deployment tool designed to streamline the process of launching containers within the Amazon Web Services (AWS) Elastic Container Service (ECS) Fargate. With its user-friendly interface and automated workflows, EasyECS empowers developers to efficiently manage containerized applications on the AWS cloud platform. This tool is similar to what skaffold can be in Kubernetes environment.

## Demonstration

![Demonstration](https://github.com/Komalis/easyecs/blob/main/easyecs.gif)

## Features

- [X] Create a CloudFormation Stack on AWS.
- [X] Create port forwarding between you and the task.
- [X] Build and push docker image on the fly.
- [X] An easy configuration file.
- [X] Manage IAM permissions via configuration file.
- [X] Synchronize file between the host and the remote containers.
- [X] Send input to the container.
- [X] Let the task run in the background.

## How to install

```
pip install easyecs
```

## Dependencies

- NodeJS needs to be installed on your machine for AWS CDK to work.

## How to use

```
Usage: easyecs [OPTIONS] COMMAND [ARGS]...

Options:
  --help  Show this message and exit.

Commands:
  delete  Delete a stack
  dev     Run a stack in development mode
  run     Run a stack
```

## Sample configuration

```
metadata:
  appname: "helloworld"
role:
  managed_policies: []
  statements:
    - sid: "ssmactions"
      resources: ["*"]
      actions: ["ssmmessages:CreateControlChannel", "ssmmessages:CreateDataChannel", "ssmmessages:OpenControlChannel", "ssmmessages:OpenDataChannel", "secretsmanager:*"]
      effect: "Allow"
execution_role:
  managed_policies: ["service-role/AmazonECSTaskExecutionRolePolicy", "AmazonEC2ContainerRegistryReadOnly"]
  statements:
    - sid: "secretmanageractions"
      resources: ["*"]
      actions: ["secretsmanager:GetSecretValue"]
      effect: "Allow"
    - sid: "s3actions"
      resources: ["*"]
      actions: ["s3:*"]
      effect: "Allow"
task_definition:
  resources:
    limits:
      cpu: 2
      memory: 4096
  containers:
    - name: helloworld
      image: docker.io/library/debian
      user: root
      tty: true
      command: "/bin/bash"
      resources:
        limits:
          cpu: 1
          memory: 2048
      volumes:
        - "./easyecs:/root/easyecs"
        - "./ecs.yml:/root/ecs.yml"
      port_forward:
        - "8000:8000"
      env: []
      secrets: []
```
