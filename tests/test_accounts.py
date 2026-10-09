import pytest

from accounts.crypto import mask_pan
from accounts.models import PanProfile
from ipos.models import Application

from .conftest import make_pan

pytestmark = pytest.mark.django_db


class TestAuth:
    def test_register_then_login(self, anon):
        res = anon.post("/api/auth/register/", {
            "email": "new@example.com", "full_name": "New",
            "password": "s3cure-Passw0rd", "password_confirm": "s3cure-Passw0rd",
        })
        assert res.status_code == 201
        assert "password" not in res.data

        res = anon.post("/api/auth/login/", {"email": "new@example.com", "password": "s3cure-Passw0rd"})
        assert res.status_code == 200
        assert {"access", "refresh", "user"} <= res.data.keys()
        assert res.data["user"]["email"] == "new@example.com"

    def test_register_rejects_mismatched_passwords(self, anon):
        res = anon.post("/api/auth/register/", {
            "email": "x@example.com", "password": "s3cure-Passw0rd", "password_confirm": "nope-Passw0rd",
        })
        assert res.status_code == 400
        assert "password_confirm" in res.data

    def test_endpoints_require_auth(self, anon):
        assert anon.get("/api/pans/").status_code == 401
        assert anon.get("/api/applications/").status_code == 401

    def test_me(self, client, user):
        make_pan(user)
        res = client.get("/api/auth/me/")
        assert res.data["email"] == user.email
        assert res.data["pan_count"] == 1


class TestPan:
    def test_pan_is_encrypted_and_masked(self, client):
        res = client.post("/api/pans/", {"label": "Self", "pan": "abcde1234f"})
        assert res.status_code == 201, res.data
        assert res.data["pan_masked"] == "XXXXX1234F"
        assert "pan" not in res.data

        obj = PanProfile.objects.get(pk=res.data["id"])
        assert b"ABCDE1234F" not in bytes(obj.pan_encrypted)
        assert obj.pan == "ABCDE1234F"

    def test_invalid_pan_rejected(self, client):
        res = client.post("/api/pans/", {"label": "Self", "pan": "12345ABCDE"})
        assert res.status_code == 400

    def test_duplicate_pan_rejected(self, client, user):
        make_pan(user)
        res = client.post("/api/pans/", {"label": "Again", "pan": "ABCDE1234F"})
        assert res.status_code == 400

    def test_same_pan_allowed_for_different_users(self, client, other_user):
        make_pan(other_user)
        res = client.post("/api/pans/", {"label": "Self", "pan": "ABCDE1234F"})
        assert res.status_code == 201

    def test_cannot_see_or_touch_other_users_pans(self, client, other_user):
        theirs = make_pan(other_user)
        assert client.get("/api/pans/").data["count"] == 0
        assert client.get(f"/api/pans/{theirs.pk}/").status_code == 404
        assert client.delete(f"/api/pans/{theirs.pk}/").status_code == 404

    def test_delete_with_history_soft_deletes(self, client, user, ipo):
        pan = make_pan(user)
        Application.objects.create(owner=user, ipo=ipo, pan=pan, bid_price=100)
        assert client.delete(f"/api/pans/{pan.pk}/").status_code == 204
        pan.refresh_from_db()
        assert pan.is_active is False


def test_mask_pan():
    assert mask_pan("ABCDE1234F") == "XXXXX1234F"


@pytest.mark.django_db
def test_login_is_throttled(anon, user):
    codes = [anon.post("/api/auth/login/", {"email": user.email, "password": "wrong"}).status_code
             for _ in range(11)]
    assert codes[:10] == [401] * 10
    assert codes[10] == 429
