#!/usr/bin/env python3

from __future__ import annotations

import csv
import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from beancount.core.amount import Amount
from beancount.core.data import (
    EMPTY_SET,
    Balance,
    Directive,
    Entries,
    Posting,
    Transaction,
    new_metadata,
)
from beangulp import Importer
from beangulp.importers import csvbase

from beancount_import_sparkasse.models import TXN

logger = logging.getLogger(__name__)


def _clean_whitespace(text: str) -> str:
    """Clean redundant whitespace from text fields.

    Removes leading/trailing whitespace and collapses multiple
    consecutive whitespace characters into single spaces.

    Args:
        text: Input text to clean

    Returns:
        Cleaned text with normalized whitespace
    """
    if not text:
        return text
    return re.sub(r"\s+", " ", text.strip())


@dataclass
class BaseImporter(Importer):
    iban: str
    importer_account: str  # Renamed to avoid collision with account() method
    fields: Sequence[str]
    date_format: str
    first_data_row: int = 1
    currency: str = "EUR"
    file_encoding: str = "ISO-8859-1"
    delimiter: str = ";"
    quotechar: str = '"'
    dates_ascending: bool = True
    flag: str = "*"  # Default flag for transactions

    def parse_amount(self, amount: str) -> Decimal:
        raise NotImplementedError

    def csv_to_txn(self, csv_row: dict[str, str]) -> TXN:
        raise NotImplementedError

    def get_final_balance(self, filepath: str) -> Directive | None:
        raise NotImplementedError

    @property
    def expected_header(self) -> str:
        return self.delimiter.join(
            [f"{self.quotechar}{field}{self.quotechar}" for field in self.fields]
        )

    def extract(self, filepath: str, existing: Entries) -> Entries:
        with open(filepath, encoding=self.file_encoding) as f:
            csv_rows = csv.DictReader(
                f,
                delimiter=self.delimiter,
                quotechar=self.quotechar,
                fieldnames=self.fields,
            )
            extracted_directives: Entries = []
            header_parsed = False
            for i, row in enumerate(csv_rows):
                if None in row:
                    del row[None]
                logger.debug(f"looking at {row=}")
                if not header_parsed:
                    if list(row.values()) != list(self.fields):
                        logger.debug("head NOT found")
                        continue
                    header_parsed = True
                    logger.debug("header FOUND, continue one more time")
                    continue

                logger.debug(f"Parsing {row=}")
                txn = self.csv_to_txn(csv_row=row)
                logger.debug(f"Converted to {txn=}")

                transaction = make_transaction(
                    account=self.importer_account,
                    txn=txn,
                    fname=filepath,
                    lineno=i + 2,
                    flag=self.flag,
                )
                logger.info(f"New {transaction=}")
                extracted_directives.append(transaction)

        final_balance = self.get_final_balance(filepath=filepath)
        if final_balance:
            logger.info(f"New {final_balance=}")
            extracted_directives.append(final_balance)

        return extracted_directives

    def account(self, filepath: str) -> str:
        """Return the account associated with this file."""
        return self.importer_account

    def date(self, filepath: str) -> datetime.date | None:
        """Return the date associated with this file."""
        try:
            entries = self.extract(filepath)
            if entries:
                return max(entry.date for entry in entries if hasattr(entry, "date"))
        except Exception:
            pass
        return None

    def identify(self, filepath: str) -> bool:
        """Return True if this importer matches the given file."""
        return False  # Override in subclasses

    def filename(self, filepath: str) -> str | None:
        """Return the archival filename for the given file."""
        return None  # Override in subclasses


