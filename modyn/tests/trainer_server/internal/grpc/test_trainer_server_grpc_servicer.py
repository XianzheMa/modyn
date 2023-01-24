# pylint: disable=unused-argument, no-name-in-module
import json
import multiprocessing as mp
import tempfile
from io import BytesIO
from unittest import mock
from unittest.mock import patch

import torch
from modyn.trainer_server.internal.grpc.generated.trainer_server_pb2 import (
    CheckpointInfo,
    Data,
    JsonString,
    RegisterTrainServerRequest,
    StartTrainingRequest,
    TrainerAvailableRequest,
    TrainingStatusRequest,
)
from modyn.trainer_server.internal.grpc.trainer_server_grpc_servicer import TrainerServerGRPCServicer
from modyn.trainer_server.internal.utils.trainer_messages import TrainerMessages
from modyn.trainer_server.internal.utils.training_info import TrainingInfo
from modyn.trainer_server.internal.utils.training_process_info import TrainingProcessInfo

start_training_request = StartTrainingRequest(
    training_id=1,
    device="cpu",
    train_until_sample_id="new",
    load_checkpoint_path="test",
)
trainer_available_request = TrainerAvailableRequest()

register_request = RegisterTrainServerRequest(
    training_id=1,
    model_id="test",
    batch_size=32,
    torch_optimizer="SGD",
    torch_criterion="CrossEntropyLoss",
    optimizer_parameters=JsonString(value=json.dumps({"lr": 0.1})),
    model_configuration=JsonString(value=json.dumps({})),
    criterion_parameters=JsonString(value=json.dumps({})),
    data_info=Data(dataset_id="Dataset", num_dataloaders=1),
    checkpoint_info=CheckpointInfo(checkpoint_interval=10, checkpoint_path="/tmp"),
    transform_list=[],
)

get_status_request = TrainingStatusRequest(training_id=1)


class DummyModelWrapper:
    def __init__(self, model_configuration=None) -> None:
        self.model = None


def noop():
    return


def get_training_process_info():
    status_query_queue = mp.Queue()
    status_response_queue = mp.Queue()
    exception_queue = mp.Queue()

    training_process_info = TrainingProcessInfo(
        mp.Process(), exception_queue, status_query_queue, status_response_queue
    )
    return training_process_info


@patch("modyn.trainer_server.internal.utils.training_info.hasattr", return_value=True)
@patch(
    "modyn.trainer_server.internal.utils.training_info.getattr",
    return_value=DummyModelWrapper,
)
def get_training_info(temp, test_getattr=None, test_hasattr=None):
    request = RegisterTrainServerRequest(
        training_id=1,
        data_info=Data(dataset_id="MNIST", num_dataloaders=2),
        optimizer_parameters=JsonString(value=json.dumps({"lr": 0.1})),
        model_configuration=JsonString(value=json.dumps({})),
        criterion_parameters=JsonString(value=json.dumps({})),
        transform_list=[],
        model_id="model",
        torch_optimizer="SGD",
        batch_size=32,
        torch_criterion="CrossEntropyLoss",
        checkpoint_info=CheckpointInfo(checkpoint_interval=10, checkpoint_path=temp),
    )
    training_info = TrainingInfo(request)
    return training_info


def test_trainer_available():
    trainer_server = TrainerServerGRPCServicer()
    response = trainer_server.trainer_available(trainer_available_request, None)
    assert response.available


@patch.object(mp.Process, "is_alive", return_value=True)
def test_trainer_not_available(test_is_alive):
    trainer_server = TrainerServerGRPCServicer()
    trainer_server._training_process_dict[10] = TrainingProcessInfo(mp.Process(), mp.Queue(), mp.Queue(), mp.Queue())
    response = trainer_server.trainer_available(trainer_available_request, None)
    assert not response.available


@patch("modyn.trainer_server.internal.utils.training_info.hasattr", return_value=False)
def test_register_invalid(test_hasattr):
    trainer_server = TrainerServerGRPCServicer()
    response = trainer_server.register(register_request, None)
    assert not response.success
    assert register_request.training_id not in trainer_server._training_dict


