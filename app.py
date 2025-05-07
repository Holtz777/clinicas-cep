from flask import Flask, request, jsonify
import csv
import requests
import math
import os

app = Flask(__name__)

# Configuração
API_KEY = os.environ.get("API_KEY")  

# Função para obter coordenadas a partir do CEP usando Google Maps API
def obter_coordenadas_google(cep):
    # Formatar o CEP para incluir o Brasil na busca
    endereco = f"{cep}, Brazil"
    
    # Construir a URL da API
    url = f"https://maps.googleapis.com/maps/api/geocode/json?address={endereco}&key={API_KEY}"
    
    try:
        response = requests.get(url)
        data = response.json()
        
        # Verificar se a requisição foi bem-sucedida
        if data['status'] == 'OK':
            # Obter o primeiro resultado
            result = data['results'][0]
            location = result['geometry']['location']
            
            # Extrair informações do endereço
            address_components = result['address_components']
            endereco_info = {}
            
            for component in address_components:
                if 'route' in component['types']:
                    endereco_info['logradouro'] = component['long_name']
                elif 'sublocality' in component['types']:
                    endereco_info['bairro'] = component['long_name']
                elif 'administrative_area_level_2' in component['types']:
                    endereco_info['cidade'] = component['long_name']
                elif 'administrative_area_level_1' in component['types']:
                    endereco_info['estado'] = component['short_name']
            
            return {
                'latitude': location['lat'],
                'longitude': location['lng'],
                'endereco': endereco_info.get('logradouro', ''),
                'bairro': endereco_info.get('bairro', ''),
                'cidade': endereco_info.get('cidade', ''),
                'estado': endereco_info.get('estado', ''),
                'endereco_completo': result['formatted_address']
            }
        else:
            print(f"Erro na API do Google: {data['status']}")
            return None
    except Exception as e:
        print(f"Erro ao consultar API do Google: {e}")
        return None

