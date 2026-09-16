"""
Deletes previously-scraped jobs (source in 'official'/'adzuna') so the next
scrape run starts clean against the new dedup_hash scheme. Leaves your
manual test job(s) alone. Uses your app's own DB engine, so it's guaranteed
to hit the real database -- not whatever branch the Neon web console
happens to be showing.

Run from project root, venv activated:
    python clear_scraped_jobs.py
"""

import asyncio

from sqlalchemy import delete, select

from app.core.database import AsyncSessionLocal
from app.models.job import Job


async def main():
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Job.id, Job.title, Job.source).where(Job.source.in_(["official", "adzuna"]))
        )
        rows = result.all()

        if not rows:
            print("No 'official'/'adzuna' rows found -- nothing to delete.")
            return

        print(f"\nAbout to delete {len(rows)} rows:")
        for r in rows[:20]:
            print(f"  id={r.id:<5} source={r.source:<10} title={r.title}")
        if len(rows) > 20:
            print(f"  ...and {len(rows) - 20} more")

        confirm = input("\nType 'yes' to delete these rows: ").strip().lower()
        if confirm == "yes":
            await db.execute(delete(Job).where(Job.source.in_(["official", "adzuna"])))
            await db.commit()
            print(f"Deleted {len(rows)} rows.")
        else:
            print("Cancelled -- nothing deleted.")


if __name__ == "__main__":
    asyncio.run(main())