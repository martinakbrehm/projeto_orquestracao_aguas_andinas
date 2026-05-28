"""
testa_selenium_xhr.py — Captura resposta AJAX do sendRegistro via interceptação de XHR no Selenium
"""
import sys
sys.path.insert(0, '.')

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time

rut = sys.argv[1] if len(sys.argv) >= 2 else '10031478-9'

options = uc.ChromeOptions()
options.add_argument('--disable-gpu')
options.add_argument('--no-sandbox')
driver = uc.Chrome(options=options)

try:
    driver.get('https://www.aguasandinas.cl/web/aguasandinas/registrese')
    WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.ID, 'rutUsuario')))
    time.sleep(2)

    # Injeta interceptador XHR antes de chamar sendRegistro
    driver.execute_script("""
        window._xhr_response = null;
        var origOpen = XMLHttpRequest.prototype.open;
        var origSend = XMLHttpRequest.prototype.send;
        XMLHttpRequest.prototype.open = function(m, url) {
            this._url = url;
            origOpen.apply(this, arguments);
        };
        XMLHttpRequest.prototype.send = function(body) {
            var xhr = this;
            this.addEventListener('load', function() {
                if (xhr._url && xhr._url.indexOf('obt') > -1) {
                    window._xhr_response = xhr.responseText;
                }
            });
            origSend.apply(this, arguments);
        };
    """)

    # Preenche o campo de RUT usando JS (sem formatação automática)
    campo = driver.find_element(By.ID, 'rutUsuario')
    driver.execute_script("arguments[0].value = arguments[1];", campo, rut)
    driver.execute_script("arguments[0].dispatchEvent(new Event('input'));", campo)
    driver.execute_script("arguments[0].dispatchEvent(new Event('change'));", campo)

    # Chama sendRegistro diretamente via JavaScript
    driver.execute_script("sendRegistro('persona');")
    time.sleep(5)

    # Captura a resposta do XHR interceptado
    resp = driver.execute_script("return window._xhr_response;")
    print('Resposta XHR:', resp)

    # Verifica se avançou para PASO 2 e captura campos visíveis
    print('\nInputs visíveis após submit:')
    for inp in driver.find_elements(By.TAG_NAME, 'input'):
        if inp.is_displayed():
            print(f'  id={inp.get_attribute("id")!r} name={inp.get_attribute("name")!r} value={inp.get_attribute("value")!r}')

    # Verifica divs/spans com dados de contato
    for sel in ['#telefono', '#correoElectronico', '.telefono', '.email', '[id*=telefon]', '[id*=correo]', '[id*=email]']:
        try:
            el = driver.find_element(By.CSS_SELECTOR, sel)
            print(f'Encontrado {sel}: value={el.get_attribute("value")!r} text={el.text!r}')
        except:
            pass

finally:
    driver.quit()
