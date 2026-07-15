#!/bin/bash
# =====================================================================
# HTTPS aktivləşdirmə skripti — DNS A record-ları qurulandan SONRA
# serverdə BİR DƏFƏ işə salın:
#     cd /opt/meeting-assistant && bash deploy/activate_https.sh
#
# Tələb: registrarda bu A record-lar droplet IP-nə yönəlməlidir:
#     api.visualkey.az  -> 64.226.123.27
#     n8n.visualkey.az  -> 64.226.123.27
# =====================================================================
set -e
cd /opt/meeting-assistant

echo "1/4 DNS yoxlanılır..."
for host in api.visualkey.az n8n.visualkey.az; do
  if ! getent hosts "$host" >/dev/null; then
    echo "XƏTA: $host hələ IP-yə yönəlmir. A record əlavə edin və DNS yayılmasını gözləyin (5-30 dəq)."
    exit 1
  fi
done

echo "2/4 Cari stack dayandırılır (port 80 certbot üçün boşaldılır)..."
docker compose down || true

echo "3/4 Let's Encrypt sertifikatı alınır (hər iki subdomain bir sertifikatda)..."
docker run --rm -p 80:80 \
  -v meeting-assistant_certbot_certs:/etc/letsencrypt \
  -v meeting-assistant_certbot_www:/var/www/certbot \
  certbot/certbot certonly --standalone \
  -d api.visualkey.az -d n8n.visualkey.az \
  --email nebiyevsamir002@gmail.com --agree-tos --no-eff-email

echo "4/4 İstehsal stack-i (nginx + HTTPS) qaldırılır..."
# --project-directory vacibdir: .env interpolyasiyası layihə kökündən oxunsun
docker compose --project-directory . -f deploy/docker-compose.prod.yml up -d --build

# Dev stack-dən qalan data volume-u root-a məxsusdur; prod image isə
# root olmayan appuser ilə işləyir — sahibliyi düzəldirik (idempotentdir)
docker compose --project-directory . -f deploy/docker-compose.prod.yml \
  exec -T -u root app chown -R appuser:appuser /app/data || true

echo ""
echo "✅ Hazırdır:"
echo "   https://api.visualkey.az/health"
echo "   https://api.visualkey.az/ui/index.html"
echo "   https://n8n.visualkey.az"
