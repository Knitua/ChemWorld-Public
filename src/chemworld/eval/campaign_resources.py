"""Compatibility exports for the top-level campaign resource contract."""

from chemworld.campaign_resources import (
    CAMPAIGN_RESOURCE_CARD_VERSION,
    CAMPAIGN_RESOURCE_DELTA_VERSION,
    CAMPAIGN_RESOURCE_LEDGER_VERSION,
    CampaignResourceCard,
    CampaignResourceDelta,
    CampaignResourceError,
    CampaignResourceIntegrityError,
    CampaignResourceLedger,
    CampaignResourcePreflight,
    campaign_resource_event_id,
    derive_campaign_resource_delta,
    generous_electrochemical_max_envelope_card,
)

__all__ = [
    "CAMPAIGN_RESOURCE_CARD_VERSION",
    "CAMPAIGN_RESOURCE_DELTA_VERSION",
    "CAMPAIGN_RESOURCE_LEDGER_VERSION",
    "CampaignResourceCard",
    "CampaignResourceDelta",
    "CampaignResourceError",
    "CampaignResourceIntegrityError",
    "CampaignResourceLedger",
    "CampaignResourcePreflight",
    "campaign_resource_event_id",
    "derive_campaign_resource_delta",
    "generous_electrochemical_max_envelope_card",
]
