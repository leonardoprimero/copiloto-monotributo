"""Running the copilot on your own invoices.

This is the mode that makes the project usable: a folder of comprobantes, your
CUIT and the category you are registered in. No ARCA credentials are involved,
because the only thing a lookup would tell us is a letter the taxpayer already
knows.
"""

from importlib.util import find_spec
from pathlib import Path

import pytest

from copiloto.cli import main

HAS_ARCA = find_spec("defusedxml") is not None

TEXT = """FACTURA C
Punto de venta 0001 - Comprobante 0000000{n}
CUIT emisor: 20-11111111-2
Fecha de emision: 15/0{m}/2026

Detalle:
- Consultoria | Cantidad 1,00 | Precio unitario 800.000,00

TOTAL: $ 800.000,00"""


@pytest.fixture
def folder(tmp_path: Path) -> Path:
    for i, month in enumerate([7, 8, 9], start=1):
        (tmp_path / f"factura-{i}.txt").write_text(
            TEXT.format(n=i, m=month), encoding="utf-8"
        )
    return tmp_path


def fake_reading(texts_to_invoices):
    """Build an extractor factory that maps the folder's texts to known invoices."""
    return lambda _case: texts_to_invoices


class TestOwnInvoices:
    def test_runs_on_a_folder_with_a_declared_category(
        self, folder: Path, capsys, monkeypatch
    ) -> None:
        monkeypatch.setattr(
            "copiloto.cli.build_extractor_factory", _mapping_factory(folder)
        )

        code = main(
            [
                "run",
                "--invoices-dir",
                str(folder),
                "--cuit",
                "20-11111111-2",
                "--category",
                "A",
                "--today",
                "2026-09-24",
                "--extractor",
                "cli",
            ]
        )
        out = capsys.readouterr().out

        assert code == 0
        assert "# Informe de monotributo" in out
        assert "Categoría registrada: A" in out

    def test_the_declared_category_is_what_it_compares_against(
        self, folder: Path, capsys, monkeypatch
    ) -> None:
        """Three invoices of 800,000 is category A; declaring K must show K."""
        monkeypatch.setattr(
            "copiloto.cli.build_extractor_factory", _mapping_factory(folder)
        )

        main(
            [
                "run",
                "--invoices-dir",
                str(folder),
                "--cuit",
                "20-11111111-2",
                "--category",
                "K",
                "--today",
                "2026-09-24",
                "--extractor",
                "cli",
                "--auto-resume",
            ]
        )

        assert "Categoría registrada: K" in capsys.readouterr().out


class TestDeclaredParameters:
    def test_declared_parameters_reach_the_report(self, folder: Path, capsys, monkeypatch) -> None:
        monkeypatch.setattr(
            "copiloto.cli.build_extractor_factory", _mapping_factory(folder)
        )

        code = main(
            [
                "run",
                "--invoices-dir",
                str(folder),
                "--cuit",
                "20-11111111-2",
                "--category",
                "A",
                "--today",
                "2026-09-24",
                "--extractor",
                "cli",
                "--surface-m2",
                "25",
                "--energy-kwh",
                "3000",
                "--annual-rent",
                "1000000",
            ]
        )
        out = capsys.readouterr().out

        assert code == 0
        assert "## Parámetros declarados" in out
        assert "25 m²" in out
        assert "3.000 kWh" in out
        assert "1.000.000,00" in out

    def test_a_declared_surface_can_change_the_category(
        self, folder: Path, capsys, monkeypatch
    ) -> None:
        """Three invoices of 800,000 are A by income; 100 m2 is E by surface."""
        monkeypatch.setattr(
            "copiloto.cli.build_extractor_factory", _mapping_factory(folder)
        )

        main(
            [
                "run",
                "--invoices-dir",
                str(folder),
                "--cuit",
                "20-11111111-2",
                "--category",
                "A",
                "--today",
                "2026-09-24",
                "--extractor",
                "cli",
                "--surface-m2",
                "100",
                "--auto-resume",
            ]
        )

        assert "Categoría estimada: E" in capsys.readouterr().out

    def test_a_negative_parameter_is_rejected_up_front(self, folder: Path, capsys) -> None:
        code = main(
            [
                "run",
                "--invoices-dir",
                str(folder),
                "--cuit",
                "20-11111111-2",
                "--category",
                "A",
                "--extractor",
                "cli",
                "--surface-m2",
                "-5",
            ]
        )

        assert code == 2
        assert "superficie" in capsys.readouterr().err.lower()


