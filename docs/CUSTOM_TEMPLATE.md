# Customize the Deployment Pipeline

The [ab-testing-pipeline.yml](../ab-testing-pipeline.yml) is included as part of this distribution, and doesn't require updating unless you change the `infra/pipeline_stack.py` implementation.

To generate a new pipeline you can run the following command.

```
cdk synth ab-testing-pipeline --path-metadata=false > ab-testing-pipeline.yml
```

This template will output a new Policy to attach to the `AmazonSageMakerServiceCatalogProductsUseRole` service role.  This policy is not required as this managed role already has these permissions.    In order for this to run within Amazon SageMaker Studio, you will need to remove this policy.  I recommend you diff the original to see where changes need to be made.  If there are additional roles or policies the project might not be validate when used inside of Amazon SageMaker Studio.

```
git diff ab-testing-pipeline.yml
```
