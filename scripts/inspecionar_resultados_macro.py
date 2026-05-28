import csv, os
files = [
    'macro/valida_dados_aguasandinas_v2.1/planilha/ENTREGA BASE NOMBRE DIRECCION FECH NAC_part1_RESULTADO.csv',
    'macro/valida_dados_aguasandinas_v2.1/planilha/ENTREGA BASE NOMBRE DIRECCION FECH NAC_part2_RESULTADO.csv',
    'macro/valida_dados_aguasandinas_v2.1/planilha/ENTREGA BASE NOMBRE DIRECCION FECH NAC_part3_RESULTADO.csv',
]
for f in files:
    with open(f, encoding='utf-8') as fh:
        rows = list(csv.DictReader(fh, delimiter=';'))
    total    = len(rows)
    sucesso  = sum(1 for r in rows if str(r.get('SUCESSO','')).strip() == '1')
    com_tel  = sum(1 for r in rows if str(r.get('TELEFONE_VALIDADO','')).strip())
    com_eml  = sum(1 for r in rows if str(r.get('EMAIL_VALIDADO','')).strip())
    erros    = sum(1 for r in rows if str(r.get('ERRO','')).strip())
    print(os.path.basename(f))
    print(f'  total={total}  sucesso={sucesso}  com_tel={com_tel}  com_email={com_eml}  com_erro={erros}')
    if rows:
        print('  Exemplo:', {k: v for k, v in list(rows[0].items())})