@dataclass
class SparkasseCSVCAMTImporter(BaseImporter):
    """Beancount importer for CSV-CAMT exports of the German Sparkasse."""

    date_format: str = "%d.%m.%y"
    delimiter: str = ";"
    quotechar: str = '"'
    fields: Sequence[str] = (
        "Auftragskonto",
        "Buchungstag",
        "Valutadatum",
        "Buchungstext",
        "Verwendungszweck",
        "Glaeubiger ID",
        "Mandatsreferenz",
        "Kundenreferenz (End-to-End)",
        "Sammlerreferenz",
        "Lastschrift Ursprungsbetrag",
        "Auslagenersatz Ruecklastschrift",
        "Beguenstigter/Zahlungspflichtiger",
        "Kontonummer/IBAN",
        "BIC (SWIFT-Code)",
        "Betrag",
        "Waehrung",
        "Info",
    )

    def parse_amount(self, amount: str) -> Decimal:
        """Removes German thousands separator and converts decimal point to US."""
        return Decimal(amount.replace(".", "").replace(",", "."))

    def get_final_balance(self, filepath: str) -> Directive | None:
        return None

    def identify(self, filepath: str) -> bool:
        with open(filepath, encoding=self.file_encoding) as f:
            header = f.readline().strip()
            csv_row = f.readline().strip()

        header_match = header == self.expected_header
        iban_match = (
            csv_row.split(self.delimiter)[0].replace(self.quotechar, "") == self.iban
        )
        return header_match and iban_match

    def csv_to_txn(self, csv_row: dict[str, str]):
        txn = TXN(
            owner_iban=csv_row["Auftragskonto"],
            date=datetime.strptime(
                csv_row["Valutadatum"], self.date_format
            ).date(),  # type: ignore
            posting_type=csv_row["Buchungstext"],
            reference=_clean_whitespace(csv_row["Verwendungszweck"]),
            payee_name=_clean_whitespace(csv_row["Beguenstigter/Zahlungspflichtiger"]),
            payee_iban=csv_row["Kontonummer/IBAN"],
            payee_bic=csv_row["BIC (SWIFT-Code)"],
            amount=self.parse_amount(csv_row["Betrag"]),
            currency=csv_row["Waehrung"],
        )
        return txn

    def filename(self, filepath: str):
        match = re.search(r"\d{8}-(\d{7})-umsatz", filepath)
        if match:
            return f"{match.group(1)}.camt.csv"
        return None


@dataclass
class DKBCsvImporter(BaseImporter):
    """Beancount importer for CSV exports of the German DKB."""

    date_format: str = "%d.%m.%Y"
    delimiter: str = ";"
    quotechar: str = '"'
    fields: Sequence[str] = (
        "Buchungstag",
        "Wertstellung",
        "Buchungstext",
        "Auftraggeber / Begünstigter",
        "Verwendungszweck",
        "Kontonummer",
        "BLZ",
        "Betrag (EUR)",
        "Gläubiger-ID",
        "Mandatsreferenz",
        "Kundenreferenz",
    )

    def parse_amount(self, amount: str) -> Decimal:
        """Removes German thousands separator and converts decimal point to US."""
        return Decimal(amount.replace(".", "").replace(",", "."))

    def get_final_balance(self, filepath: str) -> tuple[datetime, Decimal] | None:
        with open(filepath, encoding=self.file_encoding) as f:
            for i, line in enumerate(f.readlines()):
                regex = r'Kontostand vom (\d+.\d+.\d+):";"([\d.,]+) (\w+)";'
                logger.debug(f"Trying to match {regex=} in {line=}")
                match = re.search(regex, line)
                if match:
                    bal_date = datetime.strptime(match.group(1), self.date_format)
                    amount = Decimal(self.parse_amount(match.group(2)))
                    currency = match.group(3)
                    final_balance = make_balance(
                        fname=filepath,
                        lineno=i + 1,
                        date=bal_date,
                        account=self.importer_account,
                        currency=currency,
                        amount=amount,
                    )
                    return final_balance

    def identify(self, filepath: str) -> bool:
        logger.info(f"Looking at {filepath}")
        with open(filepath, encoding=self.file_encoding) as f:
            while line := f.readline():
                line = line.strip()[:-1]
                regex = r'"Kontonummer:";"(\w+) / Girokonto'
                logger.debug(f"Trying to match {regex=} in {line=}")
                match = re.search(regex, line)
                if match:
                    iban = match.group(1)
                    if iban == self.iban:
                        logger.info(f"{iban=} found.")
                        break
                    else:
                        logger.debug(f"{iban=} != {self.iban}")

            while line := f.readline():
                line = line.strip()[:-1]
                logger.debug(f"Expected header {self.expected_header}")
                logger.debug(f"Current line    {line}")
                if line == self.expected_header:
                    logger.info("Header matched.")
                    return True
        return False

    def csv_to_txn(self, csv_row: dict[str, str]):
        txn = TXN(
            owner_iban="",
            date=datetime.strptime(
                csv_row["Wertstellung"], self.date_format
            ).date(),  # type: ignore
            posting_type=csv_row["Buchungstext"],
            reference=csv_row["Verwendungszweck"],
            payee_name=csv_row["Auftraggeber / Begünstigter"],
            payee_iban=csv_row["Kontonummer"],
            payee_bic=csv_row["BLZ"],
            amount=self.parse_amount(csv_row["Betrag (EUR)"]),
            currency="EUR",
        )
        return txn

    def filename(self, filepath: str):
        match = re.search(r"(\d+)", filepath)
        if match:
            return f"{match.group(1)}.csv"
        return None


