#!/bin/bash

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "Please run as root (sudo ./install.sh)"
    exit 1
fi

echo "Updating package lists..."
apt update

echo "Installing system dependencies..."
apt install -y python3 python3-pip python3-venv aircrack-ng network-manager

# Define project directory
PROJECT_DIR="$(pwd)"
VENV_DIR="$PROJECT_DIR/venv"

# Create a virtual environment if it doesn't exist
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
fi

# Activate the virtual environment
source "$VENV_DIR/bin/activate"

echo "Installing Python dependencies in virtual environment..."
pip install --upgrade pip
pip install scapy PyQt5

echo "Configuring WiFi adapter..."
airmon-ng check kill
airmon-ng start wlan0

echo "Installation complete!"
echo "To run the application, use: sudo $VENV_DIR/bin/python main.py"
