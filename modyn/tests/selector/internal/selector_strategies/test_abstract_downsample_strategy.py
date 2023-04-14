import os
import pathlib
import shutil
import tempfile

import pytest
from modyn.metadata_database.metadata_database_connection import MetadataDatabaseConnection
from modyn.metadata_database.models import SelectorStateMetadata
from modyn.selector.internal.selector_strategies.abstract_downsample_strategy import AbstractDownsampleStrategy

database_path = pathlib.Path(os.path.abspath(__file__)).parent / "test_storage.db"

TMP_DIR = tempfile.mkdtemp()


def get_minimal_modyn_config():
    return {
        "metadata_database": {
            "drivername": "sqlite",
            "username": "",
            "password": "",
            "host": "",
            "port": "0",
            "database": f"{database_path}",
        },
        "selector": {"insertion_threads": 8, "trigger_sample_directory": TMP_DIR},
    }


@pytest.fixture(scope="function", autouse=True)
def setup_and_teardown():
    pathlib.Path(TMP_DIR).mkdir(parents=True, exist_ok=True)
    with MetadataDatabaseConnection(get_minimal_modyn_config()) as database:
        database.create_tables()
    yield

    os.remove(database_path)
    shutil.rmtree(TMP_DIR)


def get_config():
    return {"reset_after_trigger": False, "presampling_ratio": 50, "limit": -1, "downsampled_batch_size": 10}


def test_constructor():
    strat = AbstractDownsampleStrategy(get_config(), get_minimal_modyn_config(), 0, 1000)
    assert strat.presampling_ratio >= 0


def test_constructor_throws_on_invalid_config():
    conf = get_config()

    conf = get_config()
    conf["presampling_ratio"] = 0

    with pytest.raises(ValueError):
        AbstractDownsampleStrategy(conf, get_minimal_modyn_config(), 0, 1000)

    conf["presampling_ratio"] = 101

    with pytest.raises(ValueError):
        AbstractDownsampleStrategy(conf, get_minimal_modyn_config(), 0, 1000)


def test_inform_data():
    strat = AbstractDownsampleStrategy(get_config(), get_minimal_modyn_config(), 0, 1000)
    strat.inform_data([10, 11, 12], [0, 1, 2], ["dog", "dog", "cat"])

    with MetadataDatabaseConnection(get_minimal_modyn_config()) as database:
        data = database.session.query(
            SelectorStateMetadata.sample_key,
            SelectorStateMetadata.timestamp,
            SelectorStateMetadata.label,
            SelectorStateMetadata.pipeline_id,
            SelectorStateMetadata.used,
        ).all()

        assert len(data) == 3

        keys, timestamps, labels, pipeline_ids, useds = zip(*data)

        assert not any(useds)
        for pip_id in pipeline_ids:
            assert pip_id == 0

        assert keys[0] == 10 and keys[1] == 11 and keys[2] == 12
        assert timestamps[0] == 0 and timestamps[1] == 1 and timestamps[2] == 2
        assert labels[0] == "dog" and labels[1] == "dog" and labels[2] == "cat"


def test_dataset_size():
    strat = AbstractDownsampleStrategy(get_config(), get_minimal_modyn_config(), 0, 1000)
    strat.inform_data([10, 11, 12], [0, 1, 2], ["dog", "dog", "cat"])

    assert strat._get_dataset_size() == 3

    strat.inform_data([110, 111, 112], [0, 1, 2], ["dog", "dog", "cat"])

    assert strat._get_dataset_size() == 6


