#!/bin/bash
set -euo pipefail

usage() {
    echo "Usage: $0 your-domain.com"
    exit 1
}

DOMAIN="${1:-}"
if [ -z "$DOMAIN" ]; then
    usage
fi

CERTBOT_ROOT="${CERTBOT_ROOT:-/data/rag-agent/certbot}"
CERTBOT_WEBROOT="$CERTBOT_ROOT/www"
CERTBOT_CONF="$CERTBOT_ROOT/conf"

mkdir -p "$CERTBOT_WEBROOT" "$CERTBOT_CONF"

echo ">>> Starting nginx with HTTP-only for ACME challenge..."
docker compose --env-file .env.prod -f compose.prod.yml up -d nginx

echo ">>> Requesting Let's Encrypt certificate for $DOMAIN ..."
docker run -it --rm \
    -v "$CERTBOT_CONF:/etc/letsencrypt" \
    -v "$CERTBOT_WEBROOT:/var/www/certbot" \
    certbot/certbot certonly --webroot \
    -w /var/www/certbot \
    -d "$DOMAIN"

echo ">>> Switching nginx to HTTPS mode..."
sed "s/YOUR_DOMAIN/$DOMAIN/g" nginx-ssl.conf > nginx.conf

echo ">>> Restarting nginx with HTTPS..."
docker compose --env-file .env.prod -f compose.prod.yml restart nginx

echo ""
echo ">>> Auto-renewal cron (runs daily at 03:00, add with crontab -e):"
echo "0 3 * * * cd $(pwd) && docker run --rm \
    -v $CERTBOT_CONF:/etc/letsencrypt \
    -v $CERTBOT_WEBROOT:/var/www/certbot \
    certbot/certbot renew && docker compose --env-file .env.prod -f compose.prod.yml restart nginx"
echo ""
echo ">>> Done! HTTPS is active at https://$DOMAIN"
