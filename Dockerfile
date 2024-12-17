# Stage 1: Build dependencies
FROM python:3.12-slim as builder

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
ENV POETRY_HOME=/opt/poetry
ENV POETRY_VERSION=1.7.1
RUN curl -sSL https://install.python-poetry.org | python3 - && \
    cd /usr/local/bin && \
    ln -s /opt/poetry/bin/poetry && \
    poetry --version

# Set working directory
WORKDIR /app

# Copy only dependency files first to leverage cache
COPY pyproject.toml poetry.lock ./

# Configure poetry to not create virtual environment
RUN poetry config virtualenvs.create false

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

# Set working directory
WORKDIR /app

# Copy project files first
COPY pyproject.toml poetry.lock ./

# Copy Poetry from builder
COPY --from=builder /opt/poetry /opt/poetry
RUN ln -s /opt/poetry/bin/poetry /usr/local/bin/poetry

# Configure poetry and install dependencies
RUN poetry config virtualenvs.create false && \
    poetry install --no-dev --no-root

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
