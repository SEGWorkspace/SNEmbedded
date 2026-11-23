#include "CanIf.h"

static uint8_t canif_initialised = 0u;
static CanIf_ModeType canif_mode = CANIF_OFFLINE;
static uint32_t canif_tx_errors = 0u;

void CanIf_Init(const void *config)
{
    (void)config;
    canif_initialised = 1u;
    canif_mode = CANIF_ONLINE;
    canif_tx_errors = 0u;
}

/* Transmit a frame (classic CAN or CAN FD) */
Std_ReturnType CanIf_Transmit(PduIdType pduId, const CanIf_FrameType *frame)
{
    if ((canif_initialised == 0u) || (frame == NULL)) {
        canif_tx_errors++;
        return E_NOT_OK;
    }
    if (pduId >= CANIF_MAX_PDUS) {
        return E_NOT_OK;
    }
    return Can_Write(pduId, frame);
}

uint8_t CanIf_GetMode(void)
{
    /* return current controller mode */
    return (uint8_t)canif_mode;
}

uint32_t CanIf_GetTxErrorCount(void)
{
    return canif_tx_errors;
}
