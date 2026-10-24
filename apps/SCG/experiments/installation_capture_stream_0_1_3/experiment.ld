/* Isolated link-only proof of the proposed new section in currently free CCM.
 * No vector table, no startup, no MCU application. NEVER FLASH THIS ELF. */
ENTRY(Experiment_Entry)
MEMORY {
  FLASH (rx) : ORIGIN = 0x08000000, LENGTH = 64K
  CCM_FREE (rw) : ORIGIN = 0x1000F5B8, LENGTH = 2632
}
SECTIONS {
  .text : { *(.text*) *(.rodata*) } > FLASH
  .layout : { KEEP(*(.layout)) } > FLASH
  .capture_ccm (NOLOAD) : { KEEP(*(.capture_ccm)) } > CCM_FREE
  .data : { *(.data*) } > CCM_FREE
  .bss (NOLOAD) : { *(.bss*) *(COMMON) } > CCM_FREE
  /DISCARD/ : { *(.comment) *(.note*) *(.ARM.attributes) }
}
ASSERT(SIZEOF(.capture_ccm) <= 2048, "new capture state exceeds independent CCM cap")
ASSERT(SIZEOF(.data) == 0 && SIZEOF(.bss) == 0, "unexpected mutable state")
