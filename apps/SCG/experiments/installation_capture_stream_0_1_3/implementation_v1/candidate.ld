/* Isolated code/data link only. No startup/vector table. NEVER FLASH. */
ENTRY(InstallationCapture_ArmEntry)
MEMORY {
  FLASH (rx) : ORIGIN = 0x08000000, LENGTH = 128K
  CCM_FREE (rw) : ORIGIN = 0x1000F5B8, LENGTH = 2632
}
SECTIONS {
  .text : { *(.text*) *(.rodata*) } > FLASH
  .ARM.extab : { *(.ARM.extab*) } > FLASH
  .ARM.exidx : { *(.ARM.exidx*) } > FLASH
  .capture_ccm (NOLOAD) : { KEEP(*(.capture_ccm)) KEEP(*(.ccmram_bss.installation_capture)) KEEP(*(.ccmram_bss.installation_wire)) } > CCM_FREE
  .data : { *(.data*) } > CCM_FREE
  .bss (NOLOAD) : { *(.bss*) *(COMMON) } > CCM_FREE
  /DISCARD/ : { *(.comment) *(.note*) *(.ARM.attributes) }
}
ASSERT(SIZEOF(.capture_ccm) <= 2048, "capture feature cap exceeded")
ASSERT(SIZEOF(.data) == 0 && SIZEOF(.bss) == 0, "unexpected additional mutable storage")
