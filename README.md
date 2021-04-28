
# Amazon SageMaker A/B Testing Pipeline 

This project will demonstrate how to setup an Amazon SageMaker MLOps pipeline for support A/B Testing of machine learning models.

The A/B Testing pipeline architecture consists of 3 main elements:

1. Amazon API Gateway to register and invoke SageMaker endpoints with consistent variant for a user based on A/B algorithm selection.
2. Infrastructure for storing user assignment and metrics in DynamoDB, streaming logs via Kinesis Firehose to S3
3. Amazon SageMaker multi-variant endpoint.

![\[AB Testing Architecture\]](docs/ab-testing-pipeline-architecture.png)

We will be creating an AWS Service Catalog template to deploy a new MLOps Project using AWS CodePipeline.

![\[AB Testing Pipeline\]](docs/ab-testing-pipeline-deployment.png)

## Get Started

To get started first, clone this repository.

```
git clone https://github.com/aws-samples/amazon-sagemaker-ab-testing-pipeline.git
cd amazon-sagemaker-ab-testing-pipeline
```

### Install the AWS CDK

This project uses the AWS Cloud Development Kit [CDK](https://aws.amazon.com/cdk/).
To [get started](https://docs.aws.amazon.com/cdk/latest/guide/getting_started.html) with CDK you need [Node.js](https://nodejs.org/en/download/) 10.13.0 or later.

Install the AWS CDK Toolkit globally using the following Node Package Manager command.

```
npm install -g aws-cdk
```

Run the following command to verify correct installation and print the version number of the AWS CDK.

```
cdk --version
```

### Setup Python Environment for CDK

This project uses CDK with python bindings to deploy resources to your AWS account.

The `cdk.json` file tells the CDK Toolkit how to execute your app.

This project is set up like a standard Python project.  The initialization
process also creates a virtualenv within this project, stored under the `.venv`
directory.  To create the virtualenv it assumes that there is a `python3`
(or `python` for Windows) executable in your path with access to the `venv`
package. If for any reason the automatic creation of the virtualenv fails,
you can create the virtualenv manually.

To manually create a virtualenv on MacOS and Linux:

```
$ python3 -m venv .venv
```

After the init process completes and the virtualenv is created, you can use the following
step to activate your virtualenv.

```
$ source .venv/bin/activate
```

If you are a Windows platform, you would activate the virtualenv like this:

```
% .venv\Scripts\activate.bat
```

Once the virtualenv is activated, you can install the required dependencies.

```
$ pip install -r requirements.txt
```

## Create the API and testing infrastructure

In this section you will setup the API and testing infrastructure which includes
* Amazon DynamoDB table for user variant assignment.
* Amazon DynamoDB table for variant metrics.
* Amazon Kinesis Firehose, S3 Bucket and AWS Lambda for processing events.

Follow are the steps require to setup the infrastructure.

1. Install layers

In order to support X-RAY as part of our [python function](https://github.com/awsdocs/aws-lambda-developer-guide/tree/main/sample-apps/blank-python) we will require additional python libraries.  Run the following command to pip install the [AWS X-Ray SDK for Python](https://docs.aws.amazon.com/xray/latest/devguide/xray-sdk-python.html) into the `layers` folder.

```
sh install_layers.sh
```

This will enabling sample request to visualize the access patterns and drill into any specific errors.

![\[AB Testing Pipeline X-Ray\]](docs/ab-testing-pipeline-xray.png)

2. Bootstrap the CDK

If this is the first time you have run the CDK, you may need to [Bootstrap](https://docs.aws.amazon.com/cdk/latest/guide/bootstrapping.html) your account.  If you have multiple deployment targets see also [Specifying up your environment](https://docs.aws.amazon.com/cdk/latest/guide/cli.html#cli-environment) in the CDK documentation.

```
cdk bootstrap
```

To bootstrap and deploy, you will require permissions create AWS CloudFormation Stacks and the associated resources for your current execution role.

If you have cloned this notebook into SageMaker Studio, you will need to add additional permissions to the SageMaker Studio execution role.  You can find your user's role by browsing to the Studio dashboard.

![\[AB Testing Pipeline Execution Role\]](docs/ab-testing-pipeline-execution-role.png)

Browse to the [IAM](https://console.aws.amazon.com/iam) section in the console, and find this role.

Then, click the **Add inline policy** link, switch to to the **JSON** tab, and paste the following inline policy:

```
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "apigateway:*"
            ],
            "Resource": "arn:aws:apigateway:*::/*"
        },
        {
            "Action": [
                "dynamodb:*"
            ],
            "Effect": "Allow",
            "Resource": "arn:aws:dynamodb:*:*:table/ab-testing-*"
        },
        {
            "Action": [
                "lambda:*"
            ],
            "Effect": "Allow",
            "Resource": [
              "arn:aws:lambda:*:*:function:ab-testing-api-*",
              "arn:aws:lambda:*:*:layer:*"
            ]
        },
        {
            "Action": [
                "firehose:*"
            ],
            "Effect": "Allow",
            "Resource": "arn:aws:firehose:*:*:deliverystream/ab-testing-*"
        },
        {
            "Action": [
                "s3:*"
            ],
            "Effect": "Allow",
            "Resource": [
                "arn:aws:s3:::cdktoolkit-*",
                "arn:aws:s3:::ab-testing-api-*"
            ]
        },
        {
            "Action": [
                "cloudformation:*",
                "servicecatalog:*",
                "events:*"
            ],
            "Effect": "Allow",
            "Resource": "*"
        },
        {
            "Effect": "Allow",
            "Action": [
                "logs:*"
            ],
            "Resource": "arn:aws:logs:**:*:log-group:ab-testing-api-*"
        },
        {
            "Effect": "Allow",
            "Action": [
                "iam:CreateRole",
                "iam:DeleteRole"
            ],
            "Resource": "arn:aws:iam::*:role/ab-testing-api-*"
        },
        {
            "Effect": "Allow",
            "Action": [
                "iam:GetRole",
                "iam:PassRole",
                "iam:GetRolePolicy",
                "iam:AttachRolePolicy",
                "iam:PutRolePolicy",
                "iam:DetachRolePolicy",
                "iam:DeleteRolePolicy"
            ],
            "Resource": [
              "arn:aws:iam::*:role/ab-testing-api-*",
              "arn:aws:iam::*:role/service-role/AmazonSageMaker*"
            ]
        }
    ]
}
```

Click **Review policy** and provide the name `CDK-DeployPolicy` then click **Create policy**

You should now be able to list the stacks by running:

```
cdk list
```

Which will return the following stacks:

* `ab-testing-api`
* `ab-testing-pipeline`
* `ab-testing-service-catalog`

3. Deploy the API and Testing infrastructure

Use CDK to deploy the API and Testing infrastructure which creates IAM roles with least privilege to access resources.

Follow are a list of context values that are provided in the `cdk.json`, which can also be override by passing `-c context=value`:

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

Run the following command to deploy the API and testing infrastructure, optionally override context values.

```
cdk deploy ab-testing-api -c endpoint_prefix=sagemaker-ab-testing-pipeline
```

This stack will ask you to confirm any changes, and output the `ApiEndpoint` which you will provide to the A/B Testing sample notebook.

## Create the SageMaker MLOps Project Template

1. Generate the Project Template (Optional)

The `ab-testing-pipeline.yml` is included as part of this distribution, and doesn't require updating unless you change the `pipeline_stack.py` implementation.

To generate a new pipeline you can run the following command.

```
cdk synth ab-testing-pipeline --path-metadata=false > ab-testing-pipeline.yml
```

This template will output a new Policy to attach to the `AmazonSageMakerServiceCatalogProductsUseRole` service role.  This policy is not required as this managed role already has these permissions.    In order for this to run within Amazon SageMaker Studio, you will need to remove this policy.  I recommend you diff the original to see where changes need to be made.  If there are additional roles or policies the project might not be validate when used inside of Amazon SageMaker Studio.

```
git diff ab-testing-pipeline.yml
```

2. Deploy the Project Template

Use CDK to create or update the AWS Service Catalog **Portfolio** and **Product** for the SageMaker Project template.

Following are CloudFormation parameters for this stack.

| Parameter          | Description                                           | Default                            |
|--------------------|-------------------------------------------------------|------------------------------------|
| `ExecutionRoleArn` | The SageMaker Studio execution role                   |                                    |
| `PortfolioName`    | The portfolio name to in AWS Service Catalog.         | "SageMaker Organization Templates" |
| `PortfolioOwner`   | The portfolio owner in AWS Service Catalog.           | "administrator"                    |
| `ProductVersion`   | The product version to create in AWS Service Catalog. | "1.0"                              |

Run the following command to create the SageMaker Project template, making sure you provide the required `ExecutionRoleArn`.  You can copy this from your SageMaker Studio dashboard as show above.

```
export EXECUTION_ROLE_ARN=<<sagemaker-studio-execution-role>>
cdk deploy ab-testing-service-catalog \
    --parameters ExecutionRoleArn=$EXECUTION_ROLE_ARN \
    --parameters ProductVersion=1.0
```

This stack will output the `CodeCommitSeedBucket` and `CodeCommitSeedKey` which you will need when creating the Amazon SageMaker Studio project.

If you are seeing errors running the above command ensure you have [Enabled SageMaker project templates for Studio users](https://docs.aws.amazon.com/sagemaker/latest/dg/sagemaker-projects-studio-updates.html) to grant access to these resources in Amazon S3.

### Create MLOps Project Template manually (Alternative)

If you have an existing AWS Service Catalog Portfolio, or would like to create the Product manually, follow these steps:

1. Sign in to the console with the data science account.
2. On the AWS Service Catalog console, under **Administration**, choose **Portfolios**.
3. Choose **Create a new portfolio**.
4. Name the portfolio `SageMaker Organization Templates`.
5. Download the [AB testing template](ab-testing-pipeline.yml) to your computer.
6. Choose the new portfolio.
7. Choose **Upload a new product.**
8. For **Product name**¸ enter `A/B Testing Deployment Pipeline`.
9. For **Description**, enter `Amazon SageMaker Project for A/B Testing models`.
10. For **Owner**, enter your name.
11. Under **Version details**, for **Method**, choose **Use a template file**.
12. Choose **Upload a template**.
13. Upload the template you downloaded.
14. For **Version title**, enter `1.0`.

The remaining parameters are optional.

15. Choose **Review**.
16. Review your settings and choose **Create product**.
17. Choose **Refresh** to list the new product.
18. Choose the product you just created.
19. On the **Tags** tab, add the following tag to the product:
  - **Key** – `sagemaker:studio-visibility`
  - **Value** – `True`

Finally we need to add launch constraint and role permissions.

20. On the **Constraints** tab, choose Create constraint.
21. For **Product**, choose **AB Testing Pipeline** (the product you just created).
22. For **Constraint type**, choose **Launch**.
23. Under **Launch Constraint**, for **Method**, choose **Select IAM role**.
24. Choose **AmazonSageMakerServiceCatalogProductsLaunchRole**.
25. Choose **Create**.
26. On the **Groups, roles, and users** tab, choose **Add groups, roles, users**.
27. On the **Roles** tab, select the role you used when configuring your SageMaker Studio domain.
28. Choose **Add access**.

If you don’t remember which role you selected, in your data science account, go to the SageMaker console and choose **Amazon SageMaker Studio**. In the Studio **Summary** section, locate the attribute **Execution role**. Search for the name of this role in the previous step.

You’re done! Now it’s time to create a project using this template.

## Creating your project

Once your MLOps project template is registered in AWS Service Catalog you can create a project using your new template.

1. Sign in to the console with the data science account.
2. On the SageMaker console, open **SageMaker Studio** with your user.
3. Choose the **Components and registries**
4. On the drop-down menu, choose **Projects**.
5. Choose **Create project**.

![\[Select Template\]](docs/ab-testing-pipeline-sagemaker-template.png)

On the Create project page, SageMaker templates is chosen by default. This option lists the built-in templates. However, you want to use the template you published for the A/B Testing Deployment Pipeline.

6. Choose **Organization templates**.
7. Choose **A/B Testing Deployment Pipeline**.
8. Choose **Select project template**.
9. In the **Project details** section, for **Name**, enter **ab-testing-pipeline**.
  - The project name must have 32 characters or fewer.
10. In the Project template parameters
  - For **StageName**, enter `dev` 
  - For **CodeCommitSeedBucket**, enter the `CodeCommitSeedBucket` output from the `ab-testiing-service-catalog` stack
  - For **CodeCommitSeedKey**, enter the `CodeCommitSeedKey` output from the `ab-testiing-service-catalog` stack
11. Choose Create project.

![\[Create Project\]](docs/ab-testing-pipeline-sagemaker-project.png)

`NOTE`: If you have recently updated your AWS Service Catalog Project, you may need to refresh SageMaker Studio to ensure it picks up the latest version of your template.

## Running the A/B Test

In the following sections, you will learn how to **Train**, **Deploy** and **Simulate** a test against our A/B Testing Pipeline.

### Training a Model

Now that your project is ready, it’s time to train, register and approve a model.

1. Download the [Sample Notebook](notebook/mab-reviews-helpfulness.ipynb) to use for this walk-through.
2. Choose the **Upload file** button
3. Choose the Jupyter notebook you downloaded and upload it.
4. Choose the notebook to open a new tab.

![\[Upload File\]](docs/ab-testing-pipeline-upload-file.png)

This notebook will step you through the process of 
1. Download a dataset
2. Create and Run an Amazon SageMaker Pipeline
3. Approve the model.
4. Create a Amazon SageMaker Tuning Job.
5. Select the best model, register and approve the second model.

### Deploying the Multi-Variant Pipeline.

Once the second model has been approved, the MLOps deployment pipeline will run.

See the [Deployment Pipeline](deployment_pipeline) for more information on the stages to run.

### Running an A/B Testing simulation

With the Deployment Pipeline complete, you will be able to continue with the next stage:
1. Test the multi-variant endpoint
2. Evaluate the accuracy of the models, and visualize the confusion matrix and ROC Curves
3. Test the API by simulating a series of `invocation`, and recording reward `conversion`.
4. Plot the cumulative reward, and reward rate.
5. Plot the beta distributions of the course of the test.
6. Calculate the statistical significance of the test.

## Running Cost

This section outlines cost considerations for running the A/B Testing Pipeline. Completing the pipeline will deploy an endpoint with 2 production variants which will cost less than $3 per day. Further cost breakdowns are below.

- **CodeBuild** – Charges per minute used. First 100 minutes each month come at no charge. For information on pricing beyond the first 100 minutes, see [AWS CodeBuild Pricing](https://aws.amazon.com/codebuild/pricing/).
- **CodeCommit** – $1/month if you didn't opt to use your own GitHub repository.
- **CodePipeline** – CodePipeline costs $1 per active pipeline* per month. Pipelines are free for the first 30 days after creation. More can be found at [AWS CodePipeline Pricing](https://aws.amazon.com/codepipeline/pricing/).
- **SageMaker** – Prices vary based on EC2 instance usage for the Notebook Instances, Model Hosting, Model Training and Model Monitoring; each charged per hour of use. For more information, see [Amazon SageMaker Pricing](https://aws.amazon.com/sagemaker/pricing/).
  - The ten `ml.c5.4xlarge` *training jobs* run for approx 4 minutes at $0.81 an hour, and cost less than $1.
  - The two `ml.t2.medium` instances for production *hosting* endpoint costs 2 x $0.056 per hour, or $2.68 per day.
- **S3** – Low cost, prices will vary depending on the size of the models/artifacts stored. The first 50 TB each month will cost only $0.023 per GB stored. For more information, see [Amazon S3 Pricing](https://aws.amazon.com/s3/pricing/).
- **API Gateway** - Low cost, $1.29 for first 300 million requests.  For more info see [Amazon API Gateway pricing](https://aws.amazon.com/api-gateway/pricing/)
- **Lambda** - Low cost, $0.20 per 1 million request see [AWS Lambda Pricing](https://aws.amazon.com/lambda/pricing/).

## Cleaning Up

Once you have cleaned up the SageMaker Endpoints and Project as described in the [Sample Notebook](notebook/mab-reviews-helpfulness.ipynb), complete the clean up by deleting the **Service Catalog** and **API** resources with the AWS CDK:

1. Delete the Service Catalog Portfolio and Project Template

```
cdk destroy ab-testing-service-catalog
```

2. Delete the API and testing infrastructure

Before destroying the API stack, is is recommend you [empty](https://docs.aws.amazon.com/AmazonS3/latest/userguide/empty-bucket.html) and [delete](https://docs.aws.amazon.com/AmazonS3/latest/userguide/delete-bucket.html) the S3 Bucket that contains the S3 logs persisted by the Kinesis Firehose.

```
cdk destroy ab-testing-api
```

## Want to know more?

The [FAQ](FAQ.md) page has some answers to questions on the design principals of this sample. 

See also the [OPERATIONS](OPERATIONS.md) page for information on configuring experiments, and the API interface.

## Security

See [CONTRIBUTING](CONTRIBUTING.md#security-issue-notifications) for more information.

## License

This library is licensed under the MIT-0 License. See the [LICENSE](LICENSE) file.