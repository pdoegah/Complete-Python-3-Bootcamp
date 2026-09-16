import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import create_app  # noqa: E402


@pytest.fixture
def app(tmp_path):
    return create_app({"DATA_DIR": str(tmp_path), "DATABASE": str(tmp_path / "t.sqlite3"),
                       "TESTING": True, "SESSION_COOKIE_SECURE": False})


@pytest.fixture
def client(app):
    return app.test_client()


def csrf(client, path):
    html = client.get(path).get_data(as_text=True)
    return re.search(r'name="csrf" value="([^"]+)"', html).group(1)


def setup_manager(client, username="charles", name="Charles Quaye", password="secret-pass-1"):
    token = csrf(client, "/manage/setup")
    return client.post("/manage/setup", data={"csrf": token, "username": username, "display_name": name, "password": password})


def add(client, name, amount, paid_on="2026-09-16", note=""):
    token = csrf(client, "/manage")
    return client.post("/manage/entry", data={"csrf": token, "name": name, "amount": amount, "paid_on": paid_on, "note": note})


def test_public_page_is_readable_without_login(client):
    r = client.get("/")
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert "Emmanuel Papa Nii Quaye" in body
    assert "No contributions recorded yet" in body
    assert "Manager sign in" in body


def test_manage_redirects_to_setup_then_login(client):
    assert client.get("/manage").headers["Location"].endswith("/manage/setup")
    setup_manager(client)
    client.post("/manage/logout", data={"csrf": csrf(client, "/manage")})
    assert client.get("/manage").headers["Location"].startswith("/manage/login")
    assert client.get("/manage/setup").headers["Location"].endswith("/manage/login")


def test_setup_creates_and_signs_in_first_manager(client):
    r = setup_manager(client)
    assert r.headers["Location"].endswith("/manage")
    body = client.get("/manage").get_data(as_text=True)
    assert "Signed in as <b>Charles Quaye</b>" in body


def test_record_edit_delete_and_totals(client):
    setup_manager(client)
    add(client, "Amina Yusuf", "200", "2026-09-02", "Bank transfer")
    add(client, "amina  yusuf", "1,250.50", "2026-09-10")
    add(client, "Kwame Mensah", "150", "2026-09-03", "USD 10 via MoMo")
    body = client.get("/").get_data(as_text=True)
    assert "GH₵1,600.50" in body                      # total
    assert body.count("people who gave") == 1
    assert re.search(r'<div class="value">2</div><div class="sub">people who gave', body)
    assert re.search(r'<div class="value">3</div><div class="sub">payments recorded', body)
    entries = client.get("/?view=entries").get_data(as_text=True)
    assert "USD 10 via MoMo" in entries

    # edit
    html = client.get("/manage").get_data(as_text=True)
    entry_id = int(re.search(r"/manage/entry/(\d+)/edit", html).group(1))
    token = csrf(client, f"/manage/entry/{entry_id}/edit")
    r = client.post(f"/manage/entry/{entry_id}/edit", data={"csrf": token, "name": "Amina Yusuf", "amount": "99", "paid_on": "2026-09-10", "note": ""})
    assert r.status_code == 302
    # delete
    token = csrf(client, "/manage")
    r = client.post(f"/manage/entry/{entry_id}/delete", data={"csrf": token})
    assert r.status_code == 302
    body = client.get("/").get_data(as_text=True)
    assert "GH₵350.00" in body


def test_invalid_amount_is_rejected(client):
    setup_manager(client)
    add(client, "Someone", "abc")
    body = client.get("/manage").get_data(as_text=True)
    assert "Enter the amount as a number" in body
    assert "No contributions recorded yet" in body
    add(client, "Someone", "-5")
    assert "must be more than zero" in client.get("/manage").get_data(as_text=True)


def test_write_routes_need_login_and_csrf(client):
    setup_manager(client)
    client.post("/manage/logout", data={"csrf": csrf(client, "/manage")})
    r = client.post("/manage/entry", data={"name": "x", "amount": "1", "paid_on": "2026-09-16"})
    assert r.status_code == 400                       # no csrf token
    assert client.get("/").get_data(as_text=True).count("No contributions recorded yet") == 1


def test_wrong_password_and_lockout(client, app):
    setup_manager(client)
    client.post("/manage/logout", data={"csrf": csrf(client, "/manage")})
    for _ in range(8):
        token = csrf(client, "/manage/login")
        r = client.post("/manage/login", data={"csrf": token, "username": "charles", "password": "nope"})
        assert "Wrong username or password" in r.get_data(as_text=True)
    token = csrf(client, "/manage/login")
    r = client.post("/manage/login", data={"csrf": token, "username": "charles", "password": "secret-pass-1"})
    assert "Too many failed attempts" in r.get_data(as_text=True)


def test_at_most_two_managers(client):
    setup_manager(client)
    token = csrf(client, "/manage/managers")
    r = client.post("/manage/managers", data={"csrf": token, "username": "emmanuel", "display_name": "Emmanuel Kpakpo Addo", "password": "another-pass-2"})
    assert r.status_code == 302
    body = client.get("/").get_data(as_text=True)
    assert "Charles Quaye, Emmanuel Kpakpo Addo" in body
    token = csrf(client, "/manage/managers")
    r = client.post("/manage/managers", data={"csrf": token, "username": "third", "display_name": "Third Person", "password": "another-pass-3"})
    assert "at most 2 managers" in r.get_data(as_text=True)
    # second manager can sign in with the password they were given
    client.post("/manage/logout", data={"csrf": csrf(client, "/manage")})
    token = csrf(client, "/manage/login")
    r = client.post("/manage/login", data={"csrf": token, "username": "Emmanuel", "password": "another-pass-2"})
    assert r.headers["Location"].endswith("/manage")


def test_settings_and_csv(client):
    setup_manager(client)
    token = csrf(client, "/manage/settings")
    r = client.post("/manage/settings", data={"csrf": token, "group_name": "Test Fund", "description": "d", "currency": "usd", "goal": "1000"})
    assert r.status_code == 302
    add(client, "A Person", "250")
    body = client.get("/").get_data(as_text=True)
    assert "<title>Test Fund</title>" in body and "$250.00" in body and "25%" in body
    csv_text = client.get("/export.csv").get_data(as_text=True)
    assert csv_text.splitlines()[0] == "Date,Member,Amount,Currency,Note"
    assert "2026-09-16,A Person,250.00,USD," in csv_text


def test_change_password(client):
    setup_manager(client)
    token = csrf(client, "/manage/password")
    r = client.post("/manage/password", data={"csrf": token, "current": "wrong", "new": "new-pass-123", "confirm": "new-pass-123"})
    assert "current password is wrong" in r.get_data(as_text=True)
    token = csrf(client, "/manage/password")
    r = client.post("/manage/password", data={"csrf": token, "current": "secret-pass-1", "new": "new-pass-123", "confirm": "new-pass-123"})
    assert r.status_code == 302
    client.post("/manage/logout", data={"csrf": csrf(client, "/manage")})
    token = csrf(client, "/manage/login")
    r = client.post("/manage/login", data={"csrf": token, "username": "charles", "password": "new-pass-123"})
    assert r.headers["Location"].endswith("/manage")
