import time
from core.gerenciador_dados import GerenciadorDados
from core.extrator import Extrator

class Validador:
    def __init__(self, caminho_csv, callback_progresso):
        self.dados = GerenciadorDados(caminho_csv)
        self.extrator = Extrator()
        self.callback_progresso = callback_progresso

        self.rodando = False
        self.pausado = False
        self._concluido = False
        self._teve_erro_fatal = False
        
    def processamento(self):
            self.rodando = True
            self._concluido = False
            self._teve_erro_fatal = False

            self.callback_progresso({
                "status": "iniciado",
                "mensagem": "Processamento iniciado"
            })

            try:
                self._executar_fluxo()

            except Exception as e:
                self._teve_erro_fatal = True
                self.rodando = False
                mensagem = f"Erro inesperado no processo: {e}"
                self.callback_progresso({
                    "status": "erro",
                    "mensagem": mensagem,
                    "erro": str(e)
                })
                print(mensagem)

            finally:
                if not self._concluido and not self._teve_erro_fatal and not self.rodando:
                    self.callback_progresso({
                        "status": "interrompido",
                        "mensagem": "Processo encerrado pelo usuário"
                    })

        # ===============================
        # FLUXO NORMAL
        # ===============================

    def _executar_fluxo(self):

        linhas_processadas, total_linhas = self.dados.obter_status()
        
        self.dados.inicializar_arquivo_resultado(continuar=True)
        for indice, linha in self.dados.leitor_csv(pular_ate=linhas_processadas):  # Aguarda enquanto estiver pausado

            if not self.rodando:
                break
            
            while self.pausado: 
                time.sleep(1)  # Aguarda enquanto estiver pausado   

            # Cada linha é um loop
            while True:

                try:
                    rut = linha['RUT']
                    digito_rut = linha['DV']
                    
                    time.sleep(1)
                    resultado_busca = self.extrator.consultar_rut(rut, digito_rut)
                    print(resultado_busca.items())
                    print(resultado_busca.values())
                    dados_salvar = [
                        linha.get('RUT', ''),
                        linha.get('DV', ''),
                        resultado_busca.get('telefone', ''),
                        resultado_busca.get('email', ''),
                        resultado_busca.get('sucesso', 0),
                        resultado_busca.get('erro', '')
                    ]
                    self.dados.salvar_linha(dados_salvar)

                    break

                except Exception as e:
                    mensagem = f"Erro ao processar linha {atual if 'atual' in locals() else indice + 1}: {e}"
                    print(mensagem)
                    dados_erro = [
                        linha.get('RUT', ''),
                        linha.get('DV', ''),
                        '',
                        '',
                        0,
                        str(e)
                    ]
                    self.dados.salvar_linha(dados_erro)

                    self.callback_progresso({
                        "status": "erro_linha",
                        "mensagem": mensagem,
                        "linha_atual": indice + 1,
                        "total_linhas": total_linhas,
                        "erro": str(e)
                    })

                    # O extrator ja tenta novamente a mesma linha; se ainda falhou por conexao/API,
                    # tratamos como erro fatal para nao seguir requisitando as proximas linhas.
                    if isinstance(e, RuntimeError) and "Falha de conexao/API" in str(e):
                        raise

                    # break
                    # raise para ter mais controle sobre o tipo de erro e evitar loop infinito em erros inesperados
                    raise e  # Re-raise para tentar novamente a mesma linha, mas sem entrar em loop infinito caso seja um erro inesperado

            # Callback de progresso
            atual = indice + 1
            porcentagem = (atual / total_linhas) * 100

            self.callback_progresso({
                "status": "processando",
                "progresso": round(porcentagem, 2),
                "linha_atual": atual,
                "total_linhas": total_linhas
            })

            print(f"Linha {atual} de {total_linhas} ({porcentagem:.2f}%)")

        if self.rodando: # Se terminou o loop sem ser parado pelo usuário
            self._concluido = True
            self.callback_progresso({
                "status": "concluido",
                "mensagem": "Processo finalizado com sucesso"
            })

    # ===============================
    # FLUXO ALTERNATIVO - LINHAS FALTANTES
    # ===============================

    # def processar_linhas_faltantes(self):
    #     """Processa apenas as linhas que ficaram incompletas (faltantes) após o processamento normal."""
    #     try:
    #         self._executar_fluxo_linhas_faltantes()
    #     except Exception as e:
    #         print("Erro inesperado ao processar linhas faltantes:", e)
    #     finally:
    #         print("Processamento de linhas faltantes finalizado.")

    # def _executar_fluxo_linhas_faltantes(self):
    #     """Executa o fluxo de processamento para as linhas faltantes."""
    #     linhas_faltantes = self.dados.obter_linhas_faltantes()
    #     if not linhas_faltantes:
    #         print("Nenhuma linha faltante encontrada!")
    #         return
        
    #     total_faltantes = len(linhas_faltantes)
    #     print(f"Iniciando processamento de {total_faltantes} linhas faltantes...")

    #     # Lê todas as linhas do arquivo original e processa apenas as faltantes
    #     todas_linhas = []
    #     for idx, linha in self.dados.leitor_csv(pular_ate=0):
    #         todas_linhas.append((idx, linha))

    #     caminho_res = self.dados.caminho_resultado
    #     encoding_res = self.dados.detectar_encoding(caminho_res)

    #     conteudo_resultado = []
    #     with open(caminho_res, mode='r', encoding=encoding_res) as f:
    #         leitor = csv.reader(f, delimiter=';')
    #         conteudo_resultado = list(leitor)
                
    #     # Processa apenas as linhas faltantes
    #     for contador, indice_faltante in enumerate(linhas_faltantes):
    #         if indice_faltante < len(todas_linhas):
    #             indice_original, linha = todas_linhas[indice_faltante]
                
    #             try:
    #                 rut = linha['RUT']
    #                 digito_rut = linha['DV']
                    
    #                 time.sleep(1)
    #                 resultado_busca = self.extrator.consultar_rut(rut, digito_rut)
    #                 print(resultado_busca.items())
    #                 print(resultado_busca.values())
                    
    #                 dados_salvar = [
    #                     *linha.values(),
    #                     *resultado_busca.values()
    #                 ]

    #                 idx_no_arquivo = indice_faltante + 1
    #                 if idx_no_arquivo < len(conteudo_resultado):
    #                     conteudo_resultado[idx_no_arquivo] = dados_salvar
    #                 print(f"Sucesso: Linha {indice_faltante} atualizada.")
    #             except Exception as e:
    #                 print(f"Erro ao processar linha faltante {indice_original}:", e)
                
    #             # Callback de progresso
    #             atual = contador + 1
    #             porcentagem = (atual / total_faltantes) * 100
    #             print(f"Linha faltante {atual} de {total_faltantes} ({porcentagem:.2f}%)")
    #     # Escreve o arquivo de resultado atualizado
    #     with open(caminho_res, mode='w', newline='', encoding='utf-8-sig') as f:
    #         writer = csv.writer(f, delimiter=';')
    #         writer.writerows(conteudo_resultado)
    #     print("Arquivo de resultados atualizado com sucesso.")
