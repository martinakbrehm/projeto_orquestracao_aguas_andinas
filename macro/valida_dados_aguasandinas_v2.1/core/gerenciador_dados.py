from charset_normalizer import from_bytes
import csv
import os

class GerenciadorDados:
    def __init__(self, caminho_original):
        self.caminho_original = caminho_original
        self.caminho_resultado = caminho_original.replace(".csv", "_RESULTADO.csv")
        self.encoding = self.detectar_encoding(caminho_original)
        self.colunas = [
            "RUT", "DV", "TELEFONE_VALIDADO", "EMAIL_VALIDADO", "SUCESSO", "ERRO"
        ]

    def obter_status(self):
        """Retorna (linhas_processadas, total_linhas)"""
        total = 0
        with open(self.caminho_original, mode='r', encoding=self.encoding) as f:
            total = sum(1 for _ in f) - 1 # Desconta cabeçalho
        
        processadas = 0
        if os.path.exists(self.caminho_resultado):
            with open(self.caminho_resultado, mode='r', encoding='utf-8-sig') as f:
                processadas = sum(1 for _ in f) - 1
        
        return max(0, processadas), max(0, total)

    def obter_pasta_resultado(self):
        return os.path.dirname(self.caminho_resultado)

    def inicializar_arquivo_resultado(self, continuar=True):
        """Cria o arquivo de resultado com as colunas definidas, se ainda não existir."""
        if not continuar and os.path.exists(self.caminho_resultado):
            os.remove(self.caminho_resultado)
        if not os.path.exists(self.caminho_resultado):
            with open(self.caminho_resultado, mode='w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f, delimiter=';')
                writer.writerow(self.colunas)

    def existe_progresso(self):
        return os.path.exists(self.caminho_progresso)
    
    def obter_linhas_de_retomada(self):
        """Conta quantas linhas já foram processadas no resultado."""
        if not os.path.exists(self.caminho_resultado):
            return 0
        with open(self.caminho_resultado, mode='r', encoding='utf-8-sig') as f:
            return sum(1 for _ in f) - 1  # Subtrai 1 para não contar a linha de cabeçalho
        
    def obter_linhas_faltantes(self):
        """Identifica as linhas no arquivo de resultado que não foram totalmente preenchidas
            Coluna telefone_validado e email_validado estão vazias.
        """
        linhas_faltantes = []
        if os.path.exists(self.caminho_resultado):
            encoding = self.detectar_encoding(self.caminho_resultado)
            with open(self.caminho_resultado, mode='r', encoding=encoding) as f:
                leitor = csv.DictReader(f, delimiter=';')
                for i, linha in enumerate(leitor):
                    if linha['SUCESSO'] == '':
                        linhas_faltantes.append(i)
        return linhas_faltantes

    def leitor_csv(self, pular_ate=0):
        """Lê o arquivo CSV original e retorna um iterador de dicionários."""

        with open(self.caminho_original, mode='r', encoding=self.encoding) as f:
            leitor = csv.DictReader(f, delimiter=';')
            for i, linha in enumerate(leitor):
                if i < pular_ate:
                    continue

                yield i, linha
    
    def salvar_linha(self, dados):
        """Faz o Append (anexo) de uma linha processada."""
        with open(self.caminho_resultado, mode='a', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f, delimiter=';')
            writer.writerow(dados)

    def finalizar_processo(self, concluido_totalmente=False):
        """Ações ao parar ou terminar."""
        if concluido_totalmente:
            os.remove(self.caminho_original)
            os.rename(self.caminho_resultado, self.caminho_original)

    @staticmethod
    def detectar_encoding(caminho_original):
        with open(caminho_original, mode='rb') as f:
            rawdata = f.read(4)
        
        if rawdata.startswith(b'\xef\xbb\xbf'):
            return 'utf-8-sig'
        
        with open(caminho_original, mode='rb') as f:
            rawdata = f.read(100000)
        
        match = from_bytes(rawdata).best()
        if not match:
            return 'utf-8'
        
        encoding = match.encoding.lower()
        if encoding in ['utf_8', 'utf-8']:
            return 'utf-8'
        
        return encoding