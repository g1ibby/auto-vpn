# Stage 1: Build dependencies
FROM python:3.12-slim as builder

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv
ENV UV_VERSION=0.7.3
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

# Set working directory
WORKDIR /app

# Copy dependency files
COPY pyproject.toml ./
COPY README.md ./

# Stage 2: Install Pulumi
FROM builder as pulumi-installer

# Install Pulumi
ENV PULUMI_VERSION=3.142.0
RUN curl -fsSL https://get.pulumi.com | sh -s -- --version $PULUMI_VERSION

# Stage 3: Final stage
FROM python:3.12-slim

# Add image metadata
LABEL org.opencontainers.image.source="https://github.com/g1ibby/auto-vpn"

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    make \
    && rm -rf /var/lib/apt/lists/*

# Copy Pulumi from pulumi-installer stage
COPY --from=pulumi-installer /root/.pulumi/bin/pulumi /usr/local/bin/

# Copy uv from builder
COPY --from=builder /root/.local/bin/uv /usr/local/bin/

# Set working directory
WORKDIR /app

# Copy dependency files
COPY pyproject.toml ./

# Install dependencies
RUN uv pip install --system .

# Copy application code
COPY src/auto_vpn ./auto_vpn
COPY pulumi_plugins ./pulumi_plugins
COPY migrations ./migrations
COPY Makefile ./

# Create .streamlit directory and copy config
COPY .streamlit/config.toml /app/.streamlit/config.toml

# Create non-root user
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app
USER appuser

# Set environment variables
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
# Set Streamlit to run on 0.0.0.0
ENV STREAMLIT_SERVER_ADDRESS=0.0.0.0
ENV STREAMLIT_SERVER_PORT=8501

# Expose Streamlit port
EXPOSE 8501

CMD ["streamlit", "run", "auto_vpn/web/web.py"]