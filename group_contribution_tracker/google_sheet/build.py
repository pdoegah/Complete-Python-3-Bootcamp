from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.formula import ArrayFormula

TITLE = "Funeral Contribution For Our Brother Emmanuel Papa Nii Quaye"
DESC = ("Contributions from the group towards the funeral of our brother Emmanuel Papa Nii Quaye. "
        "Every amount received is recorded here by the managers so that all members can see it.")
MANAGERS = "Charles Quaye"
CUR = '"GH₵"#,##0.00'
N = 2000          # contribution rows the formulas watch (rows 2..2000)
M = 60            # max distinct members shown on the Ledger tab

F = lambda **k: Font(name="Arial", **k)
GREEN = "1F6F50"; SOFT = "DCEFE5"; INK = "17231E"; MUTED = "7A8983"; LINE = "D3DCD7"; PAPER = "F4F7F5"
thin = Side(style="thin", color=LINE)
box = Border(bottom=thin)

wb = Workbook()

# ---------------- Ledger (what members read) ----------------
ws = wb.active
ws.title = "Ledger"
ws.sheet_view.showGridLines = False
for col, w in zip("ABCDE", [6, 34, 14, 18, 4]):
    ws.column_dimensions[col].width = w

ws.merge_cells("A1:D1")
ws["A1"] = "CHARLES: to record a payment, tap the 'Contributions' tab at the bottom of the screen. Do not type on this page."
ws["A1"].font = F(size=11, bold=True, color="6D4F05"); ws["A1"].fill = PatternFill("solid", fgColor="FBF0D3")
ws["A1"].alignment = Alignment(wrap_text=True, vertical="center"); ws.row_dimensions[1].height = 34
ws.merge_cells("A2:D2"); ws["A2"] = TITLE; ws["A2"].font = F(size=16, bold=True, color=INK)
ws["A2"].alignment = Alignment(wrap_text=True, vertical="top"); ws.row_dimensions[2].height = 44
ws.merge_cells("A3:D3"); ws["A3"] = DESC; ws["A3"].font = F(size=10, color="4D5C56")
ws["A3"].alignment = Alignment(wrap_text=True, vertical="top"); ws.row_dimensions[3].height = 46
ws.merge_cells("A4:D4"); ws["A4"] = f"Managed by {MANAGERS}. Members can view this sheet but not change it."
ws["A4"].font = F(size=10, color=MUTED)

# summary tiles
for c, label in zip("BCD", ["TOTAL COLLECTED", "CONTRIBUTORS", "ENTRIES"]):
    ws[f"{c}6"] = label; ws[f"{c}6"].font = F(size=9, bold=True, color=MUTED)
    ws[f"{c}6"].fill = PatternFill("solid", fgColor=PAPER)
ws["B7"] = "=SUM(Contributions!$C$2:$C$%d)" % N
ws["B7"].number_format = CUR; ws["B7"].font = F(size=18, bold=True, color=GREEN)
ws["C7"] = '=SUMPRODUCT((Contributions!$B$2:$B$%d<>"")/COUNTIF(Contributions!$B$2:$B$%d,Contributions!$B$2:$B$%d&""))' % (N, N, N)
ws["C7"].font = F(size=18, bold=True, color=INK); ws["C7"].number_format = "0"
ws["D7"] = "=COUNT(Contributions!$C$2:$C$%d)" % N
ws["D7"].font = F(size=18, bold=True, color=INK)
for c in "BCD":
    ws[f"{c}7"].fill = PatternFill("solid", fgColor=PAPER)
    ws[f"{c}7"].alignment = Alignment(vertical="center")
ws.row_dimensions[7].height = 30
ws["B8"] = "in Ghana cedis (GHS)"; ws["C8"] = "people who gave"; ws["D8"] = "payments recorded"
for c in "BCD":
    ws[f"{c}8"].font = F(size=9, color=MUTED); ws[f"{c}8"].fill = PatternFill("solid", fgColor=PAPER)

# by-member table
ws["A10"] = "BY MEMBER"; ws["A10"].font = F(size=9, bold=True, color=GREEN)
hdr = 11
for c, label in zip("ABCD", ["#", "Member", "Payments", "Total given"]):
    cell = ws[f"{c}{hdr}"]; cell.value = label
    cell.font = F(size=10, bold=True, color="FFFFFF"); cell.fill = PatternFill("solid", fgColor=GREEN)
    cell.alignment = Alignment(horizontal="right" if c in "CD" else "left", vertical="center")
ws.freeze_panes = f"A{hdr+1}"
first, last = hdr + 1, hdr + M
for i in range(M):
    r = first + i; k = i + 1
    ws[f"A{r}"] = f'=IF(B{r}="","",{k})'
    ws[f"B{r}"] = ArrayFormula(f"B{r}", f'=IFERROR(INDEX(Contributions!$B$2:$B${N},MATCH(1,(COUNTIF($B${hdr}:B{r-1},Contributions!$B$2:$B${N})=0)*(Contributions!$B$2:$B${N}<>""),0)),"")')
    ws[f"C{r}"] = f'=IF(B{r}="","",COUNTIF(Contributions!$B$2:$B${N},B{r}))'
    ws[f"D{r}"] = f'=IF(B{r}="","",SUMIF(Contributions!$B$2:$B${N},B{r},Contributions!$C$2:$C${N}))'
    ws[f"D{r}"].number_format = CUR
