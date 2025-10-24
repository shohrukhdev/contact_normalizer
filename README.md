## Contact normalizer

Python program to normalize contact data in a CSV with columns:
id; phone; dob

### Run with Docker

1) Build the docker image: 

   `docker build -t contact-normalizer:latest . `


2) Run the docker image with the input CSV as arg from data volume:

    `docker run --rm -v "$(pwd)/data:/data" contact-normalizer:latest /data/contacts_sample_open.csv`

    output is saved to data folder.

3) Run with multiprocessing (auto-detect cores):

    `docker run --rm -v "$(pwd)/data:/data" contact-normalizer:latest /data/contacts_sample_open.csv multiprocess`

4) Run with specific number of cores (e.g., 4 cores):

    `docker run --rm -v "$(pwd)/data:/data" contact-normalizer:latest /data/contacts_sample_open.csv multiprocess 4`

Note: If the specified number of cores exceeds the actual physical cores available, the program will automatically use the available physical cores instead.


Note: If you encounter permission error with data folder, try with granting permissions to the folder:
`chmod 777 ./data`


### Requirements (local, without Docker)
- Python 3.13
- virtualenv recommended
- pip

### Install and run locally

### Create and activate a virtualenv (recommended)
`python -m venv .venv . .venv/bin/activate # Windows: ..venv\Scripts\activate`

#### Install dependencies
`pip install -r requirements.txt`

#### Run (input CSV is semicolon-delimited)
`python main.py contacts_sample_open.csv`

#### Run with multiprocessing (auto-detect cores)
`python main.py contacts_sample_open.csv multiprocess`

#### Run with specific number of cores
`python main.py contacts_sample_open.csv multiprocess 8`

#### Run tests
`python -m pytest -v`

