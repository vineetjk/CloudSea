#!/bin/sh
# Start Ollama, pull the pinned model onto the disk on first boot, then load it so the first request is warm.
set -eu

ollama serve &
server=$!

until ollama list >/dev/null 2>&1; do sleep 1; done

if ! ollama list | awk '{print $1}' | grep -qx "$GEMMA_MODEL"; then
    echo "pulling $GEMMA_MODEL to $OLLAMA_MODELS"
    ollama pull "$GEMMA_MODEL"
fi

# An empty generate request loads the model into memory (KEEP_ALIVE=-1 keeps it there).
ollama run "$GEMMA_MODEL" "" >/dev/null 2>&1 || true
echo "ready: $GEMMA_MODEL"

wait "$server"
