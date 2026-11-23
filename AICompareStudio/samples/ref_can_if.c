#include "CanIf.h"

static uint8_t canif_initialised = 0u;
static CanIf_ModeType canif_mode = CANIF_OFFLINE;

void CanIf_Init(void)
{
    canif_initialised = 1u;
    canif_mode = CANIF_ONLINE;
}

/* Transmit a frame */
Std_ReturnType CanIf_Transmit(uint16_t pduId, const CanIf_FrameType *frame)
{
    if ((canif_initialised == 0u) || (frame == NULL)) {
        return E_NOT_OK;
    }
    if (pduId >= CANIF_MAX_PDUS) {
        return E_NOT_OK;
    }
    return Can_Write(pduId, frame);
}

static void CanIf_ClearBuffers(void)
{
    /* nothing yet */
}

uint8_t CanIf_GetMode(void)
{
    return (uint8_t)canif_mode;
}
