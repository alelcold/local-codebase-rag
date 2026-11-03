#!/usr/bin/env bash
# Runs once when the codespace / dev container is created (postCreateCommand).
# Installs Ollama and the tools the scripts need, and creates .env from
# .env.codespaces if there is no .env yet. Safe to run again.
set -euo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

step() { echo; echo "==> $*"; }

step "Installing jq, zstd, iproute2 and git-lfs (used by the scripts, the Ollama installer and git push)"
# git-lfs: Codespaces can leave Git LFS hooks (e.g. .git/hooks/pre-push) in the
# clone without the git-lfs binary, and then every `git push` fails with
# "This repository is configured for Git LFS but 'git-lfs' was not found on your path".
# scripts/doctor.sh checks for this (devlog 2026-11-03).
sudo apt-get update -qq
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends jq zstd iproute2 git-lfs >/dev/null
echo "git-lfs: $(git lfs version 2>/dev/null | head -n1)"

step "Installing Ollama"
if command -v ollama >/dev/null 2>&1; then
  echo "already installed: $(ollama --version 2>/dev/null | head -n1)"
else
  # There is no systemd in a dev container, so the installer only installs the
  # binary; post-start.sh starts the server on 0.0.0.0 (ADR 0006).
  curl -fsSL https://ollama.com/install.sh | sh
fi

step "Installing PyYAML for scripts/evaluate.py"
python3 -m pip install --user --quiet -r scripts/requirements-eval.txt || echo "! could not install PyYAML; run: pip install -r scripts/requirements-eval.txt"

mkdir -p .logs "${OLLAMA_MODELS:-$HOME/.ollama/models}"

step "Creating .env"
if [ -f .env ]; then
  echo ".env already exists; leaving it alone (compare with .env.codespaces if needed)"
else
  cp .env.codespaces .env
  echo "created .env from .env.codespaces (qwen2.5-coder:3b, TOP_K=4, sample project)"
fi

# --skip-repo: only the global filter config. Plain `git lfs install` exits 2
# when .git/hooks already has the LFS hooks, which would stop this script (set -e).
step "Setting up Git LFS"
git lfs install --skip-repo

echo
echo "post-create done. post-start.sh starts Ollama and the stack (every time the codespace starts)."
