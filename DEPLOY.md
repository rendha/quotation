# Putting the quotation app on the internet as an installable app (PWA)

**What you get**

* Staff open one web address and can **install the app on a phone** (its own icon, full screen).
* **Sign-in is a switch** (`DJANGO_REQUIRE_LOGIN`). It is **off for the test period**: everybody who has the address can use the app, with no accounts. **Turn it on before real use** (see "Turning sign-in on").
* The test site tells search engines not to list it, but **anybody who has the address can see all quotations, margins and customer details**: share the address only with your testers.
* If the phone has no internet, the app shows a friendly "You are offline" page. Quotations and prices are **never stored on the phone**.
* Your PC setup (`py manage.py runserver`) keeps working exactly as before. The server uses extra settings (`quotation_pwa/settings_production.py`).

> **Honest note:** the Python code, the service worker, the settings, the start-up script and the Render blueprint file are tested. **Render itself and a real server are not**: there is none here. Do the first deploy as a test and tell me about any message you do not understand.

## Which way? (read this first)

Your database is **one SQLite file**. Render's rules decide where it can live:

| | **A. Render, paid + disk** (recommended) | **B. Render, free + free Postgres** | **C. A server of your own** |
|---|---|---|---|
| Your data | Kept on a persistent disk, with daily snapshots | Kept in Render's free Postgres, **deleted 30 days after creation** (14 days' grace to upgrade), **no backups** | Kept on the server's disk, backups by you |
| Always on? | Yes | **No**: sleeps after 15 minutes without visitors, the next visit takes about a minute | Yes |
| Size | Small paid instance | Very small free instance: **PDFs may be slow or fail** | You choose |
| Cost | Paid instance + a small disk (see Render's pricing page) | Free | A small monthly server + domain |
| Set-up | One click from GitHub (Blueprint) | A few clicks, no blueprint | Most work |
| Best for | Real use | A short trial this week | Full control |

**Way D (Railway)** is the same idea as Way A on a different platform: it deploys from GitHub, uses the same `Dockerfile`, and keeps the database on a volume. It costs about **$5 a month at least** (usage-based), has a 30-day trial, and works with a **private** repository when you sign in to Railway as the GitHub account that owns the repository. See "Way D" below.

A free Render web service **cannot** keep your SQLite file: free services lose their local files every time they restart, redeploy or go to sleep, so everything your testers enter would disappear. Disks exist only on paid services. That is why B uses Postgres.

---

## Part 1: on your PC (Windows), the same for every way

### 1. Copy the files into your project (overwrite when asked)

| File | Goes in |
|---|---|
| `pwa.py`, `pwa_views.py`, `backup.py`, `dashboard_stats.py` | `quotations\` |
| `pwa_files\sw.template.js` | `quotations\pwa_files\` (new folder) |
| `backup_database.py` | `quotations\management\commands\` |
| `static\quotations\icons\*.png` (5 icons) | `quotations\static\quotations\icons\` (new folders) |
| `_pwa_head.html`, `_pwa_register.html`, `offline.html`, `login.html`, `dashboard.html`, `person.html`, `create_quotation.html`, `quotation_detail.html` | `quotations\templates\quotations\` |
| `settings_production.py` | `quotation_pwa\` (next to your `settings.py`) |
| `render.yaml`, `Dockerfile`, `docker-entrypoint.sh`, `.dockerignore`, `.gitignore`, `.gitattributes`, `requirements-deploy.txt`, `DEPLOY.md` | the project folder (where `manage.py` is) |
| `docker-compose.yml`, `Caddyfile`, `.env.example` | the project folder (only needed for way C) |
| `tools\make_icons.py`, `tools\check_assets.py` | `tools\` (new folder) |

### 2. Add five lines to `quotations\urls.py`

At the top add:

```python
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_not_required
from . import pwa_views
```

and inside `urlpatterns = [ ... ]` add:

```python
    path("login/", login_not_required(auth_views.LoginView.as_view(
        template_name="quotations/login.html", redirect_authenticated_user=True, next_page="quotation_dashboard")), name="login"),
    path("logout/", auth_views.LogoutView.as_view(next_page="login"), name="logout"),
    path("manifest.webmanifest", pwa_views.manifest, name="manifest"),
    path("sw.js", pwa_views.service_worker, name="service_worker"),
    path("offline/", pwa_views.offline, name="offline"),
```

### 3. List what your app needs: `requirements.txt`

In the project folder, with the venv active (use **cmd**, not PowerShell):

```
pip freeze > requirements.txt
```

Open the file and delete any line that only exists on Windows (for example `pywin32`). It must contain `Django`, `weasyprint` and `pypdf`. (In PowerShell use `pip freeze | Out-File -Encoding ascii requirements.txt`, otherwise the file is unreadable on the server.)

### 4. Check the PDF files (Windows ignores capital letters, Linux does not)

```
py tools\check_assets.py
```

It must end with `OK`. If it says "rename it", rename that file to exactly the spelling shown.

### 5. Try it on your PC

```
py manage.py runserver
```

Open `http://127.0.0.1:8000/` in Chrome, press F12, open **Application**: **Manifest** shows the name and icons without red errors; **Service Workers** shows `/sw.js` as *activated*; tick **Offline** and reload to see "You are offline". Sign-in is only forced on the server.

### 5b. Move the bank details into the database (before anything goes to GitHub)

The bank account printed on the last page of the PDF used to be written in the code. It now lives in the database, so it never goes into git. **Do this before you push or make anything public.**

1. Copy the new `pdf_generator.py` over yours.
2. **Add the model.** At the very end of `quotations\models.py` add:

```python
class PaymentDetails(models.Model):
    """The company bank account printed on the last page of every quotation PDF (Admin > Payment details)."""
    beneficiary_name = models.CharField(max_length=150)
    account_number = models.CharField(max_length=40)
    ifsc = models.CharField("IFSC", max_length=20)
    bank_name = models.CharField(max_length=150)

    class Meta:
        verbose_name = "Payment details"
        verbose_name_plural = "Payment details"

    def __str__(self):
        return "%s - %s" % (self.beneficiary_name, self.bank_name)
```

3. **Show it in the Admin.** At the very end of `quotations\admin.py` add (make sure the file starts with `from django.contrib import admin`):

```python
from .models import PaymentDetails


@admin.register(PaymentDetails)
class PaymentDetailsAdmin(admin.ModelAdmin):
    list_display = ("beneficiary_name", "bank_name", "account_number", "ifsc")

    def has_add_permission(self, request):
        return not PaymentDetails.objects.exists()      # only one set of bank details
```

4. Create the table:

```
py manage.py makemigrations quotations
py manage.py migrate
```

5. Run `py manage.py runserver`, open `http://127.0.0.1:8000/admin/`, then **Payment details**, then **Add**, and type the four lines your PDFs show today (beneficiary name, account number, IFSC, bank).
6. **Check:** open a quotation PDF. The last page must show the four bank lines. If it shows none, look at the black window where `runserver` runs: it prints a warning that says what is missing.

The new file in `quotations\migrations\` (`0019_...`) **must be committed to git**: the server needs it to create the table. Your `db.sqlite3`, with the bank details inside, goes to the server with `scp` (way A, step A2), never through git.

**Important: git remembers old versions.** The account number is still in your old commits. Taking it out of the code is not enough if the repository will be public, because anyone can read the history. Start a clean history (the repository is private and new, so nothing is lost):

1. On GitHub: open `rendha/quotation`, then **Settings**, then **Danger Zone**, then **Delete this repository**. Then create a **new, empty, private** repository with the same name (no README).
2. In the project folder (cmd):

```
rmdir /s /q .git
git init
git add -A
git commit -m "quotation app"
git branch -M main
git remote add origin https://github.com/rendha/quotation.git
git push -u origin main
```

3. Check that the bank details are gone from the code **and** the history. Both of these must print nothing:

```
git grep -n "IBK[L]"
git log --all -G"IBK[L]" --oneline
```

(The square brackets are a trick: the search still finds your bank's IFSC prefix, but this guide, which spells it differently, cannot match itself.)

`rmdir /s /q .git` deletes only the history, not your files.

### 6. Put the code on GitHub (a **private** repository)

Create a private repository on GitHub, then in the project folder:

```
git init
git add .
git commit -m "quotation app"
git branch -M main
git remote add origin https://github.com/YOURNAME/YOURREPO.git
git push -u origin main
```

`.gitignore` keeps your `.env`, your database and the venv out of git. **Check on GitHub that `db.sqlite3` is not there**, and that `render.yaml` is in the main folder of the repository.

---

## Way A: Render with a disk (recommended)

### A1. Create the service from the blueprint

1. Sign in at render.com with your GitHub account.
2. **New**, then **Blueprint**. Allow Render to read your private repository, pick it, and press **Apply**.
3. Render builds the Docker image (the first build takes several minutes) and starts the service named `dehlsen-quotations`, with a 1 GB disk at `/data`, a generated secret key, and sign-in **off**.
4. When it says **Live**, open the address shown on the service page (`https://dehlsen-quotations.onrender.com`, or with a suffix if the name was taken). You land on the dashboard, empty at first.

The blueprint chooses the **Singapore** region (the nearest to India) and the `starter` paid plan, because only paid services can have a disk. You can see and change both in the dashboard.

### A2. Bring your existing quotations (`db.sqlite3`)

1. On your PC create an SSH key if you have none: `ssh-keygen -t ed25519` (press Enter at every question). Show the public key with `type %USERPROFILE%\.ssh\id_ed25519.pub`, copy it, and add it in Render: **Account Settings, SSH Public Keys**.
2. On the service page press **Connect**, then **SSH**: it shows an address like `srv-abc123@ssh.singapore.render.com`.
3. From your project folder on your PC:

```
scp -s db.sqlite3 srv-abc123@ssh.singapore.render.com:/data/db.sqlite3
```

(If your `scp` does not know `-s`, leave it out.)

4. Restart the service (**Manual Deploy**, then **Restart service**). The start-up script gives the disk to the app and the app opens your database.

Starting empty instead? Skip this section.

### A3. Updates, backups, and keeping it safe

* **Updating:** push to GitHub (`git add .`, `git commit -m "..."`, `git push`). Render rebuilds and deploys by itself. The switch takes a few seconds, during which the app is unavailable.
* **Backups:** Render snapshots the disk once every 24 hours. Now and then also download a copy to your PC:

```
scp -s srv-abc123@ssh.singapore.render.com:/data/db.sqlite3 backup-2026-10-10.sqlite3
```

* **Only one copy of the app runs** (a disk can belong to one instance), so do not raise the number of instances.

### A4. Turning sign-in on (when the test is over)

In Render: your service, **Environment**, set `DJANGO_REQUIRE_LOGIN` to `true`, save (it redeploys). Create the first user in the service's **Shell** tab:

```
python manage.py createsuperuser
```

(If your PC database already had your admin user, its username and password work.) More staff: sign in at `/admin/` and add users. Until then the **Log out** button does not appear.

---

## Way B: Render, free (a short trial)

Read the table at the top first: the database is **deleted 30 days after you create it**, the app **sleeps** when idle, and the instance is **small**.

### B1. The database

Render dashboard: **New**, **PostgreSQL**. Name `dehlsen-db`, region **Singapore**, plan **Free**, create. When it is ready, open it and copy the **Internal Database URL** (and, for step B3, the **External Database URL**).

### B2. The web service (no blueprint: do not use `render.yaml` for this way)

**New**, **Web Service**, pick your GitHub repository, then:

* **Language:** Docker. **Region:** Singapore (the **same** as the database). **Instance type:** Free.
* **Advanced, Health Check Path:** `/offline/`
* **Environment variables:**

| Name | Value |
|---|---|
| `DJANGO_SECRET_KEY` | a long random text: run `python -c "import secrets; print(secrets.token_urlsafe(50))"` on your PC and paste the result |
| `DJANGO_REQUIRE_LOGIN` | `false` |
| `DATABASE_URL` | the **Internal** Database URL from B1 |
| `DJANGO_HSTS_SECONDS` | `0` |

Create the service and wait for **Live**. The tables are created automatically on start. The first visit after a sleep takes about a minute, and Render shows a loading page meanwhile.

### B3. Bring your existing quotations (optional)

On your PC, in the project folder (cmd, venv active). Python on Windows needs UTF-8 for the rupee sign:

```
set PYTHONUTF8=1
pip install "psycopg[binary]" whitenoise
py manage.py dumpdata --natural-foreign --natural-primary -e contenttypes -e auth.permission -e admin.logentry -e sessions -o data.json
```

Then point the same project at the **External** database URL and load the file:

```
set DATABASE_URL=PASTE_THE_EXTERNAL_URL_HERE
set DJANGO_SETTINGS_MODULE=quotation_pwa.settings_production
set DJANGO_SECRET_KEY=any-long-text-of-at-least-32-characters-please
set DJANGO_ALLOWED_HOSTS=localhost
py manage.py migrate
py manage.py loaddata data.json
```

Close that cmd window afterwards (the settings you typed there only lived in it).

### B4. Before the 30 days end

Copy the data out again with the same two cmd steps, but with `dumpdata ... -o backup.json` while `DATABASE_URL` is the External URL. Then either upgrade the database to a paid plan in Render, or move to way A.

---

## Way D: Railway (a private repository works)

### Why not simply make the repository public?

* The repository contains how you calculate prices: the margin factors per plant size, the BOS amount, the structure formulas. Anyone could read them.
* Your e-mail address is in every commit.
* Making it private again later does **not** take back what was already copied.

Signing in to Railway **as `rendha`** (the owner of the repository) avoids the problem we had on Render, so there is no need.

### D1. Prepare the first-time data on your PC (once)

A new server starts with an empty database, and your app needs its rate data (products, panels, structure settings). This command saves **only that data**: not your quotations, not your users, so no customer details go to GitHub.

```
set PYTHONUTF8=1
mkdir seed
py manage.py dumpdata --natural-foreign --natural-primary -e contenttypes -e auth -e admin -e sessions -e quotations.quotation -e quotations.quotationitem --indent 1 -o seed\seed.json
dir seed
```

`seed.json` should be tens of kilobytes or more. (If dumpdata says "Unknown model", send me the message.) Then:

```
git add -A
git commit -m "first-time data"
git push
```

This file holds your **cost prices**, so the repository must stay **private**. On the server's very first start the app loads it **once**, and only into an empty database: later starts and updates never touch the data again.

### D2. Create the project

1. In a private browser window, sign in to **GitHub as `rendha`** (check the avatar).
2. Go to **railway.com**, then **Login**, then **GitHub**. Railway may ask you to verify the account (a card, or a GitHub account with some history). Check what it says before you enter anything.
3. **New Project**, then **Deploy from GitHub repo**, then pick **`rendha/quotation`**. If it is not listed, use **Configure GitHub App** and allow that repository.
4. Railway finds the `Dockerfile` by itself and starts building.

### D3. Settings

In the service, open **Variables** and add:

| Name | Value |
|---|---|
| `DJANGO_SECRET_KEY` | a long random text: `python -c "import secrets; print(secrets.token_urlsafe(50))"` |
| `DJANGO_REQUIRE_LOGIN` | `false` |
| `SQLITE_PATH` | `/data/db.sqlite3` |
| `DJANGO_HSTS_SECONDS` | `0` |
| `WEB_CONCURRENCY` | `1` |

Do **not** set `PORT` (Railway sets it) and do not set `RAILWAY_RUN_UID`. The address of your site is picked up automatically (`RAILWAY_PUBLIC_DOMAIN`).

Then add the disk: right-click the project canvas (or the service **Settings**), **Add Volume**, and use the mount path **`/data`**. Without it the database is lost at every restart.

Finally, open the service **Settings**, then **Networking**, then **Generate Domain**. You get an address like `quotation-production.up.railway.app`.

### D4. Check it

Open the **Deploy Logs**. You should see the tables being created, then **"Empty database: loading the first-time data"**, then `Listening at`. Open your address: the dashboard shows 0 quotations, and **New quotation** offers your panels and rates. Make a quotation and its **PDF**.

On later restarts the log says "The database already has data: the first-time data is NOT loaded", which is correct.

### D5. Money and updates

* **Cost:** Hobby is about $5 a month at least, then usage (memory, CPU and disk, by the second). Look at the **Usage** page after a day or two. Railway can **pause** the project if a pre-paid balance runs out.
* **Updating:** `git push`, and Railway redeploys. With a volume there is a short gap (a few seconds) while it switches.
* **Backups:** a volume has no automatic daily copy that I could confirm. Download the database now and then, or ask me for a backup button.
* Your **64 old quotations** do not come over (on purpose). If you need them, tell me and I will show you how.

---

## Way C: a server of your own (VPS)

You need: a Linux server (Ubuntu LTS, 1 vCPU and 2 GB RAM is comfortable), a **domain name** with an "A record" pointing to the server, and ports 80 and 443 open.

1. **Install Docker (once):** `curl -fsSL https://get.docker.com | sh`, then `sudo usermod -aG docker $USER` and log in again.
2. **Get the code and settings:** `git clone https://github.com/YOURNAME/YOURREPO.git quotation_pwa`, then `cd quotation_pwa`, `cp .env.example .env`, and edit `.env` (`DOMAIN`, `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS` with `https://`). The key: `python3 -c "import secrets; print(secrets.token_urlsafe(50))"`.
3. **Your existing data** (before the first start). From your PC: `scp db.sqlite3 YOURUSER@SERVER:~/quotation_pwa/db.sqlite3`. On the server:

```
docker compose build
docker compose run --rm -u root -v "$PWD/db.sqlite3:/incoming.sqlite3:ro" --entrypoint sh web -c "cp /incoming.sqlite3 /data/db.sqlite3"
rm db.sqlite3
```

4. **Start:** `docker compose up -d`, then `docker compose logs -f web`. Open `https://YOURDOMAIN`; Caddy gets the HTTPS certificate by itself.
5. **Backups every night:** `crontab -e`, add `30 2 * * * cd /home/YOURUSER/quotation_pwa && docker compose exec -T web python manage.py backup_database >> /home/YOURUSER/backup.log 2>&1`. The newest 14 copies stay in `/data/backups`; copy them off the server now and then (`docker compose cp web:/data/backups ./backups`).
6. **Updating:** `git pull` then `docker compose up -d --build`.
7. **Sign-in:** set `DJANGO_REQUIRE_LOGIN=true` in `.env`, `docker compose up -d`, then `docker compose exec web python manage.py createsuperuser`.

---

## Install it on phones (every way)

* **Android (Chrome):** open the address, tap **Install app** in the dashboard header (or the menu **Install app**).
* **iPhone (Safari):** open the address, tap **Share**, then **Add to Home Screen**. (iPhones have no install button; this is how Apple does it.)
* **PC (Chrome / Edge):** the install icon appears at the right of the address bar.

On the free Render way, the first open after a pause takes about a minute.

To use your own logo, replace the five PNG files in `quotations\static\quotations\icons\` with the **same names and sizes** (see the top of `tools\make_icons.py`) and raise `CACHE_VERSION` in `quotations\pwa.py` by one.

## Security checklist

* **Switch sign-in on (`DJANGO_REQUIRE_LOGIN=true`) before real customers' data is on the server**, or at least before the address leaves your team.
* Strong passwords for every user (the admin one especially).
* Keep secrets (`.env`, the database URL, the secret key) out of git, chat and email.
* Backups exist **and** a copy is on your own PC.

## If something goes wrong

| You see | Why / what to do |
|---|---|
| Render build fails at `pip install` | `requirements.txt` has a Windows-only package, or is missing. Open the build log, delete that line, push again |
| Render says the service did not become healthy | Check the **Logs** tab. The service must answer on the port Render gives it (the Dockerfile already uses it). `ImproperlyConfigured` lines tell you which setting is missing |
| `ImproperlyConfigured: Set DJANGO_SECRET_KEY...` | The variable is missing or shorter than 32 characters |
| `400 Bad Request` | The address is not allowed: on Render it is automatic, on your own server set `DJANGO_ALLOWED_HOSTS` |
| `403 CSRF verification failed` | Own server: `DJANGO_CSRF_TRUSTED_ORIGINS` must contain `https://YOURDOMAIN` |
| `attempt to write a readonly database` | The start-up script fixes the disk owner on every start: restart the service |
| Everything entered yesterday is gone (way B / free web service with SQLite) | A free service forgets its files. Use way A, or way B with `DATABASE_URL` |
| `django.db.utils...` or "relation does not exist" on way B | The tables were not created: check the Logs for the `migrate` step, and that `DATABASE_URL` is the **Internal** URL of a database in the **same region** |
| PDF gives an error 500 or the page never finishes (free instance) | The free instance is too small for PDFs. Look at the Logs; use way A |
| PDF has no background picture or the wrong font | A file name differs in capitals: run `py tools\check_assets.py` on your PC |
| A phone keeps showing an old version | Raise `CACHE_VERSION` in `quotations\pwa.py`, deploy again |
| Sign-in page appears when you expected none | `DJANGO_REQUIRE_LOGIN` is `true` or missing (the default is true). Set it to `false` |
