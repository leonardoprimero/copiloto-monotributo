"""Exceptions raised when interacting with ARCA's padrón.

Pure standard library: this module has no external dependencies so that
the rest of the copilot can import and catch these exceptions without
requiring the `arca` extra to be installed.
"""


class PadronError(RuntimeError):
    """The padrón answered something this copilot cannot read."""


class PersonNotFound(PadronError):
    """The padrón has no one with that CUIT."""


class ConstanciaUnavailable(PadronError):
    """The CUIT exists, but ARCA will not issue its constancia.

    `reasons` are ARCA's own words, one per `error` element, because they say
    what the taxpayer has to go and fix.
    """

    _MESSAGE_LIMIT = 240

    def __init__(self, cuit: str, reasons: tuple[str, ...]) -> None:
        self.cuit = cuit
        self.reasons = reasons
        whom = cuit or "an unidentified CUIT"
        listed = " ".join(" ".join(reason.split()) for reason in reasons) or "ARCA gave no reason."
        if len(listed) > self._MESSAGE_LIMIT:
            listed = listed[: self._MESSAGE_LIMIT] + "…"
        super().__init__(f"ARCA will not issue the constancia for {whom}: {listed}")
