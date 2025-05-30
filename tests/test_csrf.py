"""
test_csrf
~~~~~~~~~~~~~~~~~

CSRF tests

:copyright: (c) 2019-2024 by J. Christopher Wagner (jwag).
:license: MIT, see LICENSE for more details.
"""

from contextlib import contextmanager
from datetime import date, timedelta

import flask_wtf.csrf

import pytest
from flask_wtf import CSRFProtect
from freezegun import freeze_time
from flask import render_template_string

from flask_security import Security, auth_required
from tests.test_utils import get_form_input_value, get_session, logout


REAL_VALIDATE_CSRF = None


@contextmanager
def mp_validate_csrf():
    """Make sure we are really calling CSRF validation and getting correct answer"""
    orig_validate_csrf = flask_wtf.csrf.validate_csrf
    try:
        mp = MpValidateCsrf(orig_validate_csrf)
        flask_wtf.csrf.validate_csrf = mp.mp_validate_csrf
        yield mp
    finally:
        flask_wtf.csrf.validate_csrf = orig_validate_csrf


class MpValidateCsrf:
    success = 0
    failure = 0

    def __init__(self, real_validate_csrf):
        MpValidateCsrf.success = 0
        MpValidateCsrf.failure = 0
        global REAL_VALIDATE_CSRF
        REAL_VALIDATE_CSRF = real_validate_csrf

    @staticmethod
    def mp_validate_csrf(data, secret_key=None, time_limit=None, token_key=None):
        try:
            REAL_VALIDATE_CSRF(data, secret_key, time_limit, token_key)
            MpValidateCsrf.success += 1
        except Exception:
            MpValidateCsrf.failure += 1
            raise


def _get_csrf_token(client):
    response = client.get(
        "/login", data={}, headers={"Content-Type": "application/json"}
    )
    return response.json["response"]["csrf_token"]


def json_login(
    client,
    email="matt@lp.com",
    password="password",
    endpoint=None,
    use_header=False,
    remember=None,
):
    # Return tuple (auth_token, csrf_token)
    csrf_token = _get_csrf_token(client)
    data = dict(email=email, password=password, remember=remember)

    if use_header:
        headers = {"X-CSRF-Token": csrf_token}
    else:
        headers = {}
        data["csrf_token"] = csrf_token

    response = client.post(
        endpoint or "/login?include_auth_token",
        content_type="application/json",
        json=data,
        headers=headers,
    )
    assert response.status_code == 200
    rd = response.json["response"]
    return rd["user"]["authentication_token"], rd["csrf_token"]


def json_logout(client):
    response = client.post("logout", content_type="application/json", data={})
    assert response.status_code == 200
    assert response.json["meta"]["code"] == 200
    return response


@pytest.mark.csrf()
def test_login_csrf(app, client):
    # This shouldn't log in - but return login form with csrf token.
    data = dict(email="matt@lp.com", password="password", remember="y")
    response = client.post("/login", data=data)
    assert response.status_code == 200
    assert b"The CSRF token is missing." in response.data

    data["csrf_token"] = get_form_input_value(response, "csrf_token")
    response = client.post("/login", data=data, follow_redirects=True)
    assert response.status_code == 200
    assert b"Welcome matt" in response.data

    response = logout(client, follow_redirects=True)
    assert response.status_code == 200
    assert b"Log in" in response.data


def test_login_csrf_double(app, client):
    # Test if POST login while already logged in - just redirects to POST_LOGIN
    app.config["WTF_CSRF_ENABLED"] = True

    # This shouldn't log in - but return login form with csrf token.
    data = dict(email="matt@lp.com", password="password", remember="y")
    response = client.post("/login", data=data)
    assert response.status_code == 200
    assert b"csrf_token" in response.data

    data["csrf_token"] = _get_csrf_token(client)
    response = client.post("/login", data=data, follow_redirects=True)
    assert response.status_code == 200
    assert b"Welcome matt" in response.data

    data["csrf_token"] = _get_csrf_token(client)
    # Note - should redirect to POST_LOGIN with current user ignoring form data.
    data["email"] = "newguy@me.com"
    response = client.post("/login", data=data, follow_redirects=True)
    assert response.status_code == 200
    assert b"Welcome matt" in response.data


@pytest.mark.csrf()
def test_login_csrf_json(app, client):
    with mp_validate_csrf() as mp:
        auth_token, csrf_token = json_login(client)
        assert auth_token
        assert csrf_token
    # Should be just one call to validate - since CSRFProtect not enabled.
    assert mp.success == 1 and mp.failure == 0

    response = json_logout(client)
    session = get_session(response)
    assert "csrf_token" not in session


