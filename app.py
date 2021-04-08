#!/usr/bin/env python3

import logging

from aws_cdk import core
from infra.api_stack import ApiStack
from infra.pipeline_stack import PipelineStack
from infra.service_catalog import ServiceCatalogStack

# Configure the logger
logger = logging.getLogger(__name__)
logging.basicConfig(level="INFO")

# Create App and stacks
app = core.App()

# Create the API and SC stacks
ApiStack(app, "ab-testing-api")
PipelineStack(app, "ab-testing-pipeline")
ServiceCatalogStack(app, "ab-testing-service-catalog")

app.synth()
