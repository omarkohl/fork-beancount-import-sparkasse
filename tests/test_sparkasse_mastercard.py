#!/usr/bin/env python3

from datetime import datetime

import pytest

from beancount.core.data import Transaction
from beancount_import_sparkasse.importers import SparkasseMastercard


@pytest.fixture
def mastercard_csv_content():
    """Fixture providing sample Sparkasse Mastercard CSV content."""
    return (
        '"Umsatz getätigt von";"Belegdatum";"Buchungsdatum";"Originalbetrag";"Originalwährung";"Umrechnungskurs";"Buchungsbetrag";"Buchungswährung";"Transaktionsbeschreibung";"Transaktionsbeschreibung Zusatz";"Buchungsreferenz";"Gebührenschlüssel";"Länderkennzeichen";"BAR-Entgelt+Buchungsreferenz";"AEE+Buchungsreferenz";"Abrechnungskennzeichen"\n'
        '"1234 **** **** 5678";"05.10.25";"06.10.25";"0,00";"";"1,00";"-10,99";"EUR";"Spotify";"Stockholm";"6";"5815";"";"";"";""\n'
        '"1234 **** **** 5678";"26.09.25";"26.09.25";"0,00";"";"1,00";"-4,99";"EUR";"GOOGLE *Google Play Ap";"630-712-0000";"5";"5817";"";"";"";""\n'
    )


@pytest.fixture
def mastercard_csv_file(mastercard_csv_content, tmp_path):
    """Fixture providing a temporary CSV file with Mastercard data."""
    csv_file = tmp_path / "umsatz-1234________5678-20251010.CSV"
    csv_file.write_text(mastercard_csv_content, encoding="ISO-8859-1")
    return str(csv_file)


@pytest.fixture
def importer():
    """Fixture providing a configured SparkasseMastercard importer."""
    return SparkasseMastercard(
        account="Liabilities:DE:Sparkasse:Mastercard",
        credit_card_number="1234 **** **** 5678",
        currency="EUR",
    )


def test_importer_initialization():
    """Test that the importer can be initialized with correct parameters."""
    importer = SparkasseMastercard(
        account="Liabilities:DE:Sparkasse:Mastercard",
        credit_card_number="1234 **** **** 5678",
        currency="EUR",
        flag="!",
    )
    assert importer.importer_account == "Liabilities:DE:Sparkasse:Mastercard"
    assert importer.credit_card_number == "1234 **** **** 5678"
    assert importer.currency == "EUR"
    assert importer.flag == "!"


def test_importer_initialization_defaults():
    """Test that the importer uses correct default values."""
    importer = SparkasseMastercard(
        account="Liabilities:DE:Sparkasse:Mastercard",
        credit_card_number="1234 **** **** 5678",
    )
    assert importer.currency == "EUR"
    assert importer.flag == "*"


def test_identify_valid_file(importer, mastercard_csv_file):
    """Test that the importer correctly identifies a valid Mastercard CSV file."""
    assert importer.identify(mastercard_csv_file) is True


def test_identify_invalid_file(importer, tmp_path):
    """Test that the importer rejects files that are not Mastercard CSV files."""
    # Create a file with wrong headers
    invalid_file = tmp_path / "invalid.csv"
    invalid_file.write_text(
        '"Some";"Random";"Headers"\n"1";"2";"3"\n', encoding="ISO-8859-1"
    )
    assert importer.identify(str(invalid_file)) is False


def test_identify_missing_file(importer):
    """Test that the importer handles missing files gracefully."""
    assert importer.identify("/nonexistent/file.csv") is False


def test_identify_sparkasse_csv_camt_file(importer, tmp_path):
    """Test that the importer doesn't identify Sparkasse CSV-CAMT files."""
    # Create a Sparkasse CSV-CAMT file (different format)
    camt_file = tmp_path / "sparkasse.csv"
    camt_file.write_text(
        '"Auftragskonto";"Buchungstag";"Valutadatum";"Buchungstext"\n'
        '"DE123";"01.01.25";"01.01.25";"Test"\n',
        encoding="ISO-8859-1",
    )
    assert importer.identify(str(camt_file)) is False


def test_account(importer, mastercard_csv_file):
    """Test that the account() method returns the correct account."""
    assert (
        importer.account(mastercard_csv_file) == "Liabilities:DE:Sparkasse:Mastercard"
    )


def test_filename_standard_format(importer):
    """Test filename generation for standard Mastercard CSV filename format."""
    filepath = "/path/to/umsatz-1234________5678-20251010.CSV"
    result = importer.filename(filepath)
    assert result == "20251010-12345678.mastercard.csv"


