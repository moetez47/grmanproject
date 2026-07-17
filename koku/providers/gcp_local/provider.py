"""Hetzner local provider implementation to be used by Koku."""
from rest_framework import serializers

from ..hetzner.provider import HetznerProvider
from api.common import error_obj
from api.models import Provider


class HetznerLocalProvider(HetznerProvider):
    """Hetzner local provider."""

    def name(self):
        """Return name of the provider."""
        return Provider.PROVIDER_HETZNER_LOCAL

    def cost_usage_source_is_reachable(self, credentials, data_source):
        """Verify that Hetzner local source is given (no live API check)."""
        if not credentials or not credentials.get("api_token"):
            key = "api_token"
            message = "API token is a required parameter for Hetzner."
            raise serializers.ValidationError(error_obj(key, message))
        return True