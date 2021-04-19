import boto3
from decimal import Decimal
from itertools import groupby
import json
import logging
from time import time
from datetime import datetime


class ExperimentMetrics:
    """
    Class for getting and updating experiment metrics
    """

    def __init__(
        self, metrics_table: str, delivery_stream_name: str, synchronous: bool = False
    ):
        self.metrics_table = metrics_table
        self.delivery_stream_name = delivery_stream_name
        self.synchronous = synchronous
        self.dynamodb = boto3.resource("dynamodb")
        self.ddb_client = boto3.client("dynamodb")
        self.firehose = boto3.client("firehose")
        self.cloudwatch = boto3.client("cloudwatch")

    def create_variant_metrics(
        self,
        endpoint_name: str,
        endpoint_variants: list,
        strategy: str,
        epsilon: float,
        warmup: int,
        timestamp: int = int(time()),
    ):
        logging.debug(f"Get metrics for endpoint: {endpoint_name}")
        table = self.dynamodb.Table(self.metrics_table)
        # Format variants as a dictionary for persistence with only the initial weight
        variant_names = [v["variant_name"] for v in endpoint_variants]
        variant_metrics = dict(
            [
                (
                    v["variant_name"],
                    {
                        "initial_variant_weight": Decimal(
                            str(v["initial_variant_weight"])
                        )
                    },
                )
                for v in endpoint_variants
            ]
        )
        logging.debug(variant_metrics)
        response = table.put_item(
            Item={
                "endpoint_name": endpoint_name,
                "strategy": strategy,
                "variant_names": variant_names,
                "variant_metrics": variant_metrics,
                "epsilon": Decimal(str(epsilon)),
                "warmup": warmup,
                "created_at": timestamp,
            },
            ReturnValues="ALL_OLD",
            ReturnConsumedCapacity="TOTAL",
        )
        return response

    def delete_endpoint(
        self,
        endpoint_name: str,
        timestamp: int = int(time()),
    ):
        logging.debug(f"Delete endpoint: {endpoint_name}")
        table = self.dynamodb.Table(self.metrics_table)
        # Set the deleted_at property in DDB for this endpoint
        response = table.update_item(
            Key={"endpoint_name": endpoint_name},
            UpdateExpression="SET deleted_at = :now ",
            ExpressionAttributeValues={
                ":now": timestamp,
            },
            ReturnValues="UPDATED_NEW",
        )
        return response

    def get_variant_metrics(self, endpoint_name):
        """
        Return the strategy and the list of varints, with the counts defaulted to zero if not exist
        """
        table = self.dynamodb.Table(self.metrics_table)
        response = table.get_item(
            Key={
                "endpoint_name": endpoint_name,
            },
            ReturnConsumedCapacity="TOTAL",
        )
        # Return the list of invocation and success counts per variant
        if "Item" not in response:
            raise Exception(f"Endpoint {endpoint_name} not found")

        strategy = response["Item"]["strategy"]
        epsilon = float(response["Item"]["epsilon"])
        warmup = int(response["Item"]["warmup"])
        variant_names = response["Item"]["variant_names"]
        variant_metrics = response["Item"]["variant_metrics"]
        metrics = [
            {
                "endpoint_name": endpoint_name,
                "variant_name": v,
                "initial_variant_weight": float(
                    variant_metrics[v]["initial_variant_weight"]
                ),
                "invocation_count": int(variant_metrics[v].get("invocation_count", 0)),
                "conversion_count": int(variant_metrics[v].get("conversion_count", 0)),
                "reward_sum": float(variant_metrics[v].get("reward_sum", 0)),
            }
            for v in variant_names
        ]
        return strategy, epsilon, warmup, metrics

    def put_cloudwatch_metric(
        self,
        metric_name: str,
        endpoint_name: str,
        variant_name: str,
        metric_value: float,
        dt: datetime = datetime.now(),
    ):
        logging.debug(
            f"Putting metric: {metric_value} for {metric_name} on endpoint: {endpoint_name}, variant: variant_name at {dt}"
        )
        response = self.cloudwatch.put_metric_data(
            Namespace="aws/sagemaker/Endpoints/ab-testing",  # Use a sub-namespace under SageMaker endpoints
            MetricData=[
                {
                    "MetricName": metric_name,
                    "Dimensions": [
                        {"Name": "EndpointName", "Value": endpoint_name},
                        {
                            "Name": "VariantName",
                            "Value": variant_name,
                        },
                    ],
                    "Timestamp": dt,
                    "Value": metric_value,
                    "Unit": "Count",
                },
            ],
        )
        logging.debug(response)

    def update_variant_metrics(self, metrics: list, timestamp=int(time())):
        """
        Group by endpoint variants and metric type to increment dynamodb counts
        """
        table = self.dynamodb.Table(self.metrics_table)

        # Sort the list by endpoint_name and variant_name first to ensure groupby is efficient
        metrics = sorted(
            metrics, key=lambda m: (m["endpoint_name"], m["endpoint_variant"])
        )

        responses = []
        for (endpoint_name, variant_name), vg in groupby(
            metrics, lambda m: (m["endpoint_name"], m["endpoint_variant"])
        ):
            # Get the total invocation and rewards
            invocation_count = 0
            conversion_count = 0
            reward_sum = 0.0
            for m in vg:
                if m["type"] == "invocation":
                    invocation_count += 1
                elif m["type"] == "conversion":
                    conversion_count += 1
                    reward_sum += m["reward"]
                else:
                    raise Exception("Unsupported type {}".format(m["type"]))
            logging.debug(
                f"Update metrics for endpoint: {endpoint_name}, variant: {variant_name} invocations: {invocation_count}, conversions: {conversion_count}, rewards: {reward_sum}"
            )
            # Update variant in dynamo db with these counts
            response = table.update_item(
                Key={"endpoint_name": endpoint_name},
                UpdateExpression="ADD variant_metrics.#variant.invocation_count :i, "
                "variant_metrics.#variant.conversion_count :c, "
                "variant_metrics.#variant.reward_sum :r "
                "SET #created_at = if_not_exists(#created_at, :now), #updated_at = :now ",
                ExpressionAttributeNames={
                    "#variant": variant_name,
                    "#created_at": "created_at",
                    "#updated_at": "updated_at",
                },
                ExpressionAttributeValues={
                    ":i": int(invocation_count),
                    ":c": int(conversion_count),
                    ":r": Decimal(str(reward_sum)),
                    ":now": timestamp,
                },
                ReturnValues="UPDATED_NEW",
            )

            # Return total counts per endpoint_name and endpoint_variant
            logging.debug(response)
            metrics = response["Attributes"]["variant_metrics"][variant_name]
            new_counts = {
                "endpoint_name": endpoint_name,
                "endpoint_variant": variant_name,
                "invocation_count": metrics.get("invocation_count", 0),
                "conversion_count": metrics.get("conversion_count", 0),
                "reward_sum": metrics.get("reward_sum", 0.0),
            }
            responses.append(new_counts)

            # Put cloudwatch metrics against this timestamp
            dt = datetime.fromtimestamp(timestamp)
            if invocation_count > 0:
                self.put_cloudwatch_metric(
                    "Invocations", endpoint_name, variant_name, invocation_count, dt
                )
            if conversion_count > 0:
                self.put_cloudwatch_metric(
                    "Conversions", endpoint_name, variant_name, conversion_count, dt
                )
                self.put_cloudwatch_metric(
                    "Rewards", endpoint_name, variant_name, reward_sum, dt
                )

        return responses

    def log_metrics(self, metrics):
        # Update metrics directly in DDB if required.
        if self.synchronous:
            return self.update_variant_metrics(metrics)

        # Dump the results as a json lines with trailing new line
        event_log = "\n".join([json.dumps(metric) for metric in metrics]) + "\n"
        logging.debug("Log kinesis events")
        logging.debug(event_log)

        # Put to delivery stream
        return self.firehose.put_record(
            DeliveryStreamName=self.delivery_stream_name,
            Record={"Data": event_log.encode("utf-8")},
        )
