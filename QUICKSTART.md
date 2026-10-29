# PromptPriced — Quick start

Compare **answer quality, cost, and execution time** across up to three AI models using the same prompt. Blind mode hides model identities until reveal; the workflow panel projects cost and time at scale.

**How it connects:** Browser → this app → LiteLLM → model providers. LiteLLM puts several providers behind one API; it does not download or run these cloud models locally.

## 1. Install Docker

Install [Docker Desktop](https://docs.docker.com/get-started/get-docker/) for your operating system, then open it and wait until Docker is running. Verify in a terminal:

```bash
docker --version
docker run --rm hello-world
```

The commands below use a macOS/Linux shell (or Windows WSL).

## 2. Install LiteLLM and add models

Follow the **[official LiteLLM Docker quickstart](https://docs.litellm.ai/docs/proxy/docker_quick_start)** for installation. Use a separate `litellm-gateway` folder so its `.env` does not overwrite this app's settings.

1. Complete **Start LiteLLM** using the guide's Docker Compose setup, which includes the gateway and database. Keep the generated master and salt keys private and preserve the salt key.
2. Open **http://localhost:4000/ui** and sign in as instructed in the guide.
3. In **Models + Endpoints → Add Model**, choose a provider and model, enter its API key, test the connection, and add it. Repeat for each model you want in the app.
4. Create an application key under **Virtual Keys** with access to your selected models. The app also needs gateway model-discovery access; verify it with the probe below.

Use available provider models and make `config/models.yaml` match their exposed gateway names. Update `config/pricing.yaml` if their fallback prices differ. Cloud model calls can incur charges.

## 3. Connect and launch this app

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then open the `promptpriced` project folder in a terminal. Create or edit its `.env`:

```dotenv
LITELLM_API_BASE=http://127.0.0.1:4000
LITELLM_API_KEY=sk-your-litellm-application-key
```

Use your LiteLLM application key, not a provider key. Start the app:

```bash
uv sync
uv run python scripts/probe.py
uv run uvicorn promptpriced.app:app --host 127.0.0.1 --port 8000
```

The probe checks discovery without generating an answer. Open **http://127.0.0.1:8000**. If discovery fails, check key permissions and the Docker logs using the Compose filename from the official guide. Do not publish credentials.

## 4. Try the comparison

1. Choose a task and models; leave **Blind comparison** enabled.
2. Click **Pull the lever**, review the answers and grades, then **Reveal models & cost**.
3. Change the volume slider to compare projected cost and serial execution time.
4. Run and reveal the extraction and analysis presets for each model to populate **Fix the bill**. Adjust model, documents, turns, concurrency and retries. Time projections use measured latency with stated assumptions.
5. Choose **Recorded replay** to reuse a captured run without new model calls.

Unknown pricing/timing stays unavailable. Keyword grades need presenter judgment; estimates are not production guarantees. See [README](README.md) for details.

## A screenshot that explains the app

Use **one focused screenshot of a completed, revealed comparison** as the main image. Include the title/task, all three answers, grade badges, costs and measured times. Crop browser clutter and unused space; avoid a full-page image with unreadable text. Use synthetic claims and genuine results. Keep any RECORDED label visible.

On a Mac, widen the browser to roughly 1,600 px, then use **Shift–Command–4** to capture the relevant area. Save as `docs/images/comparison.png`. After saving it, place this near the top of your introduction:

```markdown
![Compare three models: answers, grades, cost and execution time](docs/images/comparison.png)
```

Suggested caption: **“One prompt. Three models. Compare quality, cost and speed before choosing.”** Add a second cropped image of **Fix the bill** only if you want to explain workflow savings. Keep keys, terminals and private prompts out of the capture.
