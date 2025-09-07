#!/bin/bash

# GoDaddy DNS Plugin Setup Script
# This script installs and configures the GoDaddy DNS plugin for CyberPanel

set -e

echo "=========================================="
echo "GoDaddy DNS Plugin Setup"
echo "=========================================="

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "Error: This script must be run as root"
    exit 1
fi

# Check if CyberPanel is installed
if [ ! -d "/usr/local/CyberCP" ]; then
    echo "Error: CyberPanel not found. Please install CyberPanel first."
    exit 1
fi

# Set proper permissions
echo "Setting permissions..."
chown -R cyberpanel:cyberpanel /usr/local/CyberCP/godaddyDNS
chmod +x /usr/local/CyberCP/godaddyDNS/install.py
chmod +x /usr/local/CyberCP/godaddyDNS/setup.sh

# Run the Python installation script
echo "Running installation script..."
cd /usr/local/CyberCP/godaddyDNS
/usr/local/CyberCP/bin/python install.py

# Check if installation was successful
if [ $? -eq 0 ]; then
    echo ""
    echo "=========================================="
    echo "✓ Installation completed successfully!"
    echo "=========================================="
    echo ""
    echo "Next steps:"
    echo "1. Access CyberPanel: https://$(hostname -I | awk '{print $1}'):8090"
    echo "2. Navigate to: https://$(hostname -I | awk '{print $1}'):8090/godaddy/config"
    echo "3. Enter your GoDaddy API credentials"
    echo "4. Discover your domains and enable sync"
    echo ""
    echo "Documentation: /usr/local/CyberCP/godaddyDNS/README.md"
    echo ""
else
    echo ""
    echo "=========================================="
    echo "⚠ Installation completed with errors"
    echo "=========================================="
    echo "Please check the output above for details."
    echo ""
    exit 1
fi