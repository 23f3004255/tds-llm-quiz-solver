import time
import json
import re
import requests
from typing import List
from app.browser_utils import fetch_page_rendered_html, find_submit_and_question_from_html, download_links_from_page
from app.file_utils import find_best_dataframe, extract_text_from_pdf, read_csv, read_excel
from app.llm_client import call_llm
from urllib.parse import urljoin

def solve_quiz_entrypoint(email: str, secret: str, start_url: str, max_seconds: int = 180):
    """
    Top-level blocking entrypoint called by main. Returns a summary dict.
    """
    start_time = time.time()
    current_url = start_url
    steps = []
    while True:
        elapsed = time.time() - start_time
        if elapsed > max_seconds:
            return {"status": "timeout", "steps": steps}

        # fetch fully rendered HTML
        print("fetching html")
        html, final_url = fetch_page_rendered_html(current_url)
        print(html,final_url)
        submit_url, question_text = find_submit_and_question_from_html(html)
        # fallback heuristics
        if not question_text:
            # ask LLM to summarize page content
            summary = call_llm("You are a helpful assistant.", f"Summarize the important parts of this HTML page:\n\n{html[:2000]}")["text"]
            question_text = summary

        # download candidate files
        files = download_links_from_page(final_url, html)

        # Ask LLM how to solve the question and what the expected answer format is
        system_prompt = "You are an expert data analyst. Provide a short plan of steps (1-5) to retrieve and compute the answer, mention required files if any, and provide the final expected answer type."
        llm_input = f"QUESTION: {question_text}\nFILES: {files}\nHTML_SNIPPET: {html[:2000]}"
        plan_resp = call_llm(system_prompt, llm_input, max_tokens=800)
        plan_text = plan_resp["text"]

        # Heuristic attempt: try to find a dataframe and compute simple aggregates
        df = None
        if files:
            df = find_best_dataframe(files)
        # If no DF but a PDF has textual table, extract text and try to parse numbers
        if df is None:
            for f in files:
                if f.lower().endswith(".pdf"):
                    txt = extract_text_from_pdf(f)
                    # naive numeric search
                    nums = re.findall(r"[-+]?\d*\.\d+|\d+", txt.replace(',', ''))
                    if nums:
                        # send to LLM to ask which aggregation is required
                        agg_q = f"Given the question: {question_text}\nAnd the extracted numbers from the file:\n{nums[:200]}\nWhich aggregate should be computed and give the numeric answer if possible?"
                        agg_resp = call_llm(system_prompt, agg_q)
                        # try to extract a number
                        m = re.search(r"([-+]?\d*\.\d+|\d+)", agg_resp["text"])
                        if m:
                            answer_val = float(m.group(0))
                            # create submission payload
                            answer_payload = {"email": email, "secret": secret, "url": current_url, "answer": answer_val}
                            # Submit if a submit url is known
                            if submit_url:
                                submit_result = submit_answer(submit_url, answer_payload)
                                steps.append({"url": current_url, "question": question_text, "answer": answer_val, "submit_result": submit_result})
                                if submit_result.get("correct") and submit_result.get("url"):
                                    current_url = submit_result["url"]
                                    continue
                                else:
                                    return {"status": "submitted", "steps": steps}
        # If a dataframe exists, ask LLM what column/operation
        if df is not None:
            # send the df head and question to LLM to compute the operation
            preview = df.head(20).to_csv(index=False)
            ask = f"QUESTION: {question_text}\nDATA_PREVIEW_CSV:\n{preview}\nINSTRUCTIONS: Provide the exact python/pandas expression to compute the answer (single line) and the expected answer (a single number or JSON). Respond in JSON: {{'expression': '...', 'answer': ...}}"
            response = call_llm(system_prompt, ask, max_tokens=800)
            text = response["text"]
            # Try to extract JSON from LLM's response
            json_blob = extract_json_from_text(text)
            if json_blob and "expression" in json_blob:
                expr = json_blob["expression"]
                # Safe eval sandbox for pandas expressions — we do limited eval: df.eval or df.query is risky; we use pandas directly in a small namespace.
                answer_val = safe_eval_pandas_expression(df, expr)
                answer_payload = {"email": email, "secret": secret, "url": current_url, "answer": answer_val}
                if submit_url:
                    submit_result = submit_answer(submit_url, answer_payload)
                    steps.append({"url": current_url, "question": question_text, "expression": expr, "answer": answer_val, "submit_result": submit_result})
                    if submit_result.get("correct") and submit_result.get("url"):
                        current_url = submit_result["url"]
                        continue
                    else:
                        return {"status": "submitted", "steps": steps}
        # If we reach here, fallback: ask LLM to provide answer text and attempt to submit it
        fallback = call_llm(system_prompt, f"Solve: {question_text}\nIf you must output a JSON payload of shape {{'answer': ...}} only output it.", max_tokens=512)
        # attempt to parse a number or JSON
        fallback_text = fallback["text"]
        j = extract_json_from_text(fallback_text)
        answer_payload = {"email": email, "secret": secret, "url": current_url}
        if j and "answer" in j:
            answer_payload["answer"] = j["answer"]
        else:
            # try to extract a number
            m = re.search(r"([-+]?\d*\.\d+|\d+)", fallback_text.replace(',', ''))
            if m:
                answer_payload["answer"] = float(m.group(0))
            else:
                # send as string
                answer_payload["answer"] = fallback_text.strip()[:1000]
        if submit_url:
            submit_result = submit_answer(submit_url, answer_payload)
            steps.append({"url": current_url, "question": question_text, "answer_payload": answer_payload, "submit_result": submit_result})
            if submit_result.get("correct") and submit_result.get("url"):
                current_url = submit_result["url"]
                continue
            else:
                return {"status": "submitted", "steps": steps}

        # If nothing worked, break
        return {"status": "unable_to_solve", "steps": steps}

def extract_json_from_text(text: str):
    """
    Attempts to find a JSON object in the given text and return it.
    """
    import json
    m = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not m:
        return None
    try:
        blob = m.group(0)
        return json.loads(blob)
    except Exception:
        # try heuristics: replace single quotes
        s = m.group(0).replace("'", "\"")
        try:
            return json.loads(s)
        except Exception:
            return None

def safe_eval_pandas_expression(df, expr: str):
    """
    Very limited safe execution: only allow these operations: df['col'].sum(), df['col'].mean(), df['col'].astype(float), groupby...agg
    This is a minimal conservative evaluator — extend carefully.
    """
    # naive: try evaluate common patterns
    try:
        # direct sum pattern "df['value'].sum()"
        m = re.search(r"df\[['\"](?P<col>[^'\"]+)['\"]\]\.sum\(\)", expr)
        if m:
            col = m.group("col")
            return float(pd.to_numeric(df[col], errors="coerce").dropna().sum())
        # mean
        m2 = re.search(r"df\[['\"](?P<col>[^'\"]+)['\"]\]\.mean\(\)", expr)
        if m2:
            col = m2.group("col")
            return float(pd.to_numeric(df[col], errors="coerce").dropna().mean())
        # count
        m3 = re.search(r"df\[['\"](?P<col>[^'\"]+)['\"]\]\.count\(\)", expr)
        if m3:
            col = m3.group("col")
            return int(df[col].count())
    except Exception as e:
        print("safe eval error", e)
    raise Exception("Could not safely evaluate expression")

def submit_answer(submit_url: str, payload: dict):
    """
    Submit answer to the quiz submit endpoint. Return parsed JSON (if any).
    """
    try:
        r = requests.post(submit_url, json=payload, timeout=15)
        r.raise_for_status()
        try:
            return r.json()
        except Exception:
            return {"status": "ok_no_json", "code": r.status_code}
    except Exception as e:
        return {"error": str(e)}
