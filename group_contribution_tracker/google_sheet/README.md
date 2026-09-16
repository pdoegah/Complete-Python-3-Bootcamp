# Google Sheet version of the ledger

The no-setup build. A spreadsheet with three tabs:

- **Ledger** – what members read: total collected, number of contributors,
  number of payments, and a by-member table. Every cell is a formula; the
  tab is protected so nothing can be typed into it.
- **Contributions** – what the two managers fill in: date, member name,
  amount in cedis, optional note. Yellow cells with blue text are the input
  cells. Names are matched case-insensitively, so "ama mensah" and
  "Ama Mensah" add up together.
- **How to use** – one-screen instructions for members and managers.

Access control is Google Drive sharing: the owner shares the file
"Anyone with the link: Viewer" and adds the two managers as Editors.

`build.py` generates `ledger.xlsx` with openpyxl (`MODE=test python3
build.py` adds sample rows for checking the formulas). Uploading the
`.xlsx` to Google Drive converts it to a Google Sheet; the formulas use only
INDEX, MATCH, COUNTIF, SUMIF and SUMPRODUCT, which convert cleanly. The
by-member table lists up to 60 distinct contributors.

Status: retired for this group in favour of the `webapp/` build (see the
folder README). No live copy is kept.
