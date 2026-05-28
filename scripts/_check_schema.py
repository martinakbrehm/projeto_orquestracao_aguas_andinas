import sys; sys.path.insert(0,'.')
import pymysql, config
conn = pymysql.connect(**config.db_aguas_andinas())
with conn.cursor() as cur:
    for tbl in ['telefones','emails']:
        cur.execute(f'SHOW COLUMNS FROM {tbl}')
        print(f'\n=== {tbl} ===')
        for r in cur.fetchall(): print(r)
    for tbl in ['telefones','emails']:
        cur.execute(f'SHOW INDEX FROM {tbl} WHERE Non_unique=0')
        print(f'\n=== UNIQUE {tbl} ===')
        for r in cur.fetchall(): print(r[2], r[4])
    cur.execute('SHOW TABLES')
    print('\n=== TABLES ===')
    for r in cur.fetchall(): print(r[0])
    cur.execute('SELECT TABLE_NAME FROM information_schema.VIEWS WHERE TABLE_SCHEMA=DATABASE()')
    print('\n=== VIEWS ===')
    for r in cur.fetchall(): print(r[0])
conn.close()
