#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Hetzner report downloader — SKELETON, built against the real interface.

Now correctly inherits from ReportDownloaderBase + DownloaderInterface,
matching what api/provider access + masu's orchestrator actually expect
(confirmed from the real downloader_interface.py / report_downloader_base.py
you shared — not guessed like the first draft was).

TODO: verify these import paths match your repo exactly:
"""
import csv
import os
import uuid
from datetime import datetime
from datetime import timezone

# TODO confirm these two import paths against your repo structure
from masu.external.downloader.downloader_interface import DownloaderInterface
from masu.external.downloader.report_downloader_base import ReportDownloaderBase

from .mock_data import MOCK_PRICING_RESPONSE
from .mock_data import MOCK_SERVERS_RESPONSE

USE_MOCK = True
HETZNER_API_BASE = "https://api.hetzner.cloud/v1"

# Column schema for the synthetic report file this downloader generates.
# Since Hetzner has no CUR-style export, WE define this schema — it will
# also need to match whatever a future HetznerReportParser (processor
# layer, not built yet) expects to read. Keep these in sync once that
# exists.
REPORT_COLUMNS = [
    "resource_id",
    "resource_name",
    "server_type",
    "location",
    "hourly_rate_eur",
    "hours_running",
    "estimated_cost_eur",
    "billing_period_start",
]


class HetznerReportDownloaderError(Exception):
    """Raised when Hetzner report data can't be fetched, built, or found locally."""


class HetznerReportDownloader(ReportDownloaderBase, DownloaderInterface):
    """
    Downloads (really: reconstructs) Hetzner cost data.

    Unlike AWS/Azure/GCP, there is no report file sitting in a bucket to
    fetch. Instead, this class calls the Hetzner API for servers + pricing,
    builds a synthetic CSV report itself, writes it to self.download_path,
    and returns it through the same manifest/file interface the rest of
    masu expects — so downstream code can treat it like any other
    downloaded report.
    """

    def __init__(self, customer_name, credentials, data_source, **kwargs):
        super().__init__(**kwargs)
        self.customer_name = customer_name
        self.credentials = credentials or {}
        self.data_source = data_source or {}
        self.api_token = self.credentials.get("api_token")

    # ---- DownloaderInterface methods --------------------------------------

    def get_manifest_context_for_date(self, date):
        """
        Build the synthetic report for `date`'s billing period and
        register a manifest record for it.

        Returns dict matching DownloaderInterface's documented shape:
            manifest_id, assembly_id, compression, files
        """
        servers = self._fetch_servers()
        pricing = self._fetch_pricing()
        line_items = self._reconstruct_costs(servers, pricing, date)

        assembly_id = str(uuid.uuid4())
        filename = f"hetzner_report_{date.strftime('%Y%m%d')}_{assembly_id}.csv"
        self._write_report_csv(line_items, filename)

        billing_start = date.replace(day=1)
        export_datetime = datetime.now(timezone.utc)

        # NOTE: this touches the DB via ReportManifestDBAccessor (inherited
        # from ReportDownloaderBase) and requires a real Django/masu
        # context to run — it will raise outside that context. That's
        # expected when smoke-testing this file standalone; see the
        # __main__ block below, which monkeypatches this for local testing.
        manifest_id = self._process_manifest_db_record(
            assembly_id=assembly_id,
            billing_start=billing_start,
            num_of_files=1,
            export_datetime=export_datetime,
        )

        return {
            "manifest_id": manifest_id,
            "assembly_id": assembly_id,
            "compression": "PLAIN",
            "files": [{"key": filename, "local_file": filename}],
        }

    def get_local_file_for_report(self, report):
        """report is the filename we generated in get_manifest_context_for_date."""
        return os.path.join(self.download_path, report)

    def download_file(self, key, stored_etag=None, manifest_id=None, start_date=None):
        """
        Nothing to actually download from Hetzner — the file was already
        generated locally during get_manifest_context_for_date. Just
        confirm it's there and hand back the path + an etag, matching
        what AWS/Azure downloaders return from a real download.
        """
        local_path = self.get_local_file_for_report(key)
        if not os.path.exists(local_path):
            raise HetznerReportDownloaderError(f"Expected generated report file not found: {local_path}")
        etag = stored_etag or "hetzner-self-generated"
        return local_path, etag

    # ---- data fetching (mocked for now) ------------------------------------

    def _fetch_servers(self):
        if USE_MOCK:
            return MOCK_SERVERS_RESPONSE["servers"]
        # TODO real implementation once credentials exist:
        # resp = requests.get(
        #     f"{HETZNER_API_BASE}/servers",
        #     headers={"Authorization": f"Bearer {self.api_token}"},
        # )
        # resp.raise_for_status()
        # return resp.json()["servers"]
        raise NotImplementedError("Real Hetzner API call not yet implemented")

    def _fetch_pricing(self):
        if USE_MOCK:
            return MOCK_PRICING_RESPONSE["pricing"]
        # TODO real implementation once credentials exist — see _fetch_servers
        raise NotImplementedError("Real Hetzner API call not yet implemented")

    # ---- cost reconstruction + file writing --------------------------------

    def _reconstruct_costs(self, servers, pricing, report_date):
        """
        Known simplifications to revisit once real data is available:
          - doesn't apply Hetzner's monthly price cap for near-full-month usage
          - doesn't account for traffic overage charges
          - assumes continuous uptime since `created`, no stop/start gaps
          - not yet validated against a real invoice
        """
        price_by_type_id = {
            st["id"]: st["prices"][0]["price_hourly"]["net"] for st in pricing["server_types"]
        }

        line_items = []
        for server in servers:
            type_id = server["server_type"]["id"]
            hourly_rate = float(price_by_type_id.get(type_id, "0"))

            created = datetime.fromisoformat(server["created"])
            hours_running = (report_date.replace(tzinfo=timezone.utc) - created).total_seconds() / 3600
            hours_running = max(hours_running, 0)

            line_items.append(
                {
                    "resource_id": server["id"],
                    "resource_name": server["name"],
                    "server_type": server["server_type"]["name"],
                    "location": server["datacenter"]["location"]["name"],
                    "hourly_rate_eur": round(hourly_rate, 6),
                    "hours_running": round(hours_running, 2),
                    "estimated_cost_eur": round(hourly_rate * hours_running, 4),
                    "billing_period_start": report_date.replace(day=1).date().isoformat(),
                }
            )
        return line_items

    def _write_report_csv(self, line_items, filename):
        os.makedirs(self.download_path, exist_ok=True)
        local_path = os.path.join(self.download_path, filename)
        with open(local_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=REPORT_COLUMNS)
            writer.writeheader()
            writer.writerows(line_items)
        return local_path


if __name__ == "__main__":
    # Smoke test: exercises everything EXCEPT the DB-touching manifest
    # record (which needs a real Django/masu context). Run with:
    #   python -m hetzner.hetzner_report_downloader

    class _StandaloneTestDownloader(HetznerReportDownloader):
        def _process_manifest_db_record(self, **kwargs):
            print(f"[skipped DB call — would have run with]: {kwargs}")
            return "fake-manifest-id"

    downloader = _StandaloneTestDownloader(
        customer_name="test-customer",
        credentials={"api_token": "fake-token"},
        data_source={},
        download_path="/tmp/hetzner_test_downloads",
    )
    context = downloader.get_manifest_context_for_date(datetime.now(timezone.utc))
    print("manifest context:", context)

    for file_info in context["files"]:
        local_path, etag = downloader.download_file(file_info["key"])
        print(f"'downloaded' file at {local_path} (etag={etag})")
        with open(local_path) as f:
            print(f.read())
