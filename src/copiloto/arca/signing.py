"""Signing the access request with an ARCA certificate.

WSAA takes the TRA wrapped in a CMS `SignedData` message, base64-encoded, with
the data attached rather than detached. That is all this module does.

About the hash, because the obvious reading of the documentation is wrong:
ARCA's technical specification 1.2.2 says "SHA1+RSA". SHA1 has since been
retired for signatures, and `cryptography` refuses it outright — the builder
accepts SHA224 and up and raises a TypeError on SHA1. Meanwhile pyafipws, the
reference Python client that works against the live service, signs with
SHA256. So the specification's text is stale, and SHA256 is what actually gets
accepted. Verified against `cryptography` 50 and against pyafipws's source,
not against ARCA: that needs a certificate this repository does not have.

Nothing here reaches the network. It turns a string and a key pair into
another string, which is the only part of the flow that can be checked without
being a registered CEE.
"""

from base64 import b64encode
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.serialization import pkcs7

# What the specification asks for is SHA1; what the ecosystem accepts is this.
_HASH = hashes.SHA256


class SigningError(RuntimeError):
    """The certificate or the private key could not be used to sign."""


def load_signer(
    cert_path: Path, key_path: Path, *, passphrase: bytes | None = None
) -> tuple[x509.Certificate, object]:
    """Read the PEM certificate and private key ARCA issued."""
    try:
        certificate = x509.load_pem_x509_certificate(cert_path.read_bytes())
    except Exception as error:
        raise SigningError(f"No pude leer el certificado {cert_path}: {error}") from error

    try:
        key = serialization.load_pem_private_key(key_path.read_bytes(), password=passphrase)
    except Exception as error:
        raise SigningError(f"No pude leer la clave privada {key_path}: {error}") from error

    return certificate, key


def sign_tra(tra: str, certificate: x509.Certificate, private_key) -> str:
    """Wrap the TRA in a base64 CMS SignedData message, ready for `loginCms`.

    The data travels inside the message, not alongside it: WSAA has to read
    the request it is verifying.
    """
    try:
        der = (
            pkcs7.PKCS7SignatureBuilder()
            .set_data(tra.encode("utf-8"))
            .add_signer(certificate, private_key, _HASH())  # pyright: ignore[reportArgumentType]
            .sign(serialization.Encoding.DER, [])
        )
    except Exception as error:
        raise SigningError(f"No pude firmar el TRA: {error}") from error

    return b64encode(der).decode("ascii")


def signer_from_files(
    cert_path: Path, key_path: Path, *, passphrase: bytes | None = None
):
    """A `sign_cms` callable for `request_ticket`, bound to one certificate."""
    certificate, key = load_signer(cert_path, key_path, passphrase=passphrase)
    return lambda tra: sign_tra(tra, certificate, key)
