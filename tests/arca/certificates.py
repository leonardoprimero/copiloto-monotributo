"""A self-signed certificate shaped like the ones ARCA issues.

ARCA would reject it, since it does not come from their certifying authority,
but it signs exactly like a real one. Shared by the signing tests and the
client tests, which both need a certificate on disk.
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID


def write_self_signed(directory: Path) -> tuple[Path, Path]:
    """Write a certificate and its key into `directory`, return both paths."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name(
        [
            x509.NameAttribute(NameOID.COUNTRY_NAME, "AR"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Prueba"),
            x509.NameAttribute(NameOID.COMMON_NAME, "copiloto"),
            x509.NameAttribute(NameOID.SERIAL_NUMBER, "CUIT 20111111112"),
        ]
    )
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(UTC) - timedelta(days=1))
        .not_valid_after(datetime.now(UTC) + timedelta(days=1))
        .sign(key, hashes.SHA256())
    )

    cert_path = directory / "cert.pem"
    key_path = directory / "key.pem"
    cert_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    return cert_path, key_path
