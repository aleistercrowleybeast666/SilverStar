#ifndef __PROJECT_STORAGE_BINDING_H
#define __PROJECT_STORAGE_BINDING_H
#include <stdint.h>
typedef unsigned int UINT;
typedef unsigned char BYTE;
typedef enum {FR_OK, FR_NO_FILE, FR_NO_PATH, FR_NOT_READY, FR_NO_FILESYSTEM, FR_DISK_ERR} FRESULT;
typedef struct {uint32_t offset; uint32_t size; uint32_t id;} FIL;
typedef struct {uint32_t index;} DIR;
typedef struct {char fname[13]; BYTE fattrib; uint32_t fsize;} FILINFO;
#define FA_READ 1U
#define AM_DIR 16U
#define f_size(file) ((file)->size)
#define f_tell(file) ((file)->offset)
FRESULT f_open(FIL *file, const char *path, BYTE mode);
FRESULT f_close(FIL *file);
FRESULT f_read(FIL *file, void *data, UINT capacity, UINT *count);
FRESULT f_lseek(FIL *file, uint32_t offset);
FRESULT f_stat(const char *path, FILINFO *info);
FRESULT f_opendir(DIR *directory, const char *path);
FRESULT f_readdir(DIR *directory, FILINFO *info);
FRESULT f_closedir(DIR *directory);
#endif
