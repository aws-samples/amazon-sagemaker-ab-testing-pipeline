#!/usr/bin/env python3

import json
import logging
import os

from aws_cdk import core
from infra.model_registry import ModelRegistry
from infra.deployment_config import DeploymentConfig
from infra.sagemaker_stack import SageMakerStack

# Configure the logger
logger = logging.getLogger(__name__)
logging.basicConfig(level="INFO")

# Load these from environment variables, that are passed into CodeBuild job from pipeline stack
project_name = os.environ["SAGEMAKER_PROJECT_NAME"]
project_id = os.environ["SAGEMAKER_PROJECT_ID"]
stage_name = os.environ["STAGE_NAME"]

# Create App and stacks
app = core.App()

# Define variables for passing down to stacks
endpoint_name = f"sagemaker-{project_name}-{stage_name}"
if len(endpoint_name) > 63:
    raise Exception(
        f"SageMaker endpoint: {endpoint_name} must be less than 64 characters"
    )

logger.info(f"Create endpoint: {endpoint_name}")


# Define the deployment tags
tags = [
    core.CfnTag(key="sagemaker:deployment-stage", value=stage_name),
    core.CfnTag(key="sagemaker:project-id", value=project_id),
    core.CfnTag(key="sagemaker:project-name", value=project_name),
]

# Get the stage specific deployment config for sagemaker
with open(f"{stage_name}-config.json", "r") as f:
    j = json.load(f)
    deployment_config = DeploymentConfig(**j)
    # Append tags for ab-testing
    tags += [
        core.CfnTag(key="ab-testing:enabled", value="true"),
        core.CfnTag(key="ab-testing:strategy", value=deployment_config.strategy),
        core.CfnTag(key="ab-testing:epsilon", value=str(deployment_config.epsilon)),
        core.CfnTag(key="ab-testing:warmup", value=str(deployment_config.warmup)),
    ]

sagemaker = SageMakerStack(
    app,
    "ab-testing-sagemaker",
    deployment_config=deployment_config,
    project_name=project_name,
    project_id=project_id,
    endpoint_name=endpoint_name,
    tags=tags,
)

app.synth()