@dataclass
class GLSCsvImporter(BaseImporter):
    """Beancount importer for CSV exports of the German DKB."""

    date_format: str = "%d.%m.%Y"
    delimiter: str = ";"
    quotechar: str = ""
    fields: Sequence[str] = (
        "Bezeichnung Auftragskonto",
        "IBAN Auftragskonto",
        "BIC Auftragskonto",
        "Bankname Auftragskonto",
        "Buchungstag",
        "Valutadatum",
        "Name Zahlungsbeteiligter",
        "IBAN Zahlungsbeteiligter",
        "BIC (SWIFT-Code) Zahlungsbeteiligter",
        "Buchungstext",
        "Verwendungszweck",
        "Betrag",
        "Waehrung",
        "Saldo nach Buchung",
        "Bemerkung",
        "Kategorie",
        "Steuerrelevant",
        "Glaeubiger ID",
        "Mandatsreferenz",
    )

    def parse_amount(self, amount: str) -> Decimal:
        """Removes German thousands separator and converts decimal point to US."""
        return Decimal(amount.replace(".", "").replace(",", "."))

    def get_final_balance(self, filepath: str) -> Directive | None:
        with open(filepath, encoding=self.file_encoding) as f:
            csv_rows = csv.DictReader(
                f, delimiter=self.delimiter, quotechar=self.quotechar
            )
            csv_row = next(csv_rows)
            return make_balance(
                fname=filepath,
                lineno=2,
                date=datetime.strptime(csv_row["Buchungstag"], self.date_format),
                account=self.importer_account,
                currency=csv_row["Waehrung"],
                amount=Decimal(self.parse_amount(csv_row["Saldo nach Buchung"])),
            )

    def identify(self, filepath: str) -> bool:
        with open(filepath, encoding=self.file_encoding) as f:
            for _ in range(10):
                header = f.readline().strip()
                if header == self.expected_header:
                    csv_row = f.readline().strip()
                    return (
                        csv_row.split(self.delimiter)[0].replace(self.quotechar, "")
                        == self.iban
                    )
        return False

    def csv_to_txn(self, csv_row: dict[str, str]):
        txn = TXN(
            owner_iban="IBAN Auftragskonto",
            date=datetime.strptime(
                csv_row["Valutadatum"], self.date_format
            ).date(),  # type: ignore
            posting_type=csv_row["Buchungstext"],
            reference=csv_row["Verwendungszweck"],
            payee_name=csv_row["Name Zahlungsbeteiligter"],
            payee_iban=csv_row["IBAN Zahlungsbeteiligter"],
            payee_bic=csv_row["BIC (SWIFT-Code) Zahlungsbeteiligter"],
            amount=self.parse_amount(csv_row["Betrag"]),
            currency=csv_row["Waehrung"],
        )
        return txn

    def filename(self, filepath: str):
        match = re.search(r"(\d+)", filepath)
        if match:
            return f"{match.group(1)}.csv"
        return None


