from selenium import webdriver
from selenium.webdriver.common.by import By

from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import sys
import time


# Uso: python consulta_aguasandinas_selenium.py <rut_completo>
if len(sys.argv) >= 2:
    rut = sys.argv[1]
else:
    rut = '12345678K'

# Configurações do Selenium (headless opcional)
chrome_options = Options()
# chrome_options.add_argument('--headless')  # Descomente para rodar sem abrir janela
chrome_options.add_argument('--disable-gpu')
chrome_options.add_argument('--no-sandbox')

# Caminho do chromedriver (ajuste se necessário)
driver = webdriver.Chrome(options=chrome_options)

try:

    driver.get('https://www.aguasandinas.cl/web/aguasandinas/registrese')
    wait = WebDriverWait(driver, 20)

    # Aguarda o painel PASO 1 estar visível
    wait.until(EC.presence_of_element_located((By.ID, 'tabs-1')))
    time.sleep(1)

    # Imprime todos os inputs encontrados para debug
    todos_inputs = driver.find_elements(By.TAG_NAME, 'input')
    print(f'DEBUG: {len(todos_inputs)} inputs encontrados na página')
    for inp in todos_inputs:
        print(f'  id={inp.get_attribute("id")!r} name={inp.get_attribute("name")!r} type={inp.get_attribute("type")!r} aria-label={inp.get_attribute("aria-label")!r} visible={inp.is_displayed()} enabled={inp.is_enabled()}')

    # Localiza o campo de RUT pelo id descoberto na inspeção
    try:
        campo_rut = wait.until(EC.element_to_be_clickable((By.ID, 'rutUsuario')))
    except:
        campo_rut = wait.until(EC.element_to_be_clickable((By.XPATH, "//input[@aria-label='RUT (*)']")))

    print('DEBUG: Campo encontrado:', campo_rut.get_attribute('outerHTML'))
    # Usa JavaScript para garantir interação
    driver.execute_script("arguments[0].value = '';", campo_rut)
    driver.execute_script("arguments[0].value = arguments[1];", campo_rut, rut)
    campo_rut.send_keys(rut[-1])  # Trigger de evento de input


    # Clica no botão "Persona Natural" que executa sendRegistro('persona')
    botao = wait.until(EC.element_to_be_clickable((By.XPATH, "//a[@onclick=\"sendRegistro('persona');\"]")))
    botao.click()
    time.sleep(4)  # Aguarda resposta

    # Imprime o HTML da tela que carregou após o submit para debug
    print('DEBUG: inputs após submit:')
    for inp in driver.find_elements(By.TAG_NAME, 'input'):
        if inp.is_displayed():
            print(f'  id={inp.get_attribute("id")!r} name={inp.get_attribute("name")!r} value={inp.get_attribute("value")!r}')

    # Extrai telefone e email (ajuste os seletores conforme necessário)
    try:
        telefone = driver.find_element(By.ID, 'telefono').get_attribute('value')
    except:
        telefone = ''
    try:
        email = driver.find_element(By.ID, 'correoElectronico').get_attribute('value')
    except:
        email = ''

    print(f'Resultado para {rut}:')
    print('Telefone:', telefone)
    print('Email:', email)

finally:
    driver.quit()