# Função para calcular distância usando fórmula de Haversine
def calcular_distancia_haversine(lat1, lon1, lat2, lon2):
    # Raio da Terra em quilômetros
    R = 6371.0
    
    # Converter graus para radianos
    lat1_rad = math.radians(float(lat1))
    lon1_rad = math.radians(float(lon1))
    lat2_rad = math.radians(float(lat2))
    lon2_rad = math.radians(float(lon2))
    
    # Diferença entre as latitudes e longitudes
    dLat = lat2_rad - lat1_rad
    dLon = lon2_rad - lon1_rad
    
    # Fórmula de Haversine
    a = math.sin(dLat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dLon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    distancia = R * c
    
    return distancia

# Função para carregar base de clínicas a partir do CSV
def carregar_clinicas(arquivo='clinicas.csv'):
    clinicas = []
    try:
        with open(arquivo, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Converter campos numéricos
                try:
                    row['latitude'] = float(row['latitude'])
                    row['longitude'] = float(row['longitude'])
                    row['id'] = int(row['id'])
                except (ValueError, KeyError) as e:
                    print(f"Erro ao converter valores para linha: {row}, erro: {e}")
                    continue
                    
                clinicas.append(row)
        print(f"Base de clínicas carregada com sucesso: {len(clinicas)} registros")
        return clinicas
    except Exception as e:
        print(f"Erro ao carregar arquivo CSV: {e}")
        return []

# Carregar a base de clínicas uma vez na inicialização
clinicas = carregar_clinicas()

# Função principal para encontrar clínicas próximas
def encontrar_clinicas_proximas(cep, max_resultados=5, distancia_maxima=None, especialidade=None):
    # Verificar se a base de clínicas foi carregada
    if not clinicas:
        return {
            "success": False,
            "error": "Não foi possível carregar a base de clínicas."
        }
    
    # Obter coordenadas do CEP de origem
    coords_origem = obter_coordenadas_google(cep)
    if not coords_origem:
        return {
            "success": False,
            "error": "Não foi possível obter as coordenadas do CEP informado."
        }
    
    # Calcular distância para cada clínica
    clinicas_com_distancia = []
    for clinica in clinicas:
        try:
            distancia = calcular_distancia_haversine(
                coords_origem['latitude'], 
                coords_origem['longitude'], 
                clinica['latitude'], 
                clinica['longitude']
            )
            
            # Aplicar filtro de distância máxima
            if distancia_maxima is not None and distancia > distancia_maxima:
                continue
                
            # Aplicar filtro de especialidade
            if especialidade is not None:
                # Verifica se a especialidade está contida na string de especialidades da clínica
                if 'especialidades' not in clinica or especialidade.upper() not in clinica['especialidades'].upper():
                    continue
            
            clinica_com_distancia = clinica.copy()
            clinica_com_distancia['distancia'] = round(distancia, 2)
            clinica_com_distancia['distancia_texto'] = f"{round(distancia, 2)} km"
            
            clinicas_com_distancia.append(clinica_com_distancia)
        except Exception as e:
            print(f"Erro ao calcular distância para clínica {clinica.get('id', 'desconhecido')}: {e}")
            continue
    
    # Ordenar por distância
    clinicas_com_distancia.sort(key=lambda x: x['distancia'])
    
    # Limitar resultados
    clinicas_proximas = clinicas_com_distancia[:max_resultados]
    
    # Formatar resposta
    resposta = {
        "success": True,
        "cep_consultado": cep,
        "endereco_origem": coords_origem.get('endereco_completo', ''),
        "coordenadas_origem": {
            "latitude": coords_origem['latitude'],
            "longitude": coords_origem['longitude']
        },
        "total_clinicas_encontradas": len(clinicas_com_distancia),
        "filtros_aplicados": {
            "distancia_maxima": distancia_maxima,
            "especialidade": especialidade,
            "max_resultados": max_resultados
        },
        "clinicas_proximas": clinicas_proximas
    }
    
    return resposta

@app.route('/api/clinicas/proximas', methods=['GET'])
def api_clinicas_proximas():
    # Obter o CEP da query string
    cep = request.args.get('cep')
    max_resultados = request.args.get('max', default=5, type=int)
    
    # Novos parâmetros
    distancia_maxima = request.args.get('distancia', default=None, type=float)
    especialidade = request.args.get('especialidade', default=None)
    
    if not cep:
        return jsonify({
            "success": False,
            "error": "CEP não fornecido. Use ?cep=SEU_CEP na URL."
        }), 400
    
    # Remover caracteres não numéricos do CEP
    cep = ''.join(filter(str.isdigit, cep))
    
    # Validar formato do CEP
    if len(cep) != 8:
        return jsonify({
            "success": False,
            "error": "Formato de CEP inválido. Deve conter 8 dígitos."
        }), 400
    
    # Buscar clínicas próximas
    resultado = encontrar_clinicas_proximas(cep, max_resultados, distancia_maxima, especialidade)
    
    if not resultado.get("success", False):
        return jsonify(resultado), 404
    
    return jsonify(resultado)

# Rota de status/healthcheck
@app.route('/', methods=['GET'])
def home():
    return jsonify({
        "status": "online",
        "info": "API de busca de clínicas próximas por CEP",
        "rotas_disponíveis": [
            {
                "rota": "/api/clinicas/proximas",
                "parametros": [
                    "cep (obrigatório): CEP para busca",
                    "max (opcional, padrão: 5): Número máximo de resultados",
                    "distancia (opcional): Distância máxima em km",
                    "especialidade (opcional): Filtro por especialidade médica"
                ],
                "exemplo": "/api/clinicas/proximas?cep=13020440&max=3&distancia=10&especialidade=PSICOLOGIA"
            }
        ],
        "total_clinicas": len(clinicas)
    })

if __name__ == "__main__":
    # Porta definida pelo ambiente ou 5000 como padrão
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)