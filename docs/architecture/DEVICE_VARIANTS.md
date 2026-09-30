# Device interface and operating variants

One physical chip is registered once. A Device manifest owns its physical identity, capabilities, shared sources and metadata. device_variants contains small named overlays for interface-specific resources, bus source changes, defines and initialization settings. A project Device instance stores the plugin ID plus interface and profile; resolving a project view selects the matching overlay for that instance. The physical_device identity cannot be overridden. Mixed interfaces of the same chip remain distinct instances and share common sources only once. Internal register-bus and UBX libraries are Core support components, not pretend physical devices.

BMI088 expresses I²C/SPI as interfaces and raw 200 Hz/Bosch synchronized 400 Hz as operating profiles. Its four combinations remain one plugin. BMI323, ICM42605, ICM42688P, ICM45686, LSM6DSV320X, LSM6DSV32X, MPU6000, MPU6500 and MPU9250 similarly have one plugin per physical chip with interface variants. UI labels use CHIP · SPI rather than the erroneous 路 SPI. Release identity remains 0.1.0; device variants do not alter AIR M0, SSLOG, decoder or navigation contract versions.

Project format 14 is a pre-release format. Existing format 12/13 projects are not a product compatibility guarantee; users should regenerate project files against this baseline.
