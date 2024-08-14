import pytest

from modyn.config.schema.pipeline.trigger.drift.metric import DynamicThresholdCriterion, ThresholdDecisionCriterion
from modyn.supervisor.internal.triggers.drift.decision_policy import DynamicDecisionPolicy, ThresholdDecisionPolicy


def test_threshold_decision_policy() -> None:
    config = ThresholdDecisionCriterion(threshold=0.5)
    policy = ThresholdDecisionPolicy(config)

    assert policy.evaluate_decision(0.6)
    assert not policy.evaluate_decision(0.4)


@pytest.mark.parametrize("percentile", [0.1, 0.5, 0.9])
def test_dynamic_decision_policy_initial(percentile: float) -> None:
    config = DynamicThresholdCriterion(window_size=3, percentile=percentile)
    policy = DynamicDecisionPolicy(config)

    # Initially, the deque is empty, so any value should trigger a drift
    assert policy.evaluate_decision(0.5)


def test_dynamic_decision_policy_with_observations() -> None:
    config = DynamicThresholdCriterion(window_size=3, percentile=0.5)
    policy = DynamicDecisionPolicy(config)

    # Add initial observations
    policy.score_observations.extend([0.4, 0.6, 0.7])

    # Testing with various distances
    assert not policy.evaluate_decision(0.3)  # Less than all observations
    assert policy.evaluate_decision(0.8)  # Greater than all observations
    assert not policy.evaluate_decision(0.5)  # 0.5 is at the 50th percentile


def test_dynamic_decision_policy_window_size() -> None:
    config = DynamicThresholdCriterion(window_size=3, percentile=0.5)
    policy = DynamicDecisionPolicy(config)

    # Add observations to fill the window
    policy.evaluate_decision(0.4)
    policy.evaluate_decision(0.6)
    policy.evaluate_decision(0.7)

    # Adding another observation should remove the oldest one (0.4)
    assert policy.evaluate_decision(0.8)  # Greater than all observations
    assert len(policy.score_observations) == 3  # Ensure the deque is still at max length


def test_dynamic_decision_policy_percentile() -> None:
    config = DynamicThresholdCriterion(window_size=4, percentile=0.75)
    policy = DynamicDecisionPolicy(config)

    # Add observations
    policy.evaluate_decision(0.4)
    policy.evaluate_decision(0.6)
    policy.evaluate_decision(0.7)
    policy.evaluate_decision(0.9)

    assert not policy.evaluate_decision(0.5)
    assert policy.evaluate_decision(0.8)
    assert not policy.evaluate_decision(0.7)
