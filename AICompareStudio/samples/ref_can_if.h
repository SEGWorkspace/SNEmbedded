#ifndef CAN_IF_H
#define CAN_IF_H
#include <stdint.h>
#include "Std_Types.h"

#define CANIF_MAX_PDUS      32u
#define CANIF_TX_TIMEOUT_MS 10u
#define CANIF_VERSION       0x0102u

typedef struct {
    uint32_t id;
    uint8_t  dlc;
    uint8_t  data[8];
} CanIf_FrameType;

typedef enum { CANIF_OFFLINE = 0, CANIF_ONLINE = 1 } CanIf_ModeType;

Std_ReturnType CanIf_Transmit(uint16_t pduId, const CanIf_FrameType *frame);
void CanIf_Init(void);
#endif
