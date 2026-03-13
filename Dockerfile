# log-essence Docker image with pre-baked FastEmbed model
# Build: docker build -t log-essence .
# Run:   docker logs mycontainer 2>&1 | docker run -i log-essence -

FROM python:3.12-slim AS builder

WORKDIR /build
COPY . .
RUN pip install --no-cache-dir build && python -m build --wheel

FROM python:3.12-slim

WORKDIR /app

# Install the wheel
COPY --from=builder /build/dist/*.whl /tmp/
RUN pip install --no-cache-dir /tmp/*.whl && rm /tmp/*.whl

# Pre-download the FastEmbed model so it's cached in the image
RUN python -c "from fastembed import TextEmbedding; TextEmbedding('BAAI/bge-small-en-v1.5')"

ENTRYPOINT ["log-essence"]
CMD ["serve"]
