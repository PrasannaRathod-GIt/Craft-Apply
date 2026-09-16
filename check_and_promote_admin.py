import asyncio
import os

import asyncpg
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://")


async def main():
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        rows = await conn.fetch("SELECT id, email, is_admin FROM users ORDER BY id;")
        print("\nCurrent users in THIS database (the one your app actually uses):")
        for r in rows:
            print(f"  id={r['id']:<4} email={r['email']:<30} is_admin={r['is_admin']}")

        target_id = input("\nEnter the id to promote to admin (or press Enter to skip): ").strip()
        if target_id:
            await conn.execute("UPDATE users SET is_admin = true WHERE id = $1;", int(target_id))
            row = await conn.fetchrow("SELECT id, email, is_admin FROM users WHERE id = $1;", int(target_id))
            print(f"\nDone. id={row['id']} email={row['email']} is_admin={row['is_admin']}")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())