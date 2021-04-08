
# Amazon SageMaker A/B Testing Pipeline 

This folder contains the CDK infrastructure for the multi-variant deployment pipeline.

## Deployment Pipeline

This deployment pipeline contains a few stages.

1. **Source**: Pull the latest deployment configuration from AWS CodeCommit repository.
1. **Build**: AWS CodeBuild job to create the AWS CloudFormation template for deploying the endpoint.
    - Query the Amazon SageMaker project to get the top approved models.
    - Use the AWS CDK to create a CFN stack with multiple endpoint variants.
    - Create a `register.json` file that contains the target SageMaker endpoint and A/B testing strategy.
2. **Deploy**: Run the AWS CloudFormation stack to create/update the SageMaker endpoint.
3. **Register**: Call the RegisterAPI for the endpoint to create/clear the A/B testing metrics.

![\[AWS CodePipeline\]](../docs/ab-testing-pipeline-code-pipeline.png)

## Testing

Once you have created a SageMaker Project, you can test the **Build** and **Register** stages locally by setting some environment variables, and running the commands found in the `buildspec` defined in the pipeline.

### Build Stage

Export the environment variables for the `SAGEMAKER_PROJECT_NAME` and `SAGEMAKER_PROJECT_ID` created by your SageMaker Project cloud formation.  Then run the `cdk synth` command:

```
export SAGEMAKER_PROJECT_NAME="<<project_name>>"
export SAGEMAKER_PROJECT_ID="<<project_id>>"
export STAGE_NAME="dev"
cdk synth
```

### Register Stage

Export the environment variable for the `REGISTER_LAMBDA` created as part of the `ab-testing-api` stack, then run `register.py` file.

```
export REGISTER_LAMBDA="<<register_lambda>>"
python register.py
```

