#ifndef __SX1281_CONFIG_H
#define __SX1281_CONFIG_H

#include <stdint.h>
#include "sx1280.h"

/*
 * E28-2G4M12SX / SX1281 LoRa configuration.
 * ThirdParty/SX1280lib is still used because Semtech's SX1280/SX1281 command set
 * is compatible in this project.
 */

//启动LoRa硬件配置程序
#define LORA_RF_FREQUENCY_HZ            2473000000UL
#define LORA_TX_OUTPUT_POWER_DBM        12
#define LORA_MAX_PAYLOAD_LEN            64U

#define LORA_TX_QUEUE_DEPTH             8U
#define LORA_RX_QUEUE_DEPTH             8U

#define LORA_PROFILE_RANGE_1K           0
#define LORA_PROFILE_2K                 1
#define LORA_PROFILE_4K                 2
#define LORA_PROFILE_6K                 3
#define LORA_PROFILE_500M_5HZ           4
#define LORA_PROFILE_FLIGHT_500M_5HZ    5

/*
 * Default profile:
 * 500 m target, 5 Hz AIR_FLIGHT_STATE, explicit header and LoRa CRC enabled.
 */
#define LORA_LINK_PROFILE               LORA_PROFILE_FLIGHT_500M_5HZ

#if (LORA_LINK_PROFILE == LORA_PROFILE_RANGE_1K)
#define LORA_CFG_SF                     LORA_SF11
#define LORA_CFG_BW                     LORA_BW_0200
#define LORA_CFG_CR                     LORA_CR_4_5
#define LORA_TX_TIMEOUT_COUNT           3000U

#elif (LORA_LINK_PROFILE == LORA_PROFILE_2K)
#define LORA_CFG_SF                     LORA_SF10
#define LORA_CFG_BW                     LORA_BW_0200
#define LORA_CFG_CR                     LORA_CR_4_5
#define LORA_TX_TIMEOUT_COUNT           2000U

#elif (LORA_LINK_PROFILE == LORA_PROFILE_4K)
#define LORA_CFG_SF                     LORA_SF9
#define LORA_CFG_BW                     LORA_BW_0200
#define LORA_CFG_CR                     LORA_CR_4_5
#define LORA_TX_TIMEOUT_COUNT           1500U

#elif (LORA_LINK_PROFILE == LORA_PROFILE_6K)
#define LORA_CFG_SF                     LORA_SF8
#define LORA_CFG_BW                     LORA_BW_0200
#define LORA_CFG_CR                     LORA_CR_4_5
#define LORA_TX_TIMEOUT_COUNT           1000U

#elif (LORA_LINK_PROFILE == LORA_PROFILE_500M_5HZ)
#define LORA_CFG_SF                     LORA_SF8
#define LORA_CFG_BW                     LORA_BW_0400
#define LORA_CFG_CR                     LORA_CR_4_5
#define LORA_TX_TIMEOUT_COUNT           800U

#elif (LORA_LINK_PROFILE == LORA_PROFILE_FLIGHT_500M_5HZ)
#define LORA_CFG_SF                     LORA_SF10
#define LORA_CFG_BW                     LORA_BW_0800
#define LORA_CFG_CR                     LORA_CR_4_5
#define LORA_TX_TIMEOUT_COUNT           800U

#else
#error "Invalid LORA_LINK_PROFILE"
#endif /* LORA_LINK_PROFILE */

#define LORA_CFG_PREAMBLE_SYMBOLS       16U
#define LORA_CFG_PREAMBLE_LEN           0x18U
#define LORA_CFG_HEADER_TYPE            LORA_PACKET_VARIABLE_LENGTH
#define LORA_CFG_CRC_MODE               LORA_CRC_ON
#define LORA_CFG_IQ_MODE                LORA_IQ_NORMAL

#if (LORA_CFG_PREAMBLE_SYMBOLS == 16U) && (LORA_CFG_PREAMBLE_LEN != 0x18U)
#error "SX1280 LoRa preamble 16 symbols must use encoded value 0x18, not 16U"
#endif /* __SX1281_CONFIG_H */

#define LORA_RX_IRQ_MASK                ( IRQ_RX_DONE | IRQ_RX_TX_TIMEOUT | IRQ_CRC_ERROR | IRQ_HEADER_ERROR )
#define LORA_TX_IRQ_MASK                ( IRQ_TX_DONE | IRQ_RX_TX_TIMEOUT )

#define LORA_TX_TIMEOUT_STEP            RADIO_TICK_SIZE_1000_US
#define LORA_SPI_TIMEOUT_MS             20U
#define LORA_BUSY_TIMEOUT_MS            100U
#define LORA_REMOTE_ONLINE_TIMEOUT_MS   3000U

#endif
