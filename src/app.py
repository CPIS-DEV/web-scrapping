from flask import Flask, request, jsonify
from flask_mail import Mail, Message
import os
import time
import requests
import glob
import shutil
from datetime import datetime
from urllib.parse import urljoin

app = Flask(__name__)

# Configurações do Flask-Mail (mantidas iguais)
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'noreplycpis@gmail.com'
app.config['MAIL_PASSWORD'] = 'ssyy cocc mffz uaop'
app.config['MAIL_DEFAULT_SENDER'] = 'noreplycpis@gmail.com'

mail = Mail(app)

def enviar_email(assunto, anexo=None):
    """Função idêntica à original para envio de e-mails."""
    msg = Message(assunto, recipients=["leonardo.pereira@cpis.com.br"])
    if anexo:
        msg.body = f'Segue em anexo arquivo do Diario Oficial do dia {datetime.now().strftime("%d/%m/%Y")}, de nome {assunto}, onde foram encontrados os termos solicitados.'
        with open(f"./downloads/{anexo}", "rb") as fp:
            msg.attach(anexo, "application/pdf", fp.read())
    else:
        msg.body = f'Mensagem enviada para registro de encontro dos termos solicitados no Diario Oficial do dia {datetime.now().strftime("%d/%m/%Y")}, de nome {anexo}. IMPORTANTE: O arquivo não foi enviado por erro do sistema ao anexa-lo. O administrador do sistema deve ser comunicado.'
    mail.send(msg)

def search_website(search_query, from_date, to_date, page_number=1, page_size=20):
    """Função idêntica à original para busca na API."""
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

def baixar_pdf_diretamente(url_pdf, download_dir):
    """Baixa o PDF diretamente da URL sem usar Selenium."""
    os.makedirs(download_dir, exist_ok=True)
    
    # Extrai o nome do arquivo da URL ou usa a data atual
    nome_arquivo = os.path.basename(url_pdf) or f"doe-{datetime.now().strftime('%Y-%m-%d')}.pdf"
    caminho_completo = os.path.join(download_dir, nome_arquivo)
    
    # Baixa o PDF
    response = requests.get(url_pdf, stream=True)
    if response.status_code == 200:
        with open(caminho_completo, 'wb') as f:
            for chunk in response.iter_content(1024):
                f.write(chunk)
        return nome_arquivo
    else:
        print(f"Erro ao baixar PDF: Status {response.status_code}")
        return None

def renomear_pdf(download_dir):
    """Função idêntica à original para renomear PDFs."""
    data_atual = datetime.now().strftime("%Y-%m-%d")
    base_nome = f"{data_atual}"
    novo_nome_arquivo = f"{base_nome}.pdf"
    arquivos_pdf = glob.glob(os.path.join(download_dir, "*.pdf"))
    if arquivos_pdf:
        arquivo_mais_recente = max(arquivos_pdf, key=os.path.getctime)
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

@app.route('/executar-busca', methods=['POST'])
def executar_busca():
    """Endpoint principal - mantém a mesma lógica, mas sem Selenium."""
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
            
            # Modificação principal: Baixa o PDF diretamente da API/URL
            url_pdf = f"https://doe.sp.gov.br/{result['slug']}.pdf"  # Assumindo que a URL do PDF é previsível
            nome_arquivo = baixar_pdf_diretamente(url_pdf, "./downloads")
            
            if nome_arquivo:
                nome_renomeado = renomear_pdf("./downloads")
                enviar_email(result['title'], nome_renomeado)
            else:
                enviar_email(result['title'])  # Envia e-mail sem anexo se o download falhar

        return jsonify({"status": "Busca e Envio executados com sucesso!", "resultados": len(results)})
    else:
        with open("registro.txt", "a", encoding="utf-8") as arquivo:
            arquivo.write("Não foram encontrados resultado para essa busca.\n\n")
        return jsonify({"status": "Nenhum resultado encontrado."})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)