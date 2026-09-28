BUILD_MANIFESTS += BuildSystem/fatfs.mk

C_SOURCES += \
  FATFS/Target/bsp_driver_sd.c \
  FATFS/Target/sd_diskio.c \
  FATFS/Target/fatfs_platform.c \
  FATFS/App/fatfs.c \
  Middlewares/Third_Party/FatFs/src/diskio.c \
  Middlewares/Third_Party/FatFs/src/ff.c \
  Middlewares/Third_Party/FatFs/src/ff_gen_drv.c

C_INCLUDES += \
  FATFS/Target \
  FATFS/App \
  Middlewares/Third_Party/FatFs/src
