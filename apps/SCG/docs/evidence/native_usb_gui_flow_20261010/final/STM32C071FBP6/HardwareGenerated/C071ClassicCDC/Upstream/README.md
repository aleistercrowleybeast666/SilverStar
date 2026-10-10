# STM32C0 Classic Core Middleware (CoreMW) MCU Firmware Package

![latest tag](https://img.shields.io/github/v/tag/STMicroelectronics/stm32c0-classic-coremw-apps.svg?color=brightgreen)

![fatfs](https://img.shields.io/badge/fatfs-v0.15-blue.svg) ![usb_device](https://img.shields.io/badge/usb_device-v2.11.5-blue.svg) ![usb_host](https://img.shields.io/badge/usb_host-v3.5.4-blue.svg)

## Description

**STM32Cube** is an STMicroelectronics original initiative to ease developers' life by reducing efforts, time and cost.

**Classic CoreMW** is a collection of middleware stacks and associated applications allowing RTOS management, File System operations and connectivity through USB and Ethernet. It is based on:
* ST's proprietary stacks: ST USB Device and ST USB Host
* Third parties' stacks: FreeRTOS, FatFS and LwIP

#### *Note*

 * *FreeRTOS* Middleware and examples are delivered on STM32C0 in the form of X-CUBE-FREERTOS that is available from [st.com](https://www.st.com/en/embedded-software/x-cube-freertos.html), from [GitHub](https://github.com/STMicroelectronics/x-cube-freertos) and from STM32CubeMX.

 * *FatFS* and *LwIP* examples are not provided in this package.

This package is **exclusively** published on GitHub (and is neither available in STM32CubeC0, STM32CubeMX nor STM32CubeIDE available on www.st.com).
It contains the integration of the Classic CoreMW stacks with STM32C0 devices, allowing users to get quick access to pre-built projects integrating them.

#### *Note*

 * The repository containing this package has been created using the `git submodule` command. Please refer to the ["How to use"](README.md#how-to-use) section explaining how to clone this repository and how to get the latest updates.

## List of applications

The **STM32C0 Classic CoreMW** package contains the following applications:

Middleware    | Application                        | Short Description
--------------|------------------------------------|------------------------------------------------------------------------
ST USB Device | CDC_Standalone                     | Shows how to use USB device application based on the Device Communication Class (CDC) following the PSTN subprotocol
ST USB Device | HID_Standalone                     | Shows a typical application where the STM32 MCU is enumerated as a HID device
ST USB Host   | CDC_Standalone                     | Shows how to use USB host application based on the Communication Class (CDC) to send/receive data to/from host from/to device
ST USB Host   | HID_Standalone                     | Shows how to use USB host application based on the Human Interface Class (HID) to connect a mouse or a keyboard
ST USB Host   | MSC_Standalone                     | Shows how to use USB host application based on the Mass Storage Class (MSC) to communicate with a usb flash disk

#### *Note*

 * All examples are provided **only** with pre-configured projects for *EWARM* toolchain.
 * Projects in this package have not been generated with STM32CubeMX (**i.e.**, no `.ioc` files are delivered).

## Boards available

 * STM32C0
   * [NUCLEO-C071RB](https://www.st.com/en/evaluation-tools/nucleo-c071rb.html) RevB

## Development Toolchains and Compilers

 * IAR Embedded Workbench for ARM (EWARM) toolchain **9.20.1** + ST-LINKV3, patch available [here](https://github.com/STMicroelectronics/STM32CubeC0/tree/main/Utilities/PC_Software/IDEs_Patches/EWARM)
 * [STM32CubeIDE **V2.1.0**](https://www.st.com/en/development-tools/stm32cubeide.html) + ST-LINKV3

## Dependencies

This package has been developed and tested using the list of components detailed in the table below.

Name                       |   Version
---------------------------|---------------
Cortex-M CMSIS             |   v5.9.0_fix_620_dsp_v1.10.0_nn_v3.1.0_no_doc
STM32C0xx CMSIS            |   V1.4.0
STM32C0xx HAL              |   V1.4.0
BSP STM32C0xx NUCLEO       |   V1.1.0
BSP Common                 |   V7.3.0
STM32 USB Device Library   |   V2.11.5
STM32 USB Host Library     |   V3.5.4

## How to use

This repository intrinsically contains the applications (projects and source files) located under folder `./Projects`. It also contains the CMSIS Core files under folder `./Drivers/CMSIS/Include` for size optimization reason. Other dependencies such as the HAL and BSP drivers, or the middleware libraries themselves are linked using the `git submodule` command. Please check the instructions below for a proper use.

---

#### *Note*

---

* To clone this repository along with the linked submodules, option `--recursive` has to be specified as shown below.

```
git clone --recursive https://github.com/STMicroelectronics/stm32c0-classic-coremw-apps.git
```

* To get the latest updates, issue the following **two** commands (with the repository `stm32c0-classic-coremw-apps` as the **current working directory**).

```
git pull
git submodule update --init --recursive
```

#### *Note*

 * If GitHub "Download ZIP" option is used instead of the `git clone` command, then the required components have to be collected manually by the user.

## Known Limitations

 * None

## Troubleshooting

Please refer to the [CONTRIBUTING.md](CONTRIBUTING.md) guide.
