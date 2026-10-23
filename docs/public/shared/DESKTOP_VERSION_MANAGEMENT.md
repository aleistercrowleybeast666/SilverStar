# Desktop version inventory

`VERSION` is the only product-number authority. `versions.json` references it
for SCG, GSHC and FLP. `python -B tools/silverstar_version.py` reports product,
independent contract, plugin and log-record identities from the current checkout.
Product version remains 0.1.3 in development; no release is created by this change.

The desktop applications display the full product string. Python packaging uses
the validated PEP 440 projection, and Windows resources use the numeric tuple
while retaining the full display string. Protocol/schema numbers stay separate.
Source-relative desktop execution and the existing portable specs are covered;
standalone wheel installation is not claimed.

The optional development references AIR, installation and navigation.journal
may be absent from an isolated checkout. The inventory then explicitly reports
`source_unavailable` and a null value. It never invents a compatible identity.
Present malformed sources and missing required sources still fail. The report
is informational and grants no decoding, hardware, replay or control permission.

This delivery includes desktop version display, inventory and packaging
metadata. Pending generator integrations, firmware changes, old document/test
dependencies and optional development sources remain outside this commit.
