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

mkdir -p certbot/www certbot/conf

echo ">>> Starting nginx with HTTP-only for ACME challenge..."
docker compose -f compose.prod.yml up -d nginx

echo ">>> Requesting Let's Encrypt certificate for $DOMAIN ..."
docker run -it --rm \
    -v "$(pwd)/certbot/conf:/etc/letsencrypt" \
    -v "$(pwd)/certbot/www:/var/www/certbot" \
    certbot/certbot certonly --webroot \
    -w /var/www/certbot \
    -d "$DOMAIN"

echo ">>> Switching nginx to HTTPS mode..."
sed "s/YOUR_DOMAIN/$DOMAIN/g" nginx-ssl.conf > nginx.conf

echo ">>> Restarting nginx with HTTPS..."
docker compose -f compose.prod.yml restart nginx

echo ""
echo ">>> Auto-renewal cron (runs daily at 03:00, add with crontab -e):"
echo "0 3 * * * cd $(pwd) && docker run --rm \
    -v $(pwd)/certbot/conf:/etc/letsencrypt \
    -v $(pwd)/certbot/www:/var/www/certbot \
    certbot/certbot renew && docker compose -f compose.prod.yml restart nginx"
echo ""
echo ">>> Done! HTTPS is active at https://$DOMAIN"
