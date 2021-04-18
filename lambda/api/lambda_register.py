import boto3
from botocore.exceptions import ClientError
import json
import logging
import os
from aws_xray_sdk.core import xray_recorder
from aws_xray_sdk.core import patch_all

from experiment_metrics import ExperimentMetrics
from algorithm import ThompsonSampling

# Get environment variables
METRICS_TABLE = os.environ["METRICS_TABLE"]
DELIVERY_STREAM_NAME = os.environ["DELIVERY_STREAM_NAME"]
DELIVERY_SYNC = os.getenv("DELIVERY_SYNC", "False").lower() == "true"
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
ENDPOINT_PREFIX = os.getenv("ENDPOINT_PREFIX", "")

# Configure logging and patch xray
logger = logging.getLogger()
logger.setLevel(LOG_LEVEL)
patch_all()

# Create the experiment classes from the lambda layer
exp_metrics = ExperimentMetrics(METRICS_TABLE, DELIVERY_STREAM_NAME, DELIVERY_SYNC)

# Configure logging and patch xray
logger = logging.getLogger()
logger.setLevel(LOG_LEVEL)
patch_all()

# Define he boto3 client resources
sm_client = boto3.client("sagemaker")


@xray_recorder.capture("Get Endpoint Variants")
def get_endpoint_variants(endpoint_name):
    """
    Get the list of production variant names for an endpoint
    """
    logger.info(f"Getting variants for endpoint: {endpoint_name}")
    response = sm_client.describe_endpoint(EndpointName=endpoint_name)
    endpoint_variants = [
        {
            "variant_name": r["VariantName"],
            "initial_variant_weight": r["CurrentWeight"],
        }
        for r in response["ProductionVariants"]
    ]
    logger.debug(endpoint_variants)
    return endpoint_variants


@xray_recorder.capture("Delete")
def handle_delete(endpoint_name: str):
    response = exp_metrics.delete_endpoint(
        endpoint_name=endpoint_name,
    )
    result = {
        "endpoint_name": endpoint_name,
    }
    return result, 200


@xray_recorder.capture("Register")
def handle_register(endpoint_name: str, strategy: str, epsilon: float, warmup: int):
    endpoint_variants = get_endpoint_variants(endpoint_name)
    response = exp_metrics.create_variant_metrics(
        endpoint_name=endpoint_name,
        endpoint_variants=endpoint_variants,
        strategy=strategy,
        epsilon=epsilon,
        warmup=warmup,
    )
    result = {
        "endpoint_name": endpoint_name,
        "endpoint_variants": endpoint_variants,
        "strategy": strategy,
        "epsilon": epsilon,
        "warmup": warmup,
    }
    if "Attributes" not in response:
        return result, 201
    return result, 200


def lambda_handler(event, context):
    try:
        logger.debug(json.dumps(event))

        if not (
            event.get("source") == "aws.sagemaker"
            and event.get("detail-type") == "SageMaker Endpoint State Change"
        ):
            raise Exception(
                "Expect CloudWatch Event for SageMaker Endpoint Stage Change"
            )

        # If this endpoint does not match prefix or not enabled return a status code of Not Modified (304)
        endpoint_name = event["detail"]["EndpointName"]
        endpoint_tags = event["detail"]["Tags"]
        endpoint_enabled = endpoint_tags["ab-testing:enabled"] == "true"
        if not (endpoint_name.startswith(ENDPOINT_PREFIX) and endpoint_enabled):
            logger.info(
                f"Endpoint: {endpoint_name} not enabled for prefix: {ENDPOINT_PREFIX}"
            )
            return {"statusCode": 304, "body": json.dumps(event)}

        # Delete or register the endpoint depending on status change
        endpoint_status = event["detail"]["EndpointStatus"]
        if endpoint_status == "DELETING":
            result, status_code = handle_delete(endpoint_name)
        elif endpoint_status == "IN_SERVICE":
            strategy = endpoint_tags["ab-testing:stategy"]
            epsilon = float(endpoint_tags["ab-testing:epsilon"])
            warmup = int(endpoint_tags["ab-testing:warmup"])
            result, status_code = handle_register(
                endpoint_name, strategy, epsilon, warmup
            )
        else:
            result = {"message": f"Endpoint Status: {endpoint_status} not supported"}
            status_code = 400

        # Log result succesful result and return
        logger.debug(json.dumps(result))
        return {"statusCode": status_code, "body": json.dumps(result)}
    except ClientError as e:
        logger.error(e)
        # Get boto3 specific error message
        error_message = e.response["Error"]["Message"]
        raise Exception(error_message)
    except Exception as e:
        logger.error(e)
        raise e
