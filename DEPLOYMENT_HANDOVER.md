# Sutawane Classes Management Software - Production Deployment & Architecture Handover

This document records the complete production deployment architecture, security model, and operational procedures for **Sutawane Classes Management Software** on the Contabo VPS server (`173.249.33.152`).

---

## 1. Server & Environment Profile

* **Server Provider:** Contabo VPS
* **Hostname:** `vmi3387652`
* **Public IP:** `173.249.33.152`
* **Operating System:** Ubuntu 24.04 LTS (Noble Numbat)
* **Application Linux User:** `sutawane`
* **Web Server User / Group:** `www-data`
* **Django Service Name:** `sutawane.service`
* **WhatsApp Bridge Service Name:** `sutawane-whatsapp.service`
* **App Server:** Gunicorn (WSGI, UNIX Socket)
* **Reverse Proxy:** Nginx
* **External Web Port:** **`8080`** (Direct IP Access: `http://173.249.33.152:8080/`)
* **Local WhatsApp Bridge Port:** `3000` (Internal loopback only)
* **Database:** SQLite (`db.sqlite3` with WhiteNoise static compression)

### Multi-Project Coexistence Guarantee
The VPS actively hosts another live production application (**UltraCoachMatrix**):
* **UltraCoachMatrix** operates on Port **`80`** (HTTP) and **`443`** (HTTPS/SSL) under Linux user `ultracoachmatrix` using PostgreSQL.
* **Sutawane Classes** operates on Port **`8080`** under Linux user `sutawane` using its self-contained database.
* **Zero Shared Sockets, Zero Shared Ports, Zero Shared Databases.** Both applications run concurrently with total process, file, and networking isolation.

---

## 2. Directory Structure

All files for Sutawane Classes are deployed under the dedicated `sutawane` user:

```text
/home/sutawane/
    sutawane_classes/             -> Cloned Git repository & Django application root
        manage.py
        requirements.txt
        .env                      -> Production environment file (Permissions: 600)
        db.sqlite3                -> Production database
        SUTAWANE_EDUCATION/       -> Django project configuration (settings, wsgi, urls)
        apps/
            MyApp/                -> Core ERP application (models, views, templates, static)
                management/
                    commands/
                        generate_stress_data.py -> High-speed 1 Lakh records generator
        staticfiles/              -> Compressed production static files (WhiteNoise)
        whatsapp_bridge/          -> Local Node.js WhatsApp Web Gateway service
            server.js             -> Express + Puppeteer + whatsapp-web.js server
            package.json
            .wwebjs_auth/         -> Persistent WhatsApp Web session authentication
            .wwebjs_cache/        -> Browser session cache
    media/                        -> Production student photos & uploaded receipts (Outside Git)
    logs/                         -> Application and access logs
    backups/                      -> Database and media backups
```

---

## 3. Dedicated User & Permissions Model

* **Main deployment user:** `sutawane`
* Do **not** deploy or run the Django application or the WhatsApp bridge as `root`.
* Use `root` or `sudo` only for OS-level tasks (system packages, UFW firewall rules, Nginx config, and systemd service registration).

### Creation and Permissions Setup (Run Once as `root`):

```bash
# Create user
sudo adduser --gecos "" sutawane
sudo usermod -aG sudo sutawane
sudo usermod -aG www-data sutawane

# Directory layout
sudo mkdir -p /home/sutawane/sutawane_classes
sudo mkdir -p /home/sutawane/media
sudo mkdir -p /home/sutawane/logs
sudo mkdir -p /home/sutawane/backups

# Strict permission hierarchy
sudo chown -R sutawane:sutawane /home/sutawane
sudo chown -R sutawane:www-data /home/sutawane/media
sudo chmod 755 /home/sutawane
sudo chmod 755 /home/sutawane/sutawane_classes
sudo chmod -R 775 /home/sutawane/media
sudo chmod -R 750 /home/sutawane/logs
sudo chmod -R 750 /home/sutawane/backups
```

