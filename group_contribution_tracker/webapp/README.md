# Contribution Ledger web app

The standalone version of the ledger. It runs on any host that can run a
Python web app, and it does not depend on claude.ai. Members open a link and
see who contributed and how much. Two managers sign in with a username and
password to record contributions.

## What is in the box

| Path | Purpose |
| --- | --- |
| `app.py` | The whole application: database, pages, sign-in, CSV export |
| `templates/` | The HTML pages |
| `static/style.css` | The look of the pages |
| `wsgi.py` | The entry point a web host imports |
| `requirements.txt` | The two Python packages it needs (Flask, gunicorn) |
| `tests/test_app.py` | Automated checks. Run with `python -m pytest tests` |

Everything the app stores goes in a `data/` folder next to `app.py`:
the database `ledger.sqlite3` and a generated `secret_key.txt`. Back up
that folder and you have backed up the ledger.

## Pages

| Address | Who | What |
| --- | --- | --- |
| `/` | Everyone | The public ledger: totals, by-member summary, all entries, search |
| `/export.csv` | Everyone | The entries as a spreadsheet file |
| `/manage/setup` | First visitor only | Creates the first manager account. Disappears afterwards |
| `/manage/login` | Managers | Sign in |
| `/manage` | Managers | Record, edit and delete contributions |
| `/manage/settings` | Managers | Group name, description, currency, optional goal |
| `/manage/managers` | Managers | Add or remove the other manager (two at most) |
| `/manage/password` | Managers | Change your own password |

## How access control works

- The public pages need no sign-in and have no way to change anything.
- Every page under `/manage` requires a signed-in manager. Passwords are
  stored as salted hashes, never in plain text.
- The ledger allows at most two manager accounts. The first is created on
  the setup page; that manager adds the second.
- Eight wrong passwords in fifteen minutes lock that username out for
  fifteen minutes.
- Every form carries a one-time token so another website cannot submit it
  on a manager's behalf.

## Hosting it for free on PythonAnywhere

PythonAnywhere keeps files permanently on its free plan, which matters
because the ledger is a file. Other free hosts wipe the disk on restart.

**Step 1. Create the account.**
Go to https://www.pythonanywhere.com, choose the free "Beginner" plan, and
pick a username. Your public link will be
`https://<username>.pythonanywhere.com`.

**Step 2. Put the code on the server.**
Open the **Files** tab. Upload `contribution-ledger-webapp.zip` (the file
that came with these instructions) into your home folder. Then open a
**Bash console** from the dashboard and run:

```
unzip contribution-ledger-webapp.zip
pip3 install --user -r webapp/requirements.txt
```

That creates a `webapp` folder at `/home/<username>/webapp`.

If you prefer to get the code from GitHub instead, run this in the Bash
console and use `/home/<username>/Complete-Python-3-Bootcamp/group_contribution_tracker/webapp`
as the folder in the steps below:

```
git clone https://github.com/pdoegah/Complete-Python-3-Bootcamp.git
pip3 install --user -r Complete-Python-3-Bootcamp/group_contribution_tracker/webapp/requirements.txt
```

**Step 3. Create the web app.**
Open the **Web** tab, press **Add a new web app**, choose **Manual
configuration**, then the newest **Python 3** version offered.

**Step 4. Point it at the code.**
Still on the Web tab:

- Under **Code**, set *Source code* to `/home/<username>/webapp`
- Under **Code**, click the *WSGI configuration file* link. Delete
  everything in it and paste:

```python
import sys
sys.path.insert(0, "/home/<username>/webapp")
from wsgi import application
```

- Under **Static files**, add one row: URL `/static/`, directory
  `/home/<username>/webapp/static`

Replace `<username>` with your PythonAnywhere username in all three places.

**Step 5. Reload and set up.**
Press the green **Reload** button. Open
`https://<username>.pythonanywhere.com/manage/setup` and create the first
manager account. Sign in, open **Managers**, and add the second manager.
Give each manager their username and password privately.

**Step 6. Share.**
Post `https://<username>.pythonanywhere.com` in the WhatsApp group.

**Total cost: nothing.** The Beginner plan is free, and the app needs
nothing beyond it.

**Keeping it alive.** Free PythonAnywhere apps must be renewed every three
months: sign in to PythonAnywhere, open the Web tab and press **Run until 3
months from today**. Set a phone reminder. The app keeps its data either
way; only the website goes to sleep if you forget.

## Hosting it anywhere else

The app is a normal WSGI application. On Render, Railway, Fly.io or a VPS:

```
pip install -r requirements.txt
gunicorn wsgi:application --bind 0.0.0.0:8000
```

Set `DATA_DIR` to a directory that survives restarts. On a host whose disk
is wiped on each deploy, attach a persistent volume and point `DATA_DIR`
at it, or the ledger will be lost.

Optional environment variables:

| Name | Meaning |
| --- | --- |
| `DATA_DIR` | Where to keep the database and key. Default: `./data` |
| `SECRET_KEY` | Cookie-signing key. Default: generated once into `data/secret_key.txt` |
| `COOKIE_SECURE` | Set to `0` only when running without HTTPS, such as on your own laptop |

## If a manager is locked out

From a console on the server, inside the `webapp` folder:

```
flask --app app reset-password charles
flask --app app list-managers
flask --app app add-manager emmanuel "Emmanuel Kpakpo Addo"
```

Each command prompts for the password rather than taking it on the command line.

## Running it on your own computer

```
pip install -r requirements.txt
COOKIE_SECURE=0 flask --app app run
```

Then open http://127.0.0.1:5000 in a browser.
