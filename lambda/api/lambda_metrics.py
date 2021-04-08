import boto3
from botocore.exceptions import ClientError
import gzip
import io
import json
import os
import logging
from aws_xray_sdk.core import xray_recorder
from aws_xray_sdk.core import patch_all
from urllib.parse import unquote_plus

from experiment_metrics import ExperimentMetrics

# set environment variable
METRICS_TABLE = os.environ["METRICS_TABLE"]
DELIVERY_STREAM_NAME = os.environ["DELIVERY_STREAM_NAME"]
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# Create the experiment classes from the lambda layer
exp_metrics = ExperimentMetrics(METRICS_TABLE, DELIVERY_STREAM_NAME)

# Configure logging and patch xray
logger = logging.getLogger()
logger.setLevel(LOG_LEVEL)
patch_all()

# Define he boto3 client resources
dynamodb = boto3.resource("dynamodb")
s3 = boto3.resource("s3")


@xray_recorder.capture("Read Metrics")
def get_metrics(event):
    """
    Download the s3 file contents, and enuemrage json lienes to extract metrics
    """
    metrics = []
    for record in event["Records"]:
        bucket = record["s3"]["bucket"]["name"]
        key = unquote_plus(record["s3"]["object"]["key"])
        obj = s3.Object(bucket, key)
        with gzip.GzipFile(fileobj=obj.get()["Body"]) as gzipfile:
            content = gzipfile.read()
            buf = io.BytesIO(content)
            line = buf.readline()
            while line:
                metrics.append(json.loads(line))
                line = buf.readline()
    return metrics


@xray_recorder.capture("Write Metrics")
def update_metrics(metrics):
    # TODO: Consider filtering metrics for high frequency sourceIp or bad user agent
    exp_metrics.update_variant_metrics(metrics)


def lambda_handler(event, context):
    try:
        logger.debug(json.dumps(event))

        # Get metrics from s3 json lines
        metrics = []
        if "Records" in event:
            metrics = get_metrics(event)
        elif "Metrics" in event:
            metrics = event["Metrics"]

        update_metrics(metrics)

        # TODO: Consider correlating ground through metrics against for user_id invocations/clicks to return
        # see: https://docs.aws.amazon.com/sagemaker/latest/dg/model-monitor-model-quality-merge.html
        # see also: https://github.com/aws/amazon-sagemaker-examples/blob/master/sagemaker_model_monitor/model_quality/model_quality_churn_sdk.ipynb

        # Log the metrics count
        result = {
            "metric_count": len(metrics),
        }
        return {"statusCode": 200, "body": json.dumps(result)}
    except ClientError as e:
        # Get boto3 specific error message
        error_message = e.response["Error"]["Message"]
        logger.error(error_message)
        raise Exception(error_message)
    except Exception as e:
        logger.error(e)
        raise e
