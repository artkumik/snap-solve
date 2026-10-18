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
YOUTUBE_API_KEY=your-youtube-key-here
```

The server loads this file automatically, including when started from another folder.
Restart the server after changing the key. `.env` is ignored by Git; never commit it.
Existing environment variables take precedence over values in `.env`.
`GEMINI_MODEL` is optional. By default the server tries `gemini-3.5-flash`, then
`gemini-3.5-flash-lite`, then `gemini-2.5-flash` when a model's daily quota runs out.
To choose your own fallback order, set `GEMINI_MODELS` to a comma-separated list instead.

Alternatively, set the key in your terminal before starting the server:

```sh
# Windows PowerShell
$env:GEMINI_API_KEY = "your-key-here"
# macOS / Linux
export GEMINI_API_KEY="your-key-here"
```

Without a key the site still runs, but the "what problem is this" step is skipped.

**Related videos** need a YouTube Data API key (`YOUTUBE_API_KEY`). In the
[Google Cloud console](https://console.cloud.google.com/), pick or create a project,
enable **YouTube Data API v3** (APIs & Services → Library), then create a key under
APIs & Services → Credentials. The free quota is 100 searches per day; each problem is
searched once, since its videos are saved in the browser with the rest of the result.
Without this key, everything else works and the "Related videos" section stays hidden.

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

On Windows, activate the venv with `.venv\Scripts\Activate.ps1` instead of `source ...`.

Open http://localhost:8000.

## Training and evaluation (TexTeller)

`newEvaluate.py`, `train_texteller.py` and `mathwriting_prep.py` need extra packages.
Install them in the same environment as the website:

```sh
python -m pip install -r requirements-training.txt
```

That file pulls PyTorch's CUDA build. If PyTorch is **already installed** as the CPU-only
build (a plain `pip install torch` on Windows gives you that), pip keeps the old one, so
remove it first:

```sh
python -m pip uninstall -y torch torchvision
python -m pip install -r requirements-training.txt
```

Check that the GPU is visible. This should print a `+cu…` version and `True`:

```sh
python -c "import torch; print(torch.__version__, torch.cuda.is_available())"
```

If it shows `+cpu`, go to https://pytorch.org/get-started/locally/, pick
Stable / Windows / Pip / the newest CUDA, run the command it gives, and then rerun
`pip install -r requirements-training.txt`. You do not need the CUDA Toolkit, just a
recent NVIDIA driver (`nvidia-smi` should list the GPU).

```sh
# Build a fixed 400-image sample from a MathWriting parquet file
python mathwriting_prep.py "data/mathwriting_val/*.parquet" data/mathwriting_val --count 400
# Score the pretrained model (or a fine-tuned one with --model-dir checkpoints/.../best)
python newEvaluate.py --csv data/mathwriting_test/labels.csv --out predictions_baseline.csv
# Fine-tune; the best checkpoint lands in <out_dir>/best
python train_texteller.py --train_dir data/mathwriting_train --val_dir data/mathwriting_val --out_dir checkpoints/texteller_mw
```

Both scripts score predictions the same way (`latex_metrics.py`), so their numbers can be
compared directly.

## Hosting online

- Images and results are stored only in each visitor's own browser (IndexedDB). The server
  keeps nothing: each upload is processed in memory and thrown away.
- Saved images belong to the site's address, so images saved on `localhost` won't show up on
  the hosted site (and vice versa).
- Start command on the host (no `--reload` in production; most hosts provide `$PORT`):

  ```sh
  python -m uvicorn app:app --host 0.0.0.0 --port $PORT
  ```

- Set `GEMINI_API_KEY` and `YOUTUBE_API_KEY` as secrets/environment variables in the
  host's dashboard. Anyone who
  can open the site can use it, so keep an eye on usage.
- Photos are shrunk to 2048 px in the browser before upload; the server also refuses images
  over 10 MB or 20 megapixels and processes at most 4 at a time, so it fits on a small host.
