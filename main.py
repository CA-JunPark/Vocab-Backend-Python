from fastapi import FastAPI
from pydantic import BaseModel
from libsql_client import create_client
from typing import List
from WordSchema import WordSchema
from datetime import datetime
from google import genai
from google.genai import types
import json
from fastapi import HTTPException
from fastapi.responses import JSONResponse
import os

# fastapi dev main.py
app = FastAPI()

try:
    import secretKeys
except ImportError:
    secretKeys = None

url = os.getenv("TURSO_URL") or (secretKeys.TURSO_URL if secretKeys else None)
auth_token = os.getenv("TURSO_TOKEN") or (secretKeys.TURSO_TOKEN if secretKeys else None)
gemini_key = os.getenv("GEMINI_API_KEY") or (secretKeys.GEMINI_API_KEY if secretKeys else None)

@app.on_event("startup")
async def startup():
    app.state.db_client = create_client(url=url, auth_token=auth_token)

@app.on_event("shutdown")
async def shutdown():
    await app.state.db_client.close()

@app.get("/")
def read_root():
    return {"message": "hello"}

class SyncRequest(BaseModel):
    lastSyncTime: str
    localChanges: List[WordSchema]

@app.post("/sync")
async def sync(request: SyncRequest):
    print("lastSyncTime: ", request.lastSyncTime)
    print("localChanges: ", request.localChanges)
    client = app.state.db_client

    statements = [
        (
            """
            INSERT INTO Word (name, meaningKr, example, antonymEn, tags, createdTime, modifiedTime, isDeleted, syncedTime, note)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                meaningKr=excluded.meaningKr,
                example=excluded.example,
                antonymEn=excluded.antonymEn,
                tags=excluded.tags,
                modifiedTime=excluded.modifiedTime,
                isDeleted=excluded.isDeleted,
                syncedTime=excluded.modifiedTime,
                note=excluded.note
            WHERE excluded.modifiedTime > Word.modifiedTime
            """,
            [
                word.name, word.meaningKr, word.example, word.antonymEn, word.tags, 
                word.createdTime, word.modifiedTime, int(word.isDeleted), word.modifiedTime, word.note
            ]
        )
        for word in request.localChanges
    ]
    await client.batch(statements)

    updates = []
    if request.lastSyncTime:
        result = await client.execute(
            "SELECT * FROM Word WHERE modifiedTime > ? ORDER BY modifiedTime ASC", 
            [request.lastSyncTime]
        )

        for row in result.rows:
            updates.append({
                "name": row[0],
                "meaningKr": row[1],
                "example": row[2],
                "antonymEn": row[3],
                "tags": row[4],
                "createdTime": row[5],
                "modifiedTime": row[6],
                "isDeleted": bool(row[7]),
                "syncedTime": row[8],
                "note": row[9]
            })
    return {
        "wordsToUpdate": updates,
        "serverTime": datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S') # for update lastSyncTime in local
    }

@app.get("/sync/pullAll")
async def pull_changes():
    client = app.state.db_client
    result = await client.execute("SELECT * FROM Word")
    
    results = []
    for row in result.rows:
        results.append({
            "name": row[0],
            "meaningKr": row[1],
            "example": row[2],
            "antonymEn": row[3],
            "tags": row[4],
            "createdTime": row[5],
            "modifiedTime": row[6],
            "isDeleted": bool(row[7]),
            "syncedTime": row[8]
        })
    return results

response_schema = {
    "type": "OBJECT",
    "properties": {
        "name": {"type": "STRING"},
        "meaningKr": {"type": "ARRAY", "items": {"type": "STRING"}},
        "example": {"type": "ARRAY", "items": {"type": "STRING"}},
        "antonymEn": {"type": "ARRAY", "items": {"type": "STRING"}},
        "tags": {"type": "ARRAY", "items": {"type": "STRING"}},
    },
    "required": ["name", "meaningKr", "example", "antonymEn", "tags"]
}
systemInstruction = """Provide linguistic details for the given word in JSON format.\
            1. PRIORITY: If a computer science or cybersecurity definition exists, list it first in all arrays.
            2. SYNC: Ensure that the index of each entry in 'meaningKr', 'example', and 'antonymEn' corresponds to the same definition. 
            3. LENGTH: All three arrays (meaningKr, example, antonymEn) must have the exact same number of elements.
            4. LANGUAGE: 'meaningKr' must be in Korean. All other fields must be English.
            5. Case: Lowercase the 'name' and 'antonymEn' fields.
            6. If the word is misspelled, provide the correct spelling in the 'name' field and provide details of that word.
            """
@app.get("/gemini")
async def gemini(word: str):
    client = genai.Client(api_key=gemini_key)
    try:
        response = client.models.generate_content(
            model='gemini-3-flash-preview',
            contents=f"Generate a vocabulary entry for the word: {word}",
            config=types.GenerateContentConfig(
                system_instruction=systemInstruction,
                temperature=0,
                response_mime_type="application/json",
                response_schema=response_schema,
            ),
        )
        data = json.loads(response.text)
        print(data)
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