class SparkasseMastercard(csvbase.Importer):
    """Beancount importer for Sparkasse Mastercard CSV exports.

    This importer handles CSV exports from Sparkasse Mastercard statements.
    """

    # CSV dialect configuration
    class dialect(csv.excel):
        delimiter = ";"
        quotechar = '"'

    # File reading configuration
    encoding = "ISO-8859-1"
    skiplines = 0
    names = True  # First row contains column names

    # Column definitions - these map to the CSV columns
    # Required fields
    date = csvbase.Date("Buchungsdatum", frmt="%d.%m.%y")
    payee = csvbase.Columns("Transaktionsbeschreibung")
    amount = csvbase.Amount("Buchungsbetrag", subs={r"\.": "", r",": "."})

    # Optional fields
    currency = csvbase.Column("Buchungswährung", default="EUR")
    narration = csvbase.Column("Transaktionsbeschreibung Zusatz")

    def __init__(
        self,
        account: str,
        credit_card_number: str,
        currency: str = "EUR",
        flag: str = "*",
    ):
        """Initialize the Sparkasse Mastercard importer.

        Args:
            account: The beancount account to use for imported transactions
            credit_card_number: Credit card number (can be full number or with 8
                middle digits obfuscated)
            currency: Default currency (default: EUR)
            flag: Default transaction flag (default: *)
        """
        super().__init__(account=account, currency=currency, flag=flag)
        self.credit_card_number = credit_card_number

    def identify(self, filepath: str) -> bool:
        """Identify if this file can be handled by this importer.

        Args:
            filepath: Path to the file to identify

        Returns:
            True if this importer can handle the file
        """
        try:
            # Check filename pattern first
            if not self._matches_filename_pattern(filepath):
                return False

            # Check file content
            with open(filepath, encoding=self.encoding) as f:
                header = f.readline().strip()
                # Check for typical Sparkasse Mastercard CSV headers
                if not (
                    "Buchungsdatum" in header and "Transaktionsbeschreibung" in header
                ):
                    return False

                # Check if credit card number matches in the first data row
                first_data_line = f.readline().strip()
                return self._matches_credit_card_in_content(first_data_line)
        except Exception:
            return False

    def _matches_filename_pattern(self, filepath: str) -> bool:
        """Check if the filename matches the expected pattern and credit card number.

        Args:
            filepath: Path to check

        Returns:
            True if filename pattern and credit card number match
        """
        # Extract filename from path
        filename = filepath.split("/")[-1]

        # Pattern: umsatz-XXXX________YYYY-YYYYMMDD.CSV
        match = re.search(r"umsatz-(\d{4})_{8}(\d{4})-\d{8}\.CSV", filename)
        if not match:
            return False

        first_four = match.group(1)
        last_four = match.group(2)

        # Check against our credit card number (handle both obfuscated and full formats)
        return self._matches_credit_card_pattern(first_four, last_four)

    def _matches_credit_card_in_content(self, data_line: str) -> bool:
        """Check if the credit card number in the CSV content matches our
        expected number.

        Args:
            data_line: First data line from CSV

        Returns:
            True if credit card number matches
        """
        # Extract credit card number from CSV line (first column)
        parts = data_line.split(";")
        if not parts:
            return False

        card_in_file = parts[0].strip('"')

        # Format: "1234 **** **** 5678"
        match = re.search(r"(\d{4}) \*{4} \*{4} (\d{4})", card_in_file)
        if not match:
            return False

        first_four = match.group(1)
        last_four = match.group(2)

        return self._matches_credit_card_pattern(first_four, last_four)

    def _matches_credit_card_pattern(self, first_four: str, last_four: str) -> bool:
        """Check if the given first and last four digits match our credit card number.

        Args:
            first_four: First 4 digits
            last_four: Last 4 digits

        Returns:
            True if pattern matches
        """
        # Handle different formats of credit_card_number
        if "*" in self.credit_card_number or "_" in self.credit_card_number:
            # Obfuscated format: extract first and last 4 digits
            # Could be "1234 **** **** 5678" or "1234________5678"
            card_match = re.search(r"(\d{4}).*?(\d{4})", self.credit_card_number)
            if card_match:
                return (
                    card_match.group(1) == first_four
                    and card_match.group(2) == last_four
                )
        else:
            # Full number format: extract first and last 4 digits
            digits_only = re.sub(r"\D", "", self.credit_card_number)
            if len(digits_only) >= 8:
                return digits_only[:4] == first_four and digits_only[-4:] == last_four

        return False

    def filename(self, filepath: str) -> str | None:
        """Generate a filename for archiving the imported file.

        Args:
            filepath: Original filepath

        Returns:
            Suggested filename for archiving, or None
        """
        match = re.search(r"umsatz-(\d{4})_{8}(\d{4})-(\d{8})\.CSV", filepath)
        if match:
            first_four = match.group(1)
            last_four = match.group(2)
            date = match.group(3)

            # Only generate filename if the card number matches
            if not self._matches_credit_card_pattern(first_four, last_four):
                return None

            # Generate a clean card identifier from our credit card number
            card_id = self._generate_card_identifier()

            return f"{date}-{card_id}.mastercard.csv"
        return None

    def _generate_card_identifier(self) -> str:
        """Generate a clean card identifier for filenames.

        Returns:
            A string identifier for the credit card
        """
        # Extract first and last 4 digits from credit card number
        if "*" in self.credit_card_number or "_" in self.credit_card_number:
            # Obfuscated format
            card_match = re.search(r"(\d{4}).*?(\d{4})", self.credit_card_number)
            if card_match:
                return f"{card_match.group(1)}{card_match.group(2)}"
        else:
            # Full number format
            digits_only = re.sub(r"\D", "", self.credit_card_number)
            if len(digits_only) >= 8:
                return f"{digits_only[:4]}{digits_only[-4:]}"

        # Fallback: use a sanitized version of the input
        return re.sub(r"[^\w]", "", self.credit_card_number)[:8]