class TestArgumentRules:
    def test_a_folder_without_a_cuit_is_rejected(self, folder: Path, capsys) -> None:
        code = main(["run", "--invoices-dir", str(folder), "--category", "A"])

        assert code == 2
        assert "--cuit" in capsys.readouterr().err

    def test_a_folder_without_a_category_is_rejected(self, folder: Path, capsys) -> None:
        code = main(["run", "--invoices-dir", str(folder), "--cuit", "20-11111111-2"])

        assert code == 2
        assert "--category" in capsys.readouterr().err

    def test_an_unknown_category_is_rejected(self, folder: Path, capsys) -> None:
        code = main(
            [
                "run",
                "--invoices-dir",
                str(folder),
                "--cuit",
                "20-11111111-2",
                "--category",
                "Z",
            ]
        )

        assert code == 2
        assert "Z" in capsys.readouterr().err

    def test_an_invalid_cuit_is_rejected_before_reading_anything(
        self, folder: Path, capsys
    ) -> None:
        """Catch the typo up front rather than blaming every invoice for it."""
        code = main(
            [
                "run",
                "--invoices-dir",
                str(folder),
                "--cuit",
                "20-11111111-3",
                "--category",
                "A",
            ]
        )

        assert code == 2
        assert "20-11111111-3" in capsys.readouterr().err

    def test_the_offline_extractor_is_refused_for_real_invoices(
        self, folder: Path, capsys
    ) -> None:
        """`fake` only knows the eval texts; it cannot read a real document."""
        code = main(
            [
                "run",
                "--invoices-dir",
                str(folder),
                "--cuit",
                "20-11111111-2",
                "--category",
                "A",
                "--extractor",
                "fake",
            ]
        )
        printed = capsys.readouterr()

        assert code == 2
        assert "--extractor" in printed.err

    def test_a_case_and_a_folder_are_mutually_exclusive(self, folder: Path) -> None:
        with pytest.raises(SystemExit):
            main(
                [
                    "run",
                    "--case",
                    "evals/cases/all_in_order.json",
                    "--invoices-dir",
                    str(folder),
                ]
            )

    def test_one_of_them_is_required(self) -> None:
        with pytest.raises(SystemExit):
            main(["run"])

    def test_a_missing_folder_is_reported(self, tmp_path: Path, capsys) -> None:
        code = main(
            [
                "run",
                "--invoices-dir",
                str(tmp_path / "no-existe"),
                "--cuit",
                "20-11111111-2",
                "--category",
                "A",
                "--extractor",
                "cli",
            ]
        )

        assert code == 1
        assert "No encontré" in capsys.readouterr().err


def _mapping_factory(folder: Path):
    """Map the folder's rendered texts to matching invoices, offline."""
    from datetime import date
    from decimal import Decimal

    from copiloto.extractors.fake import FakeExtractor
    from copiloto.models import ExtractedInvoice, InvoiceItem
    from copiloto.sources import load_invoice_texts

    texts = load_invoice_texts(folder)
    amount = Decimal("800000.00")
    mapping = {}
    for i, (text, month) in enumerate(zip(texts, [7, 8, 9], strict=True), start=1):
        item = InvoiceItem(
            description="Consultoria",
            quantity=Decimal("1"),
            unit_price=amount,
            total=amount,
            kind="service",
        )
        mapping[text] = ExtractedInvoice(
            number=f"0001-0000000{i}",
            issuer_cuit="20-11111111-2",
            issue_date=date(2026, month, 15),
            items=(item,),
            total=amount,
        )

    return lambda _mode: (lambda _case: FakeExtractor(mapping))


