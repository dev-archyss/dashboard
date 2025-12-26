from flask import Flask, render_template, jsonify, request
import requests
import os
from math import radians, sin, cos, sqrt, atan2
import re
import urllib.parse
from datetime import datetime, timedelta

app = Flask(__name__)

# Credenciales de Supabase (usa variables de entorno en producción)
SUPABASE_URL = "https://djjylikkocemrlsjxscr.supabase.co"
# OJO: DEBES MANTENER ESTA CLAVE OCULTA EN UN ENTORNO DE PRODUCCIÓN REAL
# La clave que has provisto es una clave 'anon' (anónima), que es menos peligrosa,
# pero en producción DEBERÍAS usar una clave de servicio oculta.
SUPABASE_KEY = os.getenv('SUPABASE_KEY', "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImRqanlsaWtrb2NlbXJsc2p4c2NyIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjMxNjUyNDEsImV4cCI6MjA3ODc0MTI0MX0.fnv1BKn_o-PYEAPljG0V3dt3b2Uifwn8EEzkP8Aab3M")

headers = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json"
}

# ----------------------------------------------------------------------
# --- Funciones de Utilidad ---
# ----------------------------------------------------------------------

def fetch_table(table_name, params=None):
    """Fetch genérico a Supabase con paginación en headers"""
    url = f"{SUPABASE_URL}/rest/v1/{table_name}"
    all_data = []
    limit = 1000
    offset = 0

    query_params = params or []

    while True:
        headers_with_range = headers.copy()
        headers_with_range["Range"] = f"{offset}-{offset + limit - 1}"

        try:
            response = requests.get(url, headers=headers_with_range, params=query_params)
            response.raise_for_status()
            data = response.json()

            if not data:
                break

            # print(f"Descargados {len(data)} registros desde offset {offset} para tabla {table_name}")
            all_data.extend(data)

            if len(data) < limit:
                break  # Última página

            offset += limit

        except requests.exceptions.RequestException as e:
            print(f"Error al leer tabla {table_name}: {e}")
            break

    return all_data

