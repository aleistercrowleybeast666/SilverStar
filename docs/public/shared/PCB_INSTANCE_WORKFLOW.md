# PCB instance workflow

Flight Hardware and Ground Station Hardware accept an existing PCB instance,
a CubeMX `.ioc`, or a generated CubeMX project directory. The CubeMX importer
parses the exact MCU, package, clock, peripheral and pin inventory, DMA, IRQ,
UART, SPI, I²C, SDIO, USB and ADC evidence. An `.ioc` alone is an editing
snapshot; firmware generation requires the corresponding generated sources.
The imported CubeMX files remain hardware input and are not SilverStar-owned
source.

An imported generated project can be saved with **Save as New PCB Instance**.
The save operation requires an exact MCU, a positive HCLK within that MCU's
declared limit, source digest and generated source snapshot. The installed
plugin records target role, IOC, generated hardware snapshot, clock, resource
provisions, exact MCU, source digest and provenance. Its maturity is always
`local_unverified`; saving a plugin does not validate a physical PCB. The
local package is installed under the FCCG plugin catalog, with a disposable
archive in the app's ignored `.work/board_exports/` directory.

Flight and Ground use the same CubeMX importer and board plugin exporter.
Ground's production selector includes the hardware-validated GS_SS1 reference
and locally installed Ground PCB instances. Selecting a PCB instance rebuilds
its hardware inventory and resource candidates. Ground radio bindings are
checked against the same SPI/electrical constraints as Flight; exclusive pins
and PC UART pins cannot overlap radio pins. A local board remains subject to
target resource validation and firmware build audits.

The GS_SS1 legacy firmware has run on its real F103 PCB, so that topology is a
hardware-validated reference. The new SilverStar Ground Core has an ARM build
result and awaits its own Round 5 board smoke test.
