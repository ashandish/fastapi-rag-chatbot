# Using Codex in This Repo

Quick guide to work on this project with Codex (CLI assistant) from a WSL environment.

## Launch Codex in WSL
- Open Windows Terminal or your preferred shell and start WSL.
- `cd /mnt/c/Users/ashan/Downloads/ChatBot/fastapi-rag-chatbot-v11/fastapi-rag-chatbot-v11`
- Launch Codex from this repo root (so it sees the code and AGENTS.md rules).

## Typical Workflow
- Edit and inspect files with Codex commands (search, apply_patch, etc.).
- Build and run locally via Docker: `docker compose up --build` (or `-d` to detach).
- Check status: `git status -sb`.

## Pushing Changes
- Codex sandbox blocks outbound network, so `git push` from inside Codex will fail.
- After committing in Codex, open a regular git client/terminal with network access and run `git push origin main`.

## Codex Architecture (summary)
- Codex CLI runs an AI assistant in a sandboxed workspace with limited I/O and no outbound network.
- It executes shell commands you request, edits files (prefers `apply_patch`), and follows repository instructions from `AGENTS.md`.
- Skills extend behavior via local `SKILL.md` guides; only listed skills are available per session.
- Sandbox rules: can read/write repo files; hidden files are included when explicitly searched; network calls (e.g., pushing, API fetches) are blocked.

## Tips
- Keep `.env` out of git; use `.env.example` for shared config.
- For full rebuild after changes: `docker compose build app worker && docker compose up -d app worker`.
- Use `rg` for fast searching; include `-g '.*' --hidden` when you need hidden files (e.g., `.env`).
