# AI Compare Studio

A desktop file-comparison tool with a built-in **AI agent** (Claude). It compares a **reference** file with a
**target** file and produces a human-readable report of the differences, both in the app and as a self-contained
**HTML report** with tables and descriptions. The interface uses a black, grey and gold theme.

| Format | Extensions | What gets compared |
|---|---|---|
| AUTOSAR | `.arxml` | Elements matched by their SHORT-NAME path, renames, added/removed elements, and each changed property (LENGTH, INIT-VALUE, START-POSITION, references…) |
| C / C++ | `.c .h .cpp .cc .cxx .hpp .hh .hxx` | Symbol by symbol: functions, prototypes, macros, structs/enums/unions/classes, typedefs, globals, includes. Signature changes, logic changes and comment-only changes are reported separately |
| Excel / CSV | `.xlsx .xlsm .xls .csv .tsv` | Sheet by sheet, **column by column using the column's meaning**, rows matched by key column |
| Word | `.docx` | Paragraphs (located by heading) and Word tables (as tables) |
| PDF | `.pdf` | Text by page and line, plus detected tables (as tables) |
| Notes / text | `.txt .md .log .note .ini .cfg .json .xml .yaml` | Line and paragraph text, with word-level highlighting |

## How the AI agent works

```
 Reference ─┐                         ┌─────────── AI agent (Claude, tool use) ───────────┐
            ├─► Parsers ─► Parsed ───►│ Phase 1  read reference column headings, profile  │
 Target ────┘              model      │          values, infer meaning, map to target     │
                                      │          columns (even renamed), pick key columns │
                                      └───────────────┬───────────────────────────────────┘
                                                      ▼
                                      Deterministic diff engine (exact, repeatable)
                                                      ▼
                                      │ Phase 2  describe every difference + impact       │
                                      │ Phase 3  investigate with tools, write summary    │
                                                      ▼
                                      GUI tables  +  HTML report
```

* **Phase 1 – understand and map columns.** The agent calls read-only tools (`list_tables`, `profile_column`,
  `compare_column_values`) to read every reference column heading and its values and work out what the column
  means. It then finds the target column with the same meaning, even if that column was renamed (for example
  `Factor` → `Scaling`) or moved. It also picks the key column (such as *Signal Name*) so rows are matched by
  identity, not by position.
* **Diff engine.** The comparison itself is deterministic. The AI cannot invent a difference or hide one.
* **Phase 2 – explain.** Each difference is rewritten in plain language: what changed, the old and new values,
  and why it matters (interface/ABI, timing, scaling, memory layout, safety, or documentation only). Each one
  gets an impact rating of High, Medium, Low or Info.
* **Phase 3 – summarize.** The agent looks into the differences (`get_diff_statistics`, `get_diff_items`,
  `get_code_symbol`, `get_arxml_element`, `search_document`) and writes an executive summary, key findings and
  an overall risk rating.

**No API key?** The tool still works. A rule-based engine handles column meaning, fuzzy and semantic column
matching, impact rules and descriptions. The AI agent makes the column understanding and the explanations better.

The agent uses the official Anthropic Python SDK with the `claude-opus-5-5` model by default. You can choose the
model and effort in the GUI. Tool inputs use strict schemas, answers come back as structured JSON output, and the
server-side refusal fallback is turned on for models that support it.

## Install and run

Requires Python 3.10 or newer.

**Windows:** double-click `run_windows.bat`. The first run creates a `.venv` and installs the dependencies.

**Linux/macOS:** `./run.sh`

**Manual setup:**
```bash
pip install -r requirements.txt
python -m ai_compare            # GUI
```

### Enable the AI agent
To turn on the agent, either set the environment variable `ANTHROPIC_API_KEY` or paste a key into the
*API key* field in the GUI. Tick *Remember key* to store it in your user settings.

## Using the GUI

1. Drop or browse the **Reference** file (the baseline) and the **Target** file (the new version). You can also
   drop two files onto the window at once.
2. Press **COMPARE** (or Ctrl+Enter). The *Agent Log* tab shows the agent's tool calls as they happen.
3. Look at the results in these tabs:
   * **Summary**: counts, overall risk, executive summary and key findings
   * **Differences**: a table you can search, filter (by impact, change type or category) and sort. Double-click
     a row to see a side-by-side value comparison and the code diff
   * **Column Mapping**: each reference column, the meaning the agent understood, the matching target column,
     how it was matched, the confidence, and the key column
   * **Line View**: side-by-side changed lines
   * **HTML Report**: a live preview of the report
4. Use **Export HTML** to save the report, or **Open in browser** to view it.

## Command line (headless / CI)

```bash
python -m ai_compare cli ref.arxml tgt.arxml -o report.html
python -m ai_compare cli ref.xlsx  tgt.xlsx  --no-ai          # rule-based only
python -m ai_compare cli ref.c     tgt.c     --model claude-opus-5-5 --effort high
```

## Demo files and tests

```bash
python samples/make_samples.py      # regenerates ref_*/tgt_* pairs for every format
python -m pytest tests -q           # engine tests + a mocked agent run (no API key needed)
```

## Build a standalone .exe (optional)

```bash
pip install pyinstaller
pyinstaller --noconsole --name AICompareStudio --collect-all PySide6 -p . ai_compare/__main__.py
```

## Project layout

```
ai_compare/
  parsers/        tabular.py (Excel/CSV) · documents.py (Word/PDF/text) · code.py (C/C++) · arxml.py
  diff_engine.py  deterministic comparison, heuristic column meaning/mapping, impact rules
  ai_agent.py     Claude agent: tool loop, column mapping, descriptions, summary
  comparator.py   pipeline orchestration (parse → AI map → diff → AI explain → summary)
  report.py       HTML report (black / grey / gold)
  gui.py          PySide6 desktop app
  cli.py          command line interface
```

## Notes and limits
* Legacy `.doc` and `.xls` with macros: save them as `.docx` / `.xlsx`. (`.xls` data is supported through xlrd.)
* Scanned PDFs (images only) have no text to extract, so they need OCR first.
* The C/C++ parser is a fast structural parser, not a compiler. Heavy macro-generated code may be reported at
  block level.
* When the AI agent is on, file content is sent to the Anthropic API. Only use it with data you are allowed to
  share.
