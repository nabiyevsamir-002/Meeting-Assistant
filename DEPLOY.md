# DEPLOY.md — DigitalOcean-a deployment runbook-u (Termius + parol ilə)

Bu sənəd addım-addım icra üçün nəzərdə tutulub. Server hələ YARADILMAYIB —
bütün artefaktlar hazırdır, aşağıdakı addımları özünüz icra edirsiniz.

## 0. Hansı paket (Droplet planı)?

Stack: FastAPI + Qdrant + n8n + nginx — hamısı bir serverdə.

| Plan | Qiymət | Nə vaxt |
|------|--------|---------|
| **Basic (Shared CPU) · Regular · 1 vCPU / 2GB RAM / 50GB SSD** | **$12/ay** | ✅ Kurs demo-su üçün tövsiyəm — swap ilə birlikdə kifayətdir |
| Basic · Regular · 2 vCPU / 4GB RAM / 80GB SSD | $24/ay | Daimi real istifadə planlaşdırırsınızsa |
| 1GB planı | $6/ay | ❌ Almayın — n8n + Qdrant birlikdə sığmır |

- **Region:** Frankfurt (FRA1) — Azərbaycana ən yaxın DO regionu, ping ən azdır.
- **Image:** Ubuntu 24.04 LTS x64.
- GitHub Student Pack-də DigitalOcean krediti olur — yoxlayın: https://education.github.com/pack

## 1. Droplet yarat (parol ilə)

1. https://cloud.digitalocean.com → **Create → Droplets**
2. Region: **Frankfurt**, Image: **Ubuntu 24.04**, Plan: **$12 / 2GB**
3. Authentication bölməsində: **Password** seçin və GÜCLÜ root parolu təyin edin
   (ən azı 16 simvol, hərf+rəqəm+işarə — parolla SSH açara nisbətən risklidir,
   ona görə parol gücü kritikdir; aşağıda fail2ban ilə qoruma da qururuq)
4. Hostname: `meeting-assistant` → **Create Droplet**
5. Yaranan **IP ünvanını** qeyd edin

## 2. Termius ilə qoşulma

1. Termius-u açın (Mac/iOS/Android) → **New Host**
2. Address: `<DROPLET_IP>`, Port: `22`
3. Username: `root`, Password: droplet yaradanda qoyduğunuz parol
4. Save → hosta toxunub qoşulun

> Sonradan istəsəniz Termius-da Keychain bölməsindən açar yaradıb
> `ssh-copy-id` ilə açara keçə bilərsiniz — amma bu axın parolla da tam işləyir.

## 3. Server hazırlığı (Termius terminalında)

```bash
# Sistemi yenilə
apt update && apt upgrade -y

# Docker quraşdır
curl -fsSL https://get.docker.com | sh

# 2GB RAM üçün swap (Qdrant+n8n pik anlarında xilas edir)
fallocate -l 2G /swapfile && chmod 600 /swapfile
mkswap /swapfile && swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab

# Firewall: yalnız SSH + HTTP + HTTPS
ufw allow OpenSSH && ufw allow 80 && ufw allow 443
ufw --force enable

# Parolla SSH istifadə etdiyimiz üçün brute-force qorunması MÜTLƏQDİR
apt install -y fail2ban
systemctl enable --now fail2ban
```

## 4. Layihəni serverə gətir

Layihə əvvəlcə GitHub-da olmalıdır (CI/CD üçün onsuz da lazımdır).
**Lokal Mac-də** (bir dəfəlik):

```bash
cd ~/Desktop/Project
git init && git add . && git commit -m "AI Meeting Assistant"
# GitHub-da boş repo yaradın (github.com/new, ad: meeting-assistant), sonra:
git remote add origin https://github.com/<İSTİFADƏÇİ_ADI>/meeting-assistant.git
git push -u origin main
```

**Droplet-də (Termius):**

```bash
mkdir -p /opt && cd /opt
git clone https://github.com/<İSTİFADƏÇİ_ADI>/meeting-assistant.git
cd meeting-assistant
```

## 5. Mühit faylı

