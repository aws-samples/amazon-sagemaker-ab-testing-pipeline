from botocore.stub import Stubber
from decimal import Decimal
from datetime import datetime


from experiment_metrics import ExperimentMetrics

# 1 invocations for e1v1, 2 invocations for e1v2, and 1 count for e1v2
good_metrics = [
    {
        "timestamp": 1,
        "type": "invocation",
        "user_id": "a",
        "endpoint_name": "e1",
        "endpoint_variant": "e1v1",
    },
    {
        "timestamp": 2,
        "type": "invocation",
        "user_id": "b",
        "endpoint_name": "e1",
        "endpoint_variant": "e1v2",
    },
    {
        "timestamp": 3,
        "type": "invocation",
        "user_id": "c",
        "endpoint_name": "e1",
        "endpoint_variant": "e1v2",
    },
    {
        "timestamp": 4,
        "type": "conversion",
        "reward": 1,
        "user_id": "c",
        "endpoint_name": "e1",
        "endpoint_variant": "e1v2",
    },
]


def test_log_metrics():
    # Create new metrics object and
    exp_metrics = ExperimentMetrics("test-metrics", "test-delivery-stream")

    # See the firehose put_record
    # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/firehose.html#Firehose.Client.put_record
    with Stubber(exp_metrics.firehose) as stubber:
        expected_response = {"RecordId": "xxxx", "Encrypted": True}
        expected_params = {
            "DeliveryStreamName": "test-delivery-stream",
            "Record": {
                "Data": b'{"timestamp": 1, "type": "invocation", "user_id": "a", "endpoint_name": "e1", "endpoint_variant": "e1v1"}\n'
                b'{"timestamp": 2, "type": "invocation", "user_id": "b", "endpoint_name": "e1", "endpoint_variant": "e1v2"}\n'
            },
        }
        stubber.add_response("put_record", expected_response, expected_params)

        # Log first metric
        response = exp_metrics.log_metrics(good_metrics[:2])
        assert response == expected_response


def test_create_variant_metrics():
    # Create new metrics object and
    exp_metrics = ExperimentMetrics("test-metrics", "test-delivery-stream")
    endpoint_variants = [
        {
            "variant_name": "ev1",
            "initial_variant_weight": 1,
        },
        {
            "variant_name": "ev2",
            "initial_variant_weight": 0.5,
        },
    ]

    # See the dynamodb put_item
    # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/dynamodb.html#DynamoDB.Client.put_item
    with Stubber(exp_metrics.dynamodb.meta.client) as stubber:
        expected_response = {
            "ConsumedCapacity": {
                "CapacityUnits": 1,
                "TableName": "test-metrics",
            },
        }

        expected_params = {
            "Item": {
                "created_at": 0,
                "endpoint_name": "test-endpoint",
                "strategy": "EpsilonGreedy",
                "epsilon": Decimal("0.1"),
                "warmup": Decimal("0"),
                "variant_names": ["ev1", "ev2"],
                "variant_metrics": {
                    "ev1": {"initial_variant_weight": Decimal("1")},
                    "ev2": {"initial_variant_weight": Decimal("0.5")},
                },
            },
            "ReturnConsumedCapacity": "TOTAL",
            "ReturnValues": "ALL_OLD",
            "TableName": "test-metrics",
        }
        stubber.add_response("put_item", expected_response, expected_params)

        response = exp_metrics.create_variant_metrics(
            endpoint_name="test-endpoint",
            strategy="EpsilonGreedy",
            epsilon=0.1,
            warmup=0,
            endpoint_variants=endpoint_variants,
            timestamp=0,
        )
        assert response == expected_response


