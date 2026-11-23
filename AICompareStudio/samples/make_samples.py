"""Generate demo reference/target file pairs for every supported format.

    python samples/make_samples.py
"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))


def w(name, text):
    with open(os.path.join(HERE, name), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


# ---------------------------------------------------------------- C / header
w("ref_can_if.h", """#ifndef CAN_IF_H
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
""")
w("tgt_can_if.h", """#ifndef CAN_IF_H
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
""")
w("ref_can_if.c", """#include "CanIf.h"

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
""")
w("tgt_can_if.c", """#include "CanIf.h"

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
""")

# ---------------------------------------------------------------- C++
w("ref_scheduler.cpp", """#include <vector>
#include "Task.hpp"

namespace os {

class Scheduler {
public:
    void addTask(Task* t) { tasks_.push_back(t); }
private:
    std::vector<Task*> tasks_;
};

int tickPeriodMs() { return 10; }

void Scheduler_Run(Scheduler& s, int cycles)
{
    for (int i = 0; i < cycles; ++i) {
        // run all tasks
    }
}

} // namespace os
""")
w("tgt_scheduler.cpp", """#include <vector>
#include <cstdint>
#include "Task.hpp"

namespace os {

class Scheduler {
public:
    void addTask(Task* t) { tasks_.push_back(t); }
    std::size_t taskCount() const { return tasks_.size(); }
private:
    std::vector<Task*> tasks_;
};

int tickPeriodMs() { return 5; }

void Scheduler_Run(Scheduler& s, uint32_t cycles, bool watchdog)
{
    for (uint32_t i = 0; i < cycles; ++i) {
        // run all tasks
        if (watchdog) { /* kick */ }
    }
}

} // namespace os
""")

# ---------------------------------------------------------------- ARXML
ARX = """<?xml version="1.0" encoding="UTF-8"?>
<AUTOSAR xmlns="http://autosar.org/schema/r4.0" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
 xsi:schemaLocation="http://autosar.org/schema/r4.0 {schema}">
  <AR-PACKAGES>
    <AR-PACKAGE>
      <SHORT-NAME>Signals</SHORT-NAME>
      <ELEMENTS>
        <I-SIGNAL>
          <SHORT-NAME>EngineSpeed</SHORT-NAME>
          <DATA-TYPE-POLICY>LEGACY</DATA-TYPE-POLICY>
          <INIT-VALUE><NUMERICAL-VALUE-SPECIFICATION><VALUE>{init}</VALUE></NUMERICAL-VALUE-SPECIFICATION></INIT-VALUE>
          <LENGTH>16</LENGTH>
          <SYSTEM-SIGNAL-REF DEST="SYSTEM-SIGNAL">/SystemSignals/EngineSpeed</SYSTEM-SIGNAL-REF>
        </I-SIGNAL>
        <I-SIGNAL>
          <SHORT-NAME>{coolant}</SHORT-NAME>
          <LENGTH>8</LENGTH>
          <SYSTEM-SIGNAL-REF DEST="SYSTEM-SIGNAL">/SystemSignals/CoolantTemp</SYSTEM-SIGNAL-REF>
        </I-SIGNAL>
        <I-SIGNAL>
          <SHORT-NAME>VehicleSpeed</SHORT-NAME>
          <LENGTH>{vlen}</LENGTH>
          <SYSTEM-SIGNAL-REF DEST="SYSTEM-SIGNAL">/SystemSignals/VehicleSpeed</SYSTEM-SIGNAL-REF>
        </I-SIGNAL>
{extra}
      </ELEMENTS>
    </AR-PACKAGE>
    <AR-PACKAGE>
      <SHORT-NAME>Pdus</SHORT-NAME>
      <ELEMENTS>
        <I-SIGNAL-I-PDU>
          <SHORT-NAME>EngineData_Pdu</SHORT-NAME>
          <LENGTH>8</LENGTH>
          <I-SIGNAL-TO-PDU-MAPPINGS>
            <I-SIGNAL-TO-I-PDU-MAPPING>
              <SHORT-NAME>EngineSpeed_Map</SHORT-NAME>
              <I-SIGNAL-REF DEST="I-SIGNAL">/Signals/EngineSpeed</I-SIGNAL-REF>
              <PACKING-BYTE-ORDER>{order}</PACKING-BYTE-ORDER>
              <START-POSITION>{start}</START-POSITION>
            </I-SIGNAL-TO-I-PDU-MAPPING>
          </I-SIGNAL-TO-PDU-MAPPINGS>
          <I-PDU-TIMING-SPECIFICATIONS><I-PDU-TIMING><TRANSMISSION-MODE-DECLARATION><TRANSMISSION-MODE-TRUE-TIMING>
            <CYCLIC-TIMING><TIME-PERIOD><VALUE>{period}</VALUE></TIME-PERIOD></CYCLIC-TIMING>
          </TRANSMISSION-MODE-TRUE-TIMING></TRANSMISSION-MODE-DECLARATION></I-PDU-TIMING></I-PDU-TIMING-SPECIFICATIONS>
        </I-SIGNAL-I-PDU>
      </ELEMENTS>
    </AR-PACKAGE>
  </AR-PACKAGES>