@pytest.mark.csrf(csrfprotect=True)
def test_login_csrf_json_header(app, client):
    with mp_validate_csrf() as mp:
        auth_token, csrf_token = json_login(client, use_header=True)
        assert auth_token
        assert csrf_token
    assert mp.success == 1 and mp.failure == 0
    json_logout(client)


@pytest.mark.settings(csrf_ignore_unauth_endpoints=True)
def test_login_csrf_unauth_ok(app, client):
    app.config["WTF_CSRF_ENABLED"] = True

    with mp_validate_csrf() as mp:
        # This should log in.
        data = dict(email="matt@lp.com", password="password", remember="y")
        response = client.post("/login", data=data, follow_redirects=True)
        assert response.status_code == 200
        assert b"Welcome matt" in response.data
    assert mp.success == 0 and mp.failure == 0
    logout(client)


@pytest.mark.settings(csrf_ignore_unauth_endpoints=True)
def test_login_csrf_unauth_double(app, client, get_message):
    # Test double login w/o CSRF returns unauth required error message.
    app.config["WTF_CSRF_ENABLED"] = True

    # This should log in.
    data = dict(email="matt@lp.com", password="password", remember="y")
    response = client.post("/login", data=data, follow_redirects=True)
    assert response.status_code == 200
    assert b"Welcome matt" in response.data

    # login in again - should work
    response = client.post("/login", content_type="application/json", json=data)
    assert response.status_code == 400
    assert response.json["response"]["errors"][0].encode("utf-8") == get_message(
        "ANONYMOUS_USER_REQUIRED"
    )


@pytest.mark.csrf()
@pytest.mark.recoverable()
def test_reset(app, client):
    """Test that form-based CSRF works for /reset"""
    response = client.get("/reset", content_type="application/json")
    csrf_token = response.json["response"]["csrf_token"]

    with mp_validate_csrf() as mp:
        data = dict(email="matt@lp.com")
        # should fail - no CSRF token - should get a JSON response
        response = client.post("/reset", content_type="application/json", json=data)
        assert response.status_code == 400
        assert response.json["response"]["errors"][0] == "The CSRF token is missing."
        # test template also has error - since using just Flask-WTF form based CSRF -
        # should be an error on the csrf_token field.
        response = client.post("/reset", data=data)
        assert b'class="fs-error-msg">The CSRF token is missing' in response.data

        # test sending csrf_token works - JSON
        data["csrf_token"] = csrf_token
        response = client.post("/reset", content_type="application/json", json=data)
        assert response.status_code == 200

        # test sending csrf_token works - forms
        response = client.post("/reset", data=data)
        assert b"Send password reset instructions" in response.data
    assert mp.success == 2 and mp.failure == 2


@pytest.mark.recoverable()
@pytest.mark.csrf(csrfprotect=True)
def test_cp_reset(app, client):
    """Test that header based CSRF works for /reset when
    using WTF_CSRF_CHECK_DEFAULT=False.
    """
    with mp_validate_csrf() as mp:
        data = dict(email="matt@lp.com")
        # should fail - no CSRF token
        response = client.post("/reset", content_type="application/json", json=data)
        assert response.status_code == 400
        assert response.json["response"]["errors"][0] == "The CSRF token is missing."

        csrf_token = _get_csrf_token(client)
        response = client.post(
            "/reset",
            content_type="application/json",
            json=data,
            headers={"X-CSRF-Token": csrf_token},
        )
        assert response.status_code == 200
    assert mp.success == 1 and mp.failure == 1


@pytest.mark.changeable()
@pytest.mark.csrf(csrfprotect=True)
@pytest.mark.settings(csrf_header="X-XSRF-Token")
def test_cp_with_token(app, client):
    # Make sure can use returned CSRF-Token in Header.
    # Since the csrf token isn't in the form - must enable app-wide CSRF
    # using CSRFProtect() - as the above mark does.
    # Using X-XSRF-Token as header tests that we properly
    # add that as a known header to WTFforms.
    auth_token, csrf_token = json_login(client, use_header=True)

    # make sure returned csrf_token works in header.
    data = dict(
        password="password",
        new_password="battery staple",
        new_password_confirm="battery staple",
    )

    with mp_validate_csrf() as mp:
        response = client.post(
            "/change",
            content_type="application/json",
            json=data,
            headers={"X-XSRF-Token": csrf_token},
        )
        assert response.status_code == 200
    assert mp.success == 1 and mp.failure == 0
    json_logout(client)