def calculate_distance(lat1, lon1, lat2, lon2):
    R = 6371000
    d_lat = radians(lat2 - lat1)
    d_lon = radians(lon2 - lon1)
    a = sin(d_lat / 2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(d_lon / 2)**2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return R * c

def normalize(text):
    if not text:
        return ""
    text = text.lower().strip()
    replacements = {
        'á': 'a','é': 'e','í': 'i','ó': 'o','ú': 'u','ñ': 'n',
        'ä': 'a','ë': 'e','ï': 'i','ö': 'o','ü': 'u',
        '&': 'y','-': ' ','/': ' ','.': ' '
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    text = re.sub(r'[^a-z0-9\s]', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text

def get_week_date_range(year, week_number):
    """Calculate the start and end dates for a given ISO week number in a year."""
    jan4 = datetime(year, 1, 4)
    jan4_weekday = jan4.weekday()
    monday_week1 = jan4 - timedelta(days=jan4_weekday)
    start_of_week = monday_week1 + timedelta(weeks=week_number - 1)
    end_of_week = start_of_week + timedelta(days=6)
    return start_of_week.strftime('%Y-%m-%d'), end_of_week.strftime('%Y-%m-%d')

# ----------------------------------------------------------------------
# --- Rutas de Vistas (HTML) ---
# ----------------------------------------------------------------------
@app.route('/')
def login():
    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html')

@app.route('/gps')
def gps():
    return render_template('gps.html')

@app.route('/clientes')
def clientes():
    return render_template('clientes.html')

@app.route('/analisis')
def analisis():
    return render_template('analisis.html')

@app.route('/promotores')
def promotores():
    return render_template('promotores.html')

@app.route('/competencia')
def productos_competencia():
    """Ruta para el panel CRUD de productos de la competencia."""
    return render_template('competencia.html')


@app.route('/productos')
def productos():
    """Ruta para el panel CRUD de productos."""
    return render_template('productos.html')

# ----------------------------------------------------------------------
# --- Rutas API para web_precios (Las que ya tenías) ---
# ----------------------------------------------------------------------

@app.route('/api/records', methods=['GET'])
def get_records():
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    promoter_id = request.args.get('promoter_id')
    week = request.args.get('week')
    year = request.args.get('year', str(datetime.now().year))

    params = [
        ("select", "*,web_promotores(id,promoter_name,clientes_asig,dias_trabajo)"),
        ("order", "created_at.desc")
    ]
    if week and year:
        date_from, date_to = get_week_date_range(int(year), int(week))
        params.append(("created_at", f"gte.{date_from}T00:00:00+00:00"))
        params.append(("created_at", f"lte.{date_to}T23:59:59+00:00"))
    elif date_from:
        params.append(("created_at", f"gte.{date_from}T00:00:00+00:00"))
    if date_to:
        params.append(("created_at", f"lte.{date_to}T23:59:59+00:00"))
    if promoter_id and promoter_id != 'all':
        params.append(("promoter_id", f"eq.{promoter_id}"))

    records_raw = fetch_table("web_precios", params=params)
    clientes = fetch_table("web_clientes")
    promotores = fetch_table("web_promotores")
    estados = fetch_table("web_estados")
    zonas = fetch_table("web_zonas")

    # --- Crear diccionario rápido de clientes por id ---
    clientes_by_id = {}
    for c in clientes:
        if "id" in c:
            try:
                clientes_by_id[int(c["id"])] = c
            except (ValueError, TypeError):
                pass

    # --- Formatear registros con info adicional ---
    formatted_records = []
    for record in records_raw:
        promoter_info = record.get('web_promotores')
        promoter_name = promoter_info.get('promoter_name') if promoter_info else "Sin Promotor"
        clientes_asig = promoter_info.get('clientes_asig', 0) if promoter_info else 0
        dias_trabajo = promoter_info.get('dias_trabajo', 0) if promoter_info else 0
        
        # Info del record
        estado = record.get("state", "N/A")
        zona = record.get("zone", "N/A")
        myitems = record.get("myitems", {})
        competitoritems = record.get("competitoritems", {})
        
        # --- MATCH POR ID (para traer coords del cliente) ---
        cliente_data = None
        cliente_id = record.get("cliente_id")
        
        # print(f"Procesando registro ID {record.get('id')}, cliente_id: {cliente_id}, myitems: {myitems}, competitoritems: {competitoritems}")
        if cliente_id is not None:
            try:
                cliente_id_int = int(cliente_id)
            except (ValueError, TypeError):
                # print(f"Error al convertir cliente_id {cliente_id} a int")
                cliente_id_int = None

            if cliente_id_int is not None:
                if cliente_id_int in clientes_by_id:
                    cliente_data = clientes_by_id[cliente_id_int]
                    # print(f"Match encontrado para cliente_id {cliente_id_int}: {cliente_data.get('trade_name')}")
                # else:
                    # print(f"No se encontró cliente_id {cliente_id} en web_clientes")
        # else:
            # print(f"cliente_id es None para registro ID {record.get('id')}")

        # --- Determinar coordenadas y verificación (basado en distancia) ---
        verified_status = "Cliente Desconocido"
        distance = 0
        cliente_coords_str = "N/A"
        visit_coords_str = "N/A"

        visit_lat = None
        visit_lon = None
        cliente_lat = None
        cliente_lon = None

        # Procesar coordenadas de visita
        visit_lat_str = record.get("latitude")
        visit_lon_str = record.get("longitude")
        try:
            visit_lat = float(visit_lat_str) if visit_lat_str and visit_lat_str != "None" else None
            visit_lon = float(visit_lon_str) if visit_lon_str and visit_lon_str != "None" else None
        except (ValueError, TypeError):
            visit_lat = None
            visit_lon = None

        if visit_lat is not None and visit_lon is not None:
            visit_coords_str = f"{visit_lat}, {visit_lon}"

        if cliente_data:
            # Procesar coordenadas de cliente
            cliente_lat_str = cliente_data.get("latitude")
            cliente_lon_str = cliente_data.get("longitude")
            try:
                cliente_lat = float(cliente_lat_str) if cliente_lat_str else 0
                cliente_lon = float(cliente_lon_str) if cliente_lon_str else 0
            except (ValueError, TypeError):
                cliente_lat = 0
                cliente_lon = 0

            if cliente_lat != 0 and cliente_lon != 0:
                cliente_coords_str = f"{cliente_lat}, {cliente_lon}"

            # Determinar status
            if visit_lat is None or visit_lon is None:
                verified_status = "Visita sin Coordenadas"
            elif cliente_lat == 0 and cliente_lon == 0:
                verified_status = "Cliente sin Coordenadas"
            else:
                distance = calculate_distance(visit_lat, visit_lon, cliente_lat, cliente_lon)
                verified_status = "Confirmado" if distance <= 150 else "No Confirmado"

        formatted_records.append({
            "id": record.get("id"),
            "created_at": record.get("created_at"),
            "promoter_id": record.get("promoter_id"),
            "promoter_name": promoter_name,
            "clientes_asig": clientes_asig,
            "dias_trabajo": dias_trabajo,
            "estado": estado,
            "zona": zona,
            "trade_name": record.get("trade", "N/A"),
            "visit_coords": visit_coords_str,
            "client_coords": cliente_coords_str,
            "distance": round(distance, 2),
            "verified": verified_status,
            "latitude": visit_lat,
            "longitude": visit_lon,
            "myitems": myitems,
            "competitoritems": competitoritems,
            "cliente_id": cliente_id,
            "comments": record.get("comments", "N/A")
        })

    return jsonify({
        "records": formatted_records,
        "promoters": promotores,
        "total_promoters_in_db": len(promotores),
        "estados": estados,
        "zonas": zonas
    })

@app.route('/api/weeks_with_visits', methods=['GET'])
def get_weeks_with_visits():
    year = request.args.get('year', str(datetime.now().year))
    params = [
        ("select", "created_at"),
        ("created_at", f"gte.{year}-01-01T00:00:00+00:00"),
        ("created_at", f"lte.{year}-12-31T23:59:59+00:00"),
        ("order", "created_at.desc")
    ]
    records_raw = fetch_table("web_precios", params=params)
    weeks = set()
    for r in records_raw:
        created_at = r.get('created_at')
        if created_at:
            try:
                dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                week_num = dt.isocalendar()[1]
                weeks.add(week_num)
            except ValueError:
                pass
    return jsonify({"weeks": sorted(list(weeks), reverse=True)})

@app.route('/update_record', methods=['POST'])
def update_record():
    data = request.json
    response = requests.patch(
        f"{SUPABASE_URL}/rest/v1/web_precios?id=eq.{data['id']}",
        headers=headers,
        json={k: v for k, v in data.items() if k != "id"}
    )
    return jsonify({"success": response.status_code in [200,204]})

@app.route('/delete_records', methods=['POST'])
def delete_records():
    ids = request.json.get("ids", [])
    if not ids: return jsonify({"success": False, "error": "No IDs provided"}), 400
    id_list_str = ",".join(map(str, ids))
    response = requests.delete(f"{SUPABASE_URL}/rest/v1/web_precios?id=in.({id_list_str})", headers=headers)
    return jsonify({"success": response.status_code in [200,204]})

# ----------------------------------------------------------------------
# --- Rutas API CRUD para web_competidor (Productos Competencia) ---
# ----------------------------------------------------------------------

# [CREATE] Crear una nueva presentación de competidor
@app.route('/api/competitorproducts', methods=['POST'])
def create_competitor_product():
    product_data = request.json

    payload = {
        "presentation": product_data.get("presentation")
    }

    if not payload["presentation"]:
        return jsonify({"success": False, "error": "Competitor presentation is required"}), 400

    try:
        response = requests.post(
            f"{SUPABASE_URL}/rest/v1/web_competidor",
            headers=headers,
            json=payload
        )
        response.raise_for_status() # Lanza un error para 4xx/5xx

        # ** --- CAMBIO CLAVE: Manejar respuesta JSON opcional --- **
        # Supabase devuelve 201, a veces con un cuerpo, a veces sin él.
        if response.content:
            return jsonify({"success": True, "data": response.json()}), 201
        else:
            # Si la creación fue exitosa (201) pero la respuesta está vacía, 
            # asumimos que todo está bien para evitar el error de JSON.
            return jsonify({"success": True, "message": "Product created successfully"}), 201
        # ** --------------------------------------------------- **

    except requests.exceptions.HTTPError as e:
        # Manejo de errores 4xx o 5xx (ej. 401 Unauthorized, 409 Conflict - clave única)
        status_code = e.response.status_code
        error_json = e.response.json().get('message', e.response.text) if e.response.text else str(e)
        print(f"Error al crear producto de competidor ({status_code}): {error_json}")
        return jsonify({"success": False, "error": f"Error Supabase: {error_json}"}), status_code 
        
    except requests.exceptions.RequestException as e:
        # Manejo de errores de conexión de red, timeout, etc.
        print(f"Error de conexión: {e}")
        return jsonify({"success": False, "error": "Error de conexión con el servicio de base de datos"}), 500

# [READ] Leer todos los productos de competidor
@app.route('/api/competitorproducts', methods=['GET'])
def get_competitor_products():
    params = [
        ("select", "id,presentation,created_at"),
        ("order", "presentation.asc") 
    ]
    
    products = fetch_table("web_competidor", params=params)
    
    return jsonify({"products": products}), 200

# [UPDATE] Actualizar un producto de competidor existente
@app.route('/api/competitorproducts/<product_id>', methods=['PATCH'])
def update_competitor_product(product_id):
    product_data = request.json
    
    allowed_fields = ["presentation"]
    update_payload = {k: v for k, v in product_data.items() if k in allowed_fields}
    
    if not update_payload:
        return jsonify({"success": False, "error": "No data to update"}), 400

    try:
        response = requests.patch(
            f"{SUPABASE_URL}/rest/v1/web_competidor?id=eq.{product_id}",
            headers=headers,
            json=update_payload
        )
        response.raise_for_status()
        return jsonify({"success": True, "message": "Competitor product updated"}), 200
    except requests.exceptions.RequestException as e:
        error_detail = response.json().get('message', str(e)) if response.status_code == 409 else str(e)
        print(f"Error al actualizar producto de competidor: {error_detail}")
        return jsonify({"success": False, "error": f"Error al actualizar producto de competidor: {error_detail}"}), 400

# [DELETE] Eliminar un producto de competidor por ID
@app.route('/api/competitorproducts/<product_id>', methods=['DELETE'])
def delete_competitor_product(product_id):
    try:
        response = requests.delete(
            f"{SUPABASE_URL}/rest/v1/web_competidor?id=eq.{product_id}",
            headers=headers
        )
        response.raise_for_status()
        return jsonify({"success": True, "message": "Competitor product deleted"}), 204
    except requests.exceptions.RequestException as e:
        print(f"Error al eliminar producto de competidor: {e}")
        return jsonify({"success": False, "error": f"Error al eliminar producto de competidor: {e}"}), 500



# ----------------------------------------------------------------------
# --- Rutas API CRUD para web_myproducts (NUEVAS) ---
# ----------------------------------------------------------------------
# [CREATE] Crear un nuevo producto
@app.route('/api/myproducts', methods=['POST'])
def create_myproduct():
    product_data = request.json
    
    payload = {
        "presentation": product_data.get("presentation")
    }
    
    if not payload["presentation"]:
        return jsonify({"success": False, "error": "Product presentation is required"}), 400

    try:
        response = requests.post(
            f"{SUPABASE_URL}/rest/v1/web_myproductos",
            headers=headers,
            json=payload
        )
        response.raise_for_status()
        return jsonify({"success": True, "data": response.json()}), 201
    except requests.exceptions.RequestException as e:
        # Intenta extraer un error más específico de Supabase si falla la restricción UNIQUE
        error_detail = response.json().get('message', str(e)) if response.status_code == 409 else str(e)
        print(f"Error al crear producto: {error_detail}")
        return jsonify({"success": False, "error": f"Error al crear producto: {error_detail}"}), 400

# [READ] Leer todos los productos
@app.route('/api/myproducts', methods=['GET'])
def get_myproducts():
    params = [
        ("select", "id,presentation,created_at"),
        ("order", "presentation.asc") 
    ]
    
    products = fetch_table("web_myproductos", params=params)
    
    return jsonify({"products": products}), 200

# [UPDATE] Actualizar un producto existente
@app.route('/api/myproducts/<product_id>', methods=['PATCH'])
def update_myproduct(product_id):
    product_data = request.json
    
    allowed_fields = ["presentation"]
    update_payload = {k: v for k, v in product_data.items() if k in allowed_fields}
    
    if not update_payload:
        return jsonify({"success": False, "error": "No data to update"}), 400

    try:
        response = requests.patch(
            f"{SUPABASE_URL}/rest/v1/web_myproductos?id=eq.{product_id}",
            headers=headers,
            json=update_payload
        )
        response.raise_for_status()
        return jsonify({"success": True, "message": "Product updated"}), 200
    except requests.exceptions.RequestException as e:
        error_detail = response.json().get('message', str(e)) if response.status_code == 409 else str(e)
        print(f"Error al actualizar producto: {error_detail}")
        return jsonify({"success": False, "error": f"Error al actualizar producto: {error_detail}"}), 400

# [DELETE] Eliminar un producto por ID
@app.route('/api/myproducts/<product_id>', methods=['DELETE'])
def delete_myproduct(product_id):
    try:
        response = requests.delete(
            f"{SUPABASE_URL}/rest/v1/web_myproductos?id=eq.{product_id}",
            headers=headers
        )
        response.raise_for_status()
        return jsonify({"success": True, "message": "Product deleted"}), 204
    except requests.exceptions.RequestException as e:
        print(f"Error al eliminar producto: {e}")
        return jsonify({"success": False, "error": f"Error al eliminar producto: {e}"}), 500
# ----------------------------------------------------------------------
# --- Ejecución de la Aplicación ---
# ----------------------------------------------------------------------

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8020, debug=True)