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
#define LORA_TX_NORMAL_QUEUE_DEPTH      2U
#define LORA_TX_CONTROL_QUEUE_DEPTH     6U
#define LORA_TX_CONTROL_BURST_MAX       2U
#define LORA_RX_QUEUE_DEPTH             8U

/* Owner-task scheduling policy: preserve a receive opportunity between TXs.
 * This interval bounds software starvation; RF airtime/collisions still need
 * verification for the selected PHY and host retry schedule. */
#define LORA_RX_DWELL_MS                120U
/* Four milliseconds: clock quantization plus two owner-loop observations.
 * Not a hardware WCET claim; selected PHY airtime is computed separately. */
#define LORA_RX_TURN_MARGIN_MS          4U

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

#ifdef SILVERSTAR_AIR_LINK_ENABLED
#include "air_link_config.h"
#undef LORA_RF_FREQUENCY_HZ
#undef LORA_TX_OUTPUT_POWER_DBM
#undef LORA_CFG_SF
#undef LORA_CFG_BW
#undef LORA_CFG_CR
#undef LORA_CFG_PREAMBLE_SYMBOLS
#undef LORA_CFG_PREAMBLE_LEN
#undef LORA_CFG_HEADER_TYPE
#undef LORA_CFG_CRC_MODE
#undef LORA_CFG_IQ_MODE
#define LORA_RF_FREQUENCY_HZ            AIR_LINK_FREQUENCY_HZ
#define LORA_TX_OUTPUT_POWER_DBM        AIR_LINK_TX_POWER_DBM
#define LORA_CFG_SF                     AIR_LINK_SX128X_SF
#define LORA_CFG_BW                     AIR_LINK_SX128X_BW
#define LORA_CFG_CR                     AIR_LINK_SX128X_CR
#define LORA_CFG_PREAMBLE_SYMBOLS       AIR_LINK_PREAMBLE_SYMBOLS
#define LORA_CFG_PREAMBLE_LEN           AIR_LINK_SX128X_PREAMBLE_ENCODED
#define LORA_CFG_HEADER_TYPE            AIR_LINK_SX128X_HEADER
#define LORA_CFG_CRC_MODE               AIR_LINK_SX128X_CRC
#define LORA_CFG_IQ_MODE                AIR_LINK_SX128X_IQ
#endif

#if (LORA_CFG_PREAMBLE_SYMBOLS == 16U) && (LORA_CFG_PREAMBLE_LEN != 0x18U)
#error "SX1280 LoRa preamble 16 symbols must use encoded value 0x18, not 16U"
#endif

#define LORA_RX_IRQ_MASK                ( IRQ_RX_DONE | IRQ_RX_TX_TIMEOUT | IRQ_CRC_ERROR | IRQ_HEADER_ERROR | IRQ_PREAMBLE_DETECTED | IRQ_HEADER_VALID )
#define LORA_TX_IRQ_MASK                ( IRQ_TX_DONE | IRQ_RX_TX_TIMEOUT )

#define LORA_TX_TIMEOUT_STEP            RADIO_TICK_SIZE_1000_US
#define LORA_SPI_TIMEOUT_MS             20U
#define LORA_BUSY_TIMEOUT_MS            100U
#define LORA_REMOTE_ONLINE_TIMEOUT_MS   3000U

#ifdef AIR_LINK_INSTANCE_TX_POWER_DBM
#define LORA_INSTANCE_TX_POWER_DBM(instance) AIR_LINK_INSTANCE_TX_POWER_DBM(instance)
#else
#define LORA_INSTANCE_TX_POWER_DBM(instance) LORA_TX_OUTPUT_POWER_DBM
#endif

#endif
