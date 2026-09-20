# Step 2: development environment

## Recorded machine

These observations describe this workspace machine, not every teammate's machine.
Free memory and disk space vary while applications are running.

| Item | Observed value |
|---|---|
| OS | Windows 11 Home Single Language, 64-bit, build 26200 |
| Shell | Windows PowerShell 5.1 |
| CPU | AMD Ryzen 7 6800H, 8 cores / 16 logical processors |
| RAM | Approximately 32 GB; Windows reports 31.19 GiB |
| GPU | NVIDIA GeForce RTX 3070 Ti Laptop GPU |
| Dedicated VRAM | 8192 MiB, verified with nvidia-smi |
| NVIDIA driver | 596.36 |
| Free space on C: | Approximately 386 GiB at inspection |
| Project Python | 3.12.10 in .venv |
| pip | 25.0.1 in .venv |
| SQLite | 3.49.1, in-memory query verified |
| Git | 2.52.0.windows.1 |
| Docker Engine | 29.4.3, Linux containers |
| Docker Compose | v5.1.3 |
| Ollama | 0.17.1; model listing responds |

The observed system timezone is UTC+08:00 (Kuala Lumpur/Singapore).
The deadline year and intended deadline timezone still require user confirmation.

## Python setup

The unqualified python command originally selected Anaconda Python 3.13.5.
The project uses the already-installed Python 3.12.10 in an isolated environment.
No application dependencies have been installed in that environment yet.

For a fresh checkout on Windows, after installing Python 3.12:

```powershell
Set-Location -LiteralPath 'C:\maven\MonashHack'
py -3.12 -m venv .venv
```

The environment already exists on this machine; do not recreate it routinely.
Use .venv\Scripts\python.exe explicitly. Activation is optional, so no
PowerShell execution-policy change is needed.
In VS Code, run Python: Select Interpreter and choose this executable:
C:\maven\MonashHack\.venv\Scripts\python.exe

## Repeatable verification

Docker Desktop was initially stopped. Starting it restored the Linux engine.
A disposable hello-world container then completed successfully.
The reusable check uses the cached image and does not pull images or call models.

```powershell
Set-Location -LiteralPath 'C:\maven\MonashHack'
docker desktop start --timeout 45
.\.venv\Scripts\python.exe scripts\check_environment.py --docker-smoke
$LASTEXITCODE
```

Expected: 8/8 checks passed and exit code 0. If Docker is already running,
omit the start command. A fresh machine may need docker pull hello-world:latest
before the smoke check; that download requires network access.

The check verifies Python version, project isolation, SQLite, pip consistency,
Git, Docker Compose, the Linux engine, and actual container execution.
It does not start the organizer evaluation service or read its files.

## Local inference and OCR readiness

Ollama lists downloaded models including qwen2.5:7b, llama3.1:8b,
llama3.2:1b, llama3.2:3b, and gpt-oss:20b.
Metadata for qwen2.5:7b reports 7.6B parameters and Q4_K_M quantization.
No model was selected for the project or invoked during this step.

The hardware and existing models make a small quantized-model trial plausible.
This is a feasibility assessment, not proof of inference quality, GPU offload,
available context length, latency, or offline readiness. Verify these in Step 6.

Tesseract was not found on PATH or in the checked common installation locations.
pdftoppm was not found on PATH. No working OCR/rendering path was demonstrated.
Local OCR, PDF rendering, and required language data remain setup work for Step 16.
A text-only model cannot replace OCR for scanned pages.

## Checkpoint

Agent verification: Python isolation, pip, SQLite, Git, Docker Compose,
Linux engine, and hello-world execution passed.
User verification and VS Code interpreter selection remain unreported.
Step 1 user verification is also still unreported; its file/exclusion recheck passed.
Model inference, OCR, cloud access, and application accuracy remain unverified.
Step 3 requires an explicit numbered start command.