def test_filename_different_card_number(importer):
    """Test filename generation with different card number format should return None."""
    filepath = "/path/to/umsatz-9876________1234-20250101.CSV"
    result = importer.filename(filepath)
    # Should return None because the card number doesn't match
    assert result is None


def test_filename_invalid_format(importer):
    """Test filename generation for non-standard filename format."""
    filepath = "/path/to/random-file.csv"
    result = importer.filename(filepath)
    assert result is None


def test_extract_entries_count(importer, mastercard_csv_file):
    """Test that the correct number of entries are extracted."""
    entries = importer.extract(mastercard_csv_file, existing=[])
    assert len(entries) == 2


def test_extract_entries_types(importer, mastercard_csv_file):
    """Test that extracted entries are all transactions."""
    entries = importer.extract(mastercard_csv_file, existing=[])
    assert all(isinstance(entry, Transaction) for entry in entries)


def test_extract_first_entry_details(importer, mastercard_csv_file):
    """Test details of the first extracted entry (chronologically)."""
    entries = importer.extract(mastercard_csv_file, existing=[])
    entry = entries[0]

    assert entry.date == datetime(2025, 9, 26).date()
    assert entry.flag == "*"
    assert entry.payee == "GOOGLE *Google Play Ap"
    assert entry.narration == "630-712-0000"
    assert len(entry.postings) == 1
    assert entry.postings[0].account == "Liabilities:DE:Sparkasse:Mastercard"
    assert str(entry.postings[0].units.number) == "-4.99"
    assert entry.postings[0].units.currency == "EUR"


def test_extract_second_entry_details(importer, mastercard_csv_file):
    """Test details of the second extracted entry (chronologically)."""
    entries = importer.extract(mastercard_csv_file, existing=[])
    entry = entries[1]

    assert entry.date == datetime(2025, 10, 6).date()
    assert entry.flag == "*"
    assert entry.payee == "Spotify"
    assert entry.narration == "Stockholm"
    assert len(entry.postings) == 1
    assert entry.postings[0].account == "Liabilities:DE:Sparkasse:Mastercard"
    assert str(entry.postings[0].units.number) == "-10.99"
    assert entry.postings[0].units.currency == "EUR"


def test_extract_chronological_order(importer, mastercard_csv_file):
    """Test that entries are extracted in chronological order (oldest first)."""
    entries = importer.extract(mastercard_csv_file, existing=[])
    dates = [entry.date for entry in entries]
    assert dates == sorted(dates)


def test_extract_custom_flag(mastercard_csv_file):
    """Test that custom transaction flags are applied."""
    importer = SparkasseMastercard(
        account="Liabilities:DE:Sparkasse:Mastercard",
        credit_card_number="1234 **** **** 5678",
        flag="!",
    )
    entries = importer.extract(mastercard_csv_file, existing=[])
    assert all(entry.flag == "!" for entry in entries)


def test_date_method(importer, mastercard_csv_file):
    """Test that the date() method returns the latest transaction date."""
    date = importer.date(mastercard_csv_file)
    assert date == datetime(2025, 10, 6).date()


def test_extract_empty_file(importer, tmp_path):
    """Test extraction from a file with only headers."""
    empty_file = tmp_path / "empty.csv"
    empty_file.write_text(
        '"Umsatz getätigt von";"Belegdatum";"Buchungsdatum";"Originalbetrag";"Originalwährung";"Umrechnungskurs";"Buchungsbetrag";"Buchungswährung";"Transaktionsbeschreibung";"Transaktionsbeschreibung Zusatz";"Buchungsreferenz";"Gebührenschlüssel";"Länderkennzeichen";"BAR-Entgelt+Buchungsreferenz";"AEE+Buchungsreferenz";"Abrechnungskennzeichen"\n',
        encoding="ISO-8859-1",
    )
    entries = importer.extract(str(empty_file), existing=[])
    assert len(entries) == 0


def test_extract_with_positive_amount(importer, tmp_path):
    """Test extraction of a transaction with a positive amount (refund)."""
    csv_file = tmp_path / "refund.csv"
    csv_file.write_text(
        '"Umsatz getätigt von";"Belegdatum";"Buchungsdatum";"Originalbetrag";"Originalwährung";"Umrechnungskurs";"Buchungsbetrag";"Buchungswährung";"Transaktionsbeschreibung";"Transaktionsbeschreibung Zusatz";"Buchungsreferenz";"Gebührenschlüssel";"Länderkennzeichen";"BAR-Entgelt+Buchungsreferenz";"AEE+Buchungsreferenz";"Abrechnungskennzeichen"\n'
        '"1234 **** **** 5678";"15.10.25";"16.10.25";"0,00";"";"1,00";"25,50";"EUR";"REFUND Store";"Cancellation";"7";"5815";"";"";"";""\n',
        encoding="ISO-8859-1",
    )
    entries = importer.extract(str(csv_file), existing=[])
    assert len(entries) == 1
    assert str(entries[0].postings[0].units.number) == "25.50"


