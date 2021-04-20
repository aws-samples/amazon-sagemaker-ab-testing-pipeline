from aws_cdk import (
    core,
    aws_iam,
    aws_sagemaker,
)

from datetime import datetime
import logging
from deployment_config import DeploymentConfig, VariantConfig
from model_registry import ModelRegistry

logger = logging.getLogger(__name__)


class SageMakerStack(core.Stack):
    def __init__(
        self,
        scope: core.Construct,
        construct_id: str,
        deployment_config: DeploymentConfig,
        project_name: str,
        project_id: str,
        endpoint_name: str,
        tags: list,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Define the package group names for champion and challenger
        champion_package_group = f"{project_name}-champion"
        challenger_package_group = f"{project_name}-challenger"
        challenger_creation_time: datetime = None

        # Create the model package groups if they don't exist
        registry = ModelRegistry()
        registry.create_model_package_group(
            champion_package_group,
            "Champion Models for A/B Testing",
            project_name,
            project_id,
        )
        registry.create_model_package_group(
            challenger_package_group,
            "Challenger Models for A/B Testing",
            project_name,
            project_id,
        )

        # If we don't have a specific champion variant defined, get the latest approved
        if deployment_config.champion_variant_config is None:
            logger.info("Selecting top champion variant")
            p = registry.get_latest_approved_packages(
                champion_package_group, max_results=1
            )[0]
            deployment_config.champion_variant_config = VariantConfig(
                model_package_version=p["ModelPackageVersion"],
                model_package_arn=p["ModelPackageArn"],
                initial_variant_weight=1,
                instance_count=deployment_config.instance_count,
                instance_type=deployment_config.instance_type,
            )
            challenger_creation_time = p["CreationTime"]
        else:
            # Get the versioned package and update ARN
            version = deployment_config.champion_variant_config.model_package_version
            logger.info(f"Selecting champion version {version}")
            p = registry.get_versioned_approved_packages(
                champion_package_group,
                model_package_versions=[version],
            )[0]
            deployment_config.champion_variant_config.model_package_arn = p[
                "ModelPackageArn"
            ]

        # If we don't have challenger variant config, get the latest after challenger creation time
        if deployment_config.challenger_variant_config is None:
            logger.info(
                f"Selecting top {deployment_config.challenger_variant_count} challenger variants created after {challenger_creation_time}"
            )
            deployment_config.challenger_variant_config = [
                VariantConfig(
                    model_package_version=p["ModelPackageVersion"],
                    model_package_arn=p["ModelPackageArn"],
                    initial_variant_weight=1,
                    instance_count=deployment_config.instance_count,
                    instance_type=deployment_config.instance_type,
                )
                for p in registry.get_latest_approved_packages(
                    challenger_package_group,
                    max_results=deployment_config.challenger_variant_count,
                    creation_time_after=challenger_creation_time,
                )
            ]
        else:
            # Get the versioned packages and update ARN
            versions = [
                c.model_package_version
                for c in deployment_config.challenger_variant_config
            ]
            logger.info(f"Selecting challenger versions {versions}")
            ps = registry.get_versioned_approved_packages(
                challenger_package_group,
                model_package_versions=versions,
            )
            for i, vc in enumerate(deployment_config.challenger_variant_config):
                vc.model_package_arn = ps[i]["ModelPackageArn"]

        # Get the service catalog role
        service_catalog_role = aws_iam.Role.from_role_arn(
            self,
            "SageMakerRole",
            f"arn:aws:iam::{self.account}:role/service-role/AmazonSageMakerServiceCatalogProductsUseRole",
        )

        # Add the champion and challenger variants
        model_configs = [
            deployment_config.champion_variant_config
        ] + deployment_config.challenger_variant_config

        model_variants = []
        for i, variant_config in enumerate(model_configs):
            # If variant name not in config use "Champion" for the latest approved and "Challenge{N}" for next N pending
            variant_name = variant_config.variant_name or (
                f"Champion{variant_config.model_package_version}"
                if i == 0
                else f"Challenger{variant_config.model_package_version}"
            )

            # Do not use a custom named resource for models as these get replaced
            model = aws_sagemaker.CfnModel(
                self,
                variant_name,
                execution_role_arn=service_catalog_role.role_arn,
                primary_container=aws_sagemaker.CfnModel.ContainerDefinitionProperty(
                    model_package_name=variant_config.model_package_arn,
                ),
            )

            # Create the production variant
            model_variant = aws_sagemaker.CfnEndpointConfig.ProductionVariantProperty(
                initial_instance_count=variant_config.instance_count,
                initial_variant_weight=variant_config.initial_variant_weight,
                instance_type=variant_config.instance_type,
                model_name=model.attr_model_name,
                variant_name=variant_name,
            )
            model_variants.append(model_variant)

        if len(model_variants) == 0:
            raise Exception("No model variants matching configuration")

        endpoint_config = aws_sagemaker.CfnEndpointConfig(
            self,
            "EndpointConfig",
            production_variants=model_variants,
        )

        self.endpoint = aws_sagemaker.CfnEndpoint(
            self,
            "Endpoint",
            endpoint_config_name=endpoint_config.attr_endpoint_config_name,
            endpoint_name=endpoint_name,
            tags=tags,
        )