def test_get_empty_variant_metrics():
    # Create new metrics object and
    exp_metrics = ExperimentMetrics("test-metrics", "test-delivery-stream")

    # See the dynamodb get_item
    # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/dynamodb.html#DynamoDB.Client.get_item
    with Stubber(exp_metrics.dynamodb.meta.client) as stubber:
        expected_response = {
            "Item": {
                "endpoint_name": {"S": "test-endpoint"},
                "strategy": {"S": "EpsilonGreedy"},
                "epsilon": {"N": "0.1"},
                "warmup": {"N": "0"},
                "variant_names": {"L": [{"S": "ev1"}, {"S": "ev2"}]},
                "variant_metrics": {
                    "M": {
                        "ev1": {"M": {"initial_variant_weight": {"N": "0.5"}}},
                        "ev2": {
                            "M": {
                                "initial_variant_weight": {"N": "0.1"},
                                "invocation_count": {"N": "10"},
                                "conversion_count": {"N": "1"},
                                "reward_sum": {"N": "0.5"},
                            }
                        },
                    }
                },
            }
        }
        expected_params = {
            "Key": {"endpoint_name": "test-endpoint"},
            "TableName": "test-metrics",
            "ReturnConsumedCapacity": "TOTAL",
        }
        stubber.add_response("get_item", expected_response, expected_params)

        # Validate the transformed result
        expected_variants = [
            {
                "endpoint_name": "test-endpoint",
                "variant_name": "ev1",
                "initial_variant_weight": 0.5,
                "invocation_count": 0,
                "conversion_count": 0,
                "reward_sum": 0,
            },
            {
                "endpoint_name": "test-endpoint",
                "variant_name": "ev2",
                "initial_variant_weight": 0.1,
                "invocation_count": 10,
                "conversion_count": 1,
                "reward_sum": 0.5,
            },
        ]
        strategy, epsilon, warmup, variants = exp_metrics.get_variant_metrics(
            "test-endpoint"
        )
        assert strategy == "EpsilonGreedy"
        assert epsilon == 0.1
        assert warmup == 0
        assert variants == expected_variants


