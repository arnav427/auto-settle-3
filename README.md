# Auto-Settle AI

Photos or video of vehicle damage go in; an itemised repair estimate and a negotiated cash settlement (or a human escalation with an audit trail) come out.

## Tools to install

| Tool | Needed for | Notes |
| --- | --- | --- |
| Python 3.10 or newer | Everything | Tested on 3.12. Get it from python.org and tick "Add python.exe to PATH". |
| Python packages | Everything | Installed from `requirements.txt`: streamlit (web UI), pillow (images), pandas (tables), requests (talks to Ollama), opencv-python-headless (video frames), pytest (tests). |
| Ollama | Real damage detection | Runs the vision model locally. Optional: the Demo mode works without it. |
| Vision model `qwen2.5vl:7b` | Real damage detection | About 6 GB download. Needs roughly 8 GB of free RAM. Runs on CPU, but slowly. |

## Setup

Run these in PowerShell from the project folder.

1. Install the Python packages.

   ```
   python -m pip install -r requirements.txt
   ```

2. (Optional) Install Ollama from https://ollama.com/download, or run:

   ```
   winget install --id Ollama.Ollama -e
   ```

3. (Optional) Start Ollama and download the vision model. If `ollama` is not recognised, open a new terminal, or use the full path `%LOCALAPPDATA%\Programs\Ollama\ollama.exe`.

   ```
   ollama serve
   ollama pull qwen2.5vl:7b
   ```

   `ollama serve` keeps running, so use a separate terminal for the next command. If Ollama is already running in the system tray, skip `ollama serve`. To check that it is running, open http://localhost:11434 in a browser. It should say "Ollama is running".

   On a low-memory machine, use a smaller model such as `moondream` or `llava:7b`. Enter its name in the "Vision model" box in the sidebar.

## Run

```
python -m streamlit run app.py
```

Open http://localhost:8501 if the browser does not open by itself. Stop the app with Ctrl+C.

## Use

1. In the sidebar, choose a detector:
   - **Ollama vision model**: real detection. Ollama must be running and the model downloaded.
   - **Demo (offline, simulated)**: random but repeatable detections, so the rest of the flow can be shown without Ollama.
2. Upload one or more photos (jpg, png, webp) or a short video (mp4, mov, avi, mkv).
3. Click **Analyse damage**. Review and correct the detections table, and check the cost estimate and any flags.
4. If the claim is safe to settle automatically, click **Start settlement** and chat with the assistant. Reply with "accept" or an amount. Otherwise the app shows why it was escalated and lets you download the case packet.
5. Open **Audit trail** to see every recorded step.

Use **Reset demo state** in the sidebar to forget earlier images. Otherwise uploading the same photo twice is flagged as a duplicate. Untick "Check for images reused from earlier claims" to turn the check off.

## Test

```
python -m pytest
```

## Troubleshooting

- `Ollama is not running at ...`: start it with `ollama serve`, or check the "Ollama host" box in the sidebar.
- `Model '...' is not installed`: run `ollama pull <model name>`.
- The first analysis takes a minute or more: the model is loading into memory. Later runs are faster.
- `streamlit` is not recognised: run it as `python -m streamlit run app.py`.
- Video upload fails: install `opencv-python-headless` with `python -m pip install opencv-python-headless`.
- Port 8501 is already in use: add `--server.port 8502` to the run command.

## Flow

1. `media.py` reads images and picks the sharpest frames from a video.
2. `detector.py` asks a local vision model (under 20B parameters) for component, damage type, severity and confidence. Output outside the known vocabulary is dropped.
3. `fraud.py` flags reused, edited, stale or metadata-less images.
4. `costs.py` prices each item from `data/parts_costs.csv` and `data/repair_matrix.csv`, adds GST, and gives a low and high estimate.
5. `pipeline.py` decides whether the claim may be settled automatically.
6. `settlement.py` negotiates over a fixed offer ladder. The language model never chooses an amount.
7. `audit.py` records every step in a hash-chained log in `data/audit/`.

## Guardrails (`auto_settle/config.py`)

- Cash offer stays between 60% and 85% of the garage estimate.
- Escalate when:
  - the estimate is above ₹60,000;
  - confidence is below 55%;
  - more than 5 areas are damaged;
  - a structural part (roof or quarter panel) is severely damaged;
  - nothing is detected;
  - an image is duplicated, edited, over 30 days old or dated in the future;
  - the customer asks for a human, tries to change the rules, or refuses the final offer.
- The reviewer can correct detections before pricing starts.

## Assumptions

- Prices are indicative Indian passenger-car costs in INR and would come from the insurer's garage network in production.
- Cash in lieu pays less than the garage estimate because no repair is guaranteed.
- Policy checks, excess and previous claim history are out of scope.
