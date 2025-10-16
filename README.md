# Beancount Importer - Sparkasse
[![tests_badge](https://github.com/laermannjan/beancount-import-sparkasse/actions/workflows/main.yaml/badge.svg)](https://github.com/laermannjan/beancount-import-sparkasse/actions/) [![image](https://img.shields.io/pypi/v/beancount-import-sparkasse.svg)](https://pypi.python.org/pypi/beancount-import-sparkasse) [![image](https://img.shields.io/pypi/pyversions/beancount-import-sparkasse.svg)](https://pypi.python.org/pypi/beancount-import-sparkasse) [![image](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![license_badge](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
## Installation
The importer is available on [PyPI](https://pypi.org/project/beancount-import-sparkasse)
``` sh
pip install --user beancount-import-sparkasse
```

## Download Bank Statement

1. Log into your Sparkasse account
2. Choose the correct bank account
3. Click 'Exportieren'
4. Choose `Excel (CSV-CAMT V8)` in the dropdown. Note that `CSV-CAMT V2` also
   works but contains less information.

## Configuration
Add the importer to your `beancount` import config

``` python
from beancount_import_sparkase import SparkasseCSVCAMTImporter

CONFIG = [
    SparkasseCSVCAMTImporter(
        iban="DE01234567890123456789",
        account="Assets:DE:Sparkasse:Giro"
    )
]

```
