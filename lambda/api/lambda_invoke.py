import boto3
from botocore.exceptions import ClientError
import json
import os
import time
import uuid
import logging
from aws_xray_sdk.core import xray_recorder
from aws_xray_sdk.core import patch_all

from experiment_metrics import ExperimentMetrics
from experiment_assignment import ExperimentAssignment
from algorithm import ThompsonSampling, EpsilonGreedy, UCB1, WeightedSampling

# Get environment variables
ASSIGNMENT_TABLE = os.environ["ASSIGNMENT_TABLE"]
METRICS_TABLE = os.environ["METRICS_TABLE"]
DELIVERY_STREAM_NAME = os.environ["DELIVERY_STREAM_NAME"]
DELIVERY_SYNC = os.getenv("DELIVERY_SYNC", "False").lower() == "true"
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# Configure logging and patch xray
logger = logging.getLogger()
logger.setLevel(LOG_LEVEL)
patch_all()

# Create the experiment classes from the lambda layer
exp_assignment = ExperimentAssignment(ASSIGNMENT_TABLE)
exp_metrics = ExperimentMetrics(METRICS_TABLE, DELIVERY_STREAM_NAME, DELIVERY_SYNC)

# Log the boto version (Require 1.17.5 for InferenceId target)
logger.info(f"boto version: {boto3.__version__}")

# Define he boto3 client resources
sm_runtime = boto3.client("sagemaker-runtime")
sm_client = boto3.client("sagemaker")
lambda_client = boto3.client("lambda")


@xray_recorder.capture("Get User Variant")
def get_user_variant(endpoint_name: str, user_id: str):
    # Get the variants metrics (this will fail if endpoint doesn't exist)
    strategy, epsilon, warmup, variant_metrics = exp_metrics.get_variant_metrics(
        endpoint_name
    )

    # Get the configuration for the endpoint name
    logger.info(f"Getting variant for user: {user_id}")
    user_variant = exp_assignment.get_assignment(
        user_id=user_id, endpoint_name=endpoint_name
    )

    # Ensure that our user variant is still in current metrics
    target_variant = user_variant
    if user_variant is not None:
        user_match = [v for v in variant_metrics if v["variant_name"] == user_variant]
        if len(user_match) == 0:
            logger.info(f"User variant {user_variant} not in endpoint variants")
            target_variant = None

    # Get the new target variant if not assigned
    status_code = 200
    if target_variant is None:
        # See if all variants have invocation metrics
        with_invocations = [
            v for v in variant_metrics if v["invocation_count"] > warmup
        ]
        if len(with_invocations) < len(variant_metrics):
            strategy = WeightedSampling.STRATEGY_NAME
            algo = WeightedSampling(variant_metrics)
        elif strategy == WeightedSampling.STRATEGY_NAME:
            algo = WeightedSampling(variant_metrics)
        elif strategy == ThompsonSampling.STRATEGY_NAME:
            algo = ThompsonSampling(variant_metrics)
        elif strategy == EpsilonGreedy.STRATEGY_NAME:
            algo = EpsilonGreedy(variant_metrics, epsilon)
        elif strategy == UCB1.STRATEGY_NAME:
            algo = UCB1(variant_metrics)
        else:
            raise Exception(f"Strategy {strategy} not supported")
        target_variant = algo.select_variant()
        status_code = 201

    # Assign the target variant to the user
    if user_variant != target_variant:
        logger.info(f"Set target variant: {target_variant} for user: {user_id}")
        exp_assignment.put_assignment(
            user_id=user_id, endpoint_name=endpoint_name, variant_name=target_variant
        )

    # Return the result
    return strategy, target_variant, status_code


@xray_recorder.capture("Stats")
def handle_stats(endpoint_name: str):
    # Get the variants metrics (this will fail if endpoint doesn't exist)
    strategy, epsilon, warmup, variant_metrics = exp_metrics.get_variant_metrics(
        endpoint_name
    )
    result = {
        "endpoint_name": endpoint_name,
        "variant_metrics": variant_metrics,
        "strategy": strategy,
        "epsilon": epsilon,
        "warmup": warmup,
    }
    return result, 200