### Switching to `sutawane` User:
```bash
su - sutawane
# Or direct SSH:
ssh sutawane@173.249.33.152
```

---

## 4. Production Environment Configuration (`.env`)

Located at: `/home/sutawane/sutawane_classes/.env`

```env
# =============================================================================
# Sutawane Classes - Production Environment (Direct IP Mode)
# =============================================================================
DJANGO_DEBUG=False
DJANGO_SECRET_KEY=sutawane_classes_prod_sec_key_9917_pawar_secure

# IP Whitelist (Must match server IP and loopbacks)
DJANGO_ALLOWED_HOSTS=173.249.33.152,127.0.0.1,localhost

# CSRF Trusted Origins (Mandatory for Django 4/5 form submissions over Port 8080)
DJANGO_CSRF_TRUSTED_ORIGINS=http://173.249.33.152:8080,http://127.0.0.1:8080

# Production HTTP Flag Settings
SECURE_SSL_REDIRECT=False
SESSION_COOKIE_SECURE=False
CSRF_COOKIE_SECURE=False
SECURE_HSTS_SECONDS=0

PORT=8000
```

Lock permissions to user-read only:
```bash
chmod 600 /home/sutawane/sutawane_classes/.env
```

---

## 5. Systemd Background Services

### Service 1: Django Gunicorn WSGI (`/etc/systemd/system/sutawane.service`)

```ini
[Unit]
Description=Sutawane Classes Django Gunicorn Service
After=network.target

[Service]
User=sutawane
Group=www-data
WorkingDirectory=/home/sutawane/sutawane_classes
EnvironmentFile=/home/sutawane/sutawane_classes/.env
RuntimeDirectory=sutawane
RuntimeDirectoryMode=0755
ExecStart=/home/sutawane/sutawane_classes/venv/bin/gunicorn \
          --workers 3 \
          --threads 2 \
          --bind unix:/run/sutawane/gunicorn.sock \
          --umask 007 \
          --timeout 120 \
          SUTAWANE_EDUCATION.wsgi:application
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### Service 2: WhatsApp Local Gateway Bridge (`/etc/systemd/system/sutawane-whatsapp.service`)

```ini
[Unit]
Description=Sutawane Classes WhatsApp Gateway Service
After=network.target

[Service]
User=sutawane
Group=sutawane
WorkingDirectory=/home/sutawane/sutawane_classes/whatsapp_bridge
Environment=PORT=3000
Environment=PUPPETEER_SKIP_CHROMIUM_DOWNLOAD=false
ExecStart=/usr/bin/node /home/sutawane/sutawane_classes/whatsapp_bridge/server.js
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### Service Management Commands:
```bash
sudo systemctl daemon-reload
sudo systemctl enable sutawane sutawane-whatsapp
sudo systemctl restart sutawane sutawane-whatsapp
sudo systemctl status sutawane --no-pager
sudo systemctl status sutawane-whatsapp --no-pager
```

---

## 6. Nginx Configuration on Port 8080

Located at: `/etc/nginx/sites-available/sutawane`  
Symlinked to: `/etc/nginx/sites-enabled/sutawane`

```nginx
server {
    listen 8080;
    server_name 173.249.33.152;

    client_max_body_size 50M;

    # Static Assets (WhiteNoise Precompiled)
    location /static/ {
        alias /home/sutawane/sutawane_classes/staticfiles/;
        expires 30d;
        add_header Cache-Control "public, no-transform";
    }

    # Media Uploads (Student Photos, Receipts)
    location /media/ {
        alias /home/sutawane/sutawane_classes/media/;
        expires 30d;
        add_header Cache-Control "public, no-transform";
    }

    # Gunicorn Unix Socket Proxy
    location / {
        proxy_pass http://unix:/run/sutawane/gunicorn.sock;
        proxy_http_version 1.1;
        proxy_set_header Host $http_host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_connect_timeout 60s;
        proxy_read_timeout 120s;
    }
}
```

