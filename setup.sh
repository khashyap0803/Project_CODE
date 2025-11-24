#!/bin/bash
set -e

echo "--- Phase 1: System Setup ---"
echo "This script requires sudo privileges. Please enter your password if prompted."

# Install Docker if not found
if ! command -v docker &> /dev/null; then
    echo "Installing Docker..."
    sudo apt update
    sudo apt install -y docker.io docker-compose-v2
    sudo usermod -aG docker $USER
    echo "Docker installed."
else
    echo "Docker is already installed."
fi

# Install NVIDIA Container Toolkit
echo "Installing NVIDIA Container Toolkit..."
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

sudo apt-get update
sudo apt-get install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker

echo "--- Verification ---"
echo "Running nvidia-smi in docker..."
sudo docker run --rm --runtime=nvidia --gpus all ubuntu nvidia-smi

echo "--- Setup Complete ---"
echo "Please REBOOT your computer now to ensure all driver and permission changes take effect."
echo "After reboot, run: cd ~/Documents/Project/Project_CODE/jarvis && docker compose up -d"
