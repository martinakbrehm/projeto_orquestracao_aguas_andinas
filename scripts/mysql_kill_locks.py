# Script para diagnosticar e matar conexões travadas no MySQL
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import pymysql
import config

# Conecte usando as credenciais do banco de destino
conn = pymysql.connect(**config.db_destino())
with conn.cursor() as cur:
    cur.execute("SHOW FULL PROCESSLIST")
    rows = cur.fetchall()
    print("Processos ativos:")
    locked = []
    for row in rows:
        pid = row[0]
        user = row[1]
        host = row[2]
        db = row[3]
        command = row[4]
        time = row[5]
        state = row[6]
        info = row[7]
        print(f"ID={pid} | User={user} | DB={db} | State={state} | Command={command} | Time={time}")
        if state and ("lock" in state.lower() or "Locked" in command or (command == "Sleep" and time > 60)):
            locked.append(pid)
    if not locked:
        print("Nenhum processo travado detectado.")
    else:
        print(f"Matando {len(locked)} processos travados...")
        for pid in locked:
            try:
                cur.execute(f"KILL {pid}")
                print(f"KILL {pid} OK")
            except Exception as ex:
                print(f"Erro ao matar {pid}: {ex}")
conn.close()
print("Diagnóstico e limpeza de locks finalizados.")
