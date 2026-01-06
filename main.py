from fastapi import FastAPI
from pydantic import BaseModel
import secretKeys
from libsql_client import create_client
from typing import List
from WordSchema import WordSchema

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

@app.post("/sync")
async def sync(words: List[WordSchema]):
    print("words: ", words)
    names = [word.name for word in words] 
    client = app.state.db_client
    if not names:
        return {"syncedWords": []}

    # LibSQL uses '?' as placeholders for SQLite
    placeholders = ", ".join(["?"] * len(names))
    query = f"SELECT * FROM Word WHERE name IN ({placeholders})"
    result = await client.execute(query, names)
    print("result: ", result)
    
    return {"syncedWords": ["potato"]}

@app.post("/sync/push")
async def push_changes(tasks: List[WordSchema]):
    client = app.state.db_client
    
    # batch insert
    queries = []
    for task in tasks:
        queries.append((
            """
            INSERT INTO Word (name, meaningKr, example, antonymEn, tags, createdTime, modifiedTime, isDeleted, synced) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
            meaningKr=excluded.meaningKr,
            example=excluded.example,
            antonymEn=excluded.antonymEn,
            tags=excluded.tags,
            modifiedTime=excluded.modifiedTime,
            isDeleted=excluded.isDeleted,
            synced=excluded.synced
            """,
            [task.name, task.meaningKr, task.example, task.antonymEn, 
             task.tags, task.createdTime, task.modifiedTime, task.isDeleted, task.synced]
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
            "synced": bool(row[8])
        })
    return results