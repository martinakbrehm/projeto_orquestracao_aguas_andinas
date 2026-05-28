import sys
sys.path.insert(0, '.')
from extrator import Extrator

if __name__ == '__main__':
    import sys
    if len(sys.argv) >= 3:
        rut = sys.argv[1]
        dv = sys.argv[2]
    else:
        rut = '12345678'
        dv = '9'
    print('Consultando RUT:', rut+'-'+dv)
    try:
        resultado = Extrator().consultar_rut(rut, dv)
        print('Resultado:', resultado)
    except Exception as e:
        print('Erro ao consultar:', e)
