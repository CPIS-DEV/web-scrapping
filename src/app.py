from flask import Flask, request, jsonify
from flask_mail import Mail, Message
from flask_cors import CORS, cross_origin
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options
from datetime import datetime, time, timedelta
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
import bcrypt

busca_lock = threading.Lock()

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

CORS(app,
     resources={r"/*": {
         "origins": [
             "https://www.monitoramento.cpis.com.br",
             "https://api.monitoramento.cpis.com.br"
         ],
         "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
         "allow_headers": ["Content-Type", "Authorization"]
     }},
     supports_credentials=True
)

@app.errorhandler(400)
@cross_origin(origins=[
    "https://www.monitoramento.cpis.com.br",
    "https://api.monitoramento.cpis.com.br"
])
def bad_request(error):
    return jsonify({"status": "error", "message": "Requisição inválida"}), 400

@app.errorhandler(500)
@cross_origin(origins=[
    "https://www.monitoramento.cpis.com.br",
    "https://api.monitoramento.cpis.com.br"
])
def internal_error(error):
    return jsonify({"status": "error", "message": "Erro interno do servidor"}), 500

@app.errorhandler(504)
@cross_origin(origins=[
    "https://www.monitoramento.cpis.com.br",
    "https://api.monitoramento.cpis.com.br"
])
def gateway_timeout(error):
    return jsonify({"status": "error", "message": "Tempo limite da porta de entrada excedido"}), 504

app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'noreplycpis@gmail.com'
app.config['MAIL_PASSWORD'] = 'ssyy cocc mffz uaop'
app.config['MAIL_DEFAULT_SENDER'] = 'noreplycpis@gmail.com'

mail = Mail(app)

# 🔐 CONFIGURAÇÕES JWT
app.config['JWT_SECRET_KEY'] = 'cpis-webscraper-jwt-secret-2024-super-seguro'
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = False  # Token nunca expira

jwt = JWTManager(app)

# 👥 DATABASE DE USUÁRIOS (em produção, usar banco de dados real)
USERS_DB = {
    "admin": {
        "password_hash": bcrypt.hashpw("cpis@2025##".encode('utf-8'), bcrypt.gensalt()).decode('utf-8'),
        "role": "admin"
    },
    "leonardo": {
        "password_hash": bcrypt.hashpw("cpis2025".encode('utf-8'), bcrypt.gensalt()).decode('utf-8'),
        "role": "user"
    },
    "cpis": {
        "password_hash": bcrypt.hashpw("webscraper2025".encode('utf-8'), bcrypt.gensalt()).decode('utf-8'),
        "role": "user"
    },
    "ti": {
        "password_hash": bcrypt.hashpw("ti@cpis2025".encode('utf-8'), bcrypt.gensalt()).decode('utf-8'),
        "role": "user"
    }
}

def verificar_credenciais(username, password):
    """Verifica se usuário e senha estão corretos."""
    user = USERS_DB.get(username)
    if user and bcrypt.checkpw(password.encode('utf-8'), user['password_hash'].encode('utf-8')):
        return user
    return None

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

