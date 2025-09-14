import asyncio, json
from app.core.database import init_db, engine 
from sqlalchemy import inspect 
from app.core.utils.provenance import log_provenance

async def main(): 
    await init_db(); 
    insp = inspect(engine)
    await log_provenance(actor='dev', action='db_init_test', details={'ok': True}); \
        print(json.dumps({'tables': insp.get_table_names()})) 
    asyncio.run(main())