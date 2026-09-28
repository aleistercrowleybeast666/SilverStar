#ifndef __STORAGE_INTEGRITY_H
#define __STORAGE_INTEGRITY_H

typedef enum
{
    StorageIntegrityResult_Ok = 0,
    StorageIntegrityResult_IoError,
    StorageIntegrityResult_ByteMismatch,
    StorageIntegrityResult_CodecError
} StorageIntegrityResult;

/* Bench only: scheduler running, FATFS linked/mounted, sole filesystem owner.
 * Creates BYTECHK.BIN and LOGCHK.BIN with CREATE_NEW; never formats/deletes. */
StorageIntegrityResult StorageIntegrity_Run(void);
#endif /* __STORAGE_INTEGRITY_H */
