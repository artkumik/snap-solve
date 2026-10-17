# snap-solve

website outline
	- ui
		- upload image
		- phone integration
	- math reading
	- (find/correct/display) errors
	- link to related resources

to do list

## Run the website

From the project folder, choose either setup.

### Conda

```sh
conda create --name snap-solve python=3.12 pip -y
conda activate snap-solve
python -m pip install -r requirements.txt
python -m uvicorn app:app --reload
```

### pip 

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m uvicorn app:app --reload
```

Open http://localhost:8000.