def test_dataset_size_various_scenarios():
    data1 = list(range(10))
    timestamps1 = list(range(10))
    labels1 = [0] * 10

    data2 = list(range(10, 40))
    timestamps2 = list(range(10, 40))
    labels2 = [0] * 30

    conf = get_config()
    conf["limit"] = -1
    conf["reset_after_trigger"] = True

    # first trigger
    strat = AbstractDownsampleStrategy(conf, get_minimal_modyn_config(), 0, 100)
    strat.inform_data(data1, timestamps1, labels1)
    assert strat.get_presampling_target_size() == 5  # 50% of presampling
    trigger_id, trigger_num_keys, trigger_num_partitions = strat.trigger()
    assert trigger_num_keys == 5
    assert trigger_num_partitions == 1

    # second trigger
    strat.inform_data(data2, timestamps2, labels2)
    assert strat.get_presampling_target_size() == 15  # 50% of presampling

    # limited capacity
    strat.has_limit = True
    strat.training_set_size_limit = 10
    assert strat.get_presampling_target_size() == 15

    # only trigger data
    trigger_id, trigger_num_keys, trigger_num_partitions = strat.trigger()
    assert all(int(key) >= 10 for (key, _) in strat.get_trigger_partition_keys(trigger_id, 0))

    # remove the trigger
    strat.reset_after_trigger = False
    assert strat.get_presampling_target_size() == 20

    # remove the limit
    strat.has_limit = False
    assert strat.get_presampling_target_size() == 20

    # adjust the presampling
    strat.presampling_ratio = 75
    assert strat.get_presampling_target_size() == 30


def test_stmt():
    strat = AbstractDownsampleStrategy(get_config(), get_minimal_modyn_config(), 0, 1000)
    strat.inform_data([10, 11, 12], [0, 1, 2], ["dog", "dog", "cat"])
    strat.has_limit = True
    strat.training_set_size_limit = 10

    stmt = strat.get_postgres_stmt()
    assert "LIMIT" in str(stmt)
    assert "TABLESAMPLE" not in str(stmt)  # change this test when #224 is solved

    stmt = strat.get_general_stmt()
    assert "LIMIT" in str(stmt)
    assert "TABLESAMPLE" not in str(stmt)


def test_get_all_data():
    strat = AbstractDownsampleStrategy(get_config(), get_minimal_modyn_config(), 0, 1000)
    strat.inform_data([10, 11, 12], [0, 1, 2], ["dog", "dog", "cat"])

    assert strat._get_dataset_size() == 3

    generator = strat._get_all_data()

    assert list(generator) == [[10, 11, 12]]

    strat._maximum_keys_in_memory = 2

    generator = strat._get_all_data()

    assert list(data for data in generator) == [[10, 11], [12]]


def test_on_trigger():
    strat = AbstractDownsampleStrategy(get_config(), get_minimal_modyn_config(), 0, 1000)
    strat.inform_data([10, 11, 12, 13, 14, 15], [0, 1, 2, 3, 4, 5], ["dog", "dog", "cat", "bird", "snake", "bird"])

    generator = strat._on_trigger()

    assert len(list(generator)[0]) == 3


def test_on_trigger_multi_chunks():
    config = get_config()
    config["presampling_ratio"] = 40
    strat = AbstractDownsampleStrategy(config, get_minimal_modyn_config(), 0, 1000)

    strat.inform_data([10, 11, 12, 13, 14, 15], [0, 1, 2, 3, 4, 5], ["dog", "dog", "cat", "bird", "snake", "bird"])
    strat._maximum_keys_in_memory = 4

    generator = strat._on_trigger()
    indexes = list(generator)
    assert len(indexes) == 1
    assert len(indexes[0]) == 2


def test_on_trigger_multi_chunks_unbalanced():
    config = get_config()
    strat = AbstractDownsampleStrategy(config, get_minimal_modyn_config(), 0, 1000)

    strat.inform_data([10, 11, 12, 13, 14, 15], [0, 1, 2, 3, 4, 5], ["dog", "dog", "cat", "bird", "snake", "bird"])
    strat._maximum_keys_in_memory = 2

    generator = strat._on_trigger()
    indexes = list(generator)
    assert len(indexes) == 2
    assert len(indexes[0]) == 2
    assert len(indexes[1]) == 1


