# Superseded proposal

The initial Android proposal is retired. The sole current export contract is the user-authorized shared `session_export_v1.schema.json` at SilverStar commit `cb944b7c5a844da2f277494662801f2179a268ad`.

Use [shared-contract implementation notes](SHARED_CONTRACTS.md) and the byte-exact [schema snapshot](../reference/shared-0.1.3/contracts/session_export_v1.schema.json). The obsolete `producer`, `sessions`, `created_utc`, `raw_session` and `session_metadata` manifest shapes are no longer emitted. The obsolete `SS-TFLOG/1-DRAFT` protocol is no longer implemented.
