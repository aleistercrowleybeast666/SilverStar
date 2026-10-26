#include "ff.h"

/* SilverStar-owned FatFs paths use printable ASCII. A foreign non-ASCII name
 * is rejected instead of mapping it to an ambiguous OEM byte. The selected
 * CubeMX FatFs configuration uses static LFN storage and one LoggerTask owner. */
WCHAR ff_convert(WCHAR character, UINT direction)
{
    (void)direction;
    if ((character < 0x20U) || (character > 0x7EU)) { return 0U; }
    return character;
}

WCHAR ff_wtoupper(WCHAR character)
{
    if ((character >= (WCHAR)'a') && (character <= (WCHAR)'z'))
    { return (WCHAR)(character - (WCHAR)'a' + (WCHAR)'A'); }
    return character;
}
