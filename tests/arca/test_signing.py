"""Signing the TRA, checked with openssl rather than with assertions alone.

A signature that a test declares correct proves nothing. These tests hand the
output to the `openssl` binary and ask it to verify the message and give back
what was signed: if the bytes are wrong, openssl says so.

The certificate is generated here and self-signed. ARCA would reject it — it
is not from their certifying authority — but the CMS structure it produces is
the same structure a real certificate produces, and that structure is what
can be checked without being a registered CEE.
"""

import shutil
import subprocess
from base64 import b64decode
from datetime import UTC, datetime
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives.asymmetric import rsa

from copiloto.arca.signing import SigningError, sign_tra, signer_from_files
from copiloto.arca.wsaa import build_tra
from tests.arca.certificates import write_self_signed

NOW = datetime(2026, 9, 24, 10, 0, tzinfo=UTC)
openssl_available = pytest.mark.skipif(
    shutil.which("openssl") is None, reason="openssl is not on PATH"
)


@pytest.fixture
def credentials(tmp_path: Path) -> tuple[Path, Path]:
    """A self-signed certificate shaped like the ones ARCA issues."""
    return write_self_signed(tmp_path)


@pytest.fixture
def signed(credentials: tuple[Path, Path]) -> tuple[str, str]:
    """One signed TRA, and the TRA that went into it."""
    tra = build_tra("ws_sr_constancia_inscripcion", now=NOW)
    return signer_from_files(*credentials)(tra), tra


class TestTheSignature:
    def test_it_is_base64(self, signed: tuple[str, str]) -> None:
        """`loginCms` takes a base64 string, not bytes."""
        cms, _ = signed

        assert b64decode(cms, validate=True)

    def test_it_is_not_empty(self, signed: tuple[str, str]) -> None:
        cms, _ = signed

        assert len(cms) > 500


@openssl_available
class TestOpensslAgrees:
    """The output is handed to openssl, which either verifies it or does not."""

    def _der(self, tmp_path: Path, cms: str) -> Path:
        path = tmp_path / "signed.der"
        path.write_bytes(b64decode(cms))
        return path

    def test_openssl_verifies_the_message(
        self, signed: tuple[str, str], tmp_path: Path
    ) -> None:
        cms, _ = signed

        result = subprocess.run(  # noqa: S603
            ["openssl", "smime", "-verify", "-inform", "DER",  # noqa: S607
             "-in", str(self._der(tmp_path, cms)), "-noverify"],
            capture_output=True,
            check=False,
        )

        assert result.returncode == 0, result.stderr.decode()

    def test_what_comes_back_out_is_what_went_in(
        self, signed: tuple[str, str], tmp_path: Path
    ) -> None:
        """The TRA travels inside the message, so WSAA can read it."""
        cms, tra = signed

        recovered = subprocess.run(  # noqa: S603
            ["openssl", "smime", "-verify", "-inform", "DER",  # noqa: S607
             "-in", str(self._der(tmp_path, cms)), "-noverify"],
            capture_output=True,
            check=True,
        ).stdout.decode()

        assert recovered.strip() == tra.strip()

    def test_it_is_a_signed_data_message(
        self, signed: tuple[str, str], tmp_path: Path
    ) -> None:
        cms, _ = signed

        structure = subprocess.run(  # noqa: S603
            ["openssl", "asn1parse", "-inform", "DER",  # noqa: S607
             "-in", str(self._der(tmp_path, cms))],
            capture_output=True,
            check=True,
        ).stdout.decode()

        assert "pkcs7-signedData" in structure

    def test_it_is_signed_with_sha256_not_sha1(
        self, signed: tuple[str, str], tmp_path: Path
    ) -> None:
        """The spec says SHA1; cryptography refuses it and pyafipws uses SHA256.

        Pinned because it is the one place where following the documentation
        literally produces code that cannot run.
        """
        cms, _ = signed

        structure = subprocess.run(  # noqa: S603
            ["openssl", "asn1parse", "-inform", "DER",  # noqa: S607
             "-in", str(self._der(tmp_path, cms))],
            capture_output=True,
            check=True,
        ).stdout.decode()

        assert "sha256WithRSAEncryption" in structure
        assert "sha1" not in structure.lower()

    def test_the_certificate_travels_with_the_message(
        self, signed: tuple[str, str], tmp_path: Path
    ) -> None:
        """WSAA needs it to check the signature and identify the CEE."""
        cms, _ = signed

        certs = subprocess.run(  # noqa: S603
            ["openssl", "pkcs7", "-inform", "DER",  # noqa: S607
             "-in", str(self._der(tmp_path, cms)), "-print_certs", "-noout"],
            capture_output=True,
            check=True,
        ).stdout.decode()

        assert "CUIT 20111111112" in certs


class TestBadCredentials:
    def test_a_missing_certificate_is_reported(self, tmp_path: Path) -> None:
        with pytest.raises(SigningError):
            signer_from_files(tmp_path / "no-existe.pem", tmp_path / "no-existe.key")

    def test_a_certificate_that_is_not_pem_is_reported(
        self, tmp_path: Path, credentials: tuple[Path, Path]
    ) -> None:
        _, key_path = credentials
        junk = tmp_path / "junk.pem"
        junk.write_text("no soy un certificado")

        with pytest.raises(SigningError):
            signer_from_files(junk, key_path)

    def test_a_key_that_does_not_match_is_still_usable_to_build(
        self, credentials: tuple[Path, Path]
    ) -> None:
        """Signing with the wrong key produces a message ARCA will reject.

        It cannot be caught here: only WSAA knows which certificate is
        registered. The failure surfaces as cms.sign.invalid, which is why
        the error codes travel intact.
        """
        cert_path, key_path = credentials
        other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        certificate = x509.load_pem_x509_certificate(cert_path.read_bytes())

        assert sign_tra(build_tra("x", now=NOW), certificate, other)
