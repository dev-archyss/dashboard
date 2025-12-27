from flask import Flask, render_template, jsonify, request
import requests
import os
from math import radians, sin, cos, sqrt, atan2
import re
from datetime import datetime, timedelta

app = Flask(__name__)

# Credenciales de Supabase
SUPABASE_URL = "https://djjylikkocemrlsjxscr.supabase.co"
SUPABASE_KEY = os.getenv('SUPABASE_KEY') # No pongas el string largo aquí por seguridad

if not SUPABASE_KEY:
    print("WARNING: SUPABASE_KEY no encontrada en las variables de entorno.")

headers = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json"
}

# ----------------------------------------------------------------------
# --- Funciones de Utilidad ---
# ----------------------------------------------------------------------

def fetch_table(table_name, params=None, empresa_id=None):
    """Fetch genérico a Supabase con paginación y filtro opcional por empresa_id"""
    url = f"{SUPABASE_URL}/rest/v1/{table_name}"
    all_data = []
    limit = 1000
    offset = 0

    query_params = params or []

    # Aplicar filtro de empresa si la tabla lo tiene y se proporciona empresa_id
    if empresa_id is not None:
        query_params.append(("empresa_id", f"eq.{empresa_id}"))

    while True:
        headers_with_range = headers.copy()
        headers_with_range["Range"] = f"{offset}-{offset + limit - 1}"

        try:
            response = requests.get(url, headers=headers_with_range, params=query_params)
            response.raise_for_status()
            data = response.json()

            if not data:
                break

            all_data.extend(data)

            if len(data) < limit:
                break

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

def get_week_date_range(year, week_number):
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
    return render_template('competencia.html')

@app.route('/productos')
def productos():
    return render_template('productos.html')

# ----------------------------------------------------------------------
# --- Rutas API ---
# ----------------------------------------------------------------------

