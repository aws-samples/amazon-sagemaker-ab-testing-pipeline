from aws_cdk import (
    core,
    aws_apigateway,
    aws_iam,
    aws_events as events,
    aws_events_targets as targets,
    aws_logs,
    aws_lambda,
    aws_dynamodb,
    aws_kinesisfirehose,
    aws_s3,
    aws_s3_notifications,
)


class ApiStack(core.Stack):
    def __init__(
        self,
        scope: core.Construct,
        construct_id: str,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Get some context properties
        log_level = self.node.try_get_context("log_level")
        api_name = self.node.try_get_context("api_name")
        stage_name = self.node.try_get_context("stage_name")
        endpoint_prefix = self.node.try_get_context("endpoint_prefix")
        api_lambda_memory = self.node.try_get_context("api_lambda_memory")
        api_lambda_timeout = self.node.try_get_context("api_lambda_timeout")
        metrics_lambda_memory = self.node.try_get_context("metrics_lambda_memory")
        metrics_lambda_timeout = self.node.try_get_context("metrics_lambda_timeout")
        dynamodb_read_capacity = self.node.try_get_context("dynamodb_read_capacity")
        dynamodb_write_capacity = self.node.try_get_context("dynamodb_write_capacity")
        delivery_sync = self.node.try_get_context("delivery_sync")
        firehose_interval = self.node.try_get_context("firehose_interval")
        firehose_mb_size = self.node.try_get_context("firehose_mb_size")

        # Create dynamodb tables and kinesis stream per project
        assignment_table_name = f"{api_name}-assignment-{stage_name}"
        metrics_table_name = f"{api_name}-metrics-{stage_name}"
        delivery_stream_name = f"{api_name}-events-{stage_name}"
        log_stream_name = "ApiEvents"

        assignment_table = aws_dynamodb.Table(
            self,
            "AssignmentTable",
            table_name=assignment_table_name,
            partition_key=aws_dynamodb.Attribute(
                name="user_id",
                type=aws_dynamodb.AttributeType.STRING,
            ),
            sort_key=aws_dynamodb.Attribute(
                name="endpoint_name",
                type=aws_dynamodb.AttributeType.STRING,
            ),
            read_capacity=dynamodb_read_capacity,
            write_capacity=dynamodb_write_capacity,
            removal_policy=core.RemovalPolicy.DESTROY,
            time_to_live_attribute="ttl",
        )

        metrics_table = aws_dynamodb.Table(
            self,
            "MetricsTable",
            table_name=metrics_table_name,
            partition_key=aws_dynamodb.Attribute(
                name="endpoint_name", type=aws_dynamodb.AttributeType.STRING
            ),
            read_capacity=dynamodb_read_capacity,
            write_capacity=dynamodb_write_capacity,
            removal_policy=core.RemovalPolicy.DESTROY,
        )

        # Create lambda layer for "aws-xray-sdk" and latest "boto3"
        xray_layer = aws_lambda.LayerVersion(
            self,
            "XRayLayer",
            code=aws_lambda.AssetCode.from_asset("layers"),
            compatible_runtimes=[aws_lambda.Runtime.PYTHON_3_7],
            description="A layer containing AWS X-Ray SDK for Python",
        )

        # Create Lambda function to read from assignment and metrics table, log metrics
        # 2048MB is ~3% higher than 768 MB, it runs 2.5x faster
        # https://aws.amazon.com/blogs/aws/new-for-aws-lambda-functions-with-up-to-10-gb-of-memory-and-6-vcpus/
        lambda_invoke = aws_lambda.Function(
            self,
            "ApiFunction",
            code=aws_lambda.AssetCode.from_asset("lambda/api"),
            handler="lambda_invoke.lambda_handler",
            runtime=aws_lambda.Runtime.PYTHON_3_7,
            timeout=core.Duration.seconds(api_lambda_timeout),
            memory_size=api_lambda_memory,
            environment={
                "ASSIGNMENT_TABLE": assignment_table.table_name,
                "METRICS_TABLE": metrics_table.table_name,
                "DELIVERY_STREAM_NAME": delivery_stream_name,
                "DELIVERY_SYNC": "true" if delivery_sync else "false",
                "LOG_LEVEL": log_level,
            },
            layers=[xray_layer],
            tracing=aws_lambda.Tracing.ACTIVE,
        )

        # Grant read/write permissions to assignment and metrics tables
        assignment_table.grant_read_data(lambda_invoke)
        assignment_table.grant_write_data(lambda_invoke)
        metrics_table.grant_read_data(lambda_invoke)

        # Add sagemaker invoke
        lambda_invoke.add_to_role_policy(
            aws_iam.PolicyStatement(
                actions=[
                    "sagemaker:InvokeEndpoint",
                ],
                resources=[
                    "arn:aws:sagemaker:{}:{}:endpoint/{}*".format(
                        self.region, self.account, endpoint_prefix
                    )
                ],
            )
        )

        # Create API Gateway for api lambda, which will create an output
        aws_apigateway.LambdaRestApi(
            self,
            "Api",
            rest_api_name=api_name,
            deploy_options=aws_apigateway.StageOptions(stage_name=stage_name),
            proxy=True,
            handler=lambda_invoke,
        )

        # Create lambda function for processing metrics
        lambda_register = aws_lambda.Function(
            self,
            "RegisterFunction",
            code=aws_lambda.AssetCode.from_asset("lambda/api"),
            handler="lambda_register.lambda_handler",
            runtime=aws_lambda.Runtime.PYTHON_3_7,
            timeout=core.Duration.seconds(metrics_lambda_timeout),
            memory_size=metrics_lambda_memory,
            environment={
                "METRICS_TABLE": metrics_table.table_name,
                "DELIVERY_STREAM_NAME": delivery_stream_name,
                "STAGE_NAME": stage_name,
                "LOG_LEVEL": log_level,
                "ENDPOINT_PREFIX": endpoint_prefix,
            },
            layers=[xray_layer],
            tracing=aws_lambda.Tracing.ACTIVE,
        )

        # Add write metrics
        metrics_table.grant_write_data(lambda_register)

        # Add sagemaker invoke
        lambda_register.add_to_role_policy(
            aws_iam.PolicyStatement(
                actions=[
                    "sagemaker:DescribeEndpoint",
                ],
                resources=[
                    "arn:aws:sagemaker:{}:{}:endpoint/{}*".format(
                        self.region, self.account, endpoint_prefix
                    )
                ],
            )
        )

        # Add endpoint event rule to register endpoints that are created or updated.
        # Note CDK is unable to filter on resource prefixes, so we will need to filter on this within the RegisterLambda function.
        # see: https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-event-patterns-content-based-filtering.html#filtering-prefix-matching
        endpoint_rule = events.Rule(
            self,
            "EndpointRule",
            rule_name=f"sagemaker-{api_name}-endpoint-{stage_name}",
            description="Rule to register an Amazon SageMaker Endpoint when it is created, updated or deleted.",
            event_pattern=events.EventPattern(
                source=["aws.sagemaker"],
                detail_type=[
                    "SageMaker Endpoint State Change",
                ],
                detail={
                    "EndpointStatus": ["IN_SERVICE", "DELETING"],
                },
            ),
            targets=[targets.LambdaFunction(lambda_register)],
        )

        # Return the register lambda function as output
        core.CfnOutput(self, "RegisterLambda", value=lambda_register.function_name)

        # Get cloudwatch put metrics policy ()
        cloudwatch_metric_policy = aws_iam.PolicyStatement(
            actions=["cloudwatch:PutMetricData"], resources=["*"]
        )

        # If we are only using sync delivery, don't require firehose or s3 buckets
        if delivery_sync:
            metrics_table.grant_write_data(lambda_invoke)
            lambda_invoke.add_to_role_policy(cloudwatch_metric_policy)
            print("# No Firehose")
            return

        # Add kinesis stream logging
        lambda_invoke.add_to_role_policy(
            aws_iam.PolicyStatement(
                actions=[
                    "firehose:PutRecord",
                ],
                resources=[
                    "arn:aws:firehose:{}:{}:deliverystream/{}".format(
                        self.region, self.account, delivery_stream_name
                    ),
                ],
            )
        )

        # Create s3 bucket for event logging (name must be < 63 chars)
        s3_logs = aws_s3.Bucket(
            self,
            "S3Logs",
            removal_policy=core.RemovalPolicy.DESTROY,
        )

        firehose_role = aws_iam.Role(
            self,
            "KinesisFirehoseRole",
            assumed_by=aws_iam.ServicePrincipal("firehose.amazonaws.com"),
        )

        firehose_role.add_to_policy(
            aws_iam.PolicyStatement(
                actions=[
                    "s3:AbortMultipartUpload",
                    "s3:GetBucketLocation",
                    "s3:GetObject",
                    "s3:ListBucket",
                    "s3:ListBucketMultipartUploads",
                    "s3:PutObject",
                ],
                resources=[s3_logs.bucket_arn, f"{s3_logs.bucket_arn}/*"],
            )
        )

        # Create LogGroup and Stream, and add permissions to role
        firehose_log_group = aws_logs.LogGroup(self, "FirehoseLogGroup")
        firehose_log_stream = firehose_log_group.add_stream(log_stream_name)

        firehose_role.add_to_policy(
            aws_iam.PolicyStatement(
                actions=[
                    "logs:PutLogEvents",
                ],
                resources=[
                    f"arn:{self.partition}:logs:{self.region}:{self.account}:log-group:{firehose_log_group.log_group_name}:log-stream:{firehose_log_stream.log_stream_name}",
                ],
            )
        )

        # Creat the firehose delivery stream with s3 destination
        aws_kinesisfirehose.CfnDeliveryStream(
            self,
            "KensisLogs",
            delivery_stream_name=delivery_stream_name,
            s3_destination_configuration=aws_kinesisfirehose.CfnDeliveryStream.S3DestinationConfigurationProperty(
                bucket_arn=s3_logs.bucket_arn,
                compression_format="GZIP",
                role_arn=firehose_role.role_arn,
                prefix=f"{stage_name}/",
                cloud_watch_logging_options=aws_kinesisfirehose.CfnDeliveryStream.CloudWatchLoggingOptionsProperty(
                    enabled=True,
                    log_group_name=firehose_log_group.log_group_name,
                    log_stream_name=firehose_log_stream.log_stream_name,
                ),
                buffering_hints=aws_kinesisfirehose.CfnDeliveryStream.BufferingHintsProperty(
                    interval_in_seconds=firehose_interval,
                    size_in_m_bs=firehose_mb_size,
                ),
            ),
        )

        # Create lambda function for processing metrics
        lambda_metrics = aws_lambda.Function(
            self,
            "MetricsFunction",
            code=aws_lambda.AssetCode.from_asset("lambda/api"),
            handler="lambda_metrics.lambda_handler",
            runtime=aws_lambda.Runtime.PYTHON_3_7,
            timeout=core.Duration.seconds(metrics_lambda_timeout),
            memory_size=metrics_lambda_memory,
            environment={
                "METRICS_TABLE": metrics_table.table_name,
                "DELIVERY_STREAM_NAME": delivery_stream_name,
                "LOG_LEVEL": log_level,
            },
            layers=[xray_layer],
            tracing=aws_lambda.Tracing.ACTIVE,
        )

        # Add write metrics for dynamodb table
        metrics_table.grant_write_data(lambda_metrics)

        # Add put metrics for cloudwatch
        lambda_metrics.add_to_role_policy(cloudwatch_metric_policy)

        # Allow metrics to read form S3 and write to DynamoDB
        s3_logs.grant_read(lambda_metrics)

        # Create S3 logs notification for processing lambda
        notification = aws_s3_notifications.LambdaDestination(lambda_metrics)
        s3_logs.add_event_notification(aws_s3.EventType.OBJECT_CREATED, notification)
