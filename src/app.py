from flask import Flask, request, jsonify
from flask_mail import Mail, Message
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options
import os
import time
import requests
import glob
import shutil
from datetime import datetime

app = Flask(__name__)

app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'noreplycpis@gmail.com'
app.config['MAIL_PASSWORD'] = 'ssyy cocc mffz uaop'
app.config['MAIL_DEFAULT_SENDER'] = 'noreplycpis@gmail.com'

mail = Mail(app)

def enviar_email(assunto, anexo=None):
    msg = Message(assunto, recipients=["leonardo.pereira@cpis.com.br"])
    if anexo:
        msg.body = f'Segue em anexo arquivo do Diario Oficial do dia {datetime.now().strftime("%d/%m/%Y")}, de nome {assunto}, onde foram encontrados os termos solicitados.'
        with open(f"./downloads/{anexo}", "rb") as fp:
            msg.attach(anexo, "application/pdf", fp.read())
    else:
        msg.body = f'Mensagem enviada para registro de encontro dos termos solicitados no Diario Oficial do dia {datetime.now().strftime("%d/%m/%Y")}, de nome {anexo}. IMPORTANTE: O arquivo não foi enviado por erro do sistema ao anexa-lo. O administrador do sistema deve ser comunicado.'
    mail.send(msg)

def search_website(search_query, from_date, to_date, page_number=1, page_size=20):
    url = "https://do-api-web-search.doe.sp.gov.br/v2/advanced-search/publications"
    params = {
        "PageNumber": page_number,
        "PageSize": page_size,
        "Terms[0]": search_query,
        "FromDate": from_date,
        "ToDate": to_date
    }
    response = requests.get(url, params=params)
    if response.status_code == 200:
        data = response.json()
        return data.get("items", [])
    else:
        print(f"Failed to retrieve the website. Status code: {response.status_code}")
        return []
    
def aguardar_arquivo_liberado(filepath, timeout=10):
    inicio = time.time()
    while True:
        try:
            with open(filepath, 'rb'):
                return True
        except PermissionError:
            if time.time() - inicio > timeout:
                print("Tempo limite para liberação do arquivo atingido.")
                return False
            time.sleep(0.5)

def renomear_pdf(download_dir):
    data_atual = datetime.now().strftime("%Y-%m-%d")
    base_nome = f"{data_atual}"
    novo_nome_arquivo = f"{base_nome}.pdf"
    arquivos_pdf = glob.glob(os.path.join(download_dir, "*.pdf"))
    if arquivos_pdf:
        arquivo_mais_recente = max(arquivos_pdf, key=os.path.getctime)
        aguardar_arquivo_liberado(arquivo_mais_recente)
        novo_caminho = os.path.join(download_dir, novo_nome_arquivo)
        contador = 1
        while os.path.exists(novo_caminho):
            novo_nome_arquivo = f"{base_nome}_{contador}.pdf"
            novo_caminho = os.path.join(download_dir, novo_nome_arquivo)
            contador += 1
        shutil.move(arquivo_mais_recente, novo_caminho)
        print(f"Arquivo renomeado para {novo_nome_arquivo}")
        return novo_nome_arquivo
    else:
        print("Nenhum PDF encontrado para renomear.")
        return None
    
def aguardar_download(download_dir, timeout=120):
    """Aguarda até que não haja arquivos .crdownload e o PDF esteja pronto."""
    inicio = time.time()
    pdf_antes = set(glob.glob(os.path.join(download_dir, "*.pdf")))
    while True:
        # Espera o .crdownload sumir
        if not glob.glob(os.path.join(download_dir, "*.crdownload")):
            break
        if time.time() - inicio > timeout:
            print("Tempo limite de download atingido (.crdownload).")
            return None
        time.sleep(0.5)
    # Espera um novo PDF aparecer
    while True:
        pdf_depois = set(glob.glob(os.path.join(download_dir, "*.pdf")))
        novos_pdfs = pdf_depois - pdf_antes
        if novos_pdfs:
            arquivo_pdf = list(novos_pdfs)[0]
            # Tenta abrir para garantir que não está em uso
            try:
                with open(arquivo_pdf, 'rb'):
                    return arquivo_pdf
            except PermissionError:
                pass
        if time.time() - inicio > timeout:
            print("Tempo limite de download atingido (PDF).")
            return None
        time.sleep(0.5)

def baixar_pdf(url):
    download_dir = os.path.abspath("downloads")
    os.makedirs(download_dir, exist_ok=True)

    chrome_options = Options()
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_experimental_option("prefs", {
        "download.default_directory": download_dir,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "plugins.always_open_pdf_externally": True
    })

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    driver.get(url)
    time.sleep(2)

    try:
        link_pdf = driver.find_element(By.CLASS_NAME, "css-4gzfmr")
        link_pdf.click()
        arquivo_pdf = aguardar_download(download_dir)
        if arquivo_pdf:
            nome_arquivo = renomear_pdf(download_dir)
        else:
            print("Download não concluído ou arquivo não encontrado.")
        time.sleep(2)
    except Exception as e:
        print(f"Erro ao tentar clicar no link: {e}")
    finally:
        driver.quit()
        return nome_arquivo

@app.route('/executar-busca', methods=['POST'])
def executar_busca():
    data = request.json
    search_query = data.get('search_query')
    from_date = data.get('from_date')
    to_date = data.get('to_date')

    if not search_query or not from_date or not to_date:
        return jsonify({"status": "Erro", "message": "Parâmetros de busca inválidos."}), 400

    # Garante que search_query é uma lista
    if isinstance(search_query, str):
        search_query = [search_query]

    data_atual = datetime.now().strftime("%d-%m-%Y")
    results = []

    with open("registro.txt", "a", encoding="utf-8") as arquivo:
        arquivo.write(f"\n\n\nBusca realizada no dia {data_atual}:\n\n")

    for termo in search_query:
        results += search_website(termo, from_date, to_date)

    if results:
        with open("registro.txt", "a", encoding="utf-8") as arquivo:
            arquivo.write(f"Foram encontrados {len(results)} resultados.Os nomes dos arquivos são:\n")
        for result in results:
            with open("registro.txt", "a", encoding="utf-8") as arquivo:
                arquivo.write(f"\t{result['title']}\n")
            nome_arquivo = baixar_pdf(f"https://doe.sp.gov.br/{result['slug']}")
            enviar_email(result['title'], nome_arquivo)
        return jsonify({"status": "Busca e Envio executados com sucesso!", "resultados": len(results)})
    else:
        with open("registro.txt", "a", encoding="utf-8") as arquivo:
            arquivo.write("Não foram encontrados resultado para essa busca.\n\n")
        return jsonify({"status": "Nenhum resultado encontrado."})
    
if __name__ == "__main__":
    app.run(port=5000, debug=True)