@app.route('/api/records', methods=['GET'])
def get_records():
    empresa_id = request.args.get('empresa_id')
    if not empresa_id:
        return jsonify({"error": "empresa_id es requerido"}), 400

    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    promoter_id = request.args.get('promoter_id')
    week = request.args.get('week')
    year = request.args.get('year', str(datetime.now().year))

    params = [
        ("select", "*,web_promotores(id,promoter_name,clientes_asig,dias_trabajo)"),
        ("order", "created_at.desc"),
        ("empresa_id", f"eq.{empresa_id}")
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
    clientes = fetch_table("web_clientes", empresa_id=empresa_id)
    promotores = fetch_table("web_promotores", empresa_id=empresa_id)
    estados = fetch_table("web_estados", empresa_id=empresa_id)
    zonas = fetch_table("web_zonas", empresa_id=empresa_id)

    # Diccionario rápido de clientes por id
    clientes_by_id = {int(c["id"]): c for c in clientes if "id" in c}

    formatted_records = []
    for record in records_raw:
        promoter_info = record.get('web_promotores') or {}
        promoter_name = promoter_info.get('promoter_name', "Sin Promotor")
        clientes_asig = promoter_info.get('clientes_asig', 0)
        dias_trabajo = promoter_info.get('dias_trabajo', 0)

        estado = record.get("state", "N/A")
        zona = record.get("zone", "N/A")
        myitems = record.get("myitems", {})
        competitoritems = record.get("competitoritems", {})

        cliente_data = None
        cliente_id = record.get("cliente_id")
        if cliente_id is not None:
            try:
                cliente_id_int = int(cliente_id)
                cliente_data = clientes_by_id.get(cliente_id_int)
            except (ValueError, TypeError):
                pass

        # Coordenadas de visita
        try:
            visit_lat = float(record.get("latitude")) if record.get("latitude") not in [None, "None"] else None
            visit_lon = float(record.get("longitude")) if record.get("longitude") not in [None, "None"] else None
        except (ValueError, TypeError):
            visit_lat = visit_lon = None

        visit_coords_str = f"{visit_lat}, {visit_lon}" if visit_lat and visit_lon else "N/A"

        # Coordenadas de cliente
        cliente_coords_str = "N/A"
        distance = 0
        verified_status = "Cliente Desconocido"

        if cliente_data:
            try:
                cliente_lat = float(cliente_data.get("latitude", 0))
                cliente_lon = float(cliente_data.get("longitude", 0))
            except (ValueError, TypeError):
                cliente_lat = cliente_lon = 0

            if cliente_lat != 0 and cliente_lon != 0:
                cliente_coords_str = f"{cliente_lat}, {cliente_lon}"

            if visit_lat is None or visit_lon is None:
                verified_status = "Visita sin Coordenadas"
            elif cliente_lat == 0 or cliente_lon == 0:
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
            "trade": record.get("trade", "N/A"),
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
    empresa_id = request.args.get('empresa_id')
    if not empresa_id:
        return jsonify({"error": "empresa_id es requerido"}), 400

    year = request.args.get('year', str(datetime.now().year))

    params = [
        ("select", "created_at"),
        ("empresa_id", f"eq.{empresa_id}"),
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


@app.route('/delete_records', methods=['POST'])
def delete_records():
    data = request.json or {}
    ids = data.get("ids", [])
    empresa_id = data.get("empresa_id")

    if not empresa_id:
        return jsonify({"success": False, "error": "empresa_id es requerido"}), 400
    if not ids:
        return jsonify({"success": False, "error": "No IDs provided"}), 400

    # Filtro adicional por empresa para mayor seguridad
    id_list_str = ",".join(map(str, ids))
    delete_url = f"{SUPABASE_URL}/rest/v1/web_precios?id=in.({id_list_str})&empresa_id=eq.{empresa_id}"

    response = requests.delete(delete_url, headers=headers)
    return jsonify({"success": response.status_code in [200, 204]})


# ----------------------------------------------------------------------
# --- Rutas CRUD Productos Competencia (sin cambios, pero ahora solo ven datos globales o por empresa si lo deseas) ---
# ----------------------------------------------------------------------
@app.route('/api/competitorproducts', methods=['POST'])
def create_competitor_product():
    product_data = request.json
    payload = {"presentation": product_data.get("presentation")}
    if not payload["presentation"]:
        return jsonify({"success": False, "error": "Presentation is required"}), 400

    try:
        response = requests.post(f"{SUPABASE_URL}/rest/v1/web_competidor", headers=headers, json=payload)
        response.raise_for_status()
        return jsonify({"success": True, "data": response.json() if response.content else {}}), 201
    except requests.exceptions.RequestException as e:
        error_msg = e.response.json().get('message', str(e)) if e.response else str(e)
        return jsonify({"success": False, "error": error_msg}), 400

@app.route('/api/competitorproducts', methods=['GET'])
def get_competitor_products():
    products = fetch_table("web_competidor", params=[("select", "id,presentation,created_at"), ("order", "presentation.asc")])
    return jsonify({"products": products})

@app.route('/api/competitorproducts/<int:product_id>', methods=['PATCH'])
def update_competitor_product(product_id):
    data = request.json
    update_payload = {k: v for k, v in data.items() if k == "presentation"}
    if not update_payload:
        return jsonify({"success": False, "error": "No data to update"}), 400
    response = requests.patch(f"{SUPABASE_URL}/rest/v1/web_competidor?id=eq.{product_id}", headers=headers, json=update_payload)
    return jsonify({"success": response.ok})

@app.route('/api/competitorproducts/<int:product_id>', methods=['DELETE'])
def delete_competitor_product(product_id):
    response = requests.delete(f"{SUPABASE_URL}/rest/v1/web_competidor?id=eq.{product_id}", headers=headers)
    return jsonify({"success": response.ok}), 204 if response.ok else 500


# ----------------------------------------------------------------------
# --- Rutas CRUD Productos Propios ---
# ----------------------------------------------------------------------
@app.route('/api/myproducts', methods=['POST'])
def create_myproduct():
    data = request.json
    payload = {"presentation": data.get("presentation")}
    if not payload["presentation"]:
        return jsonify({"success": False, "error": "Presentation is required"}), 400
    response = requests.post(f"{SUPABASE_URL}/rest/v1/web_myproductos", headers=headers, json=payload)
    return jsonify({"success": response.ok, "data": response.json() if response.content else {}}), 201 if response.ok else 400

@app.route('/api/myproducts', methods=['GET'])
def get_myproducts():
    products = fetch_table("web_myproductos", params=[("select", "id,presentation,created_at"), ("order", "presentation.asc")])
    return jsonify({"products": products})

@app.route('/api/myproducts/<int:product_id>', methods=['PATCH'])
def update_myproduct(product_id):
    data = request.json
    update_payload = {k: v for k, v in data.items() if k == "presentation"}
    if not update_payload:
        return jsonify({"success": False, "error": "No data to update"}), 400
    response = requests.patch(f"{SUPABASE_URL}/rest/v1/web_myproductos?id=eq.{product_id}", headers=headers, json=update_payload)
    return jsonify({"success": response.ok})

@app.route('/api/myproducts/<int:product_id>', methods=['DELETE'])
def delete_myproduct(product_id):
    response = requests.delete(f"{SUPABASE_URL}/rest/v1/web_myproductos?id=eq.{product_id}", headers=headers)
    return jsonify({"success": response.ok}), 204 if response.ok else 500


# --- INICIO DINÁMICO PARA RENDER ---
if __name__ == "__main__":
    # Render usa la variable PORT
    port = int(os.environ.get("PORT", 8020))
    app.run(host='0.0.0.0', port=port)