class TestScannedInvoices:
    """A scanned invoice is readable, but its numbers are a guess."""

    def test_a_scan_is_read_with_ocr_and_the_case_goes_to_a_person(
        self, tmp_path: Path, capsys, monkeypatch
    ) -> None:
        text = TEXT.format(n=1, m=7)
        (tmp_path / "escaneada.pdf").write_bytes(b"%PDF-1.4 fake")
        monkeypatch.setattr("copiloto.sources.read_pdf_text", lambda _p: "")
        monkeypatch.setattr("copiloto.cli.default_ocr", lambda: (lambda _p: text))
        monkeypatch.setattr(
            "copiloto.cli.build_extractor_factory", _factory_for({text: 7})
        )

        code = main(
            [
                "run",
                "--invoices-dir",
                str(tmp_path),
                "--cuit",
                "20-11111111-2",
                "--category",
                "A",
                "--today",
                "2026-09-24",
                "--extractor",
                "cli",
                "--auto-resume",
            ]
        )
        out = capsys.readouterr().out

        assert code == 0
        assert "escaneada.pdf" in out
        assert "OCR" in out

    def test_without_ocr_the_scan_is_refused_instead_of_skipped(
        self, tmp_path: Path, capsys, monkeypatch
    ) -> None:
        """Dropping it would understate the income. Better to stop."""
        (tmp_path / "escaneada.pdf").write_bytes(b"%PDF-1.4 fake")
        monkeypatch.setattr("copiloto.sources.read_pdf_text", lambda _p: "")
        monkeypatch.setattr("copiloto.cli.default_ocr", lambda: None)

        code = main(
            [
                "run",
                "--invoices-dir",
                str(tmp_path),
                "--cuit",
                "20-11111111-2",
                "--category",
                "A",
                "--extractor",
                "cli",
            ]
        )

        assert code == 1
        assert "escaneada.pdf" in capsys.readouterr().err


def _factory_for(text_to_month: dict[str, int]):
    """An offline extractor for exactly the given texts."""
    from datetime import date
    from decimal import Decimal

    from copiloto.extractors.fake import FakeExtractor
    from copiloto.models import ExtractedInvoice, InvoiceItem

    amount = Decimal("800000.00")
    mapping = {}
    for i, (text, month) in enumerate(text_to_month.items(), start=1):
        item = InvoiceItem(
            description="Consultoria",
            quantity=Decimal("1"),
            unit_price=amount,
            total=amount,
            kind="service",
        )
        mapping[text] = ExtractedInvoice(
            number=f"0001-{i:08d}",
            issuer_cuit="20-11111111-2",
            issue_date=date(2026, month, 15),
            items=(item,),
            total=amount,
        )
    return lambda _mode: (lambda _case: FakeExtractor(mapping))


class TestCliArca:
    def test_arca_requires_credentials_if_not_in_env(
        self, folder: Path, capsys, monkeypatch
    ) -> None:
        monkeypatch.delenv("COPILOTO_ARCA_CERT", raising=False)
        monkeypatch.delenv("COPILOTO_ARCA_KEY", raising=False)
        monkeypatch.delenv("COPILOTO_ARCA_CUIT", raising=False)
        code = main(
            [
                "run",
                "--invoices-dir",
                str(folder),
                "--cuit",
                "20-11111111-2",
                "--arca",
            ]
        )
        assert code == 2
        err = capsys.readouterr().err
        assert "--arca-cert" in err
        assert "--arca-key" in err
        assert "--arca-cuit" in err

    @pytest.mark.skipif(not HAS_ARCA, reason="the arca extra is not installed")
    def test_arca_allows_omitting_category(
        self, folder: Path, capsys, monkeypatch
    ) -> None:
        from copiloto.models import TaxpayerProfile
        from copiloto.registry import MockArcaRegistry

        monkeypatch.setattr(
            "copiloto.cli.build_extractor_factory", _mapping_factory(folder)
        )
        fake_reg = MockArcaRegistry(
            {"20-11111111-2": TaxpayerProfile(cuit="20-11111111-2", name="Test", category="A")}
        )
        monkeypatch.setattr(
            "copiloto.arca.client.build_registry", lambda **_kw: fake_reg
        )

        code = main(
            [
                "run",
                "--invoices-dir",
                str(folder),
                "--cuit",
                "20-11111111-2",
                "--arca",
                "--arca-cert",
                "cert.pem",
                "--arca-key",
                "key.pem",
                "--arca-cuit",
                "20-11111111-2",
                "--extractor",
                "cli",
                "--today",
                "2026-09-24",
            ]
        )
        captured = capsys.readouterr()
        assert code == 0
        assert "--category" not in captured.err
        assert "Categoría registrada: A" in captured.out

    def test_arca_reports_missing_extra(
        self, folder: Path, capsys, monkeypatch
    ) -> None:
        import sys

        monkeypatch.setitem(sys.modules, "copiloto.arca.client", None)
        code = main(
            [
                "run",
                "--invoices-dir",
                str(folder),
                "--cuit",
                "20-11111111-2",
                "--arca",
                "--arca-cert",
                "cert.pem",
                "--arca-key",
                "key.pem",
                "--arca-cuit",
                "20-11111111-2",
            ]
        )
        assert code == 2
        err = capsys.readouterr().err
        assert "uv sync --extra arca" in err

    @pytest.mark.skipif(not HAS_ARCA, reason="the arca extra is not installed")
    def test_arca_wires_build_registry(
        self, folder: Path, capsys, monkeypatch, tmp_path: Path
    ) -> None:
        from unittest.mock import MagicMock

        mock_registry = MagicMock()
        mock_build = MagicMock(return_value=mock_registry)
        monkeypatch.setattr("copiloto.arca.client.build_registry", mock_build)
        monkeypatch.setattr(
            "copiloto.cli.build_extractor_factory", _mapping_factory(folder)
        )

        mock_start = MagicMock()
        mock_outcome = MagicMock()
        mock_outcome.report = "Report output"
        mock_start.return_value = mock_outcome
        monkeypatch.setattr("copiloto.service.Copilot.start", mock_start)

        cert_file = tmp_path / "cert.pem"
        key_file = tmp_path / "key.pem"
        cache_file = tmp_path / "ticket_cache.json"

        code = main(
            [
                "run",
                "--invoices-dir",
                str(folder),
                "--cuit",
                "20-11111111-2",
                "--arca",
                "--arca-cert",
                str(cert_file),
                "--arca-key",
                str(key_file),
                "--arca-cuit",
                "20-99999999-4",
                "--arca-env",
                "homologacion",
                "--arca-ticket-cache",
                str(cache_file),
                "--arca-passphrase",
                "secret",
                "--extractor",
                "cli",
                "--today",
                "2026-09-24",
            ]
        )
        assert code == 0
        mock_build.assert_called_once_with(
            cert_path=cert_file,
            key_path=key_file,
            represented_cuit="20-99999999-4",
            environment="homologacion",
            ticket_cache=cache_file,
            passphrase=b"secret",
        )
        mock_start.assert_called_once()
        assert mock_start.call_args.kwargs["registry"] is mock_registry

    @pytest.mark.skipif(not HAS_ARCA, reason="the arca extra is not installed")
    def test_arca_defaults_to_persistent_ticket_cache(
        self, folder: Path, capsys, monkeypatch, tmp_path: Path
    ) -> None:
        from unittest.mock import MagicMock
        from copiloto.arca.client import default_ticket_cache_path

        mock_registry = MagicMock()
        mock_build = MagicMock(return_value=mock_registry)
        monkeypatch.setattr("copiloto.arca.client.build_registry", mock_build)
        monkeypatch.setattr(
            "copiloto.cli.build_extractor_factory", _mapping_factory(folder)
        )
        mock_start = MagicMock()
        mock_outcome = MagicMock()
        mock_outcome.report = "Report output"
        mock_start.return_value = mock_outcome
        monkeypatch.setattr("copiloto.service.Copilot.start", mock_start)

        cert_file = tmp_path / "cert.pem"
        key_file = tmp_path / "key.pem"

        code = main(
            [
                "run",
                "--invoices-dir",
                str(folder),
                "--cuit",
                "20-11111111-2",
                "--arca",
                "--arca-cert",
                str(cert_file),
                "--arca-key",
                str(key_file),
                "--arca-cuit",
                "20-99999999-4",
                "--extractor",
                "cli",
                "--today",
                "2026-09-24",
            ]
        )
        assert code == 0
        assert mock_build.call_args.kwargs["ticket_cache"] == default_ticket_cache_path()

    @pytest.mark.skipif(not HAS_ARCA, reason="the arca extra is not installed")
    def test_arca_no_ticket_cache_flag_disables_cache(
        self, folder: Path, capsys, monkeypatch, tmp_path: Path
    ) -> None:
        from unittest.mock import MagicMock

        mock_registry = MagicMock()
        mock_build = MagicMock(return_value=mock_registry)
        monkeypatch.setattr("copiloto.arca.client.build_registry", mock_build)
        monkeypatch.setattr(
            "copiloto.cli.build_extractor_factory", _mapping_factory(folder)
        )
        mock_start = MagicMock()
        mock_outcome = MagicMock()
        mock_outcome.report = "Report output"
        mock_start.return_value = mock_outcome
        monkeypatch.setattr("copiloto.service.Copilot.start", mock_start)

        cert_file = tmp_path / "cert.pem"
        key_file = tmp_path / "key.pem"

        code = main(
            [
                "run",
                "--invoices-dir",
                str(folder),
                "--cuit",
                "20-11111111-2",
                "--arca",
                "--arca-cert",
                str(cert_file),
                "--arca-key",
                str(key_file),
                "--arca-cuit",
                "20-99999999-4",
                "--no-arca-ticket-cache",
                "--extractor",
                "cli",
                "--today",
                "2026-09-24",
            ]
        )
        assert code == 0
        assert mock_build.call_args.kwargs["ticket_cache"] is None

    @pytest.mark.skipif(not HAS_ARCA, reason="the arca extra is not installed")
    @pytest.mark.parametrize("opt_out", ["none", "0", "false", "None", "FALSE"])
    def test_arca_ticket_cache_opt_out_strings(
        self, opt_out: str, folder: Path, capsys, monkeypatch, tmp_path: Path
    ) -> None:
        from unittest.mock import MagicMock

        mock_registry = MagicMock()
        mock_build = MagicMock(return_value=mock_registry)
        monkeypatch.setattr("copiloto.arca.client.build_registry", mock_build)
        monkeypatch.setattr(
            "copiloto.cli.build_extractor_factory", _mapping_factory(folder)
        )
        mock_start = MagicMock()
        mock_outcome = MagicMock()
        mock_outcome.report = "Report output"
        mock_start.return_value = mock_outcome
        monkeypatch.setattr("copiloto.service.Copilot.start", mock_start)

        cert_file = tmp_path / "cert.pem"
        key_file = tmp_path / "key.pem"

        code = main(
            [
                "run",
                "--invoices-dir",
                str(folder),
                "--cuit",
                "20-11111111-2",
                "--arca",
                "--arca-cert",
                str(cert_file),
                "--arca-key",
                str(key_file),
                "--arca-cuit",
                "20-99999999-4",
                "--arca-ticket-cache",
                opt_out,
                "--extractor",
                "cli",
                "--today",
                "2026-09-24",
            ]
        )
        assert code == 0
        assert mock_build.call_args.kwargs["ticket_cache"] is None