@xray_recorder.capture("Invocation")
def handle_invocation(
    strategy: str,
    endpoint_name: str,
    content_type: str,
    inference_id: str,
    user_id: str,
    target_variant: str,
    data,
):
    # InferenceId is not available in 1.16.31 which is default boto3 in lambda by default
    # https://boto3.amazonaws.com/v1/documentation/api/1.16.31/reference/services/sagemaker-runtime.html#SageMakerRuntime.Client.invoke_endpoint
    if target_variant is None:
        logger.warning("Invoking endpiont without target variant")
        response = sm_runtime.invoke_endpoint(
            EndpointName=endpoint_name,
            ContentType=content_type,
            Body=data,
            InferenceId=inference_id,
        )
    else:
        logger.info(f"Invoke endpoint with target variant: {target_variant}")
        response = sm_runtime.invoke_endpoint(
            EndpointName=endpoint_name,
            ContentType=content_type,
            TargetVariant=target_variant,
            Body=data,
            InferenceId=inference_id,
        )
    invoked_variant = response["InvokedProductionVariant"]

    return {
        "strategy": strategy,
        "endpoint_name": endpoint_name,
        "target_variant": target_variant,
        "endpoint_variant": invoked_variant,
        "inference_id": inference_id,
        "user_id": user_id,
        "predictions": json.loads(response["Body"].read()),
    }


@xray_recorder.capture("Conversion")
def handle_conversion(
    strategy: str,
    endpoint_name: str,
    inference_id: str,
    user_id: str,
    user_variant: str,
    reward: float,
):
    return {
        "strategy": strategy,
        "endpoint_name": endpoint_name,
        "endpoint_variant": user_variant,
        "inference_id": inference_id,
        "user_id": user_id,
        "reward": reward,
    }


@xray_recorder.capture("Log Metric")
def log_metric(
    event_type: str,
    body: dict,
    request_identity: dict,
):
    # Merge all properties together into a flat dictionary
    metrics = [
        {"timestamp": int(time.time()), "type": event_type, **body, **request_identity}
    ]
    try:
        response = exp_metrics.log_metrics(metrics)
        logger.debug("Log metric response")
        logger.debug(response)
    except Exception as e:
        # Log warning that we were unable to log metrics
        logger.warning("Unable to log metrics")
        logger.warning(e)


def lambda_handler(event, context):
    try:
        logger.debug(json.dumps(event))

        # Get elements from API payload
        if event["httpMethod"] in ["POST", "PUT"] and "body" in event:
            body = json.loads(event["body"])
        else:
            raise Exception("Require HTTP POST with json body")

        endpoint_name = body.get("endpoint_name")
        if endpoint_name is None:
            raise Exception("Require endpoint name in body")

        # Optionally allow overriding the endpoint variant
        endpoint_variant = body.get("endpoint_variant")

        # If this is a POST/PUT to root, then we are creating a new endpoint
        path = event["path"]
        if path == "/stats":
            # Get stats for existing endpoint
            result, status_code = handle_stats(endpoint_name)
        else:
            # Get inference id and user id from request, or generate a new ones
            inference_id = body.get("inference_id", str(uuid.uuid4()))
            user_id = str(body.get("user_id", uuid.uuid4()))

            if endpoint_variant is None:
                try:
                    # Get the configuration for the endpoint name
                    strategy, user_variant, status_code = get_user_variant(
                        endpoint_name, user_id
                    )
                except Exception as e:
                    # Log warning and return fallback strategy
                    logger.warning("Unable to get user variant")
                    logger.warning(e)
                    strategy, user_variant, status_code = ("Fallback", None, 202)
            else:
                # Log the manual strategy for the endpoint variant
                logger.info(
                    f"Manual override endpoint: {endpoint_name} variant: {endpoint_variant}"
                )
                strategy, user_variant, status_code = ("Manual", endpoint_variant, 202)

            # Get request identity that is non null (eg sourcIP, useragent)
            request_identity = {
                "source_ip": event["requestContext"]["identity"]["sourceIp"],
                "user_agent": event["requestContext"]["identity"]["userAgent"],
            }

            # Based on path handle invocation
            if path == "/invocation":
                content_type = body.get("content_type", "application/json")
                data = body["data"]
                result = handle_invocation(
                    strategy=strategy,
                    endpoint_name=endpoint_name,
                    content_type=content_type,
                    inference_id=inference_id,
                    user_id=user_id,
                    target_variant=user_variant,
                    data=data,
                )
                log_metric("invocation", result, request_identity)
            elif path == "/conversion":
                # Get default reward of "1" unless provided
                reward = float(body.get("reward", "1"))
                result = handle_conversion(
                    strategy=strategy,
                    endpoint_name=endpoint_name,
                    inference_id=inference_id,
                    user_id=user_id,
                    user_variant=user_variant,
                    reward=reward,
                )
                log_metric("conversion", result, request_identity)
            else:
                raise Exception(f"Invalid path: {path}")

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
