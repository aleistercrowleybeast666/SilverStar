# User-edited decoder view

Normal import still requires an exact log Descriptor and decoder identity.
For a manually selected log and user-edited `.ssdecoder`, explicitly select
**User custom, unverified** in the import dialog. Folder discovery and project
restore continue to use the exact path; the option resets after submission.

A `.ssdecoder` remains declarative data, not Python or executable plugin code.
Edit the documented catalog/semantics declarations and rebuild the package's
manifest and member checksums according to the [package contract](Decoder_Profile_Package.md).
The custom option only relaxes the Descriptor identity match. Archive limits,
checksums, supported primitive types, payload sizes, finite values and bounded
channel IDs still apply. Keep the original log and decoder; source bytes are
not changed. Unknown or undecodable records retain their raw payloads.

The resulting Data Explorer view is clearly marked **USER CUSTOM / UNVERIFIED**.
Field values and meanings depend on the selected declarations and may be wrong
for that log. This view does not acquire Recorded fidelity, replay permission,
an exact decoder cache entry, project-save permission or ordinary export access.
Open a matching exact pair to return to the normal workflow. The banner,
navigation and time controls then return to their normal state.
