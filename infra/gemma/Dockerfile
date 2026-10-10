# Private Gemma service: Ollama on CPU, model weights on a persistent disk.
# Same Ollama version and model tag as local development, so benchmarks compare like with like.
FROM ollama/ollama:0.35.1

ENV OLLAMA_HOST=0.0.0.0:11434 \
    OLLAMA_MODELS=/var/data/ollama/models \
    OLLAMA_KEEP_ALIVE=-1 \
    OLLAMA_CONTEXT_LENGTH=4096 \
    OLLAMA_NUM_PARALLEL=1 \
    GEMMA_MODEL=gemma4:e2b-it-q4_K_M

COPY entrypoint.sh /entrypoint.sh
EXPOSE 11434
ENTRYPOINT ["/bin/sh", "/entrypoint.sh"]