def test_cp_login_json_no_session(app, sqlalchemy_datastore):
    # Test with global CSRFProtect on and not sending cookie - nothing works.
    app.config["WTF_CSRF_ENABLED"] = True
    CSRFProtect(app)
    app.security = Security(app=app, datastore=sqlalchemy_datastore)

    client_nc = app.test_client(use_cookies=False)

    # This shouldn't log in - and will return 400
    with mp_validate_csrf() as mp:
        data = dict(email="matt@lp.com", password="password", remember="y")
        response = client_nc.post(
            "/login",
            content_type="application/json",
            json=data,
            headers={"Accept": "application/json"},
        )
        assert response.status_code == 400

        # This still wont work since we don't send a session cookie
        response = client_nc.post(
            "/login",
            content_type="application/json",
            json=data,
            headers={"X-CSRF-Token": _get_csrf_token(client_nc)},
        )
        assert response.status_code == 400

    # Although failed - CSRF should have been called
    assert mp.failure == 2


@pytest.mark.settings(CSRF_PROTECT_MECHANISMS=["basic", "session"])
def test_cp_config(app, sqlalchemy_datastore):
    # Test improper config (must have WTF_CSRF_CHECK_DEFAULT false if setting
    # CSRF_PROTECT_MECHANISMS
    from flask_security import Security

    app.config["WTF_CSRF_ENABLED"] = True
    CSRFProtect(app)

    # The check is done on first request.
    with pytest.raises(ValueError) as ev:
        Security(app=app, datastore=sqlalchemy_datastore)
    assert "must be set to False" in str(ev.value)


@pytest.mark.settings(CSRF_PROTECT_MECHANISMS=["basic", "session"])
def test_cp_config2(app, sqlalchemy_datastore):
    # Test improper config (must have CSRFProtect configured if setting
    # CSRF_PROTECT_MECHANISMS
    from flask_security import Security

    app.config["WTF_CSRF_ENABLED"] = True

    with pytest.raises(ValueError) as ev:
        Security(app=app, datastore=sqlalchemy_datastore)
    assert "CsrfProtect not part of application" in str(ev.value)


