# GUI closeout notes (2026-10-03)

On the GSHC Flight page, the status cards allocate more width to the
seven-row status card. At 1280x720 in the Chinese Qt layout probe, its height changed
from 156 to 132 pixels and each of the six plots grew from about 175 to 187
pixels. The same six plots and status fields remain visible.
At narrower English window widths, the brand and connection headings elide
within the header and expose their full text in tooltips. The Preflight page
keeps its controls reachable by vertical scrolling without horizontal overflow.
At shorter heights, the Flight status summary also scrolls when translated
text needs more rows, leaving room for all six plots. In the English 1280x720
probe, the status viewport was 151 pixels and each plot remained at least 178
pixels high; the status fields remained reachable by scrolling.

The Ground activity LED settings are on the Telemetry page. A TX pulse follows
completion of a wireless packet send; an RX pulse follows receipt of a valid
wireless packet. GPIO, active polarity and pulse length remain explicit project
settings. A shared GPIO with conflicting TX/RX polarity remains a validation
error.

New SCG drafts select E28-2G4M12SX and a PC UART interface for Ground. The
Ground target is internally enabled, while generation remains an explicit
choice. Existing project files keep their saved Ground selections. No hardware
resources or LED polarity are selected by this default.

The module selector no longer presents a generic hardware verification label.
Resource, power and compatibility validation remains active. This GUI batch
uses Qt layout and project configuration tests only. It does not establish
physical radio output power, LED electrical polarity, MCU timing, flight
qualification or any hardware behavior. Those require separate board and
radio evidence before release.
