from flask import Flask, request, jsonify
from flask_mail import Mail, Message
import os
import time
import schedule
import threading
import json
import requests
import glob
import shutil
from datetime import datetime
from urllib.parse import urljoin
import logging

# Configuração básica de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app.log'),
        logging.StreamHandler()
    ]
)

app = Flask(__name__)

# Configurações do Flask-Mail
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'noreplycpis@gmail.com'
app.config['MAIL_PASSWORD'] = 'ssyy cocc mffz uaop'
app.config['MAIL_DEFAULT_SENDER'] = 'noreplycpis@gmail.com'

mail = Mail(app)

# Lock para operações com arquivos
file_lock = threading.Lock()

def enviar_email(assunto, anexo=None):
    """Função para envio de e-mails."""
    try:
        msg = Message(assunto, recipients=["leonardo.pereira@cpis.com.br"])
        if anexo:
            msg.body = f'Segue em anexo arquivo do Diario Oficial do dia {datetime.now().strftime("%d/%m/%Y")}, de nome {assunto}, onde foram encontrados os termos solicitados.'
            with open(f"./downloads/{anexo}", "rb") as fp:
                msg.attach(anexo, "application/pdf", fp.read())
        else:
            msg.body = f'Mensagem enviada para registro de encontro dos termos solicitados no Diario Oficial do dia {datetime.now().strftime("%d/%m/%Y")}, de nome {assunto}. IMPORTANTE: O arquivo não foi enviado por erro do sistema ao anexa-lo. O administrador do sistema deve ser comunicado.'
        mail.send(msg)
        logging.info(f"E-mail enviado com sucesso: {assunto}")
    except Exception as e:
        logging.error(f"Erro ao enviar e-mail: {str(e)}")

def search_website(search_query, from_date, to_date, page_number=1, page_size=20):
    """Função para busca na API."""
    url = "https://do-api-web-search.doe.sp.gov.br/v2/advanced-search/publications"
    params = {
        "PageNumber": page_number,
        "PageSize": page_size,
        "Terms[0]": search_query,
        "FromDate": from_date,
        "ToDate": to_date
    }
    
    try:
        response = requests.get(url, params=params)
        if response.status_code == 200:
            data = response.json()
            return data.get("items", [])
        else:
            logging.error(f"Falha na requisição. Status code: {response.status_code}")
            return []
    except Exception as e:
        logging.error(f"Erro na busca: {str(e)}")
        return []

def baixar_pdf_diretamente(url_pdf, download_dir):
    """Baixa o PDF diretamente da URL."""
    os.makedirs(download_dir, exist_ok=True)
    
    nome_arquivo = os.path.basename(url_pdf) or f"doe-{datetime.now().strftime('%Y-%m-%d')}.pdf"
    caminho_completo = os.path.join(download_dir, nome_arquivo)
    
    try:
        response = requests.get(url_pdf, stream=True, timeout=30)
        if response.status_code == 200:
            with open(caminho_completo, 'wb') as f:
                for chunk in response.iter_content(1024):
                    f.write(chunk)
            logging.info(f"PDF baixado com sucesso: {nome_arquivo}")
            return nome_arquivo
        else:
            logging.error(f"Erro ao baixar PDF. Status: {response.status_code}")
            return None
    except Exception as e:
        logging.error(f"Erro no download do PDF: {str(e)}")
        return None

def renomear_pdf(download_dir):
    """Função para renomear PDFs."""
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
        logging.info(f"Arquivo renomeado para {novo_nome_arquivo}")
        return novo_nome_arquivo
    
    logging.warning("Nenhum PDF encontrado para renomear.")
    return None

def load_cron_jobs():
    """Carrega os jobs agendados do arquivo JSON."""
    try:
        with file_lock:
            with open('cron_jobs.json', 'r') as f:
                return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []
    except Exception as e:
        logging.error(f"Erro ao carregar cron jobs: {str(e)}")
        return []

def save_cron_jobs(jobs):
    """Salva os jobs agendados no arquivo JSON."""
    try:
        with file_lock:
            with open('cron_jobs.json', 'w') as f:
                json.dump(jobs, f, indent=2)
    except Exception as e:
        logging.error(f"Erro ao salvar cron jobs: {str(e)}")

