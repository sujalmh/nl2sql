from pydantic import BaseModel
from typing import List, Dict
import sqlite3

class Column(BaseModel):
    name: str
    type: str

class TableSchema(BaseModel):
    table_name: str
    columns: List[Column]

def extract_schema(db_path: str) -> List[TableSchema]:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()

    schema = []
    for table in tables:
        table_name = table[0]
        cursor.execute(f"PRAGMA table_info({table_name});")
        columns_info = cursor.fetchall()
        columns = [Column(name=col[1], type=col[2]) for col in columns_info]
        schema.append(TableSchema(table_name=table_name, columns=columns))

    conn.close()
    return schema, table_name