@patch("modyn.trainer_server.internal.utils.training_info.hasattr", return_value=True)
@patch(
    "modyn.trainer_server.internal.utils.training_info.getattr",
    return_value=DummyModelWrapper,
)
def test_register(test_getattr, test_hasattr):
    trainer_server = TrainerServerGRPCServicer()
    response = trainer_server.register(register_request, None)
    assert response.success
    assert register_request.training_id in trainer_server._training_dict


def test_start_training_not_registered():
    trainer_server = TrainerServerGRPCServicer()
    response = trainer_server.start_training(start_training_request, None)
    assert not response.training_started


def test_start_training():
    trainer_server = TrainerServerGRPCServicer()
    mock_start = mock.Mock()
    mock_start.side_effect = noop
    trainer_server._training_dict[1] = None
    with patch("multiprocessing.Process.start", mock_start):
        trainer_server.start_training(start_training_request, None)
        assert 1 in trainer_server._training_process_dict


def test_get_training_status_not_registered():
    trainer_server = TrainerServerGRPCServicer()
    response = trainer_server.get_training_status(get_status_request, None)
    assert not response.valid


@patch.object(mp.Process, "is_alive", return_value=True)
@patch.object(TrainerServerGRPCServicer, "get_status", return_value=(b"state", 10, 100))
@patch.object(TrainerServerGRPCServicer, "check_for_training_exception")
@patch.object(TrainerServerGRPCServicer, "get_latest_checkpoint")
def test_get_training_status_alive(
    test_get_latest_checkpoint,
    test_check_for_training_exception,
    test_get_status,
    test_is_alive,
):
    trainer_server = TrainerServerGRPCServicer()
    training_process_info = get_training_process_info()
    trainer_server._training_process_dict[1] = training_process_info
    trainer_server._training_dict[1] = None

    response = trainer_server.get_training_status(get_status_request, None)
    assert response.valid
    assert response.is_running
    assert not response.blocked
    assert response.state_available
    assert response.batches_seen == 10
    assert response.samples_seen == 100
    assert response.state == b"state"
    test_get_latest_checkpoint.assert_not_called()
    test_check_for_training_exception.assert_not_called()


@patch.object(mp.Process, "is_alive", return_value=True)
@patch.object(TrainerServerGRPCServicer, "get_status", return_value=(None, None, None))
@patch.object(TrainerServerGRPCServicer, "check_for_training_exception")
@patch.object(TrainerServerGRPCServicer, "get_latest_checkpoint")
def test_get_training_status_alive_blocked(
    test_get_latest_checkpoint,
    test_check_for_training_exception,
    test_get_status,
    test_is_alive,
):

    trainer_server = TrainerServerGRPCServicer()
    training_process_info = get_training_process_info()
    trainer_server._training_process_dict[1] = training_process_info
    trainer_server._training_dict[1] = None

    response = trainer_server.get_training_status(get_status_request, None)
    assert response.valid
    assert response.is_running
    assert response.blocked
    assert not response.state_available
    test_get_latest_checkpoint.assert_not_called()
    test_check_for_training_exception.assert_not_called()


@patch.object(mp.Process, "is_alive", return_value=False)
@patch.object(TrainerServerGRPCServicer, "get_latest_checkpoint", return_value=(b"state", 10, 100))
@patch.object(TrainerServerGRPCServicer, "check_for_training_exception", return_value="exception")
@patch.object(TrainerServerGRPCServicer, "get_status")
def test_get_training_status_finished_with_exception(
    test_get_status,
    test_check_for_training_exception,
    test_get_latest_checkpoint,
    test_is_alive,
):
    trainer_server = TrainerServerGRPCServicer()
    training_process_info = get_training_process_info()
    trainer_server._training_process_dict[1] = training_process_info
    trainer_server._training_dict[1] = None

    response = trainer_server.get_training_status(get_status_request, None)
    assert response.valid
    assert not response.is_running
    assert not response.blocked
    assert response.state_available
    assert response.batches_seen == 10
    assert response.samples_seen == 100
    assert response.state == b"state"
    assert response.exception == "exception"
    test_get_status.assert_not_called()


