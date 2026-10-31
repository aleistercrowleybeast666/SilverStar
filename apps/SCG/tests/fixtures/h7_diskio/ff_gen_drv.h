#ifndef __FF_GEN_DRV_H
#define __FF_GEN_DRV_H
#include <stdint.h>
typedef uint8_t BYTE;
typedef uint16_t WORD;
typedef uint32_t DWORD;
typedef unsigned UINT;
typedef uint8_t DSTATUS;
typedef enum { RES_OK, RES_ERROR, RES_WRPRT, RES_NOTRDY, RES_PARERR } DRESULT;
#define STA_NOINIT 1U
#define _USE_WRITE 1
#define _USE_IOCTL 1
#define CTRL_SYNC 0
#define GET_SECTOR_COUNT 1
#define GET_SECTOR_SIZE 2
#define GET_BLOCK_SIZE 3
typedef struct {
    DSTATUS (*initialize)(BYTE);
    DSTATUS (*status)(BYTE);
    DRESULT (*read)(BYTE, BYTE *, DWORD, UINT);
    DRESULT (*write)(BYTE, const BYTE *, DWORD, UINT);
    DRESULT (*ioctl)(BYTE, BYTE, void *);
} Diskio_drvTypeDef;
#endif
