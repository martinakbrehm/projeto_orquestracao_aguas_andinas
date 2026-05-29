import json
import time

from bs4 import BeautifulSoup
import requests

class Extrator:
    """Extrai dados de RUT via requisição AJAX."""
    def __init__(self):
        pass

    def requisicao_ajax(self, rut_com_digito, tentativas=4, backoff_inicial=1):
        url = "https://www.aguasandinas.cl/web/aguasandinas/registrese?p_p_id=aguas_registro_portlet_AguasRegistroPortlet_INSTANCE_RP9DfpVLcs0S&p_p_lifecycle=2&p_p_state=normal&p_p_mode=view&p_p_resource_id=%2Fregistro%2FobtenerInfoRut&p_p_cacheability=cacheLevelPage"

        payload = {
            "_aguas_registro_portlet_AguasRegistroPortlet_INSTANCE_RP9DfpVLcs0S_rut": f"{rut_com_digito}",
            "_aguas_registro_portlet_AguasRegistroPortlet_INSTANCE_RP9DfpVLcs0S_tipoUsuario": "persona"
        }

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
            "Origin": "https://www.aguasandinas.cl",
            "Referer": "https://www.aguasandinas.cl/web/aguasandinas/registrese"
        }

        session = requests.Session()

        ultimo_erro = None
        for tentativa in range(1, tentativas + 1):
            try:
                r = session.post(url, data=payload, headers=headers, timeout=30)
                r.raise_for_status()

                try:
                    return r.json()
                except ValueError:
                    return r.text

            except requests.exceptions.RequestException as e:
                ultimo_erro = e
                if tentativa < tentativas:
                    espera = backoff_inicial * (2 ** (tentativa - 1))
                    time.sleep(espera)

        raise RuntimeError(
            f"Falha de conexao/API apos {tentativas} tentativas para RUT {rut_com_digito}: {ultimo_erro}"
        )

    def consultar_rut(self, rut: str, digito: str):
        """Consuta RUT via requisição AJAX."""
        try:
            rut_com_digito = f'{rut}-{digito}'
            resposta = self.requisicao_ajax(rut_com_digito)

            # Se for JSON
            if isinstance(resposta, dict):

                if "motivoRetorno" in resposta:
                    return {
                        "telefone": '',
                        "email": '',
                        "sucesso": 0,
                        "erro": resposta["motivoRetorno"]
                    }

            # Se for HTML
            soup = BeautifulSoup(resposta, 'html.parser')

            telefone = soup.select_one('#telefono')
            email = soup.select_one('#correoElectronico')

            if telefone and email:
                return {
                    "telefone": telefone.get("value"),
                    "email": email.get("value"),
                    "sucesso": 1,
                    "erro": ''
                }
            
            erro = soup.select_one(".alerta.error")

            return {
                "telefone": '',
                "email": '',
                "sucesso": 0,
                "erro": erro.text.strip() if erro else "Erro ou retorno desconhecido"
            }

        except Exception as e:
            raise e
