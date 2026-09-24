"""Running the copilot on your own invoices.

This is the mode that makes the project usable: a folder of comprobantes, your
CUIT and the category you are registered in. No ARCA credentials are involved,
because the only thing a lookup would tell us is a letter the taxpayer already
knows.
"""

from pathlib import Path

import pytest

from copiloto.cli import main

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
