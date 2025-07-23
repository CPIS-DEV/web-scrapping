from flask import Flask, request, jsonify
from flask_mail import Mail, Message
from flask_cors import CORS
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options
import os
import schedule
import time
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

limite_envio_global = 6

app = Flask(__name__)

CORS(app, origins=[
    "http://localhost:3000",    # React padrão
    "http://localhost:8080",    # Vue.js padrão
    "http://127.0.0.1:3000",    # Localhost alternativo
    "http://127.0.0.1:8080",    # Localhost alternativo
    "http://127.0.0.1:5173",    # Vite padrão
    "http://localhost:5173"     # Vite padrão
])

app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'noreplycpis@gmail.com'
app.config['MAIL_PASSWORD'] = 'ssyy cocc mffz uaop'
app.config['MAIL_DEFAULT_SENDER'] = 'noreplycpis@gmail.com'

mail = Mail(app)

def load_config():
    """Carrega as configurações do arquivo config.json."""
    try:
        with file_lock:
            with open('config.json', 'r', encoding='utf-8') as f:
                return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        # Configuração padrão se arquivo não existir
        default_config = {
            "email_principal": "leonardo.pereira@cpis.com.br",
            "emails_aviso": [
                "ti@cpis.com.br"
            ],
            "ultima_execucao": "2023-10-01T12:00:00Z"
        }
        save_config(default_config)
        return default_config
    except Exception as e:
        logging.error(f"Erro ao carregar configurações: {str(e)}")
        return {
            "email_principal": "leonardo.pereira@cpis.com.br",
            "emails_aviso": [],
            "ultima_execucao": "2023-10-01T12:00:00Z"
        }

