from algorithm import EpsilonGreedy, UCB1, ThompsonSampling, WeightedSampling


def test_epsilon_greedy():
    algo = EpsilonGreedy(
        [
            {
                "variant_name": "v1",
                "invocation_count": 10,
                "reward_sum": 1,
            },
            {
                "variant_name": "v2",
                "invocation_count": 10,
                "reward_sum": 2,
            },
        ],
        epsilon=0.1,
    )

    # Validate that at least 90% of the time we v2
    lst = [algo.select_variant() for i in range(100)]
    v1_count = lst.count("v1")
    v2_count = lst.count("v2")
    # Assert with a margin of error for randomness
    assert v1_count < 20
    assert v2_count > 80


def test_UCB1_exploit():
    algo = UCB1(
        [
            {
                "variant_name": "v1",
                "invocation_count": 100,
                "reward_sum": 10,
            },
            {
                "variant_name": "v2",
                "invocation_count": 100,
                "reward_sum": 20,
            },
            {
                "variant_name": "v3",
                "invocation_count": 100,
                "reward_sum": 50,
            },
        ]
    )
    # For high values, validate the we pick the best performing
    v = algo.select_variant()
    assert v == "v3"


def test_UCB1_explore():
    algo = UCB1(
        [
            {
                "variant_name": "v1",
                "invocation_count": 10,
                "reward_sum": 1,
            },
            {
                "variant_name": "v2",
                "invocation_count": 10,
                "reward_sum": 2,
            },
            {
                "variant_name": "v3",
                "invocation_count": 100,
                "reward_sum": 50,
            },
        ]
    )
    # For low confidence values, pick the best
    v = algo.select_variant()
    assert v == "v2"


def test_thompson_sampling():
    algo = ThompsonSampling(
        [
            {
                "variant_name": "v1",
                "invocation_count": 10,
                "reward_sum": 1,
            },
            {
                "variant_name": "v2",
                "invocation_count": 10,
                "reward_sum": 2,
            },
            {
                "variant_name": "v3",
                "invocation_count": 10,
                "reward_sum": 5,
            },
        ]
    )

    lst = [algo.select_variant() for i in range(100)]
    assert max(lst, key=lst.count) == "v3"


def test_weighted_sampling():
    algo = WeightedSampling(
        [
            {"variant_name": "v1", "initial_variant_weight": 0.9},
            {"variant_name": "v2", "initial_variant_weight": 0.1},
        ],
    )

    lst = [algo.select_variant() for i in range(100)]
    assert max(lst, key=lst.count) == "v1"