Reload Nginx safely without downtime for other sites:
```bash
sudo ln -sf /etc/nginx/sites-available/sutawane /etc/nginx/sites-enabled/sutawane
sudo nginx -t
sudo systemctl reload nginx
```

---

## 7. Firewall (UFW) Configuration

To permit external browser traffic on port 8080:

```bash
sudo ufw allow 8080/tcp
sudo ufw reload
sudo ufw status
```
*(Confirms `8080/tcp ALLOW Anywhere`).*

---

## 8. High-Performance Architecture (1 Lakh+ Records)

During stress-testing with **1,00,000 (1 Lakh)** records, a database scalability enhancement was implemented in `students_list_view`:

1. **Database-Level Pagination:** Replaced in-memory loops with SQL `LIMIT` and `OFFSET` queries.
2. **Page-Scoped Prefetching:** Relational lookups (`payments`, `installments`, `fee_plan`) execute **only for the 25 records on the active page**, eliminating SQLite's `too many SQL variables` parameter limit and PostgreSQL memory spikes.
3. **Subquery Aggregations:** Summary metric cards calculate totals via indexed `.aggregate(tot=Sum(...))` subqueries in milliseconds.

### Built-in Stress Testing Command:
```bash
# As user 'sutawane' inside /home/sutawane/sutawane_classes:
source venv/bin/activate

# Generate 1 Lakh dummy students & admissions for benchmarking:
python manage.py generate_stress_data --model students --count 100000

# Generate 1 Lakh dummy notification logs:
python manage.py generate_stress_data --model notifications --count 100000

# Clear dummy stress-test records cleanly at any time:
python manage.py generate_stress_data --model students --clear
```

---

## 9. WhatsApp Web Gateway Bridge Architecture

The WhatsApp Gateway runs locally on Port `3000` without third-party cloud API costs.

* **Engine:** `whatsapp-web.js` running headless Chromium with `--no-sandbox` flags.
* **Ubuntu 24.04 Compatibility:** Uses `libatk1.0-0t64`, `libgtk-3-0t64`, `libasound2t64` libraries.
* **Server-Side Proxy:** Django view `/api/settings/whatsapp-status/` proxies health checks to `http://localhost:3000/health`, bypassing browser Private Network Access (PNA) and CORS restrictions.
* **Session Persistence:** Credentials and auth state persist in `/home/sutawane/sutawane_classes/whatsapp_bridge/.wwebjs_auth/`.
* **Pairing Procedure:**
  1. Go to **Settings $\rightarrow$ WhatsApp & Alerts (Tab 4)**.
  2. Click **Generate / Show QR Code**.
  3. Scan via institute phone (**Linked Devices $\rightarrow$ Link a Device**).

---

## 10. UI & Layout Integrity

* **Educational Taxonomy:** Terminology strictly uses Class / Institute management (Branch, Standard, Roll No, Academic Session, Student Code).
* **Single Official Logo Architecture:** One official institute logo is dynamically used throughout headers, fee receipts, print sheets, and statements.
* **Full-Width Responsive Settings:** Fluid 100% viewport layout (`w-full`) with child column containment (`minmax(0, 1fr)`) preventing field overflow on small screens.
* **Universal Color Utilities:** Explicit CSS rules for `.bg-indigo-600`, `.bg-[#25D366]`, `.bg-teal-600`, and `.bg-purple-600` in `base.html` and `app.css` ensure all buttons remain visible across browsers and print modes.

---

## 11. Routine Deployment & Maintenance Workflow

### Standard Code Update Routine (As `sutawane`):

