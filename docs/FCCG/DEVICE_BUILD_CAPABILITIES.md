# Selected device build capabilities

The matched MCU manifest declares `metadata.device_build_capabilities`: each
`SYSTEM_SELECTED_*` symbol maps to a device class and either a provided capability
or a sensor recommendation parameter. The generator writes the resolved facts to
`Generated/Inc/project_device_build_capabilities.h`, included by the generated
flight configuration before target configuration is read.

The provider is the same physical primary selected by capability routes and device
descriptors. An auxiliary JY901B does not qualify a different primary IMU. Raw
acceleration/rotation, software propagation qualification, preflight attitude
qualification, and runtime authoritative attitude qualification remain separate
facts. Missing facts are zero. A sensor without its own noise recommendation has
no recommendation; it does not inherit JY901B or NEO-M9N values. Explicit resolved
algorithm parameters remain authoritative.

Generated target builds do not include unselected JY901B or NEO-M9N private
capability headers. Legacy reference builds retain their existing package-owned
fallback definitions. This generation contract describes software composition;
it does not assert that a newly supported device has been verified on hardware.
