#!/usr/bin/env python3

import json
import logging
import os
import boto3

# Configure the logger
logger = logging.getLogger(__name__)
logging.basicConfig(level="INFO")

# Boto3 client
lambda_client = boto3.client("lambda")

# Load these from environment variables, that are passed into CodeBuild job from pipeline stack
project_name = os.environ["SAGEMAKER_PROJECT_NAME"]
project_id = os.environ["SAGEMAKER_PROJECT_ID"]
stage_name = os.environ["STAGE_NAME"]
register_lambda = os.environ["REGISTER_LAMBDA"]

# Get endpoint
endpoint_name = f"sagemaker-{project_name}-{stage_name}"
logger.info(f"Register endpoint: {endpoint_name} with lambda: {register_lambda}")

# Get the config and include with endpoint to register this model
with open(f"{stage_name}-config.json", "r") as f:
    j = json.load(f)
    event = json.dumps(
        {
            "source": "aws.sagemaker",
            "detail-type": "SageMaker Endpoint State Change",
            "detail": {
                "EndpointName": endpoint_name,
                "EndpointStatus": "IN_SERVICE",
                "Tags": {
                    "sagemaker:project-name": project_name,
                    "sagemaker:project-id": project_id,
                    "sagemaker:deployment-stage": stage_name,
                    "ab-testing:enabled": "true",
                    "ab-testing:strategy": j.get("strategy", "ThompsonSampling"),
                    "ab-testing:epsilon": str(j.get("epsilon", 0.1)),
                    "ab-testing:warmup": str(j.get("warmup", 0)),
                },
            },
        }
    )
    response = lambda_client.invoke(
        FunctionName=register_lambda,
        InvocationType="RequestResponse",
        LogType="Tail",
        Payload=event.encode("utf-8"),
    )
    # Print the result, and if not succesful raise error
    result = json.loads(response["Payload"].read())
    print(result)
    if result["statusCode"] not in [200, 201]:
        raise Exception("Unexpected status code: {}".format(result["statusCode"]))