```bash
cp .env.example .env
nano .env
# Mütləq dəyişin:
#   AUTH_ENABLED=true
#   JWT_SECRET=<openssl rand -hex 32 nəticəsi>
#   DEV_USERNAME / DEV_PASSWORD=<UI girişi üçün öz seçiminiz>
#   + real API açarları (SETUP.md-də hamısının mənbəyi var)
```

## 6-A. Variant A — SADƏ başlanğıc (domensiz, IP üzərindən)

Domen almadan sistemi dərhal işə salmaq üçün (HTTPS yoxdur, demo/kurs üçün OK):

```bash
docker compose up -d --build
```

- UI: `http://<DROPLET_IP>:8000/ui/index.html`
- n8n: `http://<DROPLET_IP>:5678` (bunun üçün `ufw allow 8000 && ufw allow 5678`)

Qeyd: Google OAuth bu variantda işləməyəcək (Google HTTPS domen tələb edir) —
təqvim mock rejimdə qalır. Digər hər şey işləyir.

## 6-B. Variant B — TAM quraşdırma (domen + HTTPS + nginx)

Domen alın (Namecheap ~$10/il) və iki A record yaradın (hər ikisi droplet IP-nə):
`api.<domen>` və `n8n.<domen>`. Sonra bu fayllarda `example.com`-u öz
domeninizlə əvəzləyin: `deploy/nginx/meeting-assistant.conf`,
`deploy/docker-compose.prod.yml` (N8N_HOST, WEBHOOK_URL, image OWNER).
`.env`-də: `GOOGLE_REDIRECT_URI=https://api.<domen>/api/auth/google/callback`

İlk sertifikat (nginx hələ işləmirken, standalone):

```bash
docker run --rm -p 80:80 \
  -v meeting-assistant_certbot_certs:/etc/letsencrypt \
  certbot/certbot certonly --standalone \
  -d api.<domen> -d n8n.<domen> \
  --email <email> --agree-tos --no-eff-email
```

Stack-i qaldır:

```bash
docker compose --project-directory . -f deploy/docker-compose.prod.yml up -d
curl https://api.<domen>/health    # {"status":"ok",...}
```

Certbot konteyneri yenilənmələri avtomatik edir (12 saatdan bir yoxlayır).

## 7. n8n qurulumu

1. n8n UI-a girin (Variant A: `http://IP:5678`, Variant B: `https://n8n.<domen>`)
2. Hesab yaradın → **Workflow → Import from File** → `n8n/scrape_ingest_workflow.json`
   və `n8n/delivery_workflow.json` → hər ikisini **Activate**
3. Credential-lar: SMTP (Gmail App Password) + Telegram (BotFather token)
4. n8n env dəyişənləri: `DELIVERY_FROM_EMAIL`, `DELIVERY_TO_EMAIL`,
   `TELEGRAM_CHAT_ID`, `OCR_SPACE_API_KEY`
5. FastAPI `.env`-də `DELIVERY_PROVIDER=n8n` → `docker compose restart app`

## 8. CI/CD (GitHub Actions, parolla)

Repo → **Settings → Secrets and variables → Actions**:

| Secret | Dəyər |
|--------|-------|
| `DEPLOY_HOST` | droplet IP |
| `DEPLOY_USER` | `root` |
| `DEPLOY_PASSWORD` | droplet parolunuz |

Bundan sonra `main`-ə hər push: test → Docker image (GHCR) → serverdə avto-yeniləmə.
GHCR image özəldirsə droplet-də bir dəfə `docker login ghcr.io` edin
(GitHub PAT, `read:packages`) və ya paketi public edin.

## 9. Yoxlama siyahısı

- [ ] `http(s)://.../health` → `"status":"ok"` və provayderlər canlı görünür
- [ ] `/ui/index.html` → giriş pəncərəsi çıxır (AUTH_ENABLED=true), daxil olub demo iclas işləyir
- [ ] n8n workflow-ları Active; test iclası bitəndə email/Telegram gəlir
- [ ] `main`-ə push → Actions yaşıl → serverdə yeni versiya

## Faydalı komandalar

```bash
docker compose logs -f app        # canlı loglar
docker compose restart app        # restart
docker compose down               # dayandır
docker system prune -f            # disk təmizliyi
fail2ban-client status sshd       # bloklanmış brute-force IP-ləri
```
