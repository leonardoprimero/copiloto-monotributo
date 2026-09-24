"""Protecting the web interface when it is not on localhost.

A case URL shows somebody's income. On a laptop that is fine; the moment the
server is reachable from another machine, anybody who guesses a case id can
read it. So there is one shared token, off by default and on the moment
`COPILOTO_TOKEN` is set.

One token for everyone is not an identity system, and the copilot does not
pretend otherwise: it answers "is this person allowed in", not "who is this
person". That is the honest shape for a tool a monotributista shares with
their accountant.
"""

from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from copiloto.web.app import WebSettings, create_app

TOKEN = "un-secreto-largo-y-dificil"  # noqa: S105  (a fixture, not a credential)
TODAY = date(2026, 9, 24)


def app_with(token: str | None, tmp_path: Path) -> TestClient:
    settings = WebSettings(
        state_db=tmp_path / "cases.sqlite",
        extractor_mode="fake",
        clock=lambda: TODAY,
        access_token=token,
    )
    return TestClient(create_app(settings), follow_redirects=False)


@pytest.fixture
def guarded(tmp_path: Path) -> TestClient:
    return app_with(TOKEN, tmp_path)


@pytest.fixture
def open_app(tmp_path: Path) -> TestClient:
    return app_with(None, tmp_path)


class TestWithoutAToken:
    def test_everything_stays_open(self, open_app: TestClient) -> None:
        """The default is a tool on your own machine; a login would be noise."""
        assert open_app.get("/").status_code == 200

    def test_there_is_no_login_page_to_find(self, open_app: TestClient) -> None:
        assert open_app.get("/entrar").status_code == 404


class TestWithAToken:
    def test_the_home_page_redirects_to_the_login(self, guarded: TestClient) -> None:
        page = guarded.get("/")

        assert page.status_code == 303
        assert page.headers["location"] == "/entrar"

    def test_a_case_url_is_protected_too(self, guarded: TestClient) -> None:
        """The case pages are the ones that actually show the income."""
        page = guarded.get("/casos/cualquiera")

        assert page.status_code == 303
        assert page.headers["location"] == "/entrar"

    def test_posting_a_case_without_entering_is_refused(self, guarded: TestClient) -> None:
        page = guarded.post("/casos/ejemplo/category_change")

        assert page.status_code == 303
        assert page.headers["location"] == "/entrar"

    def test_the_login_page_is_reachable(self, guarded: TestClient) -> None:
        page = guarded.get("/entrar")

        assert page.status_code == 200
        assert "Clave de acceso" in page.text

    def test_the_stylesheet_stays_public(self, guarded: TestClient) -> None:
        """It is a stylesheet. Locking it only breaks the login page."""
        assert guarded.get("/static/style.css").status_code == 200


class TestEntering:
    def test_the_right_token_opens_the_copilot(self, guarded: TestClient) -> None:
        entered = guarded.post("/entrar", data={"token": TOKEN})

        assert entered.status_code == 303
        assert entered.headers["location"] == "/"
        assert guarded.get("/").status_code == 200

    def test_a_wrong_token_is_refused_and_says_so(self, guarded: TestClient) -> None:
        refused = guarded.post("/entrar", data={"token": "adivinado"})

        assert refused.status_code == 401
        assert "no es correcta" in refused.text

    def test_a_wrong_token_leaves_the_door_shut(self, guarded: TestClient) -> None:
        guarded.post("/entrar", data={"token": "adivinado"})

        assert guarded.get("/").status_code == 303

    def test_an_empty_token_is_refused(self, guarded: TestClient) -> None:
        assert guarded.post("/entrar", data={"token": ""}).status_code == 401


class TestTheCookie:
    def test_it_is_not_readable_from_javascript(self, guarded: TestClient) -> None:
        """An XSS anywhere would otherwise hand over the session."""
        entered = guarded.post("/entrar", data={"token": TOKEN})

        assert "httponly" in entered.headers["set-cookie"].lower()

    def test_it_is_not_sent_on_cross_site_requests(self, guarded: TestClient) -> None:
        entered = guarded.post("/entrar", data={"token": TOKEN})

        assert "samesite=lax" in entered.headers["set-cookie"].lower()

    def test_it_never_contains_the_token_itself(self, guarded: TestClient) -> None:
        """A cookie is stored on disk by the browser; the token must not be."""
        entered = guarded.post("/entrar", data={"token": TOKEN})

        assert TOKEN not in entered.headers["set-cookie"]

    def test_a_forged_cookie_does_not_open_anything(self, guarded: TestClient) -> None:
        guarded.cookies.set("copiloto_sesion", "inventado")

        assert guarded.get("/").status_code == 303

    def test_a_cookie_from_another_token_does_not_travel(self, tmp_path: Path) -> None:
        """Changing the token must lock out whoever had the old one.

        Two servers, two tokens: the session of one is worthless on the other.
        """
        first = app_with(TOKEN, tmp_path)
        first.post("/entrar", data={"token": TOKEN})
        stolen = first.cookies.get("copiloto_sesion")

        second = app_with("otro-secreto-distinto", tmp_path)
        second.cookies.set("copiloto_sesion", stolen or "")

        assert second.get("/").status_code == 303


class TestLeaving:
    def test_logging_out_closes_the_session(self, guarded: TestClient) -> None:
        guarded.post("/entrar", data={"token": TOKEN})

        left = guarded.post("/salir")

        assert left.status_code == 303
        assert guarded.get("/").status_code == 303

    def test_the_page_offers_the_way_out(self, guarded: TestClient) -> None:
        guarded.post("/entrar", data={"token": TOKEN})

        assert "Salir" in guarded.get("/").text
