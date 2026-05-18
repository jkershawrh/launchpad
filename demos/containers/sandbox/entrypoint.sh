#!/bin/bash
set -e

echo "Starting SSH server on port 2222..."
/usr/sbin/sshd -D -e &

STACK_LEVEL="${STACK_LEVEL:-minimal}"

if [ "$STACK_LEVEL" = "ai_dev" ] || [ "$STACK_LEVEL" = "full_redhat_ai" ]; then
    echo "Installing AI dev packages..."
    pip install --no-cache-dir torch --extra-index-url https://download.pytorch.org/whl/cpu 2>/dev/null || true
    pip install --no-cache-dir jupyter vllm ansible-navigator 2>/dev/null || true
fi

if [ "$STACK_LEVEL" = "full_redhat_ai" ]; then
    echo "Installing full Red Hat AI stack..."
    pip install --no-cache-dir openvino 2>/dev/null || true
fi

echo ""
echo "============================================"
echo "  Partner AI Launchpad — Sandbox Ready"
echo "============================================"
echo "  Stack: $STACK_LEVEL"
echo "  SSH:   ssh lab-user@localhost -p 2222"
echo "  Password: launchpad"
echo "============================================"
echo ""

# Keep container running
tail -f /dev/null