def test_extract_with_large_amount(importer, tmp_path):
    """Test extraction of a transaction with a large amount (thousands separator)."""
    csv_file = tmp_path / "large.csv"
    csv_file.write_text(
        '"Umsatz getätigt von";"Belegdatum";"Buchungsdatum";"Originalbetrag";"Originalwährung";"Umrechnungskurs";"Buchungsbetrag";"Buchungswährung";"Transaktionsbeschreibung";"Transaktionsbeschreibung Zusatz";"Buchungsreferenz";"Gebührenschlüssel";"Länderkennzeichen";"BAR-Entgelt+Buchungsreferenz";"AEE+Buchungsreferenz";"Abrechnungskennzeichen"\n'
        '"1234 **** **** 5678";"15.10.25";"16.10.25";"0,00";"";"1,00";"-1.234,56";"EUR";"Large Purchase";"Expensive Item";"8";"5815";"";"";"";""\n',
        encoding="ISO-8859-1",
    )
    entries = importer.extract(str(csv_file), existing=[])
    assert len(entries) == 1
    assert str(entries[0].postings[0].units.number) == "-1234.56"


def test_extract_payee_with_empty_additional_description(importer, tmp_path):
    """Test that payee is correct when additional description is empty."""
    csv_file = tmp_path / "no_zusatz.csv"
    csv_file.write_text(
        '"Umsatz getätigt von";"Belegdatum";"Buchungsdatum";"Originalbetrag";"Originalwährung";"Umrechnungskurs";"Buchungsbetrag";"Buchungswährung";"Transaktionsbeschreibung";"Transaktionsbeschreibung Zusatz";"Buchungsreferenz";"Gebührenschlüssel";"Länderkennzeichen";"BAR-Entgelt+Buchungsreferenz";"AEE+Buchungsreferenz";"Abrechnungskennzeichen"\n'
        '"1234 **** **** 5678";"15.10.25";"16.10.25";"0,00";"";"1,00";"-10,00";"EUR";"Simple Store";"";"9";"5815";"";"";"";""\n',
        encoding="ISO-8859-1",
    )
    entries = importer.extract(str(csv_file), existing=[])
    assert len(entries) == 1
    # When additional description is empty, narration should just be the main description
    assert entries[0].payee == "Simple Store"
    assert entries[0].narration == ""


def test_extract_with_different_currency(importer, tmp_path):
    """Test extraction of a transaction with a non-EUR currency."""
    csv_file = tmp_path / "usd.csv"
    csv_file.write_text(
        '"Umsatz getätigt von";"Belegdatum";"Buchungsdatum";"Originalbetrag";"Originalwährung";"Umrechnungskurs";"Buchungsbetrag";"Buchungswährung";"Transaktionsbeschreibung";"Transaktionsbeschreibung Zusatz";"Buchungsreferenz";"Gebührenschlüssel";"Länderkennzeichen";"BAR-Entgelt+Buchungsreferenz";"AEE+Buchungsreferenz";"Abrechnungskennzeichen"\n'
        '"1234 **** **** 5678";"15.10.25";"16.10.25";"100,00";"USD";"0,95";"-95,00";"EUR";"US Store";"New York";"10";"5815";"";"";"";""\n',
        encoding="ISO-8859-1",
    )
    entries = importer.extract(str(csv_file), existing=[])
    assert len(entries) == 1
    # The Buchungswährung (posting currency) should be EUR
    assert entries[0].postings[0].units.currency == "EUR"


def test_extract_metadata(importer, mastercard_csv_file):
    """Test that transaction metadata is set correctly."""
    entries = importer.extract(mastercard_csv_file, existing=[])
    entry = entries[0]

    assert "filename" in entry.meta
    assert entry.meta["filename"] == mastercard_csv_file
    assert "lineno" in entry.meta
    assert isinstance(entry.meta["lineno"], int)


def test_date_method_with_empty_file(importer, tmp_path):
    """Test that date() handles empty file gracefully."""
    empty_file = tmp_path / "empty.csv"
    empty_file.write_text(
        '"Umsatz getätigt von";"Belegdatum";"Buchungsdatum";"Originalbetrag";"Originalwährung";"Umrechnungskurs";"Buchungsbetrag";"Buchungswährung";"Transaktionsbeschreibung";"Transaktionsbeschreibung Zusatz";"Buchungsreferenz";"Gebührenschlüssel";"Länderkennzeichen";"BAR-Entgelt+Buchungsreferenz";"AEE+Buchungsreferenz";"Abrechnungskennzeichen"\n',
        encoding="ISO-8859-1",
    )
    # csvbase.Importer.date() raises ValueError for empty files
    with pytest.raises(ValueError, match="max\\(\\) iterable argument is empty"):
        importer.date(str(empty_file))


def test_encoding_iso_8859_1(tmp_path):
    """Test that the importer correctly handles ISO-8859-1 encoded files with umlauts."""
    csv_file = tmp_path / "umsatz-1234________5678-20251010.CSV"
    # Write with German umlauts in ISO-8859-1 encoding
    content = (
        '"Umsatz getätigt von";"Belegdatum";"Buchungsdatum";"Originalbetrag";"Originalwährung";"Umrechnungskurs";"Buchungsbetrag";"Buchungswährung";"Transaktionsbeschreibung";"Transaktionsbeschreibung Zusatz";"Buchungsreferenz";"Gebührenschlüssel";"Länderkennzeichen";"BAR-Entgelt+Buchungsreferenz";"AEE+Buchungsreferenz";"Abrechnungskennzeichen"\n'
        '"1234 **** **** 5678";"05.10.25";"06.10.25";"0,00";"";"1,00";"-10,99";"EUR";"Café München";"Münchner Straße";"6";"5815";"";"";"";""\n'
    )
    csv_file.write_text(content, encoding="ISO-8859-1")

    importer = SparkasseMastercard(
        account="Liabilities:DE:Sparkasse:Mastercard",
        credit_card_number="1234 **** **** 5678",
    )
    assert importer.identify(str(csv_file)) is True


def test_extract_multiple_transactions_same_day(importer, tmp_path):
    """Test extraction when multiple transactions occur on the same day."""
    csv_file = tmp_path / "same_day.csv"
    csv_file.write_text(
        '"Umsatz getätigt von";"Belegdatum";"Buchungsdatum";"Originalbetrag";"Originalwährung";"Umrechnungskurs";"Buchungsbetrag";"Buchungswährung";"Transaktionsbeschreibung";"Transaktionsbeschreibung Zusatz";"Buchungsreferenz";"Gebührenschlüssel";"Länderkennzeichen";"BAR-Entgelt+Buchungsreferenz";"AEE+Buchungsreferenz";"Abrechnungskennzeichen"\n'
        '"1234 **** **** 5678";"15.10.25";"15.10.25";"0,00";"";"1,00";"-10,00";"EUR";"Store A";"Location A";"11";"5815";"";"";"";""\n'
        '"1234 **** **** 5678";"15.10.25";"15.10.25";"0,00";"";"1,00";"-20,00";"EUR";"Store B";"Location B";"12";"5815";"";"";"";""\n'
        '"1234 **** **** 5678";"15.10.25";"15.10.25";"0,00";"";"1,00";"-30,00";"EUR";"Store C";"Location C";"13";"5815";"";"";"";""\n',
        encoding="ISO-8859-1",
    )
    entries = importer.extract(str(csv_file), existing=[])
    assert len(entries) == 3
    assert all(entry.date == datetime(2025, 10, 15).date() for entry in entries)
    # Check that all three transactions are distinct
    payees = [entry.payee for entry in entries]
    # All same date, so order detection assumes descending (first > last would fail on same date)
    # and reverses them to ascending order, which matches file order
    assert payees == ["Store A", "Store B", "Store C"]


def test_credit_card_number_obfuscated_format():
    """Test that the importer works with obfuscated credit card number format."""
    importer = SparkasseMastercard(
        account="Liabilities:DE:Sparkasse:Mastercard",
        credit_card_number="1234 **** **** 5678",
    )
    # Test filename matching
    assert importer._matches_filename_pattern(
        "/path/to/umsatz-1234________5678-20251010.CSV"
    )
    assert not importer._matches_filename_pattern(
        "/path/to/umsatz-9999________8888-20251010.CSV"
    )

    # Test content matching
    content_line = '"1234 **** **** 5678";"05.10.25";"06.10.25";"0,00";"";"1,00";"-10,99";"EUR";"Spotify";"Stockholm";"6";"5815";"";"";"";""\n'
    assert importer._matches_credit_card_in_content(content_line)

    wrong_content_line = '"9999 **** **** 8888";"05.10.25";"06.10.25";"0,00";"";"1,00";"-10,99";"EUR";"Spotify";"Stockholm";"6";"5815";"";"";"";""\n'
    assert not importer._matches_credit_card_in_content(wrong_content_line)


