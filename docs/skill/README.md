# Install the sdmx-explorer skill

The `sdmx-explorer` skill enables guided, interactive exploration of SDMX statistical data sources directly in your AI coding agent, using the **[opensdmx](https://github.com/ondata/opensdmx)** CLI under the hood.

Skills can be installed in many ways — refer to your agent's documentation for the available options. Here we use [skills](https://github.com/vercel-labs/skills), a convenient tool that installs a skill in a single step across multiple agents (Claude Code, OpenCode, GitHub Copilot, Codex, and more) in a unified way.

## Prerequisites

Node.js (v18+) must be installed. Install it via your system's package manager or from [nodejs.org](https://nodejs.org).

## Installation

Run:

```bash
npx skills add ondata/opensdmx --skill sdmx-explorer
```

### Step 1 — Select agents

The installer fetches the skill from the repository and asks which agents to install it for. Several universal agents (including Claude Code) are enabled by default. If your agent is missing from the default list, scroll down to **Additional agents** to find and select it.

![Select agents](images/01.png)

### Step 2 — Choose installation scope (Global recommended)

Choose between installing for all agents or globally (home directory, available across all projects). In the example below, **Global** is selected so the skill is available in every project.

![Choose scope](images/02.png)

### Step 3 — Symlink (Recommended)

Choose how the skill file is installed. We recommend **Symlink**: instead of copying the file, a symbolic link is created pointing to the original source. This means any update to the skill is reflected immediately everywhere, with no need to reinstall.

![Global install](images/03.png)

### Step 4 — Confirm

Review and confirm with **Yes** to proceed.

![Confirm install](images/04.png)

## Update

To update the skill to the latest version:

```bash
npx skills update sdmx-explorer
```

## Usage

Once installed, use `/sdmx-explorer` in the selected agents to start an interactive SDMX exploration session using opensdmx.

To explore the skill's full capabilities before or after installing, see the [skill definition](../../skills/sdmx-explorer/SKILL.md).
