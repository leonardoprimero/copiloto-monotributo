"""ARCA's real padrón behind the registry Protocol.

The graph asks a `TaxpayerRegistry` for a category and cannot tell where the
answer came from. This implementation would ask ARCA, joining the two halves
documented next door: a WSAA access ticket and a constancia de inscripción
lookup.

The delegation model is the part worth understanding, because it is what keeps
this honest. The certificate belongs to whoever runs the copilot, and the
taxpayer grants that CUIT access to `ws_sr_constancia_inscripcion` from their
own Administrador de Relaciones de Clave Fiscal. The token that comes back
carries a `relations` section, and `cuitRepresentada` has to be one of them.
So the taxpayer never hands over their clave fiscal, and they can revoke the
access themselves, without asking anybody.

The ticket source and the SOAP call arrive as arguments. That is not only for
the tests: it is the seam where a deployment plugs in its own transport,
timeouts and retries, none of which belong in here.
"""

from collections.abc import Callable
from datetime import UTC, datetime

from copiloto.arca.padron import PadronError, parse_persona
from copiloto.arca.wsaa import AccessTicket
from copiloto.cuit import is_valid_cuit, normalize_cuit
from copiloto.models import TaxpayerProfile

RequestTicket = Callable[[datetime], AccessTicket]
CallPadron = Callable[[str, str, str], str]


def _utc_now() -> datetime:
    return datetime.now(UTC)


class ArcaRegistry:
    """Look a taxpayer up in ARCA's constancia de inscripción."""

    def __init__(
        self,
        *,
        represented_cuit: str,
        request_ticket: RequestTicket,
        call_padron: CallPadron,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        if not is_valid_cuit(represented_cuit):
            raise ValueError(
                f"The represented CUIT {represented_cuit!r} fails its check digit."
            )
        self._represented_cuit = normalize_cuit(represented_cuit)
        self._request_ticket = request_ticket
        self._call_padron = call_padron
        self._clock = clock
        self._ticket: AccessTicket | None = None

    @property
    def represented_cuit(self) -> str:
        """The CUIT these lookups are made on behalf of."""
        return self._represented_cuit

    def _ticket_for(self, now: datetime) -> AccessTicket:
        """The current ticket, asking for a new one only when it has to.

        A ticket lasts twelve hours and the specification says to use it while
        it lasts: requesting another one answers `coe.alreadyAuthenticated`,
        which is an error, not a warning.
        """
        if self._ticket is None or not self._ticket.is_valid(at=now):
            self._ticket = self._request_ticket(now)
        return self._ticket

    def lookup(self, cuit: str) -> TaxpayerProfile | None:
        """The taxpayer's monotributo profile, or None if they are not in it."""
        if not is_valid_cuit(cuit):
            # A bad check digit is a mistake on this side. ARCA's padrón has
            # daily limits per represented CUIT; do not spend one saying so.
            raise PadronError(f"{cuit} fails its check digit, so it was not looked up.")

        ticket = self._ticket_for(self._clock())
        response = self._call_padron(ticket.token, ticket.sign, normalize_cuit(cuit))
        return parse_persona(response)

    def known_cuits(self) -> tuple[str, ...]:
        """Always empty: a national registry cannot be enumerated.

        The mock can list the CUITs it knows because it holds them all. This
        one answers about whoever is asked for, one at a time, and pretending
        otherwise would make the two implementations differ in the one place
        the graph is allowed to trust them equally.
        """
        return ()