def save_config(config):
    """Salva as configurações no arquivo config.json."""
    try:
        with file_lock:
            with open('config.json', 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logging.error(f"Erro ao salvar configurações: {str(e)}")

def atualizar_ultima_execucao():
    """Atualiza o timestamp da última execução."""
    config = load_config()
    config['ultima_execucao'] = datetime.now().isoformat() + 'Z'
    save_config(config)
    logging.info(f"Última execução atualizada: {config['ultima_execucao']}")

# Lock para operações com arquivos
file_lock = threading.Lock()

def enviar_email(assunto, anexo=None, termo_busca=None, url_original=None, deletar_apos_envio=True):
    # Carregar configurações
    config = load_config()
    email_principal = config.get('email_principal', 'leonardo.pereira@cpis.com.br')
    
    msg = Message(assunto, recipients=[email_principal])
    data_atual = datetime.now().strftime("%d/%m/%Y")
    
    if anexo:
        # Email com anexo
        msg.body = f'''Prezado(a),

Segue em anexo o documento "{assunto}" encontrado na busca realizada no Diário Oficial do Estado de São Paulo em {data_atual}.

📋 DETALHES DO DOCUMENTO:
📄 Título: {assunto}
🔍 Termo de busca: {termo_busca if termo_busca else 'N/A'}
📅 Data da consulta: {data_atual}

🌐 LINK DIRETO PARA O DOCUMENTO:
{url_original if url_original else 'N/A'}

💡 OBSERVAÇÕES:
• Este documento foi encontrado automaticamente pelo sistema de monitoramento
• Verifique o anexo para visualizar o conteúdo completo
• O link direto permite acesso ao documento original no site oficial

Este é um email automático do sistema de monitoramento do Diário Oficial.'''

        try:
            with open(f"./downloads/{anexo}", "rb") as fp:
                msg.attach(anexo, "application/pdf", fp.read())
        except Exception as e:
            logging.error(f"Erro ao anexar arquivo {anexo}: {str(e)}")
            # Se falhar o anexo, enviar só com link
            msg.body += f"\n\n⚠️ AVISO: Não foi possível anexar o arquivo PDF. Use o link direto acima para acessar o documento."
    else:
        # Email só com link
        msg.body = f'''Prezado(a),

Foi encontrado o documento "{assunto}" na busca realizada no Diário Oficial do Estado de São Paulo em {data_atual}.

📋 DETALHES DO DOCUMENTO:
📄 Título: {assunto}
🔍 Termo de busca: {termo_busca if termo_busca else 'N/A'}
📅 Data da consulta: {data_atual}

🌐 ACESSE O DOCUMENTO:
{url_original if url_original else 'Link não disponível'}

💡 OBSERVAÇÕES:
• Este documento foi encontrado automaticamente pelo sistema de monitoramento
• Clique no link acima para visualizar o documento completo no site oficial
• O documento não pôde ser baixado automaticamente

Este é um email automático do sistema de monitoramento do Diário Oficial.'''
    
    try:
        mail.send(msg)
        logging.info(f"Email enviado com sucesso para {email_principal}: {assunto}")

        if deletar_apos_envio and anexo and os.path.exists(f"./downloads/{anexo}"):
            try:
                os.remove(f"./downloads/{anexo}")
                logging.info(f"Arquivo {anexo} deletado com sucesso após envio do email")
            except Exception as e:
                logging.error(f"Erro ao deletar arquivo {anexo}: {str(e)}")

    except Exception as e:
        logging.error(f"Erro ao enviar email: {str(e)}")

def enviar_email_excesso_resultados(termo_busca, total_resultados, results_excedentes, limite_envio):
    """Envia email informativo sobre resultados excedentes."""
    # Carregar configurações
    config = load_config()
    email_principal = config.get('email_principal', 'leonardo.pereira@cpis.com.br')
    
    data_atual = datetime.now().strftime("%d/%m/%Y")
    
    # Criar lista de links excedentes
    links_excedentes = ""
    for i, result in enumerate(results_excedentes, limite_envio + 1):
        url_documento = f"https://doe.sp.gov.br/{result['slug']}"
        links_excedentes += f"{i}º: {result['title']}\n    🔗 {url_documento}\n\n"
    
    assunto = f"AVISO: Limite de envios excedido - Busca por '{termo_busca}'"
    
    msg = Message(assunto, recipients=[email_principal])
    
    msg.body = f'''⚠️ LIMITE DE ENVIOS EXCEDIDO

Prezado(a),

A busca realizada encontrou mais resultados do que o limite configurado para envio de emails com anexos.

📊 RESUMO DA BUSCA:
📅 Data da busca: {data_atual}
🔍 Termo pesquisado: {termo_busca}
📄 Total de resultados encontrados: {total_resultados}
📧 Enviados por email (com anexo): {limite_envio}
⏭️ Resultados excedentes (apenas links): {len(results_excedentes)}

📋 LINKS DOS RESULTADOS EXCEDENTES:
{links_excedentes}

💡 INFORMAÇÕES IMPORTANTES:
• Os primeiros {limite_envio} resultados foram enviados por email com anexos PDF
• Os resultados acima são os documentos adicionais encontrados
• Todos os links direcionam para os documentos originais no site oficial
• Use os links para acessar diretamente os documentos no Diário Oficial

🌐 ACESSO GERAL:
Para consultas adicionais, acesse: https://www.doe.sp.gov.br/

Este é um email automático do sistema de monitoramento do Diário Oficial.'''
    
    try:
        mail.send(msg)
        logging.info(f"Email de excesso de resultados enviado para {email_principal} - termo '{termo_busca}' - {len(results_excedentes)} links adicionais")
    except Exception as e:
        logging.error(f"Erro ao enviar email de excesso de resultados: {str(e)}")

def enviar_email_sem_resultados(termo_busca, data_busca, horario_busca):
    """Envia email informativo quando busca agendada não encontra resultados."""
    # Carregar configurações
    config = load_config()
    email_principal = config.get('email_principal', 'leonardo.pereira@cpis.com.br')
    
    assunto = f"Busca agendada sem resultados - {termo_busca}"
    
    msg = Message(assunto, recipients=[email_principal])
    
    msg.body = f'''🔍 BUSCA AGENDADA SEM RESULTADOS

Prezado(a),

A busca agendada foi executada mas não encontrou nenhum resultado novo para o termo monitorado.

📊 DETALHES DA BUSCA:
📅 Data da busca: {data_busca}
🕐 Horário da busca: {horario_busca} (horário de Brasília)
🔍 Termo pesquisado: {termo_busca}
📄 Resultados encontrados: 0

✅ AÇÕES REALIZADAS:
• Sistema executou a busca automaticamente conforme agendamento
• Verificou o Diário Oficial do Estado de São Paulo na data atual
• Não foram encontrados documentos correspondentes ao termo pesquisado
• Esta notificação foi enviada para informar sobre a execução da busca

💡 INFORMAÇÕES ADICIONAIS:
• O sistema continuará monitorando automaticamente conforme o agendamento
• Uma nova busca será realizada na próxima data/horário programado
• Você será notificado caso sejam encontrados resultados futuros

🔄 PRÓXIMAS AÇÕES:
• O monitoramento permanece ativo
• Nenhuma ação manual é necessária
• O sistema enviará email automaticamente quando houver resultados

🌐 CONSULTA MANUAL:
Para verificação manual, acesse: https://www.doe.sp.gov.br/

Este é um email automático do sistema de monitoramento do Diário Oficial.'''
    
    try:
        mail.send(msg)
        logging.info(f"Email de busca sem resultados enviado para {email_principal} - termo '{termo_busca}' - busca agendada do dia {data_busca}")
    except Exception as e:
        logging.error(f"Erro ao enviar email de busca sem resultados: {str(e)}")

def enviar_email_informativo_resultados(termo_busca, total_resultados, data_busca, horario_busca, tipo_busca="agendada", limite_envio=6):
    """Envia email informativo quando são encontrados resultados em qualquer busca."""
    # Carregar configurações
    config = load_config()
    emails_aviso = config.get('emails_aviso', [])
    
    # Se não há emails de aviso configurados, não enviar
    if not emails_aviso:
        logging.info(f"Nenhum email de aviso configurado - email informativo não enviado para termo '{termo_busca}'")
        return
    
    # Primeiro email da lista é o destinatário principal
    destinatario_principal = emails_aviso[0]
    # Demais emails são cópias (CC)
    emails_cc = emails_aviso[1:] if len(emails_aviso) > 1 else []
    
    # Definir se é busca agendada ou manual
    tipo_texto = "agendada" if tipo_busca == "agendada" else "manual"
    emoji_tipo = "🤖" if tipo_busca == "agendada" else "👤"
    
    # Calcular quantos foram enviados por email
    enviados_por_email = min(total_resultados, limite_envio)
    excedentes = max(0, total_resultados - limite_envio)
    
    assunto = f"✅ Resultados encontrados - {termo_busca}"
    
    msg = Message(assunto, recipients=[destinatario_principal], cc=emails_cc)
    msg.body = f'''{emoji_tipo} ALERTA DE RESULTADOS ENCONTRADOS

Foi realizada uma busca {tipo_texto} e foram encontrados resultados para o termo monitorado.

📊 RESUMO DA BUSCA:
📅 Data da busca: {data_busca}
🕐 Horário da busca: {horario_busca} (horário de Brasília)
🔍 Termo pesquisado: {termo_busca}
📄 Total de resultados: {total_resultados}
📧 Enviados por email: {enviados_por_email}
{"⏭️ Excedentes (apenas links): " + str(excedentes) if excedentes > 0 else ""}

📝 AÇÕES REALIZADAS:
{"✅ Os primeiros " + str(enviados_por_email) + " resultados foram enviados por email com anexos/links" if enviados_por_email > 0 else ""}
{"✅ Email adicional enviado com links dos " + str(excedentes) + " resultados excedentes" if excedentes > 0 else ""}
✅ Todos os resultados foram registrados no arquivo de log do sistema

💡 INFORMAÇÕES ADICIONAIS:
• {"Esta busca foi executada automaticamente pelo sistema de agendamento" if tipo_busca == "agendada" else "Esta busca foi executada manualmente via API"}
• Os arquivos PDF foram baixados e {"anexados aos emails" if total_resultados <= limite_envio else "anexados aos primeiros " + str(limite_envio) + " emails"}
• Verifique sua caixa de entrada para os documentos encontrados

🌐 ACESSO DIRETO:
Para consultar diretamente no site oficial: https://www.doe.sp.gov.br/

🔔 Este é um email informativo automático do sistema de monitoramento.'''
    
    try:
        mail.send(msg)
        destinatarios_log = f"{destinatario_principal}" + (f" (CC: {', '.join(emails_cc)})" if emails_cc else "")
        logging.info(f"Email informativo de resultados enviado para {destinatarios_log} - Termo: '{termo_busca}' | Tipo: {tipo_busca} | Resultados: {total_resultados}")
    except Exception as e:
        logging.error(f"Erro ao enviar email informativo de resultados: {str(e)}")

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

def apagar_todos_agendamentos():
    """Remove todos os agendamentos do scheduler em memória."""
    schedule.clear()
    logging.info("Todos os agendamentos foram removidos do scheduler.")

def trigger_search(search_query, from_date, to_date):
    """Dispara a busca diretamente sem fazer HTTP request."""
    print("chamando trigger_search")
    logging.info(f"Iniciando busca agendada para: {search_query}")

    atualizar_ultima_execucao()
    
    with app.app_context():
        # Garante que search_query é uma lista
        if isinstance(search_query, str):
            search_query = [search_query]

        # NOVA FUNCIONALIDADE: Para tarefas agendadas, sempre usar data atual
        data_atual_str = datetime.now().strftime("%d-%m-%Y")
        data_atual_iso = datetime.now().strftime("%Y-%m-%d")  # Formato ISO para API
        
        tz_brasilia = pytz.timezone("America/Sao_Paulo")
        horario_brasilia = datetime.now(tz_brasilia).strftime("%H:%M:%S")

        # Usar data atual em vez dos parâmetros from_date e to_date
        from_date_atual = data_atual_iso
        to_date_atual = data_atual_iso
        
        logging.info(f"Busca agendada usando data atual: {data_atual_iso} (ignorando datas do JSON)")
        
        results = []

        try:
            with file_lock:
                with open("registro.txt", "a", encoding="utf-8") as arquivo:
                    arquivo.write(f"\n\n\nBusca agendada realizada no dia {data_atual_str} às {horario_brasilia} (horário de Brasília):\n\n")

            for termo in search_query:
                # Usar as datas atuais em vez dos parâmetros
                results += search_website(termo, from_date_atual, to_date_atual)

            if results:
                total_resultados = len(results)
                limite_envio = 6  # ou sua variável global
                
                with file_lock:
                    with open("registro.txt", "a", encoding="utf-8") as arquivo:
                        arquivo.write(f"Foram encontrados {total_resultados} resultados. Os nomes dos arquivos são:\n")
                
                # NOVA FUNCIONALIDADE: Processar apenas os primeiros X resultados
                results_para_envio = results[:limite_envio]
                results_excedentes = results[limite_envio:]
                
                # Processar e enviar os primeiros X resultados
                for result in results_para_envio:
                    with file_lock:
                        with open("registro.txt", "a", encoding="utf-8") as arquivo:
                            arquivo.write(f"\t{result['title']}\n")
                    
                    url_documento = f"https://doe.sp.gov.br/{result['slug']}"
                    nome_arquivo = baixar_pdf(url_documento)

                    if nome_arquivo:
                        nome_renomeado = renomear_pdf("./downloads")
                        enviar_email(result['title'], nome_renomeado, termo, url_documento)
                    else:
                        enviar_email(result['title'], None, termo, url_documento)
                
                # NOVA FUNCIONALIDADE: Enviar email informativo sobre excesso
                if results_excedentes:
                    enviar_email_excesso_resultados(termo, total_resultados, results_excedentes, limite_envio)
                    
                    # Registrar os resultados excedentes no arquivo de log
                    with file_lock:
                        with open("registro.txt", "a", encoding="utf-8") as arquivo:
                            arquivo.write(f"\n--- RESULTADOS EXCEDENTES (não enviados por email) ---\n")
                            for i, result in enumerate(results_excedentes, limite_envio + 1):
                                arquivo.write(f"\t{i}º: {result['title']}\n")
                
                # NOVA FUNCIONALIDADE: Email informativo de resultados encontrados
                termo_formatado = ", ".join(search_query) if isinstance(search_query, list) else search_query
                enviar_email_informativo_resultados(termo_formatado, total_resultados, data_atual_str, horario_brasilia, "agendada", limite_envio)
                        
            else:
                # NOVA FUNCIONALIDADE: Email para busca agendada sem resultados
                with file_lock:
                    with open("registro.txt", "a", encoding="utf-8") as arquivo:
                        arquivo.write("Não foram encontrados resultados para essa busca.\n\n")
                
                # Enviar email informativo sobre busca sem resultados
                termo_formatado = ", ".join(search_query) if isinstance(search_query, list) else search_query
                enviar_email_sem_resultados(termo_formatado, data_atual_str, horario_brasilia)
                        
        except Exception as e:
            logging.error(f"Erro durante busca agendada: {str(e)}")

def schedule_jobs():
    """Agenda os jobs baseado no arquivo JSON."""
    schedule.clear()
    jobs = load_cron_jobs()
    for job in jobs:
        if job.get('active', True):
            horario_utc = converter_horario_brasilia_para_utc(job['schedule'])
            weekdays = job.get('weekdays', [])
            if weekdays:
                for day in weekdays:
                    # Passar None para from_date e to_date já que serão ignorados
                    getattr(schedule.every(), day.lower()).at(horario_utc).do(
                        trigger_search,
                        search_query=job['search_query'],
                        from_date=None,  # ← Será ignorado na função trigger_search
                        to_date=None
                    )
                    logging.info(f"Agendando job '{job['search_query']}' para {horario_utc} em {day.capitalize()}")
            else:
                schedule.every().day.at(horario_utc).do(
                    trigger_search,
                    search_query=job['search_query'],
                    from_date=None,
                    to_date=None     
                )
                logging.info(f"Agendando job '{job['search_query']}' para {horario_utc} diariamente")
    logging.info(f"Agendados {len([j for j in jobs if j.get('active', True)])} jobs")

def run_scheduler():
    """Executa o agendador em segundo plano."""
    logging.info("Iniciando scheduler...")
    while True:
        schedule.run_pending()
        time.sleep(1)
    
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

    # Configurações Chrome otimizadas para AWS/Linux headless
    chrome_options = Options()
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--disable-dev-shm-usage")

    # Opções essenciais para ambiente AWS/Linux sem interface gráfica
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--display=:99")
    chrome_options.add_argument("--remote-debugging-port=9222")
    chrome_options.add_argument("--user-data-dir=/tmp/chrome-data")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-background-timer-throttling")
    chrome_options.add_argument("--disable-backgrounding-occluded-windows")
    chrome_options.add_argument("--disable-renderer-backgrounding")

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

    atualizar_ultima_execucao()

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

    tz_brasilia = pytz.timezone("America/Sao_Paulo")
    horario_brasilia = datetime.now(tz_brasilia).strftime("%H:%M:%S")

    results = []

    with open("registro.txt", "a", encoding="utf-8") as arquivo:
        arquivo.write(f"\n\n\nBusca realizada no dia {data_atual} às {horario_brasilia} (horário de Brasília):\n\n")

    for termo in search_query:
        results += search_website(termo, from_date, to_date)

    if results:
        total_resultados = len(results)
        limite_envio = 6  # ou sua variável global
        
        with open("registro.txt", "a", encoding="utf-8") as arquivo:
            arquivo.write(f"Foram encontrados {total_resultados} resultados. Os nomes dos arquivos são:\n")
            
        # NOVA FUNCIONALIDADE: Processar apenas os primeiros X resultados
        results_para_envio = results[:limite_envio]
        results_excedentes = results[limite_envio:]
        
        # Processar e enviar os primeiros X resultados
        for result in results_para_envio:
            with open("registro.txt", "a", encoding="utf-8") as arquivo:
                arquivo.write(f"\t{result['title']}\n")
            url_documento = f"https://doe.sp.gov.br/{result['slug']}"
            nome_arquivo = baixar_pdf(url_documento)
            enviar_email(result['title'], nome_arquivo, termo, url_documento)
            
        # NOVA FUNCIONALIDADE: Enviar email informativo sobre excesso
        if results_excedentes:
            enviar_email_excesso_resultados(termo, total_resultados, results_excedentes, limite_envio)
            
            # Registrar os resultados excedentes no arquivo de log
            with open("registro.txt", "a", encoding="utf-8") as arquivo:
                arquivo.write(f"\n--- RESULTADOS EXCEDENTES (não enviados por email) ---\n")
                for i, result in enumerate(results_excedentes, limite_envio + 1):
                    arquivo.write(f"\t{i}º: {result['title']}\n")
        
        # NOVA FUNCIONALIDADE: Email informativo de resultados encontrados para busca manual
        termo_formatado = ", ".join(search_query) if isinstance(search_query, list) else search_query
        enviar_email_informativo_resultados(termo_formatado, total_resultados, data_atual, horario_brasilia, "manual", limite_envio)
            
        if results_excedentes:
            return jsonify({
                "status": "Busca executada com limite de envios!", 
                "resultados_totais": total_resultados,
                "enviados": limite_envio,
                "excedentes": len(results_excedentes)
            })
        else:
            return jsonify({"status": "Busca e Envio executados com sucesso!", "resultados": total_resultados})
    else:
        with open("registro.txt", "a", encoding="utf-8") as arquivo:
            arquivo.write("Não foram encontrados resultado para essa busca.\n\n")
        return jsonify({"status": "Nenhum resultado encontrado."})
    
@app.route('/cron', methods=['GET', 'POST', 'PUT', 'DELETE'])
def gerencia_crons():
    """Endpoint para gerenciar jobs agendados (CRUD)."""
    if request.method == 'GET':
        # Lista todos os jobs + informações do sistema
        jobs = load_cron_jobs()
        config = load_config()
        
        response = {
            "jobs": jobs,
            "ultima_execucao": config.get('ultima_execucao', 'Nunca executado'),
            "total_jobs": len(jobs),
            "jobs_ativos": len([job for job in jobs if job.get('active', True)]),
            "jobs_inativos": len([job for job in jobs if not job.get('active', True)])
        }
        
        return jsonify(response)

    elif request.method == 'POST':
        # Cria novo job
        new_job = request.json
        required_fields = ['search_query', 'schedule']
        if not all(field in new_job for field in required_fields):
            return jsonify({"status": "error", "message": "Campos obrigatórios faltando"}), 400

        jobs = load_cron_jobs()
        new_id = max([job.get('id', 0) for job in jobs] or [0]) + 1
        new_job['id'] = new_id
        new_job['active'] = new_job.get('active', True)
        # Garantir que weekdays existe (opcional)
        if 'weekdays' not in new_job:
            new_job['weekdays'] = []
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

@app.route('/registro', methods=['GET'])
def download_registro():
    """Endpoint para baixar o arquivo registro.txt."""
    from flask import send_file
    registro_path = os.path.abspath('registro.txt')
    if not os.path.exists(registro_path):
        return jsonify({"status": "error", "message": "Arquivo registro.txt não encontrado"}), 404
    return send_file(registro_path, as_attachment=True)

@app.route('/config', methods=['GET', 'PUT'])
def gerencia_config():
    """Endpoint para gerenciar configurações do sistema."""
    if request.method == 'GET':
        # Retorna configurações atuais
        return jsonify(load_config())
    
    elif request.method == 'PUT':
        # Atualiza configurações
        nova_config = request.json
        
        # Validações básicas
        if 'email_principal' not in nova_config or not nova_config['email_principal']:
            return jsonify({"status": "error", "message": "email_principal é obrigatório"}), 400
        
        if 'emails_aviso' not in nova_config:
            nova_config['emails_aviso'] = []
        
        # Manter ultima_execucao se não fornecida
        config_atual = load_config()
        if 'ultima_execucao' not in nova_config:
            nova_config['ultima_execucao'] = config_atual.get('ultima_execucao', datetime.now().isoformat() + 'Z')
        
        save_config(nova_config)
        return jsonify({"status": "success", "message": "Configurações atualizadas"})
    
    return jsonify({"status": "error", "message": "Método não suportado"}), 405
    
if __name__ == "__main__":
    # Criar diretório de downloads
    os.makedirs("./downloads", exist_ok=True)
    
    # Carregar e agendar os jobs do JSON
    schedule_jobs()
    
    # Iniciar o scheduler em uma thread separada (background)
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()
    
    logging.info("Aplicação iniciada com scheduler ativo")
    
    # Iniciar aplicação Flask
    app.run(host="0.0.0.0", port=5000, debug=False)