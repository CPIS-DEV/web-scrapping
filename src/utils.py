from flask import app, jsonify, request
from utils import fetch_page, parse_html, extract_data

# Exemplo de uso dentro de um endpoint Flask:
@app.route('/extrair-dados', methods=['POST'])
def extrair_dados():
    data = request.json
    url = data.get('url')
    selector = data.get('selector')
    html = fetch_page(url)
    soup = parse_html(html)
    resultados = extract_data(soup, selector)
    return jsonify({"resultados": [str(r) for r in resultados]})