## Frequency Asked Questions (FAQ)

### Can I use this A/B Testing Pipeline for any SageMaker model?

Yes, the API and testing infrastructure allows any endpoint with 1 or more production variants to be registered with it.   The API passes the `content_type` and `data` payload down to the Amazon SageMaker endpoint after selecting the best model variant to target for a user.

### Why do I need to register my new endpoint with the API after deployment?

The `Register` stage in the deployment pipeline ensures that the Amazon SageMaker Endpoint is able to be reached by the API.  The API retrieves the initial weights for the Production Variants configured against the endpoint.  These are saved back to DynamoDB and any metrics that we previously associated with this endpoint are cleared in preparation for a new test.

### How often will metrics be updated in DynamoDB?

On every `invocation` and `conversion` request against the API, events are written to a Kinesis Data Firehose stream. This stream has a buffer which is configured to write these events to an S3 bucket every 60 seconds or 1MB. When these events are written to S3, an AWS Lambda is triggered which loads these events, sums up the `invocation` and `conversion` records and writes these metrics to DynamoDB.

### Why not write metrics directly to DynamoDB?

The solution can be configured to write metrics to DynamoDB, however this is not recommend for a couple of reasons.

1. Less frequent writes to dynamoDB will requires in a lower [Write Capacity](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/HowItWorks.ReadWriteCapacityMode.html) and reduce cost.
2. Batching up metrics is recommend ensure that Bandit Algorithms explore early and don't arrive too quickly at a winner.
3. Batches of metrics could be analyzed before writing to DynamoDB which provide the opportunity to strip out noisy or fraudulent users by filtering on client IP, user agent or other context.
4. Metrics written as JSON lines to Kinesis Data Firehose with land in S3, partitioned by date and time can be queried by Athena or S3 Select.

### What happens if DynamoDB or Kinesis Firehose is unavailable?

If there was an error reaching the DynamoDB store to retrieve user assignment, or variant metrics, the solution will still continue to operate but will fallback to the default traffic distribution for [Multi-Variant](https://docs.aws.amazon.com/sagemaker/latest/dg/model-ab-testing.html) endpoints.   Logs will still attempt to be written to Kinesis Firehose which if available will record the fact that a `Fallback` was registered - see the [operations manual](OPERATIONS.md) for more information.

This solution has been instrumented with [AWS X-Ray](https://docs.aws.amazon.com/xray/latest/devguide/aws-xray.html) so you should be able to detect any [throttling](https://aws.amazon.com/premiumsupport/knowledge-center/on-demand-table-throttling-dynamodb/) which is the most likely cause of any unavailability.