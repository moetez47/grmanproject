"""Hetzner provider implementation to be used by Koku."""
import requests
from rest_framework import serializers

from api.common import error_obj
from api.models import Provider
from providers.provider_errors import ProviderErrors
from ..provider_interface import ProviderInterface


HETZNER_API_BASE = "https://api.hetzner.cloud/v1"


class HetznerProvider(ProviderInterface):
    """Hetzner provider."""

    def name(self):
        """Return name of the provider."""
        return Provider.PROVIDER_HETZNER

    def cost_usage_source_is_reachable(self, credentials, data_source):
        """Verify that the Hetzner API token is valid and reachable."""
        api_token = credentials.get("api_token") if credentials else None
        if not api_token:
            key = ProviderErrors.HETZNER_INVALID_TOKEN
            message = ProviderErrors.HETZNER_INVALID_TOKEN_MESSAGE
            raise serializers.ValidationError(error_obj(key, message))

        headers = {"Authorization": f"Bearer {api_token}"}
        try:
            response = requests.get(f"{HETZNER_API_BASE}/pricing", headers=headers, timeout=10)
        except requests.exceptions.RequestException:
            key = ProviderErrors.HETZNER_UNREACHABLE
            message = ProviderErrors.HETZNER_UNREACHABLE_MESSAGE
            raise serializers.ValidationError(error_obj(key, message))

        if response.status_code != 200:
            key = ProviderErrors.HETZNER_UNREACHABLE
            message = ProviderErrors.HETZNER_UNREACHABLE_MESSAGE
            raise serializers.ValidationError(error_obj(key, message))

        return True

    def infra_type_implementation(self, provider_uuid, schema_name):
        """Return infra type. Not applicable for Hetzner."""
        return None

    def infra_key_list_implementation(self, infrastructure_type, schema_name):
        """Return infra key list. Not applicable for Hetzner."""
        return []