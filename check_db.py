# check_db.py
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

import asyncio
from sqlalchemy import text
from app.db import SessionLocal

async def main():
    async with SessionLocal() as session:
        result = await session.execute(
            text("""
                SELECT id, tenant_id, endpoint, model, latency_ms, status_code, created_at 
                FROM request_logs 
                ORDER BY created_at DESC 
                LIMIT 5;
            """)
        )
        rows = result.mappings().all()
        
        print("\n=================== RECENT REQUEST LOGS ===================")
        if not rows:
            print("No request logs found.")
        for row in rows:
            print(dict(row))
        print("===========================================================\n")

if __name__ == "__main__":
    asyncio.run(main())