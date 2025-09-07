#!/bin/bash

# GoDaddy DNS Plugin Uninstall Script
# This script removes the GoDaddy DNS plugin from CyberPanel

set -e

echo "=========================================="
echo "GoDaddy DNS Plugin Uninstall"
echo "=========================================="

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "Error: This script must be run as root"
    exit 1
fi

# Check if CyberPanel is installed
if [ ! -d "/usr/local/CyberCP" ]; then
    echo "Error: CyberPanel not found."
    exit 1
fi

# Check if plugin exists
if [ ! -d "/usr/local/CyberCP/godaddyDNS" ]; then
    echo "Error: GoDaddy DNS plugin not found."
    exit 1
fi

# Confirmation
echo "This will remove the GoDaddy DNS plugin from CyberPanel."
echo "Your DNS settings will revert to the default PowerDNS configuration."
echo ""
read -p "Are you sure you want to continue? (y/N): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Uninstall cancelled."
    exit 0
fi

# Set proper permissions
echo "Setting permissions..."
chmod +x /usr/local/CyberCP/godaddyDNS/uninstall.py

# Run the Python uninstall script
echo "Running uninstall script..."
cd /usr/local/CyberCP/godaddyDNS
/usr/local/CyberCP/bin/python uninstall.py

# Check if uninstall was successful
if [ $? -eq 0 ]; then
    echo ""
    echo "=========================================="
    echo "✓ Uninstall completed successfully!"
    echo "=========================================="
    echo ""
    echo "The GoDaddy DNS plugin has been removed from CyberPanel."
    echo "Your DNS menu will now show the default PowerDNS options."
    echo ""
    echo "Plugin files remain in /usr/local/CyberCP/godaddyDNS/"
    echo "You can delete this directory manually if desired:"
    echo "  rm -rf /usr/local/CyberCP/godaddyDNS"
    echo ""
else
    echo ""
    echo "=========================================="
    echo "⚠ Uninstall completed with errors"
    echo "=========================================="
    echo "Please check the output above for details."
    echo ""
    exit 1
fi