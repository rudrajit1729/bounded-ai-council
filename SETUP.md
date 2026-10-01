# Set up the council with real models

The offline demo needs nothing. A real study needs three things the demo does not:

1. **Three model families**, each reached through its command-line tool (you log in once) or
   through an API key kept in an environment variable.
2. **In Full mode, a decision model**, or the choice to run Full without one.
3. **Data you are allowed to send** to those vendors, de-identified.

This page walks through each step for macOS, Linux and Windows. It takes about 15 minutes per
family the first time.

## Start with the check

At any point, ask the pipeline what is missing:

```bash
python3 pipeline/council.py --config config.yaml doctor
```

It checks your Python version, the config, each family's tool or key, the decision model, the
corpus and the workspace, and prints PASS, FAIL or WARN with the fix for each problem. It never
prints a key: it only says whether the variable that should hold it is set. It sends nothing to any
model. When everything passes, prove the connections work end to end:

```bash
python3 pipeline/council.py --config config.yaml doctor --ping
```

`--ping` sends one tiny request (a few tokens) to each family and to the decision model.

In the local app (`python3 pipeline/app.py`), the Start page has the same check under
**Connect your models**. With no config yet, `doctor` runs general checks (which tools are
installed, which key variables are set).

## 1. Choose how to reach each family

The method uses three model families, for example Claude (Anthropic), GPT (OpenAI) and Gemini
(Google). For each one you choose a route:

| Family | Route A: API key | Route B: the vendor's command-line tool |
|---|---|---|
| Claude | `backend: anthropic_api`, key in `ANTHROPIC_API_KEY` | `backend: claude_cli` (Claude Code, `claude`) |
| GPT | `backend: openai_api`, key in `OPENAI_API_KEY` | `backend: codex_cli` (Codex CLI, `codex`) |
| Gemini | `backend: gemini_api`, key in `GEMINI_API_KEY` | no built-in route; see below |
| A local model | `backend: openai_api` with `base_url` (no data leaves your computer) | |

Which route? **Route B** uses the login of a subscription you may already have; there is no key to
handle, and use counts against your plan's limits. **Route A** is billed per token, is the easiest
to run unattended, and is what an institution's agreement with a vendor usually covers. You can mix
routes: one family by CLI, another by API.

Use the exact model id that the vendor's model list gives. The paper used Claude Opus 5, GPT-5.6 and
Gemini Flash 3.7.

### Claude

**Route A, API key.**
1. Sign in at https://console.anthropic.com, add a payment method, then open Settings, API keys,
   and create a key. Copy it; it is shown once.
2. Put it in the variable `ANTHROPIC_API_KEY` (section 2 below).
3. Install the vendor's Python package: `python3 -m pip install anthropic`.
4. In `config.yaml`:
   ```yaml
   models:
     claude: {backend: anthropic_api, model: claude-opus-5, api_key_env: ANTHROPIC_API_KEY}
   ```