def trigger_search(search_query, from_date, to_date):
    """Dispara a busca diretamente sem fazer HTTP request."""
    logging.info(f"Iniciando busca agendada para: {search_query}")
    
    # Garante que search_query é uma lista
    if isinstance(search_query, str):
        search_query = [search_query]

    data_atual = datetime.now().strftime("%d-%m-%Y")
    results = []

    try:
        with file_lock:
            with open("registro.txt", "a", encoding="utf-8") as arquivo:
                arquivo.write(f"\n\n\nBusca agendada realizada no dia {data_atual}:\n\n")

        for termo in search_query:
            results += search_website(termo, from_date, to_date)

        if results:
            with file_lock:
                with open("registro.txt", "a", encoding="utf-8") as arquivo:
                    arquivo.write(f"Foram encontrados {len(results)} resultados. Os nomes dos arquivos são:\n")
            
            for result in results:
                with file_lock:
                    with open("registro.txt", "a", encoding="utf-8") as arquivo:
                        arquivo.write(f"\t{result['title']}\n")
                
                url_pdf = f"https://doe.sp.gov.br/{result['slug']}.pdf"
                nome_arquivo = baixar_pdf_diretamente(url_pdf, "./downloads")
                
                if nome_arquivo:
                    nome_renomeado = renomear_pdf("./downloads")
                    enviar_email(result['title'], nome_renomeado)
                else:
                    enviar_email(result['title'])
                    
        else:
            with file_lock:
                with open("registro.txt", "a", encoding="utf-8") as arquivo:
                    arquivo.write("Não foram encontrados resultados para essa busca.\n\n")
                    
    except Exception as e:
        logging.error(f"Erro durante busca agendada: {str(e)}")

def schedule_jobs():
    """Agenda os jobs baseado no arquivo JSON."""
    schedule.clear()  # Limpa todos os jobs existentes
    jobs = load_cron_jobs()
    
    for job in jobs:
        if job.get('active', True):
            schedule.every().day.at(job['schedule']).do(
                trigger_search,
                search_query=job['search_query'],
                from_date=job['from_date'],
                to_date=job['to_date']
            )
    logging.info(f"Agendados {len(jobs)} jobs")

def run_scheduler():
    """Executa o agendador em segundo plano."""
    logging.info("Iniciando scheduler...")
    while True:
        schedule.run_pending()
        time.sleep(60)

@app.route('/executar-busca', methods=['POST'])
def executar_busca():
    """Endpoint para busca manual."""
    data = request.json
    search_query = data.get('search_query')
    from_date = data.get('from_date')
    to_date = data.get('to_date')

    if not search_query or not from_date or not to_date:
        return jsonify({"status": "error", "message": "Parâmetros de busca inválidos."}), 400

    # Dispara a busca diretamente
    trigger_search(search_query, from_date, to_date)
    return jsonify({"status": "success", "message": "Busca iniciada"})

@app.route('/cron', methods=['GET', 'POST', 'DELETE'])
def gerencia_crons():
    """Endpoint para gerenciar jobs agendados."""
    if request.method == 'POST':
        new_job = request.json
        
        # Validação dos campos obrigatórios
        required_fields = ['search_query', 'from_date', 'to_date', 'schedule']
        if not all(field in new_job for field in required_fields):
            return jsonify({"status": "error", "message": "Campos obrigatórios faltando"}), 400
        
        jobs = load_cron_jobs()
        
        # Gera um ID único
        new_id = max(job['id'] for job in jobs) + 1 if jobs else 1
        new_job['id'] = new_id
        new_job['active'] = new_job.get('active', True)
        
        jobs.append(new_job)
        save_cron_jobs(jobs)
        schedule_jobs()  # Reagenda tudo
        
        return jsonify({"status": "success", "id": new_id}), 201
    
    elif request.method == 'DELETE':
        job_id = request.json.get('id')
        if not job_id:
            return jsonify({"status": "error", "message": "ID do job não fornecido"}), 400
            
        jobs = load_cron_jobs()
        jobs = [job for job in jobs if job['id'] != job_id]
        save_cron_jobs(jobs)
        schedule_jobs()  # Reagenda tudo
        
        return jsonify({"status": "success", "message": "Job removido"})
    
    # GET request
    return jsonify(load_cron_jobs())

if __name__ == "__main__":
    # Cria diretório de downloads se não existir
    os.makedirs("./downloads", exist_ok=True)
    
    # Inicia o scheduler em uma thread separada
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()
    
    # Carrega e agenda os jobs existentes
    schedule_jobs()
    
    # Inicia o servidor Flask
    app.run(host="0.0.0.0", port=5000, debug=True)