@pytest.mark.changeable()
@pytest.mark.csrf(csrfprotect=True)
@pytest.mark.settings(CSRF_PROTECT_MECHANISMS=["basic", "session"])
def test_different_mechanisms(app, client):
    # Verify that using token doesn't require CSRF, but sessions do
    with mp_validate_csrf() as mp:
        auth_token, csrf_token = json_login(client, use_header=True)

        # session based change password should fail
        data = dict(
            password="password",
            new_password="battery staple",
            new_password_confirm="battery staple",
        )

        response = client.post(
            "/change", json=data, headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 400
        assert b"The CSRF token is missing" in response.data

        # token based should work
        response = client.post(
            "/change",
            json=data,
            headers={
                "Content-Type": "application/json",
                "Authentication-Token": auth_token,
            },
        )
        assert response.status_code == 200
    assert mp.success == 1 and mp.failure == 1


@pytest.mark.changeable()
@pytest.mark.settings(
    CSRF_PROTECT_MECHANISMS=["basic", "session"], csrf_ignore_unauth_endpoints=True
)
def test_different_mechanisms_nc(app, client_nc):
    # Verify that using token and no session cookie works
    # Note that we had to disable unauth_endpoints since you can't log in
    # w/ CSRF if you don't send in the session cookie.
    app.config["WTF_CSRF_ENABLED"] = True
    app.config["WTF_CSRF_CHECK_DEFAULT"] = False
    CSRFProtect(app)

    with mp_validate_csrf() as mp:
        auth_token, csrf_token = json_login(client_nc)

        # token based should work
        data = dict(
            password="password",
            new_password="battery staple",
            new_password_confirm="battery staple",
        )
        response = client_nc.post(
            "/change",
            json=data,
            headers={
                "Content-Type": "application/json",
                "Authentication-Token": auth_token,
            },
        )
        assert response.status_code == 200
    assert mp.success == 0 and mp.failure == 0


@pytest.mark.changeable()
@pytest.mark.csrf(csrfprotect=True)
@pytest.mark.settings(csrf_protect_mechanisms=[])
def test_cp_with_token_empty_mechanisms(app, client):
    # If no mechanisms - shouldn't do any CSRF
    auth_token, csrf_token = json_login(client, use_header=True)

    # make sure returned csrf_token works in header.
    data = dict(
        password="password",
        new_password="battery staple",
        new_password_confirm="battery staple",
    )

    response = client.post(
        "/change",
        content_type="application/json",
        json=data,
        headers={
            "Content-Type": "application/json",
            "Authentication-Token": auth_token,
        },
    )
    assert response.status_code == 200


@pytest.mark.csrf(csrfprotect=True)
@pytest.mark.settings(csrf_ignore_unauth_endpoints=True, CSRF_COOKIE_NAME="XSRF-Token")
def test_csrf_cookie(app, client):
    json_login(client)
    assert client.get_cookie("XSRF-Token")

    # Make sure cleared on logout
    response = client.post("/logout", content_type="application/json")
    assert response.status_code == 200
    assert not client.get_cookie("XSRF-Token")


@pytest.mark.csrf(csrfprotect=True)
@pytest.mark.settings(CSRF_COOKIE={"key": "XSRF-Token"})
@pytest.mark.changeable()
def test_cp_with_token_cookie(app, client):
    # Make sure can use returned CSRF-Token cookie in Header when changing password
    json_login(client, use_header=True)

    # make sure returned csrf_token works in header.
    data = dict(
        password="password",
        new_password="battery staple",
        new_password_confirm="battery staple",
    )
    csrf_token = client.get_cookie("XSRF-Token")
    with mp_validate_csrf() as mp:
        response = client.post(
            "/change",
            content_type="application/json",
            json=data,
            headers={"X-XSRF-Token": csrf_token.value},
        )
        assert response.status_code == 200
    assert mp.success == 1 and mp.failure == 0
    json_logout(client)
    assert not client.get_cookie("XSRF-Token")


@pytest.mark.csrf(csrfprotect=True)
@pytest.mark.app_settings(wtf_csrf_time_limit=1)
@pytest.mark.settings(CSRF_COOKIE_NAME="XSRF-Token", csrf_ignore_unauth_endpoints=True)
@pytest.mark.changeable()
def test_cp_with_token_cookie_expire(app, client):
    # Make sure that we get a new Csrf-Token cookie if expired.
    # Note that we need relatively new-ish date since session cookies also expire.
    with freeze_time(date.today() + timedelta(days=-1)):
        json_login(client, use_header=True)

    # time unfrozen so should be expired
    data = dict(
        password="password",
        new_password="battery staple",
        new_password_confirm="battery staple",
    )
    csrf_token = client.get_cookie("XSRF-Token")
    with mp_validate_csrf() as mp:
        response = client.post(
            "/change",
            content_type="application/json",
            json=data,
            headers={"X-XSRF-Token": csrf_token.value},
        )
        assert response.status_code == 400
        assert b"expired" in response.data

        # Should have gotten a new CSRF cookie value
        new_csrf_token = client.get_cookie("XSRF-Token")
        assert csrf_token.value != new_csrf_token.value
    # 2 failures since the utils:csrf_cookie_handler will check
    assert mp.success == 0 and mp.failure == 2
    json_logout(client)
    assert not client.get_cookie("XSRF-Token")


@pytest.mark.csrf(csrfprotect=True)
@pytest.mark.settings(
    CSRF_COOKIE_NAME="XSRF-Token", CSRF_COOKIE_REFRESH_EACH_REQUEST=True
)
@pytest.mark.changeable()
def test_cp_with_token_cookie_refresh(app, client):
    # Test CSRF_COOKIE_REFRESH_EACH_REQUEST
    json_login(client, use_header=True)

    # make sure returned csrf_token works in header.
    data = dict(
        password="password",
        new_password="battery staple",
        new_password_confirm="battery staple",
    )

    csrf_cookie = client.get_cookie("XSRF-Token")
    with mp_validate_csrf() as mp:
        # Delete cookie - we should always get a new one
        client.delete_cookie("XSRF-Token")
        response = client.post(
            "/change",
            content_type="application/json",
            json=data,
            headers={"X-XSRF-Token": csrf_cookie.value},
        )
        assert response.status_code == 200
        assert client.get_cookie("XSRF-Token")
    assert mp.success == 1 and mp.failure == 0

    # delete cookie again, do a 'GET' - the REFRESH_COOKIE_ON_EACH_REQUEST should
    # send us a new one
    client.delete_cookie("XSRF-Token")
    response = client.get("/change")
    assert response.status_code == 200
    assert client.get_cookie("XSRF-Token")

    json_logout(client)
    assert not client.get_cookie("XSRF-Token")


@pytest.mark.csrf(csrfprotect=True)
@pytest.mark.settings(CSRF_COOKIE_NAME="XSRF-Token")
@pytest.mark.changeable()
def test_remember_login_csrf_cookie(app, client):
    # Test csrf cookie upon resuming a remember session
    # Login with remember_token generation
    json_login(client, use_header=True, remember=True)

    client.delete_cookie("XSRF-Token")
    client.delete_cookie("session")

    # Do a simple get request with the remember_token cookie present
    assert client.get_cookie("remember_token")
    response = client.get("/profile")
    assert response.status_code == 200
    assert client.get_cookie("session")
    assert client.get_cookie("XSRF-Token")
    # Logout and check that everything cleans up nicely
    json_logout(client)
    assert not client.get_cookie("remember_token")
    assert not client.get_cookie("session")
    assert not client.get_cookie("XSRF-Token")


@pytest.mark.csrf(csrfprotect=True)
@pytest.mark.registerable()
@pytest.mark.settings(csrf_header="X-CSRF-Token")
def test_json_register_csrf_with_ignore_unauth_set_to_false(app, client):
    """
    Test that you are able to register a user when using the JSON api
    and the CSRF_IGNORE_UNAUTH_ENDPOINTS is set to False.
    """

    csrf_token = client.get("/login", headers={"Accept": "application/json"}).json[
        "response"
    ]["csrf_token"]

    email = "eg@testuser.com"
    data = {"email": email, "password": "password"}

    response = client.post(
        "/register", json=data, headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 400
    assert response.json["response"]["errors"][0] == "The CSRF token is missing."

    response = client.post(
        "/register",
        json=data,
        headers={"Content-Type": "application/json", "X-CSRF-Token": csrf_token},
    )
    assert response.status_code == 200
    assert response.json["response"]["user"]["email"] == email


@pytest.mark.csrf(csrfprotect=True)
@pytest.mark.settings(
    csrf_protect_mechanisms=["session"], csrf_ignore_unauth_endpoints=True
)
def test_myform(app, client):
    # Create app form - and make sure protect_mechanisms properly skips CSRF
    # For this test - we don't configure CSRFProtect - just use form CSRF
    from flask_wtf import FlaskForm
    from wtforms import StringField

    class custom_form(FlaskForm):
        name = StringField("Name")

    @app.route("/custom", methods=["GET", "POST"])
    @auth_required()
    def custom():
        form = custom_form()
        if form.validate_on_submit():
            return render_template_string(f"Nice POST {form.name.data}")
        return render_template_string(
            f"Hi {form.name.data}, anything wrong? {form.errors}"
        )

    auth_token, csrf_token = json_login(client, use_header=True)

    # using session - POST should fail - no CSRF
    response = client.post("/custom", json={"name": "first POST"})
    assert response.status_code == 400
    assert response.json["response"]["errors"][0] == "The CSRF token is missing."

    # use CSRF token - should work
    response = client.post(
        "/custom", json={"name": "second POST"}, headers={"X-XSRF-Token": csrf_token}
    )
    assert response.status_code == 200

    # try with form input
    response = client.post(
        "/custom", data={"name": "form POST", "csrf_token": csrf_token}
    )
    assert response.data == b"Nice POST form POST"

    # now try authenticating via token - shouldn't need CSRF token
    client_nc = app.test_client(use_cookies=False)
    response = client_nc.post(
        "/custom",
        json={"name": "authtoken POST"},
        headers={
            "Content-Type": "application/json",
            "Authentication-Token": auth_token,
        },
    )
    assert b"CSRF" not in response.data


@pytest.mark.csrf(csrfprotect=True)
def test_csrf_json_protect(app, client):
    # test sending CSRF token in json body for an unauth endpoint (/login)
    # In older code the @unauth_csrf() decorator would 'fall through' - if the
    # decorator CSRF checked failed it would fall through to the form CSRF check.
    # The decorator CSRF check returns a 400 JSON response.
    csrf_token = _get_csrf_token(client)
    response = client.post(
        "/login",
        json=dict(email="matt@lp.com", password="password", csrf_token=csrf_token),
    )
    assert response.status_code == 400
    assert response.json["response"]["errors"][0] == "The CSRF token is missing."
