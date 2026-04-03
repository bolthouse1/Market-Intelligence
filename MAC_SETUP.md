# Getting Set Up — C-Suite Intel Scanner (Mac)

## 1. Install VS Code

- Download from https://code.visualstudio.com/
- Drag to Applications, open it

## 2. Install Claude Code Extension

- In VS Code, click the Extensions icon in the left sidebar (or `Cmd+Shift+X`)
- Search **"Claude Code"** by Anthropic
- Click **Install**
- Once installed, you'll see a Claude icon in the left sidebar — click it to open the Claude Code panel
- It will ask you to sign in to your Anthropic account (or create one). Follow the prompts.

## 3. Install Prerequisites

Open Terminal (the Mac app, not inside VS Code yet) and run:

```bash
# Install Homebrew if you don't have it
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install Python 3.10+ and PortAudio (needed for voice features)
brew install python portaudio
```

## 4. Clone the Repo

```bash
git clone https://github.com/YOUR_ORG/Market_Intelligence.git
cd Market_Intelligence
```

## 5. Open in VS Code

```bash
code .
```

This opens the project folder. You should see the file tree on the left with `src/`, `config.yaml`, etc.

## 6. Talk to Claude Code

Click the Claude icon in the sidebar to open the chat panel. Type:

> I just cloned this repo on Mac. Help me get set up — install deps, configure .env, and run a dry-run scan to make sure everything works.

Claude Code knows this project and has instructions saved for Mac setup. It will walk you through:

- Creating a Python virtual environment
- Installing dependencies
- Setting up your `.env` file
- Running a test scan

## 7. What You'll Need for the `.env` File

Claude will help you create this, but have these ready:

| Key | What it is | Required? |
|-----|-----------|-----------|
| `ANTHROPIC_API_KEY` | API key from console.anthropic.com | **Yes** |
| `ELEVENLABS_API_KEY` | For natural voice briefings (elevenlabs.com) | Optional — has a free fallback |
| `SMTP_USER` | Gmail address for sending reports | Only if testing email |
| `SMTP_PASSWORD` | Gmail App Password (not your regular password) | Only if testing email |

## 8. Verify It Works

Once Claude walks you through setup, run this in the VS Code terminal:

```bash
python -m src.cli scan --dry-run
```

You should see it scan and generate a report without sending email.

## 9. Voice Briefing (Bonus)

The voice feature needs some Mac-specific work — Claude Code knows about this too. When you're ready to test voice, ask it:

> Help me test the voice briefing on Mac — list mics and test audio

**Heads up:** macOS will pop up a microphone permission dialog the first time. Click **Allow** or voice input will silently fail.

---

**TL;DR:** Install VS Code → install Claude Code extension → clone repo → open folder → ask Claude Code to help you set up. It knows what to do.
