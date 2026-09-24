"""One shared access token for the web interface.

A case page shows somebody's income, so the moment the server is reachable
from another machine it needs a door. This is the smallest door that actually
closes: one token, set in `COPILOTO_TOKEN`, entered once and remembered in a
signed cookie.

What it is not: an identity system. It answers "is this person allowed in",
not "who is this person", and everyone who has the token is the same to it.
For a tool a monotributista shares with their accountant that is the honest
shape. Anything more would need users, and users need a place to store them.

The cookie never carries the token. It carries an HMAC of a fixed label keyed
by the token, so a stolen cookie reveals nothing and stops working the moment
the token changes. Both comparisons use `compare_digest`, which does not leak
the answer through how long it takes to say no.
"""

import hmac
from hashlib import sha256

COOKIE_NAME = "copiloto_sesion"
_SESSION_LABEL = b"copiloto-sesion-v1"

# Eight hours: a working day, so an accountant is not asked twice in one
# afternoon, and a borrowed laptop does not stay open until next week.
COOKIE_MAX_AGE = 8 * 60 * 60


def session_value(token: str) -> str:
    """The cookie contents for a given token."""
    return hmac.new(token.encode("utf-8"), _SESSION_LABEL, sha256).hexdigest()


def token_matches(token: str, offered: str) -> bool:
    """Whether what was typed into the form is the access token."""
    return hmac.compare_digest(token.encode("utf-8"), offered.encode("utf-8"))


def session_is_valid(token: str, cookie: str | None) -> bool:
    """Whether a request's cookie was issued for this token."""
    if not cookie:
        return False
    return hmac.compare_digest(session_value(token), cookie)
