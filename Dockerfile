# Use a slim Python image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy project metadata
COPY pyproject.toml README.md ./

# ✅ OPTIMIZATION: Only copy the exact files the web app needs!
# We skip catalogue.py, updater.py, ecmwf_extractor.py, etc.
COPY s1iw_catalogue/__init__.py ./s1iw_catalogue/
COPY s1iw_catalogue/stats.py ./s1iw_catalogue/
COPY s1iw_catalogue/web/ ./s1iw_catalogue/web/

# Set the version for setuptools-scm
ENV SETUPTOOLS_SCM_PRETEND_VERSION=2026.7.3

# Install only web dependencies (no xarray, joblib, cdsodatacli, s1ifr!)
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir ".[web]"

# Expose the port
EXPOSE 8649

# Launch the web server (No ENV vars needed, CLI handles it directly)
ENTRYPOINT ["catalog-iw-serve"]
CMD ["--host", "0.0.0.0", "--port", "8649", "--catalogue", "/data/catalogue.parquet", "--config", "/data/config.yml"]
