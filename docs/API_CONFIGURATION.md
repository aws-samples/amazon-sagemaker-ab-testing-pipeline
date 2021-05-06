# API and Testing infrastructure Configuration

The API and Testing infrastructure stack reads configuration from context values in `cdk.json`.  These values can also be override by passing arguments to the cdk deploy command eg:

```
cdk deploy ab-testing-api -c stage_name=dev -c endpoint_prefix=sagemaker-ab-testing-pipeline
```

Following is a list of the context parameters and their defaults.

| Property                  | Description                                                                                                                                                     | Default                            |
|---------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------|------------------------------------|
| `api_name`                | The API Gateway Name                                                                                                                                            | "ab-testing"                       |
| `stage_name`              | The stage namespace for resource and API Gateway path                                                                                                           | "dev"                              |
| `endpoint_prefix`         | A prefix to filter Amazon SageMaker endpoints the API can invoke.                                                                                               | "sagemaker-"                       |
| `api_lambda_memory`       | The [lambda memory](https://docs.aws.amazon.com/lambda/latest/dg/configuration-memory.html) allocation for API endpoint.                                        | 768                                |
| `api_lambda_timeout`      | The lambda timeout for the API endpoint.                                                                                                                        | 10                                 |
| `metrics_lambda_memory`   | The [lambda memory](https://docs.aws.amazon.com/lambda/latest/dg/configuration-memory.html) allocated for metrics processing Lambda                             | 768                                |
| `metrics_lambda_timeout`  | The lambda timeout for the processing lambda.                                                                                                                   | 10                                 |
| `dynamodb_read_capacity`  | The [Read Capacity](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/HowItWorks.ReadWriteCapacityMode.html) for the DynamoDB tables             | 5                                  |
| `dynamodb_write_capacity` | The [Write Capacity](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/HowItWorks.ReadWriteCapacityMode.html) for the DynamoDB tables            | 5                                  |
| `delivery_sync`           | When`true` metrics will be written directly to DynamoDB, instead of the Amazon Kinesis for processing.                                                          | false                              |
| `firehose_interval`       | The [buffering](https://docs.aws.amazon.com/firehose/latest/dev/create-configure.html) interval in seconds which firehose will flush events to S3.              | 60                                 |
| `firehose_mb_size`        | The buffering size in MB before the firehose will flush its events to S3.                                                                                       | 1                                  |
| `log_level`               | Logging level for AWS Lambda functions                                                                                                                          | "INFO"                             |
