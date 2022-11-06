# Dynamic Datasets DSL Project

## Dynamic Datasets Testing Infrastructure:

### Requirements:
- [Docker](https://docs.docker.com/get-docker/)

### Configuration:
- In `src/config/devel.yaml` you will find a test configuration for the system, adapt as required

### Current state:

![Current node and class diagram](docs/images/Current_design.png)

### Current state in a pipeline view:

![Current pipeline diagram](docs/images/Pipeline.png)

- DataFeeder feeds the defined file in defined batch sizes to the Kafka stream
- DataPreprocessor reads the data, does some minimal offline preprocessing, writes the batch to harddisk, updates the metadata and every now and then creates new batches from the existing batches

### How to run:
1. Install [Docker](https://docs.docker.com/get-docker/) 
2. Run docker `docker compose -f "src/docker-compose.yml" up -d --build`
3. To read output [ssh](https://phase2.github.io/devtools/common-tasks/ssh-into-a-container/) into the docker container you are interested in

### How to test:
0. Create [virtual environment](https://docs.python.org/3/tutorial/venv.html) 
1. cd into src
2. Install python requirements `pip install -r src/requirements.txt`
3. Install local requirements `pip install .`
3. Run tests `pytest .`