**Route B, Claude Code.**
1. Install Claude Code (instructions for every system: https://docs.claude.com/en/docs/claude-code/setup).
   With Node.js installed, one way is `npm install -g @anthropic-ai/claude-code`.
2. Open a new terminal, run `claude` once and sign in with your Claude subscription or Console account.
   `claude auth status` tells you whether you are logged in.
3. In `config.yaml`:
   ```yaml
   models:
     claude: {backend: claude_cli, model: claude-opus-5}
   ```
   If `ANTHROPIC_API_KEY` is also set in that terminal, Claude Code may use the key (billed per
   token) instead of your login; `doctor` tells you when it is set.

### GPT

**Route A, API key.**
1. Sign in at https://platform.openai.com, add billing, and create a key under API keys
   (https://platform.openai.com/api-keys).
2. Put it in the variable `OPENAI_API_KEY` (section 2). No package is needed.
3. In `config.yaml`:
   ```yaml
   models:
     gpt: {backend: openai_api, model: REPLACE_WITH_MODEL_ID, api_key_env: OPENAI_API_KEY}
   ```

**Route B, Codex CLI.**
1. Install the Codex CLI (https://github.com/openai/codex). With Node.js installed:
   `npm install -g @openai/codex`.
2. Run `codex login` and sign in with your ChatGPT account (or an API key, if you prefer).
   `codex login status` tells you whether you are logged in.
3. In `config.yaml` (the example config uses this route):
   ```yaml
   models:
     gpt: {backend: codex_cli, model: REPLACE_WITH_MODEL_ID}
   ```

### Gemini

**Route A, API key.**
1. Sign in at https://aistudio.google.com/apikey and create an API key.
2. Put it in the variable `GEMINI_API_KEY` (section 2). No package is needed.
3. In `config.yaml`:
   ```yaml
   models:
     gemini: {backend: gemini_api, model: REPLACE_WITH_MODEL_ID, api_key_env: GEMINI_API_KEY}
   ```
   Check the data terms of the tier you use (section 4): free tiers of some APIs let the vendor use
   what you send to improve its products.

**Route B.** The pipeline has no built-in Gemini command-line route. The `command` backend runs any
program that reads the prompt on standard input and prints the reply
(`gemini: {backend: command, model: ..., command: ["your-program", "--model", "{model}"]}`); test
such a program with `doctor --ping` before a run. For most people the API key route is simpler.

### A local model (OpenAI-compatible server)

Ollama, vLLM, LM Studio and similar servers speak the OpenAI protocol. Nothing leaves your computer,
so this is the route when consent does not allow a vendor. A local open-weight model (for example
Llama, Qwen or Mistral) counts as its own family; the other two families must differ from it.

```yaml
models:
  local: {backend: openai_api, model: llama3.1:70b, base_url: "http://localhost:11434/v1", api_key_env: LOCAL_KEY, reasoning_param: false}
```

Typical addresses: Ollama `http://localhost:11434/v1`, LM Studio `http://localhost:1234/v1`, vLLM
`http://localhost:8000/v1`. The server usually ignores the key, but the variable must exist: set
`LOCAL_KEY` to `none` (section 2). Discovery reads the whole corpus in one call, so the model's
context window must hold it; otherwise set `discovery_block_size` in the config.

### Manual: an agent or you answer each prompt

`backend: manual` writes every prompt to `<workspace>/manual/` and waits for a reply file. A coding
agent of the right family can answer them; `AGENTS.md`, section 2, route B, explains how. No key is
needed, but it is slow for a large corpus.

## 2. Set an API key

Only the API route needs this. The rules:

- The key goes in an **environment variable**. `config.yaml` holds only the variable's **name**
  (`api_key_env: GEMINI_API_KEY`), never the key.
- Never paste a key into `config.yaml`, a file in this folder, a chat, or a commit.
- Set the variable in the terminal you run the pipeline from. The local app sees the variables of
  the terminal it was started from, so set the key first, then start the app.

### For this terminal session

macOS or Linux:
```bash
export GEMINI_API_KEY="paste-your-key-here"
```

Windows PowerShell:
```powershell
$env:GEMINI_API_KEY = "paste-your-key-here"
```

Windows Command Prompt:
```bat
set GEMINI_API_KEY=paste-your-key-here
```

The variable lasts until you close that window. Run the pipeline, or start the app, in the same window.

### Keep a key set

So that every new terminal has it:

- **macOS** (zsh is the default shell): open `~/.zshrc` in a text editor (for example
  `open -e ~/.zshrc`; create the file if it does not exist), add the line
  `export GEMINI_API_KEY="paste-your-key-here"`, save, and open a new terminal.
- **Linux** (bash): the same line in `~/.bashrc`, then open a new terminal.
- **Windows**: run `setx GEMINI_API_KEY "paste-your-key-here"` once, then open a new terminal. Or:
  Start menu, "Edit environment variables for your account", New, name and value.

These places store the key as plain text in your user account. That is common practice on a
personal computer; on a shared computer, set the key per session instead.

Then check: `python3 pipeline/council.py --config config.yaml doctor` reports
"GEMINI_API_KEY is set in this environment".

## 3. The decision model

Full mode can use a calibrated yes/no decision model. It scores, for each unit and each code, how
likely the code applies, so that adversaries get leads and coders see a screened list. Lite mode
does not use it. You have four options:

1. **TypeSafe Jev** (what the paper used). Get a key from TypeSafe (https://typesafe.ai), put it in
   `TYPESAFE_API_KEY` (section 2), and keep the defaults:
   ```yaml
   decision_model: {enabled: true, backend: typesafe, endpoint: https://api.typesafe.ai/v1/systemone, model: jev-latest, api_key_env: TYPESAFE_API_KEY}
   ```
   It is cheap: in the paper it cost $0.84 of the $87 Full run on 256 threads.
2. **Run Full without it.** The adversaries still challenge every role; there is no screening and
   there are no decision-model leads:
   ```yaml
   decision_model: {enabled: false}
   ```
3. **Manual.** `backend: manual` writes each request to `<workspace>/manual/` for you or an agent
   to answer. There is one request per unit per analyst at discovery and one per unit at coding
   (about 1,000 for 256 units), and the answers are not calibrated. Practical only with an agent.
4. **Your own classifier** with the same contract (`backend: command`; the contract is in
   `prompts/decision_model_questions.md`).

## 4. Before any data leaves your computer

- **De-identify the corpus.** Remove names, email addresses, user names, employers, team and
  project names that point to a person, links, and ids. Read a sample of the free text for details
  that identify someone indirectly.
- **Consent decides the vendors.** Send data only to vendors your participants' consent (and your
  ethics approval) allows. If it allows none, use a local model for every family, or the manual
  route with a tool you are allowed to use.
- **Check each vendor's data terms for the plan you use.** API terms, consumer subscriptions and
  free tiers differ, for example on whether what you send may be kept or used to improve the
  vendor's models. Your institution may have an agreement that covers some vendors and not others.
- **Write it down.** Put what leaves the machine, to which vendors, and under which terms in
  `data_governance` in `config.yaml`. The report prints it as written, and `doctor` warns while it
  is empty.

## 5. What a run costs

From the paper, on 256 Stack Overflow threads (about 1,700 characters each, five research
questions), at 2026 list prices for Claude Opus 5, GPT-5.6, Gemini Flash 3.7 and Jev:

| Mode | Total | Per 100 threads |
|---|---|---|
| Lite | $35 | about $14 |
| Full | $87 | about $34 |

How it scales: coding cost grows with the number of units; discovery cost grows with the length of
the corpus and the number of research questions (each analyst reads the whole corpus once per
question). Units twice as long cost roughly twice as much. Reasoning tokens are a large share of the
output. With a CLI subscription (route B) the same work counts against your plan's limits instead of
a bill. Researcher time is not included.

To know your own cost before the full run, run Lite on a pilot of 30 to 50 units and run
`python3 pipeline/council.py --config config.yaml cost` (fill in `prices` in the config with your
vendors' current list prices, in dollars per million input and output tokens).

## 6. Put it together

Three common setups (only the `models` block differs; `roles` assigns them to the analysts and coders):

```yaml
# a) Two CLIs and one API (this is config.example.yaml)
models:
  claude: {backend: claude_cli, model: claude-opus-5}
  gpt:    {backend: codex_cli, model: REPLACE_WITH_MODEL_ID}
  gemini: {backend: gemini_api, model: REPLACE_WITH_MODEL_ID, api_key_env: GEMINI_API_KEY}

# b) Three APIs
models:
  claude: {backend: anthropic_api, model: claude-opus-5, api_key_env: ANTHROPIC_API_KEY}
  gpt:    {backend: openai_api, model: REPLACE_WITH_MODEL_ID, api_key_env: OPENAI_API_KEY}
  gemini: {backend: gemini_api, model: REPLACE_WITH_MODEL_ID, api_key_env: GEMINI_API_KEY}

# c) Two CLIs and a local model (the local model's family name goes in `roles`)
models:
  claude: {backend: claude_cli, model: claude-opus-5}
  gpt:    {backend: codex_cli, model: REPLACE_WITH_MODEL_ID}
  local:  {backend: openai_api, model: llama3.1:70b, base_url: "http://localhost:11434/v1", api_key_env: LOCAL_KEY, reasoning_param: false}
```

Then:

1. `python3 pipeline/council.py --config config.yaml doctor` until nothing fails.
2. `python3 pipeline/council.py --config config.yaml doctor --ping` once.
3. Run the stages (README, "Scripted use"), press the buttons in the app, or let a coding agent
   follow `AGENTS.md`.

## 7. When something fails

| Message | What to do |
|---|---|
| `environment variable X is not set` | Set it in the same terminal (section 2); restart the app if you use it. |
| `Claude Code CLI is not logged in` | Run `claude` once and sign in. |
| `Codex CLI is not logged in` | Run `codex login`. |
| HTTP 401 or 403 | The key is wrong, revoked, or the account has no billing. Create a new key. |
| HTTP 404, or "model not found" | The model id is wrong; copy it from the vendor's model list. |
| HTTP 429 | Rate limit. Lower `workers` in the config and run the same command again; finished calls are kept. |
| `nothing answers at http://localhost:...` | Start the local model server; check the port. |
| `the model id is not set` | Replace `REPLACE_WITH_...` in `config.yaml` with a real model id. |
