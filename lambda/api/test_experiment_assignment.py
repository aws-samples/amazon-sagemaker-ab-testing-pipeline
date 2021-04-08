from botocore.stub import Stubber

from experiment_assignment import ExperimentAssignment


def test_get_assignment():
    # Create new metrics object and
    exp_assignment = ExperimentAssignment("test-ass")

    # See the dynamodb get_item
    # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/dynamodb.html#DynamoDB.Client.get_item
    with Stubber(exp_assignment.dynamodb.meta.client) as stubber:
        expected_response = {
            "Item": {
                "variant_name": {"S": "e1v1"},
            }
        }
        expected_params = {
            "AttributesToGet": ["variant_name"],
            "Key": {"endpoint_name": "test-endpoint", "user_id": "user-1"},
            "TableName": "test-ass",
        }
        stubber.add_response("get_item", expected_response, expected_params)

        response = exp_assignment.get_assignment(
            user_id="user-1", endpoint_name="test-endpoint"
        )
        assert response == "e1v1"


def test_put_assignment():
    # Create new metrics object and
    exp_assignment = ExperimentAssignment("test-ass")

    # See the dyanmodb put_item
    # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/dynamodb.html#DynamoDB.Client.put_item
    with Stubber(exp_assignment.dynamodb.meta.client) as stubber:
        expected_response = {
            "ConsumedCapacity": {
                "CapacityUnits": 1,
                "TableName": "test-ass",
            },
        }
        expected_params = {
            "Item": {
                "endpoint_name": "test-endpoint",
                "ttl": 0,
                "user_id": "user-1",
                "variant_name": "e1v1",
            },
            "TableName": "test-ass",
        }
        stubber.add_response("put_item", expected_response, expected_params)

        response = exp_assignment.put_assignment(
            user_id="user-1", endpoint_name="test-endpoint", variant_name="e1v1", ttl=0
        )
        assert response == expected_response
