#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests for the Hetzner report downloader.

Mirrors the style of the existing test_hetzner_provider-adjacent tests
(test_models.py / test_serializers.py, currently 39/39 passing).

TODO: confirm file location against your repo's convention — likely
masu/test/external/downloader/hetzner/test_hetzner_report_downloader.py,
following wherever masu/test/external/downloader/azure/ puts its tests.

Run with (once in place):
    python manage.py test masu.test.external.downloader.hetzner.test_hetzner_report_downloader
"""
import csv
import os
import tempfile
from datetime import datetime
from datetime import timezone
from unittest.mock import patch

from django.test import TestCase

from masu.external.downloader.hetzner.hetzner_report_downloader import (
    HetznerReportDownloader,
    HetznerReportDownloaderError,
)
from masu.external.downloader.hetzner.mock_data import (
    MOCK_PRICING_RESPONSE,
    MOCK_SERVERS_RESPONSE,
)


class HetznerReportDownloaderTest(TestCase):
    """Tests for HetznerReportDownloader.

    NOTE: as long as USE_MOCK = True inside hetzner_report_downloader.py,
    _fetch_servers/_fetch_pricing already return canned data — no need to
    mock the HTTP layer separately. Once real API calls are implemented
    (USE_MOCK = False), these tests should be updated to patch `requests.get`
    instead, so they keep passing without real credentials.
    """

    def setUp(self):
        self.download_path = tempfile.mkdtemp(prefix="hetzner_test_")
        self.credentials = {"api_token": "fake-token"}
        self.data_source = {}
        # Manifest DB writes need a real Provider row to satisfy the FK,
        # which this test suite doesn't set up — patch it out, same way
        # the __main__ smoke test in the downloader file does.
        patcher = patch.object(
            HetznerReportDownloader,
            "_process_manifest_db_record",
            return_value="fake-manifest-id",
        )
        self.mock_manifest_record = patcher.start()
        self.addCleanup(patcher.stop)

        self.downloader = HetznerReportDownloader(
            customer_name="test-customer",
            credentials=self.credentials,
            data_source=self.data_source,
            download_path=self.download_path,
            provider_uuid="00000000-0000-0000-0000-000000000000",
            provider_type="Hetzner",
        )

    # ---- get_manifest_context_for_date -------------------------------------

    def test_get_manifest_context_for_date_returns_expected_keys(self):
        """Return shape must match what DownloaderInterface documents."""
        date = datetime(2026, 7, 16, tzinfo=timezone.utc)
        context = self.downloader.get_manifest_context_for_date(date)

        self.assertIn("manifest_id", context)
        self.assertIn("assembly_id", context)
        self.assertIn("compression", context)
        self.assertIn("files", context)
        self.assertEqual(len(context["files"]), 1)
        self.assertIn("key", context["files"][0])
        self.assertIn("local_file", context["files"][0])

    def test_get_manifest_context_for_date_writes_csv_with_all_servers(self):
        date = datetime(2026, 7, 16, tzinfo=timezone.utc)
        context = self.downloader.get_manifest_context_for_date(date)

        filename = context["files"][0]["key"]
        local_path = os.path.join(self.download_path, filename)
        self.assertTrue(os.path.exists(local_path))

        with open(local_path) as f:
            rows = list(csv.DictReader(f))

        expected_server_count = len(MOCK_SERVERS_RESPONSE["servers"])
        self.assertEqual(len(rows), expected_server_count)

    def test_get_manifest_context_for_date_calls_manifest_db_record(self):
        """Confirms the base class DB-record helper gets invoked with the
        right assembly_id / billing_start, without actually hitting the DB."""
        date = datetime(2026, 7, 16, tzinfo=timezone.utc)
        context = self.downloader.get_manifest_context_for_date(date)

        self.mock_manifest_record.assert_called_once()
        _, kwargs = self.mock_manifest_record.call_args
        self.assertEqual(kwargs["assembly_id"], context["assembly_id"])
        self.assertEqual(kwargs["billing_start"], date.replace(day=1))
        self.assertEqual(kwargs["num_of_files"], 1)

    # ---- download_file -------------------------------------------------------

    def test_download_file_returns_path_and_etag_for_existing_file(self):
        date = datetime(2026, 7, 16, tzinfo=timezone.utc)
        context = self.downloader.get_manifest_context_for_date(date)
        filename = context["files"][0]["key"]

        local_path, etag = self.downloader.download_file(filename)

        self.assertTrue(os.path.exists(local_path))
        self.assertIsNotNone(etag)

    def test_download_file_raises_for_missing_file(self):
        """download_file should fail loudly, not silently, if the generated
        report is somehow missing — e.g. get_manifest_context_for_date
        wasn't called first, or the file was deleted out from under it."""
        with self.assertRaises(HetznerReportDownloaderError):
            self.downloader.download_file("nonexistent_report.csv")

    # ---- cost reconstruction math ---------------------------------------------

    def test_reconstruct_costs_uses_correct_hourly_rate(self):
        """Sanity-check the actual cost math against the mock pricing data,
        since this is the part with no source of truth to compare against
        yet (no real invoice available)."""
        date = datetime(2026, 7, 16, tzinfo=timezone.utc)
        line_items = self.downloader._reconstruct_costs(
            MOCK_SERVERS_RESPONSE["servers"], MOCK_PRICING_RESPONSE["pricing"], date
        )

        first_server = MOCK_SERVERS_RESPONSE["servers"][0]
        first_item = next(i for i in line_items if i["resource_id"] == first_server["id"])

        expected_rate = float(MOCK_PRICING_RESPONSE["pricing"]["server_types"][0]["prices"][0]["price_hourly"]["net"])
        self.assertAlmostEqual(first_item["hourly_rate_eur"], expected_rate, places=6)
        self.assertGreaterEqual(first_item["hours_running"], 0)
        self.assertAlmostEqual(
            first_item["estimated_cost_eur"],
            round(expected_rate * first_item["hours_running"], 4),
            places=4,
        )

    def test_reconstruct_costs_never_returns_negative_hours(self):
        """A server with a `created` timestamp in the future (clock skew,
        bad data, etc.) shouldn't produce a negative cost."""
        future_server = {
            **MOCK_SERVERS_RESPONSE["servers"][0],
            "created": "2099-01-01T00:00:00+00:00",
        }
        line_items = self.downloader._reconstruct_costs(
            [future_server], MOCK_PRICING_RESPONSE["pricing"], datetime(2026, 7, 16, tzinfo=timezone.utc)
        )
        self.assertEqual(line_items[0]["hours_running"], 0)
        self.assertEqual(line_items[0]["estimated_cost_eur"], 0)