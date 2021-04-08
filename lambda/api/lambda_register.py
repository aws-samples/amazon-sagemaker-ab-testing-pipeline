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

        endpoint_name = event.get("endpoint_name")
        if endpoint_name is None:
            raise Exception("Require endpoint name in event")

        strategy = event.get("strategy", ThompsonSampling.STRATEGY_NAME)
        epsilon = float(event.get("epsilon", 0.1))
        warmup = int(event.get("warmup", 0))
        result, status_code = handle_register(endpoint_name, strategy, epsilon, warmup)

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
