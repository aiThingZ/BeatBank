FROM pytorch/pytorch:2.2.2-cuda12.1-cudnn8-runtime

# Install system dependencies
RUN apt update && apt install -y ffmpeg sox git

# Install Demucs from GitHub (latest version from main branch)
RUN pip install --no-cache-dir git+https://github.com/facebookresearch/demucs@main

# Set working directory inside container
WORKDIR /data
