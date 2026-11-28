import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from obliryx.broker_catalog import load_catalog
from obliryx.cli import main


class BrokerCatalogTests(unittest.TestCase):
    def test_catalog_cli_reads_packaged_data_without_network_or_archive(self):
        output = io.StringIO()
        with (patch("sys.argv", ["obliryx", "broker-catalog"]),
              patch("obliryx.cli.Store", side_effect=AssertionError("archive opened")),
              patch("socket.create_connection", side_effect=AssertionError("network opened")),
              redirect_stdout(output)):
            self.assertEqual(main(), 0)
        catalog = json.loads(output.getvalue())
        self.assertTrue(10 <= len(catalog["procedures"]) <= 20)
        self.assertTrue(all(row["support"] == "manuale" for row in catalog["procedures"]))

        output = io.StringIO()
        with patch("sys.argv", ["obliryx", "broker-catalog", "liveramp-accesso-it"]), redirect_stdout(output):
            self.assertEqual(main(), 0)
        procedure = json.loads(output.getvalue())
        self.assertEqual(procedure["holding_state"], "unknown")
        self.assertEqual(procedure["countries"], ["IT"])
        self.assertEqual(procedure["channel"]["destination"], "privacy.it@liveramp.com")

    def test_changed_recipient_or_fields_requires_a_new_review(self):
        for key, value in (("destination", "different@example.invalid"), ("fields", ["nuovo campo"])):
            with self.subTest(key=key), tempfile.TemporaryDirectory() as temp:
                catalog = load_catalog()
                procedure = next(row for row in catalog["procedures"] if row["id"] == "liveramp-accesso-it")
                procedure["channel"][key] = value
                folder = Path(temp)
                (folder / "broker_procedures.json").write_text(json.dumps(catalog), encoding="utf-8")
                with (patch("obliryx.broker_catalog.files", return_value=folder),
                      patch("sys.argv", ["obliryx", "broker-catalog", "liveramp-accesso-it"]),
                      redirect_stdout(io.StringIO()) as output, redirect_stderr(io.StringIO()) as errors):
                    self.assertEqual(main(), 1)
                self.assertEqual(output.getvalue(), "")
                self.assertIn("nuova revisione", errors.getvalue())
