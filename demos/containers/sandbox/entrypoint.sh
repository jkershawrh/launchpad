#!/bin/bash

echo "Starting SSH server on port 2222..."
/usr/sbin/sshd -D -e 2>/dev/null &

STACK_LEVEL="${STACK_LEVEL:-minimal}"

echo ""
echo "============================================"
echo "  Partner AI Launchpad — Sandbox Ready"
echo "============================================"
echo "  Stack: $STACK_LEVEL"
echo "  SSH:   ssh lab-user@localhost -p 2222"
echo "  MaaS:  $MODEL_ENDPOINT"
echo "============================================"
echo ""

# Keep container running
tail -f /dev/null
