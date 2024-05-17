from modyn.supervisor.internal.eval_strategies import MatrixEvalStrategy


def get_minimal_eval_strategies_config() -> dict:
    return {
        "eval_every": "100s",
        "eval_start_from": 0,
        "eval_end_at": 300,
    }


def test_initialization() -> None:
    eval_strategy = MatrixEvalStrategy(get_minimal_eval_strategies_config())
    assert eval_strategy.eval_every == 100
    assert eval_strategy.eval_start_from == 0
    assert eval_strategy.eval_end_at == 300


def test_get_eval_intervals() -> None:
    config = get_minimal_eval_strategies_config()
    eval_strategy = MatrixEvalStrategy(config)
    assert list(eval_strategy.get_eval_intervals(0, 0)) == [
        (0, 100),
        (100, 200),
        (200, 300),
    ]

    config["eval_start_from"] = 50
    config["eval_every"] = "60s"
    eval_strategy = MatrixEvalStrategy(config)
    assert list(eval_strategy.get_eval_intervals(0, 0)) == [
        (50, 110),
        (110, 170),
        (170, 230),
        (230, 290),
        (290, 300),
    ]