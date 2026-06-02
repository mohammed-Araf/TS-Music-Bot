#!/bin/bash
# Shell script to configure a 2GB Swap File on Ubuntu/Debian VPS
set -e

echo "=== Setting up 2GB Swap File ==="

# Check if swap is already enabled
if [ $(swapon --show | wc -l) -gt 0 ]; then
    echo "Swap is already active. Current status:"
    swapon --show
    free -h
    exit 0
fi

# Allocate 2GB file
echo "Allocating swapfile..."
if fallocate -l 2G /swapfile 2>/dev/null; then
    echo "Allocated swapfile using fallocate."
else
    echo "fallocate failed, falling back to dd (this may take a few seconds)..."
    dd if=/dev/zero of=/swapfile bs=1M count=2048
fi

# Set permissions
chmod 600 /swapfile

# Format as swap
mkswap /swapfile

# Enable swap
swapon /swapfile

# Persist swap across reboots
if ! grep -q "/swapfile" /etc/fstab; then
    echo '/swapfile none swap sw 0 0' >> /etc/fstab
    echo "Added swap to /etc/fstab for persistence."
fi

echo "=== Swap Configuration Complete ==="
free -h