def test_credit_card_number_underscore_format():
    """Test that the importer works with underscore-obfuscated credit card number format."""
    importer = SparkasseMastercard(
        account="Liabilities:DE:Sparkasse:Mastercard",
        credit_card_number="1234________5678",
    )
    # Test filename matching
    assert importer._matches_filename_pattern(
        "/path/to/umsatz-1234________5678-20251010.CSV"
    )
    assert not importer._matches_filename_pattern(
        "/path/to/umsatz-9999________8888-20251010.CSV"
    )

    # Test content matching - should work even with different obfuscation in content vs filename
    content_line = '"1234 **** **** 5678";"05.10.25";"06.10.25";"0,00";"";"1,00";"-10,99";"EUR";"Spotify";"Stockholm";"6";"5815";"";"";"";""\n'
    assert importer._matches_credit_card_in_content(content_line)


def test_credit_card_number_full_format():
    """Test that the importer works with full credit card number format."""
    importer = SparkasseMastercard(
        account="Liabilities:DE:Sparkasse:Mastercard",
        credit_card_number="1234567890125678",
    )
    # Test filename matching
    assert importer._matches_filename_pattern(
        "/path/to/umsatz-1234________5678-20251010.CSV"
    )
    assert not importer._matches_filename_pattern(
        "/path/to/umsatz-9999________8888-20251010.CSV"
    )

    # Test content matching
    content_line = '"1234 **** **** 5678";"05.10.25";"06.10.25";"0,00";"";"1,00";"-10,99";"EUR";"Spotify";"Stockholm";"6";"5815";"";"";"";""\n'
    assert importer._matches_credit_card_in_content(content_line)


def test_credit_card_number_with_spaces_format():
    """Test that the importer works with full credit card number with spaces."""
    importer = SparkasseMastercard(
        account="Liabilities:DE:Sparkasse:Mastercard",
        credit_card_number="1234 5678 9012 5678",
    )
    # Test filename matching
    assert importer._matches_filename_pattern(
        "/path/to/umsatz-1234________5678-20251010.CSV"
    )

    # Test content matching
    content_line = '"1234 **** **** 5678";"05.10.25";"06.10.25";"0,00";"";"1,00";"-10,99";"EUR";"Spotify";"Stockholm";"6";"5815";"";"";"";""\n'
    assert importer._matches_credit_card_in_content(content_line)


def test_filename_generation_with_credit_card():
    """Test that filename generation uses the credit card number correctly."""
    # Test with obfuscated format
    importer1 = SparkasseMastercard(
        account="Liabilities:DE:Sparkasse:Mastercard",
        credit_card_number="1234 **** **** 5678",
    )
    result1 = importer1.filename("/path/to/umsatz-1234________5678-20251010.CSV")
    assert result1 == "20251010-12345678.mastercard.csv"

    # Test with full number
    importer2 = SparkasseMastercard(
        account="Liabilities:DE:Sparkasse:Mastercard",
        credit_card_number="1234567890125678",
    )
    result2 = importer2.filename("/path/to/umsatz-1234________5678-20251010.CSV")
    assert result2 == "20251010-12345678.mastercard.csv"


def test_identify_wrong_credit_card_number(tmp_path):
    """Test that the importer rejects files with different credit card numbers."""
    # Create a file for card 1234...5678
    csv_file = tmp_path / "umsatz-1234________5678-20251010.CSV"
    content = (
        '"Umsatz getätigt von";"Belegdatum";"Buchungsdatum";"Originalbetrag";"Originalwährung";"Umrechnungskurs";"Buchungsbetrag";"Buchungswährung";"Transaktionsbeschreibung";"Transaktionsbeschreibung Zusatz";"Buchungsreferenz";"Gebührenschlüssel";"Länderkennzeichen";"BAR-Entgelt+Buchungsreferenz";"AEE+Buchungsreferenz";"Abrechnungskennzeichen"\n'
        '"1234 **** **** 5678";"05.10.25";"06.10.25";"0,00";"";"1,00";"-10,99";"EUR";"Spotify";"Stockholm";"6";"5815";"";"";"";""\n'
    )
    csv_file.write_text(content, encoding="ISO-8859-1")

    # Create importer for different card 9999...8888
    importer = SparkasseMastercard(
        account="Liabilities:DE:Sparkasse:Mastercard",
        credit_card_number="9999 **** **** 8888",
    )

    # Should not identify this file
    assert not importer.identify(str(csv_file))
