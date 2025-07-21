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
import pytz

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
    from flask import current_app
    try:
        # Garante contexto de aplicação
        with app.app_context():
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
    
def apagar_todos_agendamentos():
    """Remove todos os agendamentos do scheduler em memória."""
    schedule.clear()
    logging.info("Todos os agendamentos foram removidos do scheduler.")

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

def converter_horario_brasilia_para_utc(hora_brasilia: str) -> str:
    """
    Recebe uma string 'HH:MM' no horário de Brasília e retorna uma string 'HH:MM' em UTC.
    """
    tz_brasilia = pytz.timezone("America/Sao_Paulo")
    tz_utc = pytz.utc
    hoje = datetime.now(tz_brasilia).date()
    hora, minuto = map(int, hora_brasilia.split(":"))
    dt_brasilia = tz_brasilia.localize(datetime(hoje.year, hoje.month, hoje.day, hora, minuto))
    dt_utc = dt_brasilia.astimezone(tz_utc)
    return dt_utc.strftime("%H:%M")

def trigger_search(search_query, from_date, to_date):
    """Dispara a busca diretamente sem fazer HTTP request."""
    print("chamando trigger_search")
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
    schedule.clear()
    jobs = load_cron_jobs()
    for job in jobs:
        if job.get('active', True):
            horario_utc = converter_horario_brasilia_para_utc(job['schedule'])
            weekdays = job.get('weekdays')
            if weekdays:
                for day in weekdays:
                    # Exemplo: schedule.every().monday.at("19:00").do(...)
                    getattr(schedule.every(), day.lower()).at(horario_utc).do(
                        trigger_search,
                        search_query=job['search_query'],
                        from_date=job['from_date'],
                        to_date=job['to_date']
                    )
                    logging.info(f"Agendando job '{job['search_query']}' para {horario_utc} UTC em {day.capitalize()} (original: {job['schedule']} BRT)")
            else:
                schedule.every().day.at(horario_utc).do(
                    trigger_search,
                    search_query=job['search_query'],
                    from_date=job['from_date'],
                    to_date=job['to_date']
                )
                logging.info(f"Agendando job '{job['search_query']}' para {horario_utc} UTC (original: {job['schedule']} BRT)")
    logging.info(f"Agendados {len([j for j in jobs if j.get('active', True)])} jobs")

def run_scheduler():
    """Executa o agendador em segundo plano."""
    logging.info("Iniciando scheduler...")
    while True:
        schedule.run_pending()
        time.sleep(1)

@app.route('/cron', methods=['GET', 'POST', 'PUT', 'DELETE'])
def gerencia_crons():
    """Endpoint para gerenciar jobs agendados (CRUD)."""
    if request.method == 'GET':
        # Lista todos os jobs
        return jsonify(load_cron_jobs())

    elif request.method == 'POST':
        # Cria novo job
        new_job = request.json
        required_fields = ['search_query', 'from_date', 'to_date', 'schedule']
        if not all(field in new_job for field in required_fields):
            return jsonify({"status": "error", "message": "Campos obrigatórios faltando"}), 400

        jobs = load_cron_jobs()
        new_id = max([job.get('id', 0) for job in jobs] or [0]) + 1
        new_job['id'] = new_id
        new_job['active'] = new_job.get('active', True)
        jobs.append(new_job)
        save_cron_jobs(jobs)
        apagar_todos_agendamentos()
        schedule_jobs()
        return jsonify({"status": "success", "id": new_id}), 201

    elif request.method == 'PUT':
        # Atualiza um job existente
        update_job = request.json
        if 'id' not in update_job:
            return jsonify({"status": "error", "message": "ID do job não fornecido"}), 400

        jobs = load_cron_jobs()
        for idx, job in enumerate(jobs):
            if job.get('id') == update_job['id']:
                jobs[idx].update(update_job)
                break
        else:
            return jsonify({"status": "error", "message": "Job não encontrado"}), 404

        save_cron_jobs(jobs)
        apagar_todos_agendamentos()
        schedule_jobs()
        return jsonify({"status": "success", "message": "Job atualizado"})

    elif request.method == 'DELETE':
        # Deleta um job pelo ID
        job_id = request.json.get('id')
        if not job_id:
            return jsonify({"status": "error", "message": "ID do job não fornecido"}), 400

        jobs = load_cron_jobs()
        jobs = [job for job in jobs if job.get('id') != job_id]
        save_cron_jobs(jobs)
        apagar_todos_agendamentos()
        schedule_jobs()
        return jsonify({"status": "success", "message": "Job removido"})

    return jsonify({"status": "error", "message": "Método não suportado"}), 405

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

@app.route('/registro', methods=['GET'])
def download_registro():
    """Endpoint para baixar o arquivo registro.txt."""
    from flask import send_file
    registro_path = os.path.join(os.path.dirname(__file__), '..', 'registro.txt')
    if not os.path.exists(registro_path):
        return jsonify({"status": "error", "message": "Arquivo registro.txt não encontrado"}), 404
    return send_file(registro_path, as_attachment=True)

if __name__ == "__main__":
    # Cria diretório de downloads se não existir
    os.makedirs("./downloads", exist_ok=True)

    # Só inicia o scheduler se não for o reloader do Flask
    import os
    if os.environ.get("WERKZEUG_RUN_MAIN") == "true" or not app.debug:
        scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
        scheduler_thread.start()
        schedule_jobs()

    app.run(host="0.0.0.0", port=5000, debug=False)