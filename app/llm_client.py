import os
import requests
import json
from typing import Dict, Any
from dotenv import load_dotenv
load_dotenv()

AIPIPE_TOKEN = os.getenv("AIPIPE_TOKEN")
AIPIPE_MODEL = os.getenv("AIPIPE_MODEL", "gpt-4.1")


def call_llm(system_prompt: str, user_prompt: str, max_tokens: int = 1024) -> Dict[str, Any]:
    """
    Drop-in replacement for OpenAI ChatCompletion using AIPipe.
    Works exactly like the provided OpenAI wrapper.

    Returns:
        {
            "text": "<model_output_text>",
            "raw": <full_json_response>
        }
    """

    # If token missing → mock mode
    if not AIPIPE_TOKEN:
        return {
            "text": f"[MOCK] System: {system_prompt[:80]} | User: {user_prompt[:200]}",
            "raw": None
        }

    # Prepare AIPipe-compatible input: system + user prompt combined
    combined_prompt = f"[SYSTEM]\n{system_prompt}\n\n[USER]\n{user_prompt}"

    # Make request
    response = requests.post(
        "https://aipipe.org/openai/v1/responses",
        headers={
            "Authorization": f"Bearer {AIPIPE_TOKEN}",
            "Content-Type": "application/json"
        },
        json={
            "model": AIPIPE_MODEL,
            "input": combined_prompt,
            # AIPipe ignores max_tokens but we keep it to match signature
        }
    )

    # Raise exception for HTTP errors
    response.raise_for_status()

    data = response.json()

    # Extract text from AIPipe structure
    try:
        text = data["output"][0]["content"][0]["text"]
    except Exception:
        text = str(data)

    return {"text": text, "raw": data}







def ask_steps_from_llm(html: str, aipipe_token: str = AIPIPE_TOKEN, model: str = "gpt-5-nano"):
    """
    Calls AI Pipe's OpenAI proxy correctly using the /openai/v1/responses API.

    AI Pipe does NOT support OpenAI chat format.
    Only: { model, input } is allowed.

    So we combine system + user prompt manually into one long input string.
    """
    print(aipipe_token)

    if not aipipe_token:
        raise RuntimeError("AIPIPE token missing")

    # SYSTEM PROMPT
    SYSTEM_PROMPT = """
            You are an expert automation planner.
            Input: HTML of a quiz/task page.
            Output: A JSON plan describing EXACTLY what steps the executor should perform.
            
            Rules:
            - DO NOT solve the task yourself.
            - Only produce a plan.
            - Plan must be deterministic, executable, and unambiguous.
            - Never include code.
            - Use only the allowed action names:
              ["download_file", "extract_table", "sum_column", "sum_values", "extract_text",
               "find_number", "submit_result", "parse_html"]
            
            JSON format:
            {
              "steps": [
                {
                  "action": "action_name",
                  "params": { ... }
                }
              ]
            }
            
            Guidelines:
            - If the HTML contains a link → use "download_file".
            - If the task requires table extraction → use "extract_table".
            - If the task requires summing → use "sum_column" or "sum_values".
            - If values are embedded in text → use "extract_text" or "find_number".
            - Always end with "submit_result" if applicable.
            - Include required fields: email, secret, task_url, answer_key where applicable.
            - Keep steps minimal but complete.
            """

    # USER PROMPT
    USER_PROMPT = f"""
            Here is the HTML content:
            {html}
            
            Generate ONLY the JSON plan described above.
            Output must be valid JSON object with a "steps" array.
            """

    # Combine into a single text (AI Pipe requires this)
    full_prompt = SYSTEM_PROMPT + "\n\n" + USER_PROMPT

    # ----------------------------
    # Correct AIPipe API Call
    # ----------------------------
    response = requests.post(
        "https://aipipe.org/openai/v1/responses",
        headers={
            "Authorization": f"Bearer {aipipe_token}",
            "Content-Type": "application/json"
        },
        json={
            "model": model,
            "input": full_prompt
        }
    )

    response.raise_for_status()
    data = response.json()

    # Extract text (AI Pipe format)
    # Structure:
    # {
    #   "output": [
    #      { "role": "assistant", "content": [{ "text": "..."}] }
    #   ]
    # }

    text = data["output"][0]["content"][0]["text"].strip()

    # Parse the returned JSON
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        raise ValueError(f"AIPipe returned invalid JSON:\n{text}")

    return parsed