</AUTOSAR>
"""
w("ref_com.arxml", ARX.format(schema="AUTOSAR_4-2-2.xsd", init="0", coolant="CoolantTemp", vlen="12", extra="",
                              order="MOST-SIGNIFICANT-BYTE-LAST", start="0", period="0.01"))
w("tgt_com.arxml", ARX.format(schema="AUTOSAR_00049.xsd", init="800", coolant="CoolantTemperature", vlen="16",
                              extra="""        <I-SIGNAL>
          <SHORT-NAME>GearPosition</SHORT-NAME>
          <LENGTH>4</LENGTH>
          <SYSTEM-SIGNAL-REF DEST="SYSTEM-SIGNAL">/SystemSignals/GearPosition</SYSTEM-SIGNAL-REF>
        </I-SIGNAL>""", order="MOST-SIGNIFICANT-BYTE-FIRST", start="8", period="0.02"))

# ---------------------------------------------------------------- notes
w("ref_notes.txt", """Release notes – Body Controller SW 1.4
The door lock shall engage when vehicle speed exceeds 15 km/h.
Interior light timeout is 30 seconds.
Diagnostics session timeout: 5000 ms.
Known issue: LIN wake-up may take up to 200 ms.
Contact: integration team.
""")
w("tgt_notes.txt", """Release notes – Body Controller SW 1.5
The door lock shall engage when vehicle speed exceeds 10 km/h.
Interior light timeout is 30 seconds.
Diagnostics session timeout: 5000 ms.
New: automatic unlock after crash detection.
Contact: integration team.
""")

# ---------------------------------------------------------------- Excel
try:
    import openpyxl
    def book(path, headers, rows, extra_sheet=None):
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Signals"
        ws.append(["CAN signal database"])          # title row – header detection must skip it
        ws.append(headers)
        for r in rows:
            ws.append(r)
        if extra_sheet:
            ws2 = wb.create_sheet(extra_sheet[0])
            for r in extra_sheet[1]:
                ws2.append(r)
        wb.save(os.path.join(HERE, path))
    book("ref_signals.xlsx",
         ["Signal Name", "Message ID", "Start Bit", "Length", "Factor", "Unit", "Description"],
         [["EngineSpeed", "0x100", 0, 16, 0.25, "rpm", "Engine speed"],
          ["CoolantTemp", "0x100", 16, 8, 1, "degC", "Coolant temperature"],
          ["VehicleSpeed", "0x200", 0, 12, 0.1, "km/h", "Vehicle speed"],
          ["BrakePressed", "0x200", 12, 1, 1, "", "Brake pedal switch"],
          ["FuelLevel", "0x300", 0, 8, 0.5, "%", "Fuel level"]],
         ("Nodes", [["Node", "Role"], ["ECM", "Sender"], ["BCM", "Receiver"]]))
    book("tgt_signals.xlsx",
         ["Signal", "CAN ID", "Start Bit", "Bit Length", "Scaling", "Unit", "Comment", "Cycle Time (ms)"],
         [["EngineSpeed", "0x100", 0, 16, 0.125, "rpm", "Engine speed", 10],
          ["CoolantTemp", "0x101", 16, 8, 1, "°C", "Coolant temperature", 100],
          ["VehicleSpeed", "0x200", 0, 16, 0.1, "km/h", "Vehicle speed (filtered)", 20],
          ["FuelLevel", "0x300", 0, 8, 0.5, "%", "Fuel level", 1000],
          ["GearPosition", "0x300", 8, 4, 1, "", "Selected gear", 50]])
except ImportError:
    print("openpyxl not installed – skipping Excel samples")

# ---------------------------------------------------------------- Word
try:
    import docx
    def word(path, version, speed, extra, rows):
        d = docx.Document()
        d.add_heading(f"Software Requirements Specification v{version}", 0)
        d.add_heading("1 Door locking", 1)
        d.add_paragraph(f"REQ-001: The doors shall lock automatically above {speed} km/h.")
        d.add_paragraph("REQ-002: The driver can unlock all doors with the central switch.")
        if extra:
            d.add_paragraph(extra)
        d.add_heading("2 Parameters", 1)
        t = d.add_table(rows=1, cols=3)
        for i, h in enumerate(["Parameter", "Value", "Unit"]):
            t.rows[0].cells[i].text = h
        for r in rows:
            cells = t.add_row().cells
            for i, v in enumerate(r):
                cells[i].text = v
        d.save(os.path.join(HERE, path))
    word("ref_spec.docx", "1.0", "15", "", [["LockSpeed", "15", "km/h"], ["LightTimeout", "30", "s"]])
    word("tgt_spec.docx", "1.1", "10", "REQ-003: Doors shall unlock automatically after a crash event.",
         [["LockSpeed", "10", "km/h"], ["LightTimeout", "30", "s"], ["CrashUnlockDelay", "200", "ms"]])
except ImportError:
    print("python-docx not installed – skipping Word samples")

print("Samples written to", HERE)

# ---------------------------------------------------------------- PDF
try:
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Table as RLTable, Spacer
    from reportlab.lib.styles import getSampleStyleSheet

    def pdf(path, version, timeout, rows):
        st = getSampleStyleSheet()
        story = [Paragraph(f"ECU Test Report – build {version}", st["Title"]),
                 Paragraph(f"Wake-up timeout measured at {timeout} ms.", st["Normal"]),
                 Paragraph("All bus-off recovery tests passed.", st["Normal"]), Spacer(1, 12),
                 RLTable([["Test case", "Result", "Duration (s)"]] + rows, style=[("GRID", (0, 0), (-1, -1), 0.5, "black")])]
        SimpleDocTemplate(os.path.join(HERE, path), pagesize=A4).build(story)
    pdf("ref_report.pdf", "1.4.0", "180", [["TC_001 Wakeup", "PASS", "2.1"], ["TC_002 BusOff", "PASS", "5.0"],
                                            ["TC_003 Sleep", "FAIL", "3.2"]])
    pdf("tgt_report.pdf", "1.5.0", "210", [["TC_001 Wakeup", "PASS", "2.3"], ["TC_002 BusOff", "PASS", "5.0"],
                                            ["TC_003 Sleep", "PASS", "3.0"], ["TC_004 CrashUnlock", "PASS", "1.2"]])
except ImportError:
    print("reportlab not installed – skipping PDF samples")