def make_transaction(
    account: str, txn: TXN, fname: str, lineno: int, flag: str
) -> Transaction:  # type: ignore
    postings = [make_posting(account=account, amount=txn.amount, currency=txn.currency)]
    for posting in txn.induced_postings:
        postings.append(
            make_posting(
                account=posting.account, amount=None, currency=None, flag=posting.flag
            )
        )

    t = Transaction(
        meta=new_metadata(filename=fname, lineno=lineno, kvlist=txn.meta),
        date=txn.date,
        flag=flag,
        payee=txn.payee_name,
        narration=txn.reference,
        tags=EMPTY_SET,
        links=EMPTY_SET,
        postings=postings,
    )
    return t


def make_posting(
    amount: Decimal | None,
    currency: str,
    account: str,
    flag: str | None = None,
):
    if amount is not None:
        units = Amount(number=amount, currency=currency)
    else:
        units = None
    posting = Posting(
        account=account,
        units=units,  # type: ignore
        cost=None,
        price=None,
        flag=flag,
        meta=None,
    )
    return posting


def make_balance(
    fname: str,
    lineno: int,
    date: datetime,
    account: str,
    currency: str,
    amount: Decimal,
):
    return Balance(
        meta=new_metadata(filename=fname, lineno=lineno),
        date=date.date() + timedelta(days=1),
        account=account,
        amount=Amount(number=amount, currency=currency),
        tolerance=None,
        diff_amount=None,
    )