tot = last + 1
ws[f"B{tot}"] = f'=COUNTIF(B{first}:B{last},"?*")&" contributors"'
ws[f"C{tot}"] = f"=SUM(C{first}:C{last})"
ws[f"D{tot}"] = f"=SUM(D{first}:D{last})"; ws[f"D{tot}"].number_format = CUR
for c in "BCD":
    ws[f"{c}{tot}"].font = F(size=10, bold=True); ws[f"{c}{tot}"].border = Border(top=Side(style="medium", color=INK))
ws[f"C{tot}"].alignment = Alignment(horizontal="right"); ws[f"D{tot}"].alignment = Alignment(horizontal="right")
ws[f"A{tot+2}"] = "Every payment, in date order, is on the Contributions tab. Only the managers can add or change entries."
ws[f"A{tot+2}"].font = F(size=9, italic=True, color=MUTED)
ws.protection.sheet = True   # formulas only; nothing to type here

# ---------------- Contributions (what managers fill in) ----------------
cs = wb.create_sheet("Contributions")
heads = ["Date received", "Member name", "Amount (GHS)", "Note (optional)"]
widths = [14, 30, 15, 40]
for i, (h, w) in enumerate(zip(heads, widths), 1):
    c = cs.cell(row=1, column=i, value=h)
    c.font = F(size=10, bold=True, color="FFFFFF"); c.fill = PatternFill("solid", fgColor=GREEN)
    c.alignment = Alignment(vertical="center")
    cs.column_dimensions[get_column_letter(i)].width = w
cs.column_dimensions["A"].number_format = "d mmm yyyy"
cs.column_dimensions["C"].number_format = CUR
cs.row_dimensions[1].height = 24
cs.freeze_panes = "A2"
input_fill = PatternFill("solid", fgColor="FFFDE7")
for r in range(2, 62):
    cs[f"A{r}"].number_format = "d mmm yyyy"
    cs[f"C{r}"].number_format = CUR
    for c in "ABCD":
        cs[f"{c}{r}"].font = F(size=10, color="0000FF"); cs[f"{c}{r}"].fill = input_fill
# sample rows: only in the test build, used to verify the formulas after upload
import os, datetime
MODE = os.environ.get("MODE", "final")
if MODE == "final" and os.environ.get("PREFILL"):
    for i, line in enumerate(os.environ["PREFILL"].split(";"), 2):
        d, n, a, note = line.split("|")
        cs.cell(row=i, column=1, value=datetime.date.fromisoformat(d)); cs.cell(row=i, column=2, value=n)
        cs.cell(row=i, column=3, value=float(a)); cs.cell(row=i, column=4, value=note)
if MODE == "test":
    rows = [(datetime.date(2026,9,2),"Amina Yusuf",200,"Bank transfer"),(datetime.date(2026,9,3),"Kwame Mensah",150.5,"Cash"),
            (datetime.date(2026,9,5),"Priya Raman",300,""),(datetime.date(2026,9,10),"amina yusuf",100,"USD 8 via MoMo"),
            (datetime.date(2026,9,12),"Kwame Mensah",50,"")]
    for i, row in enumerate(rows, 2):
        for j, v in enumerate(row, 1):
            cs.cell(row=i, column=j, value=v)
# validation
dv_date = DataValidation(type="date", operator="greaterThan", formula1="DATE(2020,1,1)", allow_blank=True,
                         showErrorMessage=True, errorTitle="Date", error="Type the date the money was received, e.g. 16/09/2026.")
dv_amt = DataValidation(type="decimal", operator="greaterThan", formula1="0", allow_blank=True,
                        showErrorMessage=True, errorTitle="Amount", error="Type the amount in cedis as a number, e.g. 150 or 150.50.")
cs.add_data_validation(dv_date); dv_date.add("A2:A2000")
cs.add_data_validation(dv_amt); dv_amt.add("C2:C2000")

# ---------------- Instructions ----------------
hs = wb.create_sheet("How to use")
hs.column_dimensions["A"].width = 100
lines = [
    ("How this ledger works", True),
    ("", False),
    ("MEMBERS: open the Ledger tab. It shows the total collected, how many people have given, and each person's total. Nothing on it can be typed into.", False),
    ("", False),
    ("MANAGER (Charles Quaye): open the Contributions tab and type one row per payment received:", False),
    ("   1. Date received – the day the money arrived.", False),
    ("   2. Member name – type the name the same way each time so the person's payments add up together (e.g. always 'Ama Mensah', not sometimes 'Ama').", False),
    ("   3. Amount (GHS) – the amount in cedis, numbers only.", False),
    ("   4. Note – optional. For money from abroad, put the original amount here, e.g. 'USD 50 via Western Union'.", False),
    ("The Ledger tab updates itself the moment a row is saved.", False),
    ("", False),
    ("The yellow cells with blue text are the ones to type in. Start on row 2, directly under the headings.", False),
    ("To correct a mistake, edit the row. To remove a payment, clear the whole row.", False),
    ("The Ledger tab lists up to 60 different contributors; payments themselves are unlimited.", False),
]
for i, (t, b) in enumerate(lines, 1):
    c = hs.cell(row=i, column=1, value=t); c.font = F(size=12 if b else 10, bold=b); c.alignment = Alignment(wrap_text=True)

if MODE == "test":
    del wb["How to use"]
wb.save("ledger-%s.xlsx" % MODE)
print("built")
