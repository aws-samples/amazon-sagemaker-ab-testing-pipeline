from aws_cdk import (
    core,
    aws_iam,
    aws_s3_assets,
    aws_servicecatalog,
)

# Create a Portfolio and Product
# see: https://docs.aws.amazon.com/cdk/api/latest/python/aws_cdk.aws_servicecatalog.html
# see also: https://github.com/mattmcclean/cdk-mlops-sm-project-template/blob/main/lib/mlops-sc-portfolio-stack.ts


class ServiceCatalogStack(core.Stack):
    def __init__(
        self,
        scope: core.Construct,
        construct_id: str,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        execution_role_arn = core.CfnParameter(
            self,
            "ExecutionRoleArn",
            type="String",
            description="The SageMaker Studio execution role",
        )

        portfolio_name = core.CfnParameter(
            self,
            "PortfolioName",
            type="String",
            description="The name of the portfolio",
            default="SageMaker Organization Templates",
        )

        portfolio_owner = core.CfnParameter(
            self,
            "PortfolioOwner",
            type="String",
            description="The owner of the portfolio.",
            default="administrator",
        )

        product_version = core.CfnParameter(
            self,
            "ProductVersion",
            type="String",
            description="The product version to deploy",
            default="1.0",
        )

        portfolio = aws_servicecatalog.CfnPortfolio(
            self,
            "Portfolio",
            display_name=portfolio_name.value_as_string,
            description="Organization templates for AB Testing pipeline",
            provider_name=portfolio_owner.value_as_string,
        )

        asset = aws_s3_assets.Asset(
            self, "TemplateAsset", path="./ab-testing-pipeline.yml"
        )

        product = aws_servicecatalog.CfnCloudFormationProduct(
            self,
            "Product",
            name="A/B Testing Deployment Pipeline",
            description="Amazon SageMaker Project for A/B Testing models",
            owner=portfolio_owner.value_as_string,
            provisioning_artifact_parameters=[
                aws_servicecatalog.CfnCloudFormationProduct.ProvisioningArtifactPropertiesProperty(
                    name=product_version.value_as_string,
                    info={"LoadTemplateFromURL": asset.s3_url},
                ),
            ],
            tags=[
                core.CfnTag(key="sagemaker:studio-visibility", value="true"),
            ],
        )

        aws_servicecatalog.CfnPortfolioProductAssociation(
            self,
            "ProductAssoication",
            portfolio_id=portfolio.ref,
            product_id=product.ref,
        )

        launch_role = aws_iam.Role.from_role_arn(
            self,
            "LaunchRole",
            role_arn=f"arn:{self.partition}:iam::{self.account}:role/service-role/AmazonSageMakerServiceCatalogProductsLaunchRole",
        )

        portfolio_association = aws_servicecatalog.CfnPortfolioPrincipalAssociation(
            self,
            "PortfolioPrincipalAssociation",
            portfolio_id=portfolio.ref,
            principal_arn=execution_role_arn.value_as_string,
            principal_type="IAM",
        )
        portfolio_association.add_depends_on(product)

        # Ensure we run the LaunchRoleConstrait last as there are timing issues on product/portfolio being created
        role_constraint = aws_servicecatalog.CfnLaunchRoleConstraint(
            self,
            "LaunchRoleConstraint",
            portfolio_id=portfolio.ref,
            product_id=product.ref,
            role_arn=launch_role.role_arn,
            description=f"Launch as {launch_role.role_arn}",
        )
        role_constraint.add_depends_on(portfolio_association)

        # Create the deployment asset as an output to pass to pipeline stack
        deployment_asset = aws_s3_assets.Asset(
            self, "DeploymentAsset", path="./deployment_pipeline"
        )

        deployment_asset.grant_read(grantee=launch_role)

        # Ouput the deployment bucket and key, for input into pipeline stack
        core.CfnOutput(
            self,
            "CodeCommitSeedBucket",
            value=deployment_asset.s3_bucket_name,
        )
        core.CfnOutput(self, "CodeCommitSeedKey", value=deployment_asset.s3_object_key)