def test_on_trigger_multi_chunks_bis():
    config = get_config()
    config["presampling_ratio"] = 70
    strat = AbstractDownsampleStrategy(config, get_minimal_modyn_config(), 0, 1000)

    strat.inform_data([10, 11, 12, 13, 14, 15], [0, 1, 2, 3, 4, 5], ["dog", "dog", "cat", "bird", "snake", "bird"])
    strat._maximum_keys_in_memory = 2

    generator = strat._on_trigger()
    indexes = list(generator)
    assert len(indexes) == 2
    assert len(indexes[0]) == 2
    assert set(key for key, _ in indexes[0]) < set([10, 11, 12, 13, 14, 15])


def test_no_presampling():
    config = get_config()
    config["presampling_ratio"] = 100
    strat = AbstractDownsampleStrategy(config, get_minimal_modyn_config(), 0, 1000)

    strat.inform_data([10, 11, 12, 13, 14, 15], [0, 1, 2, 3, 4, 5], ["dog", "dog", "cat", "bird", "snake", "bird"])
    strat._maximum_keys_in_memory = 5

    generator = strat._on_trigger()
    indexes = list(generator)
    assert len(indexes) == 2
    assert len(indexes[0]) == 5
    assert len(indexes[1]) == 1
    assert set(key for key, _ in indexes[0]) == set([10, 11, 12, 13, 14])
    assert indexes[1][0] == (15, 1.0)


def test_chunking():
    config = get_config()
    config["presampling_ratio"] = 90
    strat = AbstractDownsampleStrategy(config, get_minimal_modyn_config(), 0, 1000)

    strat.inform_data([10, 11, 12, 13, 14, 15], [0, 1, 2, 3, 4, 5], ["dog", "dog", "cat", "bird", "snake", "bird"])
    strat._maximum_keys_in_memory = 2

    generator = strat._on_trigger()
    indexes = list(generator)
    assert len(indexes) == 3
    assert len(indexes[0]) == 2
    assert len(indexes[1]) == 2
    assert len(indexes[2]) == 1
    assert set(key for key, _ in indexes[0]) <= set([10, 11, 12])


def test_chunking_with_stricter_limit():
    config = get_config()
    config["presampling_ratio"] = 90  # presampling should produce 5 points
    config["limit"] = 3  # but the limit is stricter so we get only 3
    strat = AbstractDownsampleStrategy(config, get_minimal_modyn_config(), 0, 1000)

    strat.inform_data([10, 11, 12, 13, 14, 15], [0, 1, 2, 3, 4, 5], ["dog", "dog", "cat", "bird", "snake", "bird"])
    strat._maximum_keys_in_memory = 2

    generator = strat._on_trigger()
    indexes = list(generator)
    assert len(indexes) == 2
    assert len(indexes[0]) == 2
    assert len(indexes[1]) == 1


def test_chunking_with_stricter_presampling():
    config = get_config()
    config["presampling_ratio"] = 50
    config["limit"] = 4
    strat = AbstractDownsampleStrategy(config, get_minimal_modyn_config(), 0, 1000)

    strat.inform_data([10, 11, 12, 13, 14, 15], [0, 1, 2, 3, 4, 5], ["dog", "dog", "cat", "bird", "snake", "bird"])
    strat._maximum_keys_in_memory = 5

    generator = strat._on_trigger()
    indexes = list(generator)
    assert len(indexes) == 1
    assert len(indexes[0]) == 3


def test_no_presampling_with_limit():
    config = get_config()
    config["presampling_ratio"] = 100
    config["limit"] = 3
    strat = AbstractDownsampleStrategy(config, get_minimal_modyn_config(), 0, 1000)

    strat.inform_data([10, 11, 12, 13, 14, 15], [0, 1, 2, 3, 4, 5], ["dog", "dog", "cat", "bird", "snake", "bird"])
    strat._maximum_keys_in_memory = 5

    generator = strat._on_trigger()
    indexes = list(generator)
    assert len(indexes) == 1
    assert len(indexes[0]) == 3
