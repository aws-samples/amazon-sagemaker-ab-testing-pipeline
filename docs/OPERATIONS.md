# A/B Testing Pipeline Operations Manual

Having created the A/B Testing Deployment Pipeline, this operations manual provides instructions on how to run your A/B Testing experiment.

## A/B Testing for Machine Learning models

Successful A/B Testing for machine learning models requires measuring how effective predictions are against end users.   It is important to be able to identify users consistently and be able to attribute success actions against the model predictions back to users.

### Conversion Metrics

A/B Testing can be applied to a number of use cases for which you have defined a success or `conversion` metric for predictions returned form an ML model.

Examples include:
* User **Click Through** on advertisement predicted based on browsing history and geo location.
* User **Dwell Time** for personalized content based exceeds relevancy threshold.
* User **Opens** marketing email with personalized subject line.
* User **Watches** recommended video for more than 30 seconds based on viewing history.
* User **Purchases** a product upgrade being offered an pricing discount.

Conversion rates will vary for each use case, so successful models will be measure as a percentage improvement (eg 5%) over a baseline, or previous best model.

## Deployment Pipeline

The A/B Deployment Pipeline provides an additional stage after Endpoint deployment to register the endpoint for A/B Testing.

This Register stage invokes a lambda by providing an event that includes the `enpdoint_name` along with configuration to select models from the registry based on the testing strategy.

### Testing Strategies

Following is a list of the testing strategies available.

1. `WeightedSampling` - Random selection based in initial variant weights.  Also be select during `warmup` phase.
2. `EpsilonGreedy` - Simple strategy picks a random variant a fraction of the time based on `epsilon`.
3. `UCB1` - Smart strategy explores variants with upper confidence bounds until uncertainty drops.
4. `ThompsonSampling` - Smart strategy picks random points from beta distributions to exploit variants.

### Configuration parameters

The configuration is stored in the CodeCommit source repository by stage name eg `dev-config.json` for the `dev` stage, and has the following parameters

* `stage_name` - The stage suffix for the SageMaker endpoint eg. `dev`
* `instance_count` - The number of instances to deploy per variant
* `instance_type` - The type of instance to deploy per variant.
* `strategy` - The algorithm strategy for selecting user model variants.
* `epsilon` - The epsilon parameter used by the `EpsilonGreedy` strategy.
* `warmup` - The number of invocations to warm up before applying the strategy.

In addition to the above, you must specify the `champion` and `challenger` model variants for the deployment.  

These will be loaded from the two Model Package Groups in the registry that include the project name and suffixed with `champion` or `challenger` for example project name `ab-testing-pipeline` these model package groups in the sample notebook:

![\[Model Registry\]](ab-testing-pipeline-model-registry.png)

**Latest Approved Versions**

To deploy the latest approved approved `champion` model, and the latest `N` approved `challenger` models, you can provide the single `challenger_variant_count` parameter eg:

```
{
    "stage_name": "dev",
    "strategy": "ThompsonSampling",
    "instance_count": 1,
    "instance_type": "ml.t2.large",
    "challenger_variant_count": 1
}
```

Alternatively, such as the case for production environments, you way prefer to select specific approved model package versions.  In this case you can specify the `model_package_version` for both the `champion_variant_config` and for one or more `challenger_variant_config` configuration entries.

You also have the option of overriding one or both of the `instance_count` and `instance_type` parameters for each variant. 

**Specific Versions**

```
{
    "stage_name": "prod",
    "strategy": "ThompsonSampling",
    "warmup": 100,
    "instance_count": 2,
    "instance_type": "ml.c5.large",
    "champion_variant_config": {
        "model_package_version": 1,
        "variant_name": "Champion",
        "instance_count": 3,
        "instance_type": "ml.m5.xlarge"
    },
    "challenger_variant_config": [
        {
            "model_package_version": 1,
            "variant_name": "Challenger1",
            "instance_type": "ml.c5.xlarge"
        },
        {
            "model_package_version": 2,
            "variant_name": "Challenger2",
            "instance_count": 1
        }
    ]
}
```

## API Front-end

The API has two endpoints `invocation` and `conversion` both of which take a `JSON` payload and return a `JSON` response.

### Invocation

The invocation API requires an `endpoint_name`. It also expects a `user_id` input parameter to identify the user, if none is provided a new `user_id` in the form of a UUID will be generated and return in response.