def test_update_variant_metrics():
    # Create new metrics object and
    exp_metrics = ExperimentMetrics("test-metrics", "test-delivery-stream")

    # See dynamodb update_item
    # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/dynamodb.html#DynamoDB.Client.update_item
    ddb_stubber = Stubber(exp_metrics.dynamodb.meta.client)
    cw_stubber = Stubber(exp_metrics.cloudwatch)

    # 1 invocation for ev1v1
    expected_response = {
        "Attributes": {
            "endpoint_name": {
                "S": "e1",
            },
            "variant_metrics": {
                "M": {
                    "e1v1": {"M": {"invocation_count": {"N": "1"}}},
                }
            },
        },
    }
    expected_params = {
        "ExpressionAttributeNames": {
            "#created_at": "created_at",
            "#updated_at": "updated_at",
            "#variant": "e1v1",
        },
        "ExpressionAttributeValues": {
            ":c": 0,
            ":i": 1,
            ":now": 0,
            ":r": Decimal("0.0"),
        },
        "Key": {"endpoint_name": "e1"},
        "ReturnValues": "UPDATED_NEW",
        "TableName": "test-metrics",
        "UpdateExpression": "ADD variant_metrics.#variant.invocation_count :i, "
        "variant_metrics.#variant.conversion_count :c, "
        "variant_metrics.#variant.reward_sum :r SET #created_at = "
        "if_not_exists(#created_at, :now), #updated_at = :now ",
    }
    ddb_stubber.add_response("update_item", expected_response, expected_params)

    # Add CW metrics for invocations
    expected_response = {}
    expected_params = {
        "MetricData": [
            {
                "Dimensions": [
                    {"Name": "EndpointName", "Value": "e1"},
                    {"Name": "VariantName", "Value": "e1v1"},
                ],
                "MetricName": "Invocations",
                "Timestamp": datetime(1970, 1, 1, 10, 0),
                "Unit": "Count",
                "Value": 1,
            }
        ],
        "Namespace": "aws/sagemaker/Endpoints/ab-testing",
    }
    cw_stubber.add_response("put_metric_data", expected_response, expected_params)

    # 2 invocation for ev1v2
    expected_response = {
        "Attributes": {
            "endpoint_name": {
                "S": "e1",
            },
            "variant_metrics": {
                "M": {
                    "e1v2": {
                        "M": {
                            "invocation_count": {"N": "2"},
                            "conversion_count": {"N": "1"},
                            "reward_sum": {"N": "1"},
                        }
                    },
                }
            },
        },
    }
    expected_params = {
        "ExpressionAttributeNames": {
            "#created_at": "created_at",
            "#updated_at": "updated_at",
            "#variant": "e1v2",
        },
        "ExpressionAttributeValues": {":i": 2, ":c": 1, ":r": 1, ":now": 0},
        "Key": {"endpoint_name": "e1"},
        "ReturnValues": "UPDATED_NEW",
        "TableName": "test-metrics",
        "UpdateExpression": "ADD variant_metrics.#variant.invocation_count :i, "
        "variant_metrics.#variant.conversion_count :c, "
        "variant_metrics.#variant.reward_sum :r SET #created_at = "
        "if_not_exists(#created_at, :now), #updated_at = :now ",
    }
    ddb_stubber.add_response("update_item", expected_response, expected_params)

    # Add CW metrics for invocations/converisons/rewoards
    expected_response = {}
    expected_params = {
        "MetricData": [
            {
                "Dimensions": [
                    {"Name": "EndpointName", "Value": "e1"},
                    {"Name": "VariantName", "Value": "e1v2"},
                ],
                "MetricName": "Invocations",
                "Timestamp": datetime(1970, 1, 1, 10, 0),
                "Unit": "Count",
                "Value": 2,
            }
        ],
        "Namespace": "aws/sagemaker/Endpoints/ab-testing",
    }
    cw_stubber.add_response("put_metric_data", expected_response, expected_params)
    expected_params = {
        "MetricData": [
            {
                "Dimensions": [
                    {"Name": "EndpointName", "Value": "e1"},
                    {"Name": "VariantName", "Value": "e1v2"},
                ],
                "MetricName": "Conversions",
                "Timestamp": datetime(1970, 1, 1, 10, 0),
                "Unit": "Count",
                "Value": 1,
            }
        ],
        "Namespace": "aws/sagemaker/Endpoints/ab-testing",
    }
    cw_stubber.add_response("put_metric_data", expected_response, expected_params)
    expected_params = {
        "MetricData": [
            {
                "Dimensions": [
                    {"Name": "EndpointName", "Value": "e1"},
                    {"Name": "VariantName", "Value": "e1v2"},
                ],
                "MetricName": "Rewards",
                "Timestamp": datetime(1970, 1, 1, 10, 0),
                "Unit": "Count",
                "Value": 1,
            }
        ],
        "Namespace": "aws/sagemaker/Endpoints/ab-testing",
    }
    cw_stubber.add_response("put_metric_data", expected_response, expected_params)

    # Activate stubbers
    ddb_stubber.activate()
    cw_stubber.activate()

    # Update metrics, and validate the first response
    responses = exp_metrics.update_variant_metrics(good_metrics, timestamp=0)
    assert len(responses) == 2
    assert responses[0] == {
        "endpoint_name": "e1",
        "endpoint_variant": "e1v1",
        "invocation_count": 1,
        "conversion_count": 0,
        "reward_sum": 0,
    }
    assert responses[1] == {
        "endpoint_name": "e1",
        "endpoint_variant": "e1v2",
        "invocation_count": 2,
        "conversion_count": 1,
        "reward_sum": 1,
    }


def test_delete_endpoint():
    # Create new metrics object and
    exp_metrics = ExperimentMetrics("test-metrics", "test-delivery-stream")

    with Stubber(exp_metrics.dynamodb.meta.client) as ddb_stubber:
        # 1 invocation for ev1v1
        expected_response = {
            "Attributes": {
                "endpoint_name": {
                    "S": "e1",
                },
                "deleted_at": {
                    "N": "0",
                },
            },
        }
        expected_params = {
            "ExpressionAttributeValues": {
                ":now": 0,
            },
            "Key": {"endpoint_name": "e1"},
            "ReturnValues": "UPDATED_NEW",
            "TableName": "test-metrics",
            "UpdateExpression": "SET deleted_at = :now ",
        }
        ddb_stubber.add_response("update_item", expected_response, expected_params)

        response = exp_metrics.delete_endpoint("e1", timestamp=0)
        assert response is not None
        assert response["Attributes"]["deleted_at"] == 0
