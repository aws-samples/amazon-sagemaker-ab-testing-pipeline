
# Amazon SageMaker A/B Testing Pipeline 

This folder contains the CDK infrastructure for the multi-variant deployment pipeline.

## Deployment Pipeline

This deployment pipeline contains a few stages.

1. **Source**: Pull the latest deployment configuration from AWS CodeCommit repository.
1. **Build**: AWS CodeBuild job to create the AWS CloudFormation template for deploying the endpoint.
    - Query the Amazon SageMaker project to get the top approved models.
    - Use the AWS CDK to create a CFN stack to deploy multi-variant SageMaker Endpoint.
2. **Deploy**: Run the AWS CloudFormation stack to create/update the SageMaker endpoint, tagged with properties based on configuration:
    - `ab-testing:enabled` equals `true`
    - `ab-testing:strategy` is one `WeightedSampling`, `EpslionGreedy`, `UCB1` or `ThompsonSampling`.
    - `ab-testing:epsilon` is parameters for `EpslionGreedy` strategy, defaults to `0.1`.
    - `ab-testing:warmup` the number of invocations to warmup with `WeightedSampling` strategy, defaults to `0`.

![\[AWS CodePipeline\]](../docs/ab-testing-pipeline-code-pipeline.png)

## Testing

Once you have created a SageMaker Project, you can test the **Build** stage and **Register** events locally by setting some environment variables.

### Build Stage

Export the environment variables for the `SAGEMAKER_PROJECT_NAME` and `SAGEMAKER_PROJECT_ID` created by your SageMaker Project cloud formation.  Then run the `cdk synth` command:

```
export SAGEMAKER_PROJECT_NAME="<<project_name>>"
export SAGEMAKER_PROJECT_ID="<<project_id>>"
export STAGE_NAME="dev"
cdk synth
```

### Register

Export the environment variable for the `REGISTER_LAMBDA` created as part of the `ab-testing-api` stack, then run `register.py` file.

```
export REGISTER_LAMBDA="<<register_lambda>>"
python register.py
```
