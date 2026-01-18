from fastapi import FastAPI
from pydantic import BaseModel
import secretKeys
from libsql_client import create_client
from typing import List
from WordSchema import WordSchema
from datetime import datetime

# fastapi dev main.py
app = FastAPI()

# Connect to Turso
# TODO change it to environment variables 
# for Google Cloud Run server
url = secretKeys.TURSO_URL
auth_token = secretKeys.TURSO_TOKEN

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
    if not request.lastSyncTime:
        return {"wordsToUpdate": []}

    for word in request.localChanges:
        await client.execute(
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
            """,
            [word.name, word.meaningKr, word.example, word.antonymEn, word.tags, 
             word.createdTime, word.modifiedTime, int(word.isDeleted), word.modifiedTime, word.note]
        )

    # Handle PULL: Get words updated by OTHER devices
    result = await client.execute(
        "SELECT * FROM Word WHERE modifiedTime > ? ORDER BY modifiedTime ASC", 
        [request.lastSyncTime]
    )

    updates = []
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

    print("wordsToUpdate: ", updates)
    return {
        "wordsToUpdate": updates,
        "serverTime": datetime.utcnow().isoformat() # Send server time to avoid clock drift
    }

@app.post("/sync/push")
async def push_changes(tasks: List[WordSchema]):
    client = app.state.db_client
    
    # batch insert
    queries = []
    for task in tasks:
        queries.append((
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
            syncedTime=excluded.syncedTime,
            note=excluded.note
            """,
            [task.name, task.meaningKr, task.example, task.antonymEn, 
             task.tags, task.createdTime, task.modifiedTime, task.isDeleted, task.syncedTime, task.note]
        ))
    
    results = await client.batch(queries)
    success = sum(res.rows_affected for res in results)

    # get all updated [word.name] 
    return {"message": "Success: " + str(success)}

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