def enviar_email(assunto, anexo=None, termo_busca=None, url_original=None, deletar_apos_envio=True, destinatario=None):
    """
    Envia email com anexo PDF se o arquivo tiver até 25MB.
    Se o arquivo for maior, envia apenas o link do documento.
    """
    config = load_config()
    email_principal = config.get('email_principal', 'leonardo.pereira@cpis.com.br')
    if destinatario:
        destinatarios = [destinatario]
    else:
        destinatarios = [config.get('email_principal', 'leonardo.pereira@cpis.com.br')]
    msg = Message(assunto, recipients=destinatarios)
    data_atual = datetime.now().strftime("%d/%m/%Y")

    anexo_path = f"./downloads/{anexo}" if anexo else None
    anexo_grande = False
    tamanho_mb = 0

    if anexo_path and os.path.exists(anexo_path):
        tamanho_mb = os.path.getsize(anexo_path) / (1024 * 1024)
        if tamanho_mb > 25:
            anexo_grande = True

    if anexo and not anexo_grande:
        # Email com anexo (até 25MB)
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
            with open(anexo_path, "rb") as fp:
                msg.attach(anexo, "application/pdf", fp.read())
        except Exception as e:
            logging.error(f"Erro ao anexar arquivo {anexo}: {str(e)}")
            msg.body += f"\n\n⚠️ AVISO: Não foi possível anexar o arquivo PDF. Use o link direto acima para acessar o documento."
    else:
        # Email só com link (anexo grande ou não existe)
        motivo = ""
        if anexo_grande:
            motivo = f"O arquivo PDF excede o limite de 25MB do Gmail ({tamanho_mb:.2f}MB)."
        else:
            motivo = "O arquivo PDF não pôde ser anexado automaticamente."
        msg.body = f'''Prezado(a),

O documento "{assunto}" encontrado na busca realizada no Diário Oficial do Estado de São Paulo em {data_atual} não pôde ser anexado ao email, devido seu tamanho.

📋 DETALHES DO DOCUMENTO:
📄 Título: {assunto}
🔍 Termo de busca: {termo_busca if termo_busca else 'N/A'}
📅 Data da consulta: {data_atual}

🌐 LINK DIRETO PARA O DOCUMENTO:
{url_original if url_original else 'N/A'}

💡 OBSERVAÇÕES:
• {motivo}
• Para acessar o documento, utilize o link acima
• Este é um email automático do sistema de monitoramento do Diário Oficial.
'''

    try:
        mail.send(msg)
        logging.info(f"Email enviado com sucesso para {email_principal}: {assunto}")

        if deletar_apos_envio and anexo_path and os.path.exists(anexo_path):
            try:
                os.remove(anexo_path)
                logging.info(f"Arquivo {anexo} deletado com sucesso após envio do email")
            except Exception as e:
                logging.error(f"Erro ao deletar arquivo {anexo}: {str(e)}")

    except Exception as e:
        logging.error(f"Erro ao enviar email: {str(e)}")

def enviar_email_excesso_resultados(termo_busca, total_resultados, todos_resultados, limite_envio, destinatario_extra=None):
    """
    Envia email informativo sobre todos os resultados encontrados, incluindo os enviados por anexo.
    """
    config = load_config()
    email_principal = config.get('email_principal', 'leonardo.pereira@cpis.com.br')
    destinatarios = [email_principal]
    if destinatario_extra and destinatario_extra not in destinatarios:
        destinatarios.append(destinatario_extra)
    data_atual = datetime.now().strftime("%d/%m/%Y")

    # Criar lista de links de TODOS os resultados
    links_todos = ""
    for i, result in enumerate(todos_resultados, 1):
        url_documento = f"https://doe.sp.gov.br/{result['slug']}"
        links_todos += f"{i}º: {result['title']}\n    🔗 {url_documento}\n\n"

    assunto = f"AVISO: Resumo completo da busca por '{termo_busca}'"

    msg = Message(assunto, recipients=destinatarios)
    msg.body = f'''⚠️ RESUMO COMPLETO DA BUSCA

Prezado(a),

A busca realizada encontrou os seguintes resultados para o termo pesquisado.

📊 RESUMO DA BUSCA:
📅 Data da busca: {data_atual}
🔍 Termo pesquisado: {termo_busca}
📄 Total de resultados encontrados: {total_resultados}
📧 Enviados por email (com anexo): {limite_envio}
⏭️ Resultados excedentes (apenas links): {max(0, total_resultados - limite_envio)}

📋 TODOS OS RESULTADOS ENCONTRADOS:
{links_todos}

💡 INFORMAÇÕES IMPORTANTES:
• Os primeiros {limite_envio} resultados foram enviados por email com anexos PDF
• Todos os resultados estão listados acima, inclusive os já enviados por anexo
• Use os links para acessar diretamente os documentos no Diário Oficial

🌐 ACESSO GERAL:
Para consultas adicionais, acesse: https://www.doe.sp.gov.br/

Este é um email automático do sistema de monitoramento do Diário Oficial.'''

    try:
        mail.send(msg)
        logging.info(f"Email de resumo completo enviado para {email_principal} - termo '{termo_busca}' - {total_resultados} resultados listados")
    except Exception as e:
        logging.error(f"Erro ao enviar email de resumo completo: {str(e)}")

def enviar_email_sem_resultados(termo_busca, data_busca, horario_busca, destinatario_extra=None):
    """Envia email informativo quando busca agendada não encontra resultados."""
    # Carregar configurações
    config = load_config()
    emails_aviso = config.get('emails_aviso', [])
    email_principal = config.get('email_principal', 'leonardo.pereira@cpis.com.br')
    destinatarios = list(set([email_principal] + emails_aviso))
    if destinatario_extra and destinatario_extra not in destinatarios:
        destinatarios.append(destinatario_extra)
    
    assunto = f"Busca agendada sem resultados - {termo_busca}"
    
    msg = Message(assunto, recipients=destinatarios)
    
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

🌐 CONSULTA MANUAL:
Para verificação manual, acesse: https://www.doe.sp.gov.br/

Este é um email automático do sistema de monitoramento do Diário Oficial.'''
    
    try:
        mail.send(msg)
        logging.info(f"Email de busca sem resultados enviado para {', '.join(destinatarios)} - termo '{termo_busca}' - busca agendada do dia {data_busca}")
    except Exception as e:
        logging.error(f"Erro ao enviar email de busca sem resultados: {str(e)}")

def enviar_email_informativo_resultados(termo_busca, total_resultados, data_busca, horario_busca, tipo_busca="agendada", limite_envio=6, resultados=None, destinatario_extra=None):
    """Envia email informativo quando são encontrados resultados em qualquer busca, incluindo os links dos resultados."""
    config = load_config()
    emails_aviso = config.get('emails_aviso', [])

    if not emails_aviso and not destinatario_extra:
        logging.info(f"Nenhum email de aviso configurado - email informativo não enviado para termo '{termo_busca}'")
        return
    
    destinatario_principal = emails_aviso[0] if emails_aviso else None
    emails_cc = emails_aviso[1:] if len(emails_aviso) > 1 else []
    recipients = []
    if destinatario_principal:
        recipients.append(destinatario_principal)
    if total_resultados <= limite_envio and destinatario_extra and destinatario_extra not in recipients and destinatario_extra not in emails_cc:
        recipients.append(destinatario_extra)
    
    
    tipo_texto = "agendada" if tipo_busca == "agendada" else "manual"
    emoji_tipo = "🤖" if tipo_busca == "agendada" else "👤"
    
    enviados_por_email = total_resultados if total_resultados <= limite_envio else limite_envio
    excedentes = 0 if total_resultados <= limite_envio else total_resultados - limite_envio
    
    # Montar lista de links dos resultados
    links_resultados = ""
    if resultados:
        for i, result in enumerate(resultados, 1):
            url_documento = f"https://doe.sp.gov.br/{result['slug']}"
            links_resultados += f"{i}º: {result['title']}\n    🔗 {url_documento}\n\n"
    
    assunto = f"✅ Resultados encontrados - {termo_busca}"
    
    msg = Message(assunto, recipients=recipients, cc=emails_cc)
    msg.body = f'''{emoji_tipo} ALERTA DE RESULTADOS ENCONTRADOS

Foi realizada uma busca {tipo_texto} e foram encontrados resultados para o termo monitorado.

📊 RESUMO DA BUSCA:
📅 Data da busca: {data_busca}
🕐 Horário da busca: {horario_busca} (horário de Brasília)
🔍 Termo pesquisado: {termo_busca}
📄 Total de resultados: {total_resultados}
📧 Enviados por email: {enviados_por_email}
{"⏭️ Excedentes (apenas links): " + str(excedentes) if excedentes > 0 else ""}

📋 LINKS DOS RESULTADOS ENCONTRADOS:
{links_resultados if links_resultados else "Nenhum link disponível."}

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

def enviar_email_erro_busca_agendada(erro, search_query, from_date, to_date, data_busca, horario_busca):
    """Envia notificação de erro em busca agendada para o responsável."""
    destinatarios = list(set([
        "leonardo.pereira@cpis.com.br",
        load_config().get('email_principal', 'leonardo.pereira@cpis.com.br')
    ]))
    assunto = f"❌ ERRO NA BUSCA AGENDADA - {search_query}"
    msg = Message(assunto, recipients=destinatarios)
    msg.body = f'''⚠️ ERRO DURANTE BUSCA AGENDADA

Ocorreu um erro durante a execução de uma busca agendada.

📊 DADOS DA BUSCA:
• Termo(s): {search_query}
• Período: {from_date} até {to_date}
• Data/Hora da execução: {data_busca} às {horario_busca} (horário de Brasília)

❗ DETALHES DO ERRO:
{erro}

Por favor, verifique os logs do sistema para mais detalhes.

Este é um alerta automático do sistema de monitoramento do Diário Oficial.
'''
    try:
        mail.send(msg)
        logging.info(f"Email de erro de busca agendada enviado para {', '.join(destinatarios)}")
    except Exception as e:
        logging.error(f"Erro ao enviar email de erro de busca agendada: {str(e)}")

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

def get_dates_for_job(job):
    quant_dias = int(job.get("quant_dias", 0))
    today = datetime.now().date()
    from_date = (today - timedelta(days=quant_dias)).strftime("%Y-%m-%d")
    to_date = today.strftime("%Y-%m-%d")
    return from_date, to_date
    
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
    """Dispara a busca agendada, calcula datas usando quant_dias e processa resultados."""
    logging.info(f"Iniciando busca agendada para: {search_query}")

    with busca_lock:
        atualizar_ultima_execucao()
        with app.app_context():
            # Garante que search_query é uma lista
            if isinstance(search_query, str):
                search_query_list = [search_query]
            else:
                search_query_list = search_query

            # Se chamado pelo agendamento, calcula as datas usando quant_dias
            if from_date is None or to_date is None:
                jobs = load_cron_jobs()
                job_encontrado = None
                for job in jobs:
                    job_query = job.get("search_query")
                    # Normaliza para comparar corretamente
                    if job_query == search_query or job_query == search_query_list:
                        job_encontrado = job
                        break
                    if isinstance(job_query, list) and job_query == search_query_list:
                        job_encontrado = job
                        break
                    if isinstance(job_query, str) and [job_query] == search_query_list:
                        job_encontrado = job
                        break
                if job_encontrado:
                    from_date, to_date = get_dates_for_job(job_encontrado)
                    email_envio = job_encontrado.get("email_envio")
                else:
                    today = datetime.now().strftime("%Y-%m-%d")
                    from_date, to_date = today, today
                    email_envio = None 

            data_atual_str = datetime.now().strftime("%d-%m-%Y")
            tz_brasilia = pytz.timezone("America/Sao_Paulo")
            horario_brasilia = datetime.now(tz_brasilia).strftime("%H:%M:%S")

            results = []

            try:
                with file_lock:
                    with open("registro.txt", "a", encoding="utf-8") as arquivo:
                        arquivo.write(f"\n\n\nBusca agendada realizada no dia {data_atual_str} às {horario_brasilia} (horário de Brasília):\n\n")

                for termo in search_query_list:
                    resultados_termo = search_website(termo, from_date, to_date)
                    for r in resultados_termo:
                        r['termo_busca'] = termo
                    results += resultados_termo

                total_resultados = len(results)
                limite_envio = 6
                results_para_envio = results[:limite_envio]
                results_excedentes = results[limite_envio:] 

                for result in results_para_envio:
                    url_documento = f"https://doe.sp.gov.br/{result['slug']}"
                    nome_arquivo = baixar_pdf(url_documento)
                    if not nome_arquivo:
                        logging.warning(f"Não foi possível baixar ou renomear o PDF para: {url_documento}")
                    termo_resultado = result.get('termo_busca', '')
                    enviar_email(result['title'], nome_arquivo, termo_resultado, url_documento, destinatario=email_envio)

                if results_excedentes:
                    enviar_email_excesso_resultados(termo, total_resultados, results, limite_envio, destinatario_extra=email_envio)

                termo_formatado = ", ".join(search_query_list)

                if len(results) > 0:
                    enviar_email_informativo_resultados(
                        termo_formatado,
                        total_resultados,
                        data_atual_str,
                        horario_brasilia,
                        "agendada",
                        limite_envio,
                        resultados=results,
                        destinatario_extra=email_envio
                    )
                    with open("registro.txt", "a", encoding="utf-8") as arquivo:
                        arquivo.write(f"Foram encontrados {total_resultados} resultados. Os nomes dos arquivos são:\n")
                        for i, result in enumerate(results, 1):
                            arquivo.write(f"\t{i}º: {result['title']}\n")
                else:
                    with open("registro.txt", "a", encoding="utf-8") as arquivo:
                        arquivo.write("Nenhum resultado foi encontrado essa busca.\n\n")
                    enviar_email_sem_resultados(
                        termo_formatado,
                        data_atual_str,
                        horario_brasilia,
                        destinatario_extra=email_envio
                    )

            except Exception as e:
                logging.error(f"Erro durante busca agendada: {str(e)}")
                # Envia notificação de erro
                enviar_email_erro_busca_agendada(
                    erro=str(e),
                    search_query=search_query,
                    from_date=from_date,
                    to_date=to_date,
                    data_busca=data_atual_str,
                    horario_busca=horario_brasilia
                )

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
                    getattr(schedule.every(), day.lower()).at(horario_utc).do(
                        trigger_search,
                        search_query=job['search_query'],
                        from_date=None,  # ← Será calculado usando quant_dias
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
    nome_arquivo = None

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
    
@app.route('/login', methods=['POST'])
def login():
    """Endpoint para fazer login e obter token JWT."""
    try:
        data = request.json
        
        if not data or 'username' not in data or 'password' not in data:
            return jsonify({
                "status": "error", 
                "message": "Username e password são obrigatórios"
            }), 400
        
        username = data['username']
        password = data['password']
        
        user = verificar_credenciais(username, password)
        
        if user:
            # Criar token JWT
            access_token = create_access_token(
                identity=username,
                additional_claims={"role": user["role"]}
            )
            
            logging.info(f"✅ Login realizado com sucesso para usuário: {username}")
            
            return jsonify({
                "status": "success",
                "message": "Login realizado com sucesso",
                "access_token": access_token,
                "user": {
                    "username": username,
                    "role": user["role"]
                }
            }), 200
        else:
            logging.warning(f"❌ Tentativa de login falhada para usuário: {username}")
            return jsonify({
                "status": "error",
                "message": "Credenciais inválidas"
            }), 401
            
    except Exception as e:
        logging.error(f"❌ Erro no endpoint de login: {str(e)}")
        return jsonify({
            "status": "error",
            "message": "Erro interno do servidor"
        }), 500

@app.route('/verify-token', methods=['GET'])
@jwt_required()
def verify_token():
    """Verifica se o token é válido."""
    try:
        current_user = get_jwt_identity()
        user_data = USERS_DB.get(current_user, {})
        
        return jsonify({
            "status": "success",
            "message": "Token válido",
            "user": {
                "username": current_user,
                "role": user_data.get("role", "user")
            }
        }), 200
    except Exception as e:
        logging.error(f"❌ Erro na verificação de token: {str(e)}")
        return jsonify({
            "status": "error",
            "message": "Token inválido"
        }), 401

@app.route('/change-password', methods=['PUT'])
@jwt_required()
def change_password():
    """Permite ao usuário alterar sua própria senha."""
    try:
        current_user = get_jwt_identity()
        data = request.json
        
        if not data or 'current_password' not in data or 'new_password' not in data:
            return jsonify({
                "status": "error",
                "message": "Senha atual e nova senha são obrigatórias"
            }), 400
        
        # Verificar senha atual
        if not verificar_credenciais(current_user, data['current_password']):
            return jsonify({
                "status": "error",
                "message": "Senha atual incorreta"
            }), 401
        
        # Atualizar senha (em produção, salvar em banco de dados)
        new_password_hash = bcrypt.hashpw(data['new_password'].encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        USERS_DB[current_user]['password_hash'] = new_password_hash
        
        logging.info(f"🔐 Senha alterada com sucesso para usuário: {current_user}")
        
        return jsonify({
            "status": "success",
            "message": "Senha alterada com sucesso"
        }), 200
        
    except Exception as e:
        logging.error(f"❌ Erro ao alterar senha: {str(e)}")
        return jsonify({
            "status": "error",
            "message": "Erro interno do servidor"
        }), 500

# 🔓 ENDPOINT PÚBLICO PARA STATUS
@app.route('/status', methods=['GET'])
def status():
    """Endpoint público para verificar se API está online."""
    try:
        jobs = load_cron_jobs()
        config = load_config()
        
        return jsonify({
            "status": "online",
            "message": "Web Scraper API está funcionando",
            "timestamp": datetime.now().isoformat() + 'Z',
            "jobs_ativos": len([j for j in jobs if j.get('active', True)]),
            "jobs_total": len(jobs),
            "ultima_execucao": config.get('ultima_execucao', 'Nunca executado')
        }), 200
    except Exception as e:
        logging.error(f"❌ Erro no endpoint de status: {str(e)}")
        return jsonify({
            "status": "error",
            "message": "Erro ao obter status"
        }), 500

@app.route('/executar-busca', methods=['POST'])
@jwt_required()
def executar_busca():
    current_user = get_jwt_identity()
    logging.info(f"🔍 Busca manual executada por usuário: {current_user}")

    with busca_lock:
        # Atualiza a última execução
        atualizar_ultima_execucao()

        data = request.json
        search_query = data.get('search_query')
        from_date = data.get('from_date')
        to_date = data.get('to_date')

        if not search_query or not from_date or not to_date:
            return jsonify({
                "status": "Erro", 
                "message": "Parâmetros de busca inválidos.",
                "executado_por": current_user
            }), 400

        # Garante que search_query é uma lista
        if isinstance(search_query, str):
            search_query = [search_query]

        data_atual = datetime.now().strftime("%d-%m-%Y")
        tz_brasilia = pytz.timezone("America/Sao_Paulo")
        horario_brasilia = datetime.now(tz_brasilia).strftime("%H:%M:%S")

        results = []

        with open("registro.txt", "a", encoding="utf-8") as arquivo:
            arquivo.write(f"\n\n\nBusca realizada no dia {data_atual} às {horario_brasilia} (horário de Brasília):\n")
            arquivo.write(f"Executada por usuário: {current_user}\n\n")

        for termo in search_query:
            results += search_website(termo, from_date, to_date)

        if results:
            total_resultados = len(results)
            limite_envio = 6

            with open("registro.txt", "a", encoding="utf-8") as arquivo:
                arquivo.write(f"Foram encontrados {total_resultados} resultados. Os nomes dos arquivos são:\n")

            # Processar apenas os primeiros X resultados
            results_para_envio = results[:limite_envio]
            results_excedentes = results[limite_envio:]

            # Processar e enviar os primeiros X resultados
            for i, result in enumerate(results_para_envio, 1):
                with open("registro.txt", "a", encoding="utf-8") as arquivo:
                    arquivo.write(f"\t{i}º: {result['title']}\n")
                url_documento = f"https://doe.sp.gov.br/{result['slug']}"
                nome_arquivo = baixar_pdf(url_documento)
                enviar_email(result['title'], nome_arquivo, termo, url_documento)

            # Enviar email informativo sobre excesso (agora com TODOS os resultados)
            if results_excedentes:
                enviar_email_excesso_resultados(termo, total_resultados, results, limite_envio)

                # Registrar os resultados excedentes no arquivo de log
                with open("registro.txt", "a", encoding="utf-8") as arquivo:
                    for i, result in enumerate(results_excedentes, limite_envio + 1):
                        arquivo.write(f"\t{i}º: {result['title']}\n")

            # Email informativo de resultados encontrados para busca manual
            termo_formatado = ", ".join(search_query) if isinstance(search_query, list) else search_query
            enviar_email_informativo_resultados(termo_formatado, total_resultados, data_atual, horario_brasilia, "manual", limite_envio, resultados=results)

            if results_excedentes:
                return jsonify({
                    "status": "Busca executada com limite de envios!", 
                    "resultados_totais": total_resultados,
                    "enviados": limite_envio,
                    "excedentes": len(results_excedentes),
                    "executado_por": current_user
                })
            else:
                return jsonify({
                    "status": "Busca e Envio executados com sucesso!", 
                    "resultados": total_resultados,
                    "executado_por": current_user
                })
        else:
            with open("registro.txt", "a", encoding="utf-8") as arquivo:
                arquivo.write("Nenhum resultado foi encontrado para essa busca.\n\n")
            return jsonify({
                "status": "Nenhum resultado encontrado.",
                "executado_por": current_user
            })
    
@app.route('/cron', methods=['GET', 'POST', 'PUT', 'DELETE'])
@jwt_required()
def gerencia_crons():
    """Endpoint para gerenciar jobs agendados (CRUD)."""
    current_user = get_jwt_identity()
    logging.info(f"⚙️ Gerenciamento de crons acessado por usuário: {current_user}")

    if request.method == 'GET':
        # Lista todos os jobs + informações do sistema
        jobs = load_cron_jobs()
        config = load_config()
        
        response = {
            "jobs": jobs,
            "ultima_execucao": config.get('ultima_execucao', 'Nunca executado'),
            "total_jobs": len(jobs),
            "jobs_ativos": len([job for job in jobs if job.get('active', True)]),
            "jobs_inativos": len([job for job in jobs if not job.get('active', True)]),
            "acessado_por": current_user
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
        new_job['criado_por'] = current_user
        new_job['criado_em'] = datetime.now().isoformat() + 'Z'
        # Garantir que weekdays existe (opcional)
        if 'weekdays' not in new_job:
            new_job['weekdays'] = []
        jobs.append(new_job)
        save_cron_jobs(jobs)
        apagar_todos_agendamentos()
        schedule_jobs()
        
        logging.info(f"📅 Job criado por {current_user}: {new_job['search_query']}")
        return jsonify({"status": "success", "id": new_id, "criado_por": current_user}), 201

    elif request.method == 'PUT':
        # Atualiza um job existente
        update_job = request.json
        if 'id' not in update_job:
            return jsonify({"status": "error", "message": "ID do job não fornecido"}), 400

        jobs = load_cron_jobs()
        for idx, job in enumerate(jobs):
            if job.get('id') == update_job['id']:
                update_job['atualizado_por'] = current_user
                update_job['atualizado_em'] = datetime.now().isoformat() + 'Z'
                jobs[idx].update(update_job)
                break
        else:
            return jsonify({"status": "error", "message": "Job não encontrado"}), 404

        save_cron_jobs(jobs)
        apagar_todos_agendamentos()
        schedule_jobs()
        
        logging.info(f"📝 Job atualizado por {current_user}: ID {update_job['id']}")
        return jsonify({"status": "success", "message": "Job atualizado", "atualizado_por": current_user})

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
        
        logging.info(f"🗑️ Job removido por {current_user}: ID {job_id}")
        return jsonify({"status": "success", "message": "Job removido", "removido_por": current_user})

    return jsonify({"status": "error", "message": "Método não suportado"}), 405

@app.route('/registro', methods=['GET'])
@jwt_required()
def download_registro():
    """Endpoint para baixar o arquivo registro.txt."""
    current_user = get_jwt_identity()
    logging.info(f"📄 Download de registro acessado por usuário: {current_user}")
    
    try:
        from flask import send_file
        registro_path = os.path.abspath('registro.txt')
        
        if not os.path.exists(registro_path):
            logging.warning(f"❌ Arquivo registro.txt não encontrado - solicitado por {current_user}")
            return jsonify({
                "status": "error", 
                "message": "Arquivo registro.txt não encontrado",
                "solicitado_por": current_user
            }), 404
        
        # Log de sucesso antes do envio
        logging.info(f"✅ Arquivo registro.txt enviado com sucesso para {current_user}")
        
        return send_file(registro_path, as_attachment=True)
        
    except Exception as e:
        logging.error(f"❌ Erro ao processar download de registro para {current_user}: {str(e)}")
        return jsonify({
            "status": "error",
            "message": "Erro interno ao processar download",
            "solicitado_por": current_user
        }), 500

@app.route('/config', methods=['GET', 'PUT'])
@jwt_required()
def gerencia_config():
    """Endpoint para gerenciar configurações do sistema."""
    current_user = get_jwt_identity()
    logging.info(f"⚙️ Configurações acessadas por usuário: {current_user}")

    if request.method == 'GET':
        # Retorna configurações atuais
        config = load_config()
        config['acessado_por'] = current_user
        return jsonify(config)
    
    elif request.method == 'PUT':
        # Atualiza configurações
        try:
            nova_config = request.json
            
            # Validações básicas
            if 'email_principal' not in nova_config or not nova_config['email_principal']:
                return jsonify({
                    "status": "error", 
                    "message": "email_principal é obrigatório",
                    "alterado_por": current_user
                }), 400
            
            if 'emails_aviso' not in nova_config:
                nova_config['emails_aviso'] = []
            
            # Manter ultima_execucao se não fornecida
            config_atual = load_config()
            if 'ultima_execucao' not in nova_config:
                nova_config['ultima_execucao'] = config_atual.get('ultima_execucao', datetime.now().isoformat() + 'Z')
            
            # AUDITORIA: Adicionar logs de alteração
            nova_config['ultima_alteracao_por'] = current_user
            nova_config['ultima_alteracao_em'] = datetime.now().isoformat() + 'Z'
            
            save_config(nova_config)
            logging.info(f"⚙️ Configurações alteradas por {current_user}")
            
            return jsonify({
                "status": "success", 
                "message": "Configurações atualizadas", 
                "alterado_por": current_user
            })
            
        except Exception as e:
            logging.error(f"❌ Erro ao alterar configurações por {current_user}: {str(e)}")
            return jsonify({
                "status": "error",
                "message": "Erro interno ao processar alterações",
                "alterado_por": current_user
            }), 500
    
    return jsonify({
        "status": "error", 
        "message": "Método não suportado",
        "acessado_por": current_user
    }), 405
    
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