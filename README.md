# snap-solve

website outline
	- ui
		- upload image
		- phone integration
	- math reading
	- (find/correct/display) errors
	- link to related resources

to do list

    - figure out how the images are stored json
		-[
          {
            "image_id": "image_name",
            "lines": [
              { "data": "..." },
              { "data": "..." }
            ]
          }
        ]
    - process image asyncronously (loading bar)
    - have upload for the question (context for solution)
    - 

## Run the website

From the project folder, choose either setup.

You also need a Gemini API key. Create a `.env` file in the project folder
(next to `app.py`), using `.env.example` as a template:

```dotenv
GEMINI_API_KEY=your-key-here
GEMINI_MODEL=gemini-3.5-flash
```

The server loads this file automatically, including when started from another folder.
Restart the server after changing the key. `.env` is ignored by Git; never commit it.
Existing environment variables take precedence over values in `.env`.
`GEMINI_MODEL` is optional; the default is `gemini-3.5-flash`.

Alternatively, set the key in your terminal before starting the server:

```sh
# Windows PowerShell
$env:GEMINI_API_KEY = "your-key-here"
# macOS / Linux
export GEMINI_API_KEY="your-key-here"
```

Without a key the site still runs, but the "what problem is this" step is skipped.

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

## Hosting online

- Images and results are stored only in each visitor's own browser (IndexedDB). The server
  keeps nothing: each upload is processed in memory and thrown away.
- Saved images belong to the site's address, so images saved on `localhost` won't show up on
  the hosted site (and vice versa).
- Start command on the host (no `--reload` in production; most hosts provide `$PORT`):

  ```sh
  python -m uvicorn app:app --host 0.0.0.0 --port $PORT
  ```

- Set `GEMINI_API_KEY` as a secret/environment variable in the host's dashboard. Anyone who
  can open the site can use it, so keep an eye on usage.
- Photos are shrunk to 2048 px in the browser before upload; the server also refuses images
  over 10 MB or 20 megapixels and processes at most 4 at a time, so it fits on a small host.
