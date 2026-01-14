import io
import pandas as pd


def _col_letter(n: int) -> str:
    """1-indexed -> Excel column letter"""
    out = ""
    while n > 0:
        n, r = divmod(n - 1, 26)
        out = chr(65 + r) + out
    return out


def to_xlsx_bytes(df: pd.DataFrame) -> bytes:
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="결과")
        ws = writer.sheets["결과"]
        for i, col in enumerate(df.columns, start=1):
            # Width based on header + first 200 rows
            max_len = max([len(str(col))] + [len(str(x)) for x in df[col].astype(str).head(200)])
            ws.column_dimensions[_col_letter(i)].width = min(max(10, max_len + 2), 60)
    return output.getvalue()
