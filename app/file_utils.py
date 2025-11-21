import os
import pandas as pd
import pdfplumber
from typing import List, Dict, Any
from pathlib import Path
from PIL import Image
import pytesseract

def read_csv(path: str) -> pd.DataFrame:
    return pd.read_csv(path)

def read_excel(path: str) -> pd.DataFrame:
    # returns first sheet by default
    return pd.read_excel(path)

def read_pdf_tables(path: str) -> List[pd.DataFrame]:
    """
    Extract tables from PDF using pdfplumber. Return list of dataframes (all pages).
    """
    dfs = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            for table in tables:
                # convert table (list of lists) to DataFrame
                if not table:
                    continue
                df = pd.DataFrame(table[1:], columns=table[0])
                dfs.append(df)
    return dfs

def extract_text_from_pdf(path: str) -> str:
    text = ""
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            text += page.extract_text() or ""
    return text

def ocr_image(path: str) -> str:
    img = Image.open(path)
    text = pytesseract.image_to_string(img)
    return text

def find_best_dataframe(files: List[str]):
    """
    Heuristic: among downloaded files, return the most promising DataFrame for operations.
    """
    for f in files:
        ext = Path(f).suffix.lower()
        try:
            if ext == ".csv":
                return read_csv(f)
            elif ext in (".xlsx", ".xls"):
                return read_excel(f)
            elif ext == ".pdf":
                tables = read_pdf_tables(f)
                if tables:
                    # return concatenated first table
                    return pd.concat(tables, ignore_index=True)
        except Exception as e:
            print("file parse error", f, e)
    return None
