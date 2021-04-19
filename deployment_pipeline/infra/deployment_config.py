from enum import Enum


class InstanceConfig:
    def __init__(self, instance_count: int = 1, instance_type: str = "ml.t2.medium"):
        self.instance_count = instance_count
        self.instance_type = instance_type


class VariantConfig(InstanceConfig):
    def __init__(
        self,
        model_package_version: str,
        initial_variant_weight: float = 1.0,
        variant_name: str = None,
        instance_count: int = 1,
        instance_type: str = "ml.t2.medium",
        model_package_arn: str = None,
    ):
        self.model_package_version = model_package_version
        self.initial_variant_weight = initial_variant_weight
        self.variant_name = variant_name
        self.model_package_arn = model_package_arn
        super().__init__(instance_count, instance_type)


class AlgorithmStrategy(Enum):
    WEIGHTED_SAMPLING = 0
    EPSILOM_GREEDY = 1
    UCB1 = 2
    THOMPSON_SAMPLING = 3


class DeploymentConfig(InstanceConfig):
    def __init__(
        self,
        stage_name: str,
        challenger_variant_count: int = 1,
        champion_variant_config: dict = None,
        challenger_variant_config: list = None,
        instance_count: int = 1,
        instance_type: str = "ml.t2.medium",
        strategy: str = "ThompsonSampling",
        warmup: int = 0,
        epsilon: float = 0.1,
    ):
        self.stage_name = stage_name
        # Provide either the challenger variant count, or specific champion/challenger config
        self.challenger_variant_count = challenger_variant_count
        # Turn dict into typed object
        if type(champion_variant_config) is dict:
            self.champion_variant_config = VariantConfig(
                **{
                    "instance_count": instance_count,
                    "instance_type": instance_type,
                    **champion_variant_config,
                }
            )
        else:
            self.champion_variant_config = None
        # Turn list into typed objects
        if type(challenger_variant_config) is list:
            self.challenger_variant_config = [
                # Use deployment instance count/type as default for variant config
                VariantConfig(
                    **{
                        "instance_count": instance_count,
                        "instance_type": instance_type,
                        **vc,
                    }
                )
                for vc in challenger_variant_config
            ]
        else:
            self.challenger_variant_config = None
        self.strategy = strategy
        self.warmup = warmup
        self.epsilon = epsilon
        super().__init__(instance_count, instance_type)
