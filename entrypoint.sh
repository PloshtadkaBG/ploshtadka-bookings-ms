#!/bin/sh
set -e

# Auto-detect pod CIDR from own IP if FORWARDED_ALLOW_IPS is not set.
# In k8s, all pods (including Traefik/ingress) share the same pod CIDR,
# so deriving a /16 from our own IP covers the ingress controller's IP.
if [ -z "$FORWARDED_ALLOW_IPS" ]; then
  POD_IP=$(hostname -i 2>/dev/null | awk '{print $1}' || echo "127.0.0.1")
  FORWARDED_ALLOW_IPS=$(echo "$POD_IP" | awk -F. '{print $1"."$2".0.0/16"}')
fi

exec uv run uvicorn main:application \
  --host 0.0.0.0 \
  --port "${UVICORN_PORT:-8000}" \
  --proxy-headers \
  --forwarded-allow-ips "$FORWARDED_ALLOW_IPS" \
  "$@"