@patch.object(mp.Process, "is_alive", return_value=False)
@patch.object(TrainerServerGRPCServicer, "get_latest_checkpoint", return_value=(None, None, None))
@patch.object(TrainerServerGRPCServicer, "check_for_training_exception", return_value="exception")
@patch.object(TrainerServerGRPCServicer, "get_status")
def test_get_training_status_finished_no_checkpoint(
    test_get_status,
    test_check_for_training_exception,
    test_get_latest_checkpoint,
    test_is_alive,
):
    trainer_server = TrainerServerGRPCServicer()
    training_process_info = get_training_process_info()
    trainer_server._training_process_dict[1] = training_process_info
    trainer_server._training_dict[1] = None

    response = trainer_server.get_training_status(get_status_request, None)
    assert response.valid
    assert not response.is_running
    assert not response.state_available
    assert response.exception == "exception"
    test_get_status.assert_not_called()


def test_get_training_status():
    trainer_server = TrainerServerGRPCServicer()
    state_dict = {"state": {}, "num_batches": 10, "num_samples": 100}

    training_process_info = get_training_process_info()
    trainer_server._training_process_dict[1] = training_process_info
    training_process_info.status_response_queue.put(state_dict)
    state, num_batches, num_samples = trainer_server.get_status(1)
    assert state == state_dict["state"]
    assert num_batches == state_dict["num_batches"]
    assert num_samples == state_dict["num_samples"]
    assert training_process_info.status_query_queue.qsize() == 1
    assert training_process_info.status_response_queue.empty()
    query = training_process_info.status_query_queue.get()
    assert query == TrainerMessages.STATUS_QUERY_MESSAGE


def test_check_for_training_exception_not_found():
    trainer_server = TrainerServerGRPCServicer()
    training_process_info = get_training_process_info()
    trainer_server._training_process_dict[1] = training_process_info
    child_exception = trainer_server.check_for_training_exception(1)
    assert child_exception is None


def test_check_for_training_exception_found():
    trainer_server = TrainerServerGRPCServicer()
    training_process_info = get_training_process_info()
    trainer_server._training_process_dict[1] = training_process_info

    exception_msg = "exception"
    training_process_info.exception_queue.put(exception_msg)

    child_exception = trainer_server.check_for_training_exception(1)
    assert child_exception == exception_msg


def test_get_latest_checkpoint_not_found():
    trainer_server = TrainerServerGRPCServicer()
    with tempfile.TemporaryDirectory() as temp:
        trainer_server._training_dict[1] = get_training_info(temp)

    training_state, num_batches, num_samples = trainer_server.get_latest_checkpoint(1)
    assert training_state is None
    assert num_batches is None
    assert num_samples is None


def test_get_latest_checkpoint_found():
    trainer_server = TrainerServerGRPCServicer()
    with tempfile.TemporaryDirectory() as temp:

        training_info = get_training_info(temp)
        trainer_server._training_dict[1] = training_info

        dict_to_save = {"state": {"weight": 10}, "num_batches": 10, "num_samples": 100}

        checkpoint_file = training_info.checkpoint_path + "/checkp"
        torch.save(dict_to_save, checkpoint_file)

        training_state, num_batches, num_samples = trainer_server.get_latest_checkpoint(1)
        assert num_batches == 10
        assert num_samples == 100

        dict_to_save.pop("num_batches")
        dict_to_save.pop("num_samples")
        assert torch.load(BytesIO(training_state))["state"] == dict_to_save["state"]


def test_get_latest_checkpoint_invalid():
    trainer_server = TrainerServerGRPCServicer()
    with tempfile.TemporaryDirectory() as temp:

        training_info = get_training_info(temp)
        trainer_server._training_dict[1] = training_info

        dict_to_save = {"state": {"weight": 10}}
        checkpoint_file = training_info.checkpoint_path + "/checkp"
        torch.save(dict_to_save, checkpoint_file)

        training_state, num_batches, num_samples = trainer_server.get_latest_checkpoint(1)
        assert training_state is None
        assert num_batches is None
        assert num_samples is None