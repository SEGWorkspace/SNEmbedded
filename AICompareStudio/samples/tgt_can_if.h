#ifndef CAN_IF_H
#define CAN_IF_H
#include <stdint.h>
#include "Std_Types.h"
#include "ComStack_Types.h"

#define CANIF_MAX_PDUS      64u
#define CANIF_TX_TIMEOUT_MS 10u   /* unchanged, comment added */
#define CANIF_VERSION       0x0200u
#define CANIF_FD_SUPPORT    STD_ON

typedef struct {
    uint32_t id;
    uint8_t  dlc;
    uint8_t  data[64];   /* CAN FD */
    uint8_t  isFd;
} CanIf_FrameType;

typedef enum { CANIF_OFFLINE = 0, CANIF_ONLINE = 1, CANIF_TX_OFFLINE = 2 } CanIf_ModeType;

Std_ReturnType CanIf_Transmit(PduIdType pduId, const CanIf_FrameType *frame);
void CanIf_Init(const void *config);
#endif
