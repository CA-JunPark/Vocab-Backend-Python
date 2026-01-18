from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class WordSchema(BaseModel):
    name: str
    meaningKr: str
    example: str
    antonymEn: str
    tags: Optional[str] = None
    createdTime: Optional[str] = None
    modifiedTime: Optional[str] = None
    isDeleted: bool = False
    syncedTime: Optional[str] = None
    note: Optional[str] = None