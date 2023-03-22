# Training Supervisor

This is the Training Supervisor submodule. 

The training supervisor is the brain of Modyn. ML engineers start the supervisor using `modyn-supervisor pipeline.yaml config.yaml`″. 
The script should be in PATH after installing the `modyn` module.
The first configuration file describes the pipeline setup, while the second configuration file describes the system setup.

Optional command line flag: `--start-replay-at TIMESTAMP`.
This mode does not trigger on new data but just replays data starting at `TIMESTAMP` and ends all training afterwards.
`TIMESTAMP` can be 0 and then just replays all data.
In case of `initial_mode == train_until` with `now` as timestamp or a timestamp that is higher than the replay timestamp in the pipeline config we fail because then the initialization will conflict with the experiment.
We need to think about how communication will work in this case, probably the supervisor will need to tell the storage to replay the data in order to ensure correct communication with the selector etc. TBD

## How a pipeline is configured

- Model Type (ResNet, ...)
- Framework (Pytorch/Tensorflow)
- Training setup
    - single GPU
    - multi GPU (with the various suboptions, parameter server, all reduce, ...)
    - num workers
    - augmentation pipeline
    - lr / lr scheduling / ... (TODO think about the semantics of this in dynamic settings)
    - batch size
    - model config, if applicable, such as number of channels etc, passed directly to model.
- Dataset source and identifier
    - Unclear: How to define test set/validation set? needs to be updated over time as well, at least in some cases where we observe distribution shifts!
- Trigger
    - Time Trigger: Interval
    - Data Count Trigger: How many new data points for retraining?
    - Data Shift Trigger: Detection Algorithm
- Initial Model
    - Randomly initialized
    - Pretrained
- The training strategy 
    - Baselines, GDumb, ... with strategy subconfig passed directly to strategy, if applicable.
- Do we do an initial pass to train on all existing data or not?
    - If not, do we replay the existing data as a stream for our training strategy (requires that strategy is not retraining)
    - maybe: `initial_mode = [replay, ignore, train_until]` where train_until expects a subconfig that is either a timestamp or `now` and tells on which data we should train initially. replay = use algorithm for all data, train_until = just train until that data
- Logging
    - what to log, where to log
- Evaluation tasks?
- Deployment
    - where to send trained model

## On Pipelines, Triggers, and Trainings

We differentiate between pipelines, triggers, and trainings.
A pipeline is defined as the continously running model training process, i.e., what model we train on which dataset and how training is done (data selection and triggering).
The supervisor registers the pipeline at the selector and gets a pipeline ID in return.

When the supervisor informs the selector about a trigger, the Selector returns a trigger_id which defines the data that the GPU node should train on for the last interval of data that we have used. 
Imagine that we saw data points {a,b,c} in the interval [0,10] and data points {d,e,f} in inteval [11,20] and had a trigger after data point c and f.
Then, a selector strategy could decide on trigger that the training after the first trigger is training on {a,c}. 
This dataset {a,c} is uniquely identified by its trigger_id, e.g., 0.
The supervisor then tells the GPU node to train on trigger ID 0, and the GPU node asks the Selector: Hey, for pipeline_id 0 and trigger ID 0, on which data should I train?

After the second trigger, the selector could decide to train on all data {d,e,f}.
This would be trigger ID 1, and we tell this the GPU again and the GPU asks for the data for trigger 1.
Note that the data set for trigger ID 1 can also include data points from the previous trigger, e.g., imagine GDumb could decide after trigger 1 to train on {a,f}. 
The trigger ID defines until which data point the selector has processed all data points. 
It is not necessarily mutally exclusive with the previous trigger.

Last, we have the training_id: This is the ID returned by the GPU server to uniquely identify the training process on that node on a dataset, such that the supervisor can continously ask the GPU node what its current status is.
It is not necessarily equivalent to the trigger_id because trigger_ids might overlap over different trainings, the training_id is unique per GPU node.
We can always query the status of a training given the training ID.
To start a training process on a GPU node, the supervisor needs to send the pipeline information, pipeline id and trigger id.

## What happens

1. Supervisor validates config
    - Is the model known to the system (implementation exists within the system for PyTorch/Tensorflow)
    - Is everything else valid / implemented in the config yaml?

2. Supervisor validates system
    - GPU nodes available
    - Can we reach the source/storage system and actually find the data set?

3. Register pull OR push (TBD) notification for new data

4. Setup training on all GPU nodes (send all required info)

5. If applicable: Run initial pass

6. Repeat on trigger:
    1. Trigger training on GPU Nodes, make sure to send timestamp of latest datapoint at trigger known to supervisor. All datapoints until that need to have been processed by the selector before the selector returns any data to the GPU node.
    2. Fetch trained model and evaluate

... Wait for termination (CTRL+C -> deregister training etc OR experiment mode ends replay)