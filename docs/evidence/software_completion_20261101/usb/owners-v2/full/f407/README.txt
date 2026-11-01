Experimental integration kit, not a ready firmware. Native project unchanged.
See apps/SCG/docs/USB_CDC_TRANSPORT_20261013.md for all hook contracts.
Includes the unchanged SilverStar fail-stop owner and its Apache-2.0 license.
Call Configure only after real configuration success. Native Init owns first RX arm.
CDC Receive: call UsbCdc_Receive exactly once; remove native immediate rearm.
Main owner: call UsbCdc_Service regularly and check every result.
Reset/disconnect/unconfigure/suspend/fault: LinkDown before application publication.
Quiesced only after successful hardware cancellation; never from timeout/state alone.
Then Configure on a new successful configuration. All TX writers must use this kit.
USBD_OK can hide discarded LL failures; middleware acceptance remains NOT PROVEN.
CMake >= 3.17: include usb_cdc_transport.cmake; UsbCdc_Attach(target BUNDLED).
For an existing compatible SilverStar assertion owner use EXISTING instead.
Make: add both Src C files, Inc and Common/Inc; include Common/Src/silverstar_assert.c
only when the native target does not already link that assertion owner.
No hooks, stack source patches, clock or IRQ edits are applied automatically.

OPT-IN SOURCE-BOUND INTEGRATION: lifecycle-integration.json lists exact replacements.
Compile each Native derivative instead of its original, never both; add all additional_sources.
Input project is unchanged. Original configuration is preserved in configuration_derivation.native.
Only the byte-exact reviewed F407 LL initializer gets fixed RX/EP0/EP1/EP2 FIFO geometry.
Other user FIFO/PMA/clock/startup configuration is not rewritten. See configuration_derivation.
A recognized sysmem source is replaced by the rejecting no-heap ABI; force-link its required symbols.
Configuration is checked before class initialization; invalid PMA/FIFO layout blocks online state.
Do not use the plain UsbCdc_Attach fragment alone for an integrated build.
Suspend invalidates the session; resume stays offline until reset/reconfiguration.
This connects callbacks in source, not a hardware or full safety acceptance.