```bash
cd /home/sutawane/sutawane_classes
source venv/bin/activate

# 1. Fetch latest commits
git pull origin main

# 2. Update Python packages (if requirements changed)
pip install -r requirements.txt

# 3. Apply database migrations
python manage.py migrate

# 4. Compile static files for WhiteNoise
python manage.py collectstatic --noinput

# 5. Restart application services
sudo systemctl restart sutawane
sudo systemctl restart sutawane-whatsapp
```

### Viewing Live Logs:
```bash
# Django / Gunicorn logs:
sudo journalctl -u sutawane -f

# WhatsApp Bridge logs:
sudo journalctl -u sutawane-whatsapp -f

# Nginx error log:
sudo tail -f /var/log/nginx/error.log
```

### Manual Backup (Database + Media):
```bash
# Backup SQLite DB with timestamp
cp /home/sutawane/sutawane_classes/db.sqlite3 /home/sutawane/backups/db_$(date +%Y%m%d_%H%M%S).sqlite3

# Backup student media files
tar -czf /home/sutawane/backups/media_$(date +%Y%m%d_%H%M%S).tar.gz /home/sutawane/media
```

---

## 12. Verification Checklist

- [x] Dedicated Linux user `sutawane` isolated from `root` and `ultracoachmatrix`.
- [x] Port `8080` open in UFW firewall.
- [x] Port `80` and `443` completely untouched for `UltraCoachMatrix`.
- [x] Gunicorn bound to dedicated socket `/run/sutawane/gunicorn.sock`.
- [x] WhatsApp Gateway bridge active on `localhost:3000`.
- [x] 1 Lakh records stress tested with sub-second response times.
- [x] Web access functional at `http://173.249.33.152:8080/`.

---

## 13. Software Capability & Stress Testing Suite (Temporary)

A high-performance benchmark suite has been integrated directly into the **Developer Portal** (`/developer-portal/`) to allow on-demand generation and testing of large datasets (e.g. 500 up to 100,000+ records) and assessing database indexing, search speed, and pagination responsiveness.

### How to Use:
1. Log in to the application as a **DEVELOPER** (`/login/` -> OTP -> Developer Dashboard).
2. Navigate to **Developer Portal** (`/developer-portal/`).
3. Under **Software Capability & Stress Testing Suite**:
   - **Generation Scope**: Select *Students + Fee Plans + Payments (Full Ecosystem)*, *Students Only*, or *Payments Only*.
   - **Record Count**: Type any number or click quick preset buttons (`+500`, `+1,000`, `+5,000`, `+10,000`, `+25,000`, `+50,000`, `⚡ 1 Lakh`).
   - Click **Generate Dummy Records**. Records are created in bulk at ~2,000 records/sec.
   - When finished testing, click **Clear Dummy Records** to permanently wipe all test data.

### Data Isolation & Safety:
- **Identifier Prefix**: All dummy students use `student_code="STRESS-SC-..."` and `roll_number="STR-..."`.
- **Payment Prefix**: All dummy receipts use `receipt_number="STRESS-REC-..."`.
- Real production records are completely isolated; cleanup commands filter strictly on these prefixes and never touch real students or receipts.

### Clean Removal Instructions (When Testing is Finished):
When software capability benchmarking is complete and you wish to remove this tool completely:
1. In `Django/apps/MyApp/views.py`:
   - Delete the block between `# === TEMPORARY BENCHMARK & STRESS-TEST GENERATOR ===` and `# === END TEMPORARY BENCHMARK ===` (lines ~360-590).
   - In `developer_portal_view`, remove the two action handlers (`action == 'generate_dummy_records'` and `action == 'clear_dummy_records'`), and remove `dummy_students_count` and `dummy_payments_count` from `stats`.
2. In `Django/apps/MyApp/templates/developer_portal.html`:
   - Delete the HTML card between `<!-- === TEMPORARY BENCHMARK & STRESS-TEST GENERATOR === -->` and `<!-- === END TEMPORARY BENCHMARK SUITE === -->`.
   - Delete the temporary JavaScript functions at the bottom of the script block.
