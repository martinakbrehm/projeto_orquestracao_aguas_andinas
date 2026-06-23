"""
Extrai clientes com telefone_validado e extraido=0,
atualiza extraido=1 + data_extracao=now(), gera CSV no formato padrão.
"""
import sys
import csv
from datetime import date, datetime

sys.path.insert(0, ".")
from config import db_aguas_andinas
import pymysql

HOJE = date.today()
ARQUIVO_SAIDA = f"dados/resultados/extracao_{HOJE.strftime('%Y-%m-%d')}.csv"
CABECALHO = [
    "RUT", "DV", "NOME", "SEXO", "DATA_NASCIMENTO", "IDADE",
    "DIRECCION", "COMUNA", "REGION",
    "telefone_1", "telefone_2", "telefone_3", "telefone_4", "telefone_5",
    "email_1", "email_2",
]


def calcular_idade(data_nasc):
    if not data_nasc:
        return ""
    hoje = date.today()
    return hoje.year - data_nasc.year - (
        (hoje.month, hoje.day) < (data_nasc.month, data_nasc.day)
    )


def formatar_data(data_nasc):
    if not data_nasc:
        return ""
    return data_nasc.strftime("%d/%m/%Y")


conn = pymysql.connect(**db_aguas_andinas())
cur = conn.cursor(pymysql.cursors.DictCursor)

# IDs a extrair
cur.execute("""
    SELECT id, cliente_id
    FROM tabela_macros_aa
    WHERE status = 'telefone_validado'
      AND extraido = 0
""")
registros = cur.fetchall()
ids_macros   = [r["id"]         for r in registros]
ids_clientes = [r["cliente_id"] for r in registros]

print(f"Registros a extrair: {len(ids_macros)}")

if not ids_macros:
    print("Nenhum registro para extrair.")
    conn.close()
    sys.exit(0)

# Dados dos clientes
placeholders = ",".join(["%s"] * len(ids_clientes))

cur.execute(f"""
    SELECT c.id, c.rut, c.dv, c.nome, c.sexo, c.data_nascimento,
           e.direccion, e.comuna, e.region
    FROM clientes c
    LEFT JOIN enderecos e ON e.cliente_id = c.id
    WHERE c.id IN ({placeholders})
""", ids_clientes)
clientes_raw = cur.fetchall()

# Um cliente pode ter mais de um endereço — pega o primeiro
clientes = {}
for row in clientes_raw:
    cid = row["id"]
    if cid not in clientes:
        clientes[cid] = row

# Telefones (todos, ordenados por origem: validado primeiro, depois enriquecimento)
cur.execute(f"""
    SELECT cliente_id, numero,
           CASE origem WHEN 'validado' THEN 0 ELSE 1 END AS ord
    FROM telefones
    WHERE cliente_id IN ({placeholders})
    ORDER BY cliente_id, ord, id
""", ids_clientes)
telefones_raw = cur.fetchall()

telefones = {}
for row in telefones_raw:
    cid = row["cliente_id"]
    telefones.setdefault(cid, []).append(row["numero"])

# Emails (todos, validado primeiro)
cur.execute(f"""
    SELECT cliente_id, endereco,
           CASE origem WHEN 'validado' THEN 0 ELSE 1 END AS ord
    FROM emails
    WHERE cliente_id IN ({placeholders})
    ORDER BY cliente_id, ord, id
""", ids_clientes)
emails_raw = cur.fetchall()

emails = {}
for row in emails_raw:
    cid = row["cliente_id"]
    emails.setdefault(cid, []).append(row["endereco"])

# Gera CSV
with open(ARQUIVO_SAIDA, "w", newline="", encoding="utf-8-sig") as f:
    writer = csv.writer(f, delimiter=";")
    writer.writerow(CABECALHO)

    for macro in registros:
        cid  = macro["cliente_id"]
        c    = clientes.get(cid, {})
        fones = telefones.get(cid, [])[:5]
        mails = emails.get(cid, [])[:2]

        # Preenche até 5 telefones e 2 emails com string vazia
        fones += [""] * (5 - len(fones))
        mails += [""] * (2 - len(mails))

        writer.writerow([
            c.get("rut", ""),
            c.get("dv", ""),
            c.get("nome", ""),
            c.get("sexo", ""),
            formatar_data(c.get("data_nascimento")),
            calcular_idade(c.get("data_nascimento")),
            c.get("direccion", ""),
            c.get("comuna", ""),
            c.get("region", ""),
            *fones,
            *mails,
        ])

print(f"CSV gerado: {ARQUIVO_SAIDA}")

# Atualiza extraido=1 e data_extracao=now() em lotes de 1000
LOTE = 1000
agora = datetime.now()
total_atualizado = 0
for i in range(0, len(ids_macros), LOTE):
    lote = ids_macros[i : i + LOTE]
    ph   = ",".join(["%s"] * len(lote))
    cur.execute(f"""
        UPDATE tabela_macros_aa
        SET extraido = 1, data_extracao = %s
        WHERE id IN ({ph})
    """, [agora] + lote)
    total_atualizado += cur.rowcount

conn.commit()
conn.close()

print(f"Registros atualizados no banco: {total_atualizado}")
