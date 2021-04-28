from aws_cdk import (
    core,
    aws_iam,
    aws_cloudformation as cloudformation,
    aws_events as events,
    aws_events_targets as targets,
    aws_codebuild as codebuild,
    aws_codecommit as codecommit,
    aws_codepipeline as codepipeline,
    aws_codepipeline_actions as codepipeline_actions,
    aws_lambda as lambda_,
    aws_s3 as s3,
    aws_s3_assets as s3_assets,
)


class PipelineStack(core.Stack):
    def __init__(
        self,
        scope: core.Construct,
        construct_id: str,
        # deployment_asset: s3_assets.Asset,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Create Required parameters for sagemaker projects
        # see: https://docs.aws.amazon.com/sagemaker/latest/dg/sagemaker-projects-templates-custom.html
        # see also: # https://docs.aws.amazon.com/cdk/latest/guide/parameters.html
        project_name = core.CfnParameter(
            self,
            "SageMakerProjectName",
            type="String",
            description="The name of the SageMaker project.",
            min_length=1,
            max_length=32,
        )
        project_id = core.CfnParameter(
            self,
            "SageMakerProjectId",
            type="String",
            min_length=1,
            max_length=16,
            description="Service generated Id of the project.",
        )
        stage_name = core.CfnParameter(
            self,
            "StageName",
            type="String",
            min_length=1,
            max_length=8,
            description="The stage name.",
            default="dev",
        )
        seed_bucket = core.CfnParameter(
            self,
            "CodeCommitSeedBucket",
            type="String",
            description="The optional s3 seed bucket",
            min_length=1,
        )
        seed_key = core.CfnParameter(
            self,
            "CodeCommitSeedKey",
            type="String",
            description="The optional s3 seed key",
            min_length=1,
        )

        # Get the service catalog role for all permssions (if None CDK will create new roles)
        # CodeBuild and CodePipeline resources need to start with "sagemaker-" to be within default policy
        service_catalog_role = aws_iam.Role.from_role_arn(
            self,
            "PipelineRole",
            f"arn:{self.partition}:iam::{self.account}:role/service-role/AmazonSageMakerServiceCatalogProductsUseRole",
        )

        # Define the repository name and branch
        branch_name = "main"

        # Create source repo from seed bucket/key
        repo = codecommit.CfnRepository(
            self,
            "CodeRepo",
            repository_name="sagemaker-{}-repo".format(project_name.value_as_string),
            repository_description="Amazon SageMaker A/B testing pipeline",
            code=codecommit.CfnRepository.CodeProperty(
                s3=codecommit.CfnRepository.S3Property(
                    bucket=seed_bucket.value_as_string,
                    key=seed_key.value_as_string,
                    object_version=None,
                ),
                branch_name=branch_name,
            ),
            tags=[
                core.CfnTag(
                    key="sagemaker:deployment-stage", value=stage_name.value_as_string
                ),
                core.CfnTag(
                    key="sagemaker:project-id", value=project_id.value_as_string
                ),
                core.CfnTag(
                    key="sagemaker:project-name", value=project_name.value_as_string
                ),
            ],
        )

        # Reference the newly created repository
        code = codecommit.Repository.from_repository_name(
            self, "ImportedRepo", repo.attr_name
        )

        cdk_build = codebuild.PipelineProject(
            self,
            "CdkBuild",
            project_name="sagemaker-{}-cdk-{}".format(
                project_name.value_as_string, stage_name.value_as_string
            ),
            role=service_catalog_role,
            build_spec=codebuild.BuildSpec.from_object(
                dict(
                    version="0.2",
                    phases=dict(
                        install=dict(
                            commands=[
                                "npm install aws-cdk",
                                "npm update",
                                "python -m pip install -r requirements.txt",
                            ]
                        ),
                        build=dict(
                            commands=[
                                "npx cdk synth -o dist --path-metadata false",
                            ]
                        ),
                    ),
                    artifacts={
                        "base-directory": "dist",
                        "files": ["*.template.json"],
                    },
                    environment=dict(
                        buildImage=codebuild.LinuxBuildImage.AMAZON_LINUX_2_3,
                    ),
                )
            ),
            environment_variables={
                "SAGEMAKER_PROJECT_NAME": codebuild.BuildEnvironmentVariable(
                    value=project_name.value_as_string
                ),
                "SAGEMAKER_PROJECT_ID": codebuild.BuildEnvironmentVariable(
                    value=project_id.value_as_string
                ),
                "STAGE_NAME": codebuild.BuildEnvironmentVariable(
                    value=stage_name.value_as_string
                ),
            },
        )

        source_output = codepipeline.Artifact()
        cdk_build_output = codepipeline.Artifact()

        # Create the s3 artifact (name must be < 63 chars)
        s3_artifact = s3.Bucket(
            self,
            "S3Artifact",
            bucket_name="sagemaker-{}-artifact-{}-{}".format(
                project_id.value_as_string, stage_name.value_as_string, self.region
            ),
            removal_policy=core.RemovalPolicy.DESTROY,
        )

        deploy_pipeline = codepipeline.Pipeline(
            self,
            "Pipeline",
            role=service_catalog_role,
            artifact_bucket=s3_artifact,
            pipeline_name="sagemaker-{}-pipeline-{}".format(
                project_name.value_as_string, stage_name.value_as_string
            ),
            stages=[
                codepipeline.StageProps(
                    stage_name="Source",
                    actions=[
                        codepipeline_actions.CodeCommitSourceAction(
                            action_name="CodeCommit_Source",
                            repository=code,
                            trigger=codepipeline_actions.CodeCommitTrigger.NONE,  # Created below
                            event_role=service_catalog_role,
                            output=source_output,
                            branch=branch_name,
                            role=service_catalog_role,
                        )
                    ],
                ),
                codepipeline.StageProps(
                    stage_name="Build",
                    actions=[
                        codepipeline_actions.CodeBuildAction(
                            action_name="CDK_Build",
                            project=cdk_build,
                            input=source_output,
                            outputs=[
                                cdk_build_output,
                            ],
                            role=service_catalog_role,
                        ),
                    ],
                ),
                codepipeline.StageProps(
                    stage_name="Deploy",
                    actions=[
                        codepipeline_actions.CloudFormationCreateUpdateStackAction(
                            action_name="SageMaker_CFN_Deploy",
                            run_order=1,
                            template_path=cdk_build_output.at_path(
                                "ab-testing-sagemaker.template.json"
                            ),
                            stack_name="sagemaker-{}-deploy-{}".format(
                                project_name.value_as_string, stage_name.value_as_string
                            ),
                            admin_permissions=False,
                            role=service_catalog_role,
                            deployment_role=service_catalog_role,
                            replace_on_failure=True,
                        ),
                    ],
                ),
            ],
        )

        # Add deploy role to target the code pipeline when model package is approved
        deploy_rule = events.Rule(
            self,
            "DeployRule",
            rule_name="sagemaker-{}-model-{}".format(
                project_name.value_as_string, stage_name.value_as_string
            ),
            description="Rule to trigger a deployment when SageMaker Model registry is updated with a new model package.",
            event_pattern=events.EventPattern(
                source=["aws.sagemaker"],
                detail_type=["SageMaker Model Package State Change"],
                detail={
                    "ModelPackageGroupName": [
                        f"{project_name.value_as_string}-champion",
                        f"{project_name.value_as_string}-challenger",
                    ]
                },
            ),
            targets=[
                targets.CodePipeline(
                    pipeline=deploy_pipeline,
                    event_role=service_catalog_role,
                )
            ],
        )

        code_rule = events.Rule(
            self,
            "CodeRule",
            rule_name="sagemaker-{}-code-{}".format(
                project_name.value_as_string, stage_name.value_as_string
            ),
            description="Rule to trigger a deployment when deployment configured is updated in CodeCommit.",
            event_pattern=events.EventPattern(
                source=["aws.codecommit"],
                detail_type=["CodeCommit Repository State Change"],
                detail={
                    "event": ["referenceCreated", "referenceUpdated"],
                    "referenceType": ["branch"],
                    "referenceName": [branch_name],
                },
                resources=[code.repository_arn],
            ),
            targets=[
                targets.CodePipeline(
                    pipeline=deploy_pipeline,
                    event_role=service_catalog_role,
                )
            ],
        )
