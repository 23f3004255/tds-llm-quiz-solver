import asyncio
import os
import time
from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel
from starlette.responses import JSONResponse
from app.solver import solve_quiz_entrypoint
from dotenv import load_dotenv
load_dotenv()

app = FastAPI()


# Environment Variables
MAX_RUN_SECONDS = int(os.getenv("MAX_RUN_SECOND"))
secret = os.getenv("SECRET_KEY")



# Payload model
class QuizRequest(BaseModel):
    email:str
    secret:str
    url:str

@app.get("/")
def home():
    return {
        "status": "running",
        "message": "TDS Automation API is up and running!",
        "usage": "Send a POST request to /solve with your quiz task."
    }

@app.post("/solve")
async def solve(req:Request):
    try:
        payload = await req.json()
    except Exception:
        raise HTTPException(status_code=400,detail="invalid JSON")

    try:
        q = QuizRequest(**payload)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid payload: {e}")

    if q.secret != secret:
        raise HTTPException(status_code=403, detail="Invalid secret")

    # Run solver with timeout
    start = time.time()

    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(solve_quiz_entrypoint, q.email, q.secret,q.url,MAX_RUN_SECONDS),
            timeout=MAX_RUN_SECONDS + 5
        )
    except asyncio.TimeoutError:
        raise HTTPException(status_code=500,detail="solver time out")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"solver error {e}")
    elapsed = time.time()-start
    return JSONResponse(status_code=200, content={"ok":True,"elapsed_second":elapsed,"result":result})