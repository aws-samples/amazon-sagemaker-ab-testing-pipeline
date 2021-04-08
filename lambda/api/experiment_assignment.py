import boto3
from datetime import datetime, timedelta


def get_ttl(days=90):
    return int((datetime.utcnow() + timedelta(days=days)).timestamp())


class ExperimentAssignment:
    """
    Class for managing experiments
    """

    def __init__(
        self,
        assignment_table: str,
    ):
        self.assignment_table = assignment_table
        self.dynamodb = boto3.resource("dynamodb")
        self.ddb_client = boto3.client("dynamodb")

    def get_assignment(self, user_id: str, endpoint_name: str):
        table = self.dynamodb.Table(self.assignment_table)
        response = table.get_item(
            Key={
                "user_id": user_id,
                "endpoint_name": endpoint_name,
            },
            AttributesToGet=["variant_name"],
        )
        if "Item" in response:
            return response["Item"]["variant_name"]
        return None

    def put_assignment(
        self, user_id: str, endpoint_name: str, variant_name: str, ttl=get_ttl()
    ):
        """
        Put the user endpoint variant with a time to live
        """
        table = self.dynamodb.Table(self.assignment_table)
        response = table.put_item(
            Item={
                "user_id": user_id,
                "endpoint_name": endpoint_name,
                "variant_name": variant_name,
                "ttl": ttl,
            }
        )
        return response