```
curl -X POST -d '<<request>>' https://<<domain>>.execute-api.<<region>>.amazonaws.com/<<stage>>/invocation
```

**Request**:
```
{
    "endpoint_name": "sagemaker-ab-testing-pipeline-dev", 
    "user_id": "user_1", 
    "content_type": "application/json", 
    "data": "{\"instances\": [\"Excellent Item This is the perfect media device\"]}"
}
```

The response will return the invoked `endpoint_variant` that return the predictions as well as algorithm `strategy` and `target_variant` selected.

**Response**:
```
{
    "endpoint_name": "sagemaker-ab-testing-pipeline-dev", 
    "user_id": "user_1", 
    "strategy": "ThompsonSampling", 
    "target_variant": "Challenger1", 
    "endpoint_variant": "Challenger1", 
    "inference_id": "5aa61fe8-70d7-4eed-9419-8f4efc33662d", 
    "predictions": [{"label": ["__label__NotHelpful"], "prob": [0.735004723072052]}]
}
```

### Manual overriding endpoint variant

You can provide a manual override for the `endpoint_variant` by specifying this the request payload.

**Request**:
```
{
    "endpoint_name": "sagemaker-ab-testing-pipeline-dev", 
    "endpoint_variant": "Champion", 
    "user_id": "user_1", 
    "content_type": "application/json", 
    "data": "{\"instances\": [\"Excellent Item This is the perfect media device\"]}"
}
```

The response will output a `strategy` of "Manual" which will be logged.

**Response**:
```
{
    "endpoint_name": "sagemaker-ab-testing-pipeline-dev", 
    "user_id": "user_1", 
    "strategy": "Manual", 
    "target_variant": "Champion", 
    "endpoint_variant": "Champion", 
    "inference_id": "5aa61fe8-70d7-4eed-9419-8f4efc33662d", 
    "predictions": [{"label": ["__label__NotHelpful"], "prob": [0.735004723072052]}]
}
```

### Fallback strategy

In the event of an error reaching the DynamoDB tables for user assignment of variant metrics, the API will still continue invoke the SageMaker endpoint. 

The response will return a `strategy` of "Fallback" along with an empty `target_variant` and the actual invoked `endpoint_variant` which will be logged in there are no issues writing to Kinesis. 

**Response**:
```
{
    "endpoint_name": "sagemaker-ab-testing-pipeline-dev", 
    "user_id": "user_1", 
    "strategy": "Fallback", 
    "target_variant": null, 
    "endpoint_variant": "Challenger2", 
    "inference_id": "5aa61fe8-70d7-4eed-9419-8f4efc33662d", 
    "predictions": [{"label": ["__label__NotHelpful"], "prob": [0.735004723072052]}]
}
```

### Conversion

The conversion API requires an `endpoint_name` and a `user_id`.  
You can optionally provide the `inference_id` which was returned from the original invocation request to allow correlation when querying the logs in S3.
The `reward` parameters is a floating point number that defaults to `1.0` if not provided.

```
curl -X POST -d '<<request>>' https://<<domain>>.execute-api.<<region>>.amazonaws.com/<<stage>>/conversion
```

**Request**:
```
{
    "endpoint_name": "sagemaker-ab-testing-pipeline-dev", 
    "user_id": "user_1", 
    "inference_id": "5aa61fe8-70d7-4eed-9419-8f4efc33662d", 
    "reward": 1.0
}
```

The response will return the `endpoint_variant` assigned to the user.

**Response**:
```
{
    "endpoint_name": "sagemaker-ab-testing-pipeline-dev", 
    "user_id": "user_1", 
    "strategy": "ThompsonSampling", 
    "endpoint_name": "Challenger1", 
    "endpoint_variant": "Challenger1", 
    "inference_id": "5aa61fe8-70d7-4eed-9419-8f4efc33662d",
    "reward": 1.0
}
```

## Monitoring

### Metrics

AWS CloudWatch metrics are published to every time metrics are updated in Amazon DynamoDB.

The following metrics are recorded against dimensions `EndpointName` and `VariantName` in namespace `aws/sagemaker/Endpoints/ab-testing`
* `Invocations`
* `Conversions`
* `Rewards`

### Traces

The API Lambda functions are instrumented with [AWS X-Ray](https://aws.amazon.com/xray/) so you can inspect the latency for all downstream services including
* DynamoDB
* Amazon SageMaker
* Kinesis Firehose

![\[AB Testing Pipeline X-Ray\]](ab-testing-pipeline-xray.png)