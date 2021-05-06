import random
import math

# Contains pure python class implementations for WeightedSampling, EpsilonGreedy, UCB1 and ThompsonSampling.
# For maths and theory behind these algorithms see the following resource:
# https://lilianweng.github.io/lil-log/2018/01/23/the-multi-armed-bandit-problem-and-its-solutions.html#ucb1


class AlgorithmBase:
    """
    Base class for implementing the following bandit strategiesß
    1. Epsilom Greedy
    2. UCB
    3. Thompson Smampling
    """

    def __init__(self, variant_metrics: list):
        pass

    @staticmethod
    def argmax(a):
        """
        This is a pure-python version of the np.argmax() given we don't support numpy.
        """
        return max(range(len(a)), key=lambda x: a[x])

    @staticmethod
    def random_beta(alpha, beta):
        """
        Pure python implement of random beta
        """
        return random.betavariate(alpha, beta)


class WeightedSampling(AlgorithmBase):
    STRATEGY_NAME = "WeightedSampling"

    def __init__(self, variant_metrics: list):
        if len(variant_metrics) == 0:
            raise Exception("Require at least one encpoint variant")
        self.variant_metrics = variant_metrics

    def select_variant(self):
        variant_names = [ev["variant_name"] for ev in self.variant_metrics]
        variant_weights = [ev["initial_variant_weight"] for ev in self.variant_metrics]
        return random.choices(variant_names, weights=variant_weights)[0]


class EpsilonGreedy(AlgorithmBase):
    STRATEGY_NAME = "EpsilonGreedy"

    def __init__(self, variant_metrics: list, epsilon: float):
        if len(variant_metrics) == 0:
            raise Exception("Require at least one endpoint variant")
        self.variant_metrics = variant_metrics
        if epsilon < 0 or epsilon > 1:
            raise Exception("Epsilon must be value between 0 and 1")
        self.epsilon = epsilon

    def select_variant(self):
        """
        The Epsilon-Greedy algorithm balances exploitation and exploration fairly basically.
        It takes a parameter, epsilon, between 0 and 1, as the probability of exploring the variants
        as opposed to exploiting the current best variant in the test.
        """
        if random.random() > self.epsilon:
            rates = [
                1.0 * v["reward_sum"] / v["invocation_count"]
                for v in self.variant_metrics
            ]
            variant_index = AlgorithmBase.argmax(rates)
        else:
            variant_index = random.randrange(len(self.variant_metrics))
        return self.variant_metrics[variant_index]["variant_name"]


class UCB1(AlgorithmBase):
    STRATEGY_NAME = "UCB1"

    def __init__(self, variant_metrics: list):
        if len(variant_metrics) == 0:
            raise Exception("Require at least one endpoint variant")
        self.variant_metrics = variant_metrics

    def select_variant(self):
        """
        UCB1 algorithm is its “curiosity bonus”. When selecting an arm,
        it takes the expected reward of each arm and then adds a bonus
        which is calculated in inverse proportion to the confidence of that reward.
        It is optimistic about uncertainty. So lower confidence arms are given a bit
        of a boost relative to higher confidence arms.
        """
        invocation_total = sum([v["invocation_count"] for v in self.variant_metrics])
        ucb_values = []
        for v in self.variant_metrics:
            curiosity_bonus = math.sqrt(
                (2 * math.log(invocation_total)) / float(v["invocation_count"])
            )
            rate = 1.0 * v["reward_sum"] / v["invocation_count"]
            ucb_values.append(rate + curiosity_bonus)
        variant_index = AlgorithmBase.argmax(ucb_values)
        return self.variant_metrics[variant_index]["variant_name"]


class ThompsonSampling(AlgorithmBase):
    STRATEGY_NAME = "ThompsonSampling"

    def __init__(self, variant_metrics: list):
        if len(variant_metrics) == 0:
            raise Exception("Require at least one endpoint variant")
        self.variant_metrics = variant_metrics

    def select_variant(self):
        """
        Tompson sampling uses Beta distribution takes two parameters, ‘α’ (alpha) and ‘β’ (beta).
        In the simplest terms these parameters can be thought of as respectively the count of successes and failures.
        see: https://towardsdatascience.com/thompson-sampling-fc28817eacb8
        """
        probs = []
        for v in self.variant_metrics:
            success = v["reward_sum"]
            failure = v["invocation_count"] - success
            probs.append(AlgorithmBase.random_beta(1 + success, 1 + failure))
        variant_index = AlgorithmBase.argmax(probs)
        return self.variant_metrics[variant_index]["variant_name"]
