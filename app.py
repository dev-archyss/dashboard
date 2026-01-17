from flask import Flask, render_template, jsonify, request, session, redirect, url_for
import requests
import os
from math import radians, sin, cos, sqrt, atan2
import re
from datetime import datetime, timedelta

app = Flask(__name__)

# ¡Obligatorio para usar session!
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'tu-clave-secreta-super-larga-y-segura-2025-xyz123')

# Credenciales de Supabase
SUPABASE_URL = "https://djjylikkocemrlsjxscr.supabase.co"
SUPABASE_KEY = os.getenv('eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImRqanlsaWtrb2NlbXJsc2p4c2NyIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjMxNjUyNDEsImV4cCI6MjA3ODc0MTI0MX0.fnv1BKn_o-PYEAPljG0V3dt3b2Uifwn8EEzkP8Aab3M')  # No pongas el string largo aquí por seguridad

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
# --- Obtener empresa logueada (usada en planograma) ---
# ----------------------------------------------------------------------
def get_current_empresa():
    empresa_id = session.get('empresa_id')
    if not empresa_id:
        return None
    
    url = f"{SUPABASE_URL}/rest/v1/empresas?id=eq.{empresa_id}&select=id,nombre,planogram_image"
    response = requests.get(url, headers=headers)
    if response.status_code == 200 and response.json():
        return response.json()[0]
    return None

# ----------------------------------------------------------------------
# --- Rutas de Vistas (HTML) ---
# ----------------------------------------------------------------------
@app.route('/')
def login():
    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    if 'empresa_id' not in session:
        return redirect(url_for('login'))
    return render_template('dashboard.html')

@app.route('/gps')
def gps():
    if 'empresa_id' not in session:
        return redirect(url_for('login'))
    return render_template('gps.html')

@app.route('/clientes')
def clientes():
    if 'empresa_id' not in session:
        return redirect(url_for('login'))
    return render_template('clientes.html')

@app.route('/analisis')
def analisis():
    if 'empresa_id' not in session:
        return redirect(url_for('login'))
    return render_template('analisis.html')

@app.route('/promotores')
def promotores():
    if 'empresa_id' not in session:
        return redirect(url_for('login'))
    return render_template('promotores.html')

@app.route('/competencia')
def productos_competencia():
    if 'empresa_id' not in session:
        return redirect(url_for('login'))
    return render_template('competencia.html')

@app.route('/productos')
def productos():
    if 'empresa_id' not in session:
        return redirect(url_for('login'))
    return render_template('productos.html')

@app.route('/stock')
def stock():
    if 'empresa_id' not in session:
        return redirect(url_for('login'))
    return render_template('stock.html')

@app.route('/planograma')
def planograma():
    empresa = get_current_empresa()
    if not empresa:
        return redirect(url_for('login'))
    
    return render_template('planograma.html', 
                           empresa_nombre=empresa['nombre'],
                           empresa_id=empresa['id'])

# ----------------------------------------------------------------------
# --- Rutas API para Planograma ---
# ----------------------------------------------------------------------
@app.route('/api/planograma', methods=['GET'])
def api_get_planograma():
    empresa = get_current_empresa()
    if not empresa:
        return jsonify({"success": False, "error": "No hay sesión activa"}), 401

    planogram_image = empresa.get('planogram_image')
    if not planogram_image:
        return jsonify({"success": True, "has_planograma": False})

    public_url = f"{SUPABASE_URL}/storage/v1/object/public/visits_photos/{planogram_image}"
    return jsonify({
        "success": True,
        "has_planograma": True,
        "url": public_url
    })

@app.route('/login', methods=['POST'])
def do_login():
    data = request.get_json()  # Usamos JSON porque tu frontend envía fetch con JSON
    nombre = data.get('nombre', '').strip()
    clave = data.get('clave', '').strip()
    
    if not nombre or not clave:
        return jsonify({"success": False, "error": "Completa ambos campos"}), 400

    # Buscar empresa por nombre exacto
    url = f"{SUPABASE_URL}/rest/v1/empresas?nombre=eq.{nombre}&select=id,nombre,clave_acceso,estatus,fecha_vencimiento"
    response = requests.get(url, headers=headers)
    
    if response.status_code != 200 or not response.json():
        return jsonify({"success": False, "error": "Empresa no encontrada. Verifica el nombre exacto."}), 401
    
    empresa = response.json()[0]
    
    # Comparación directa de la clave (texto plano, como pediste)
    if empresa.get('clave_acceso') != clave:
        return jsonify({"success": False, "error": "Clave de acceso incorrecta."}), 401
    
    # Validaciones adicionales
    if empresa.get('estatus') != 'activa':
        return jsonify({"success": False, "error": f"La empresa está {empresa['estatus']}. Contacta al administrador."}), 403
    
    if empresa.get('fecha_vencimiento'):
        try:
            venc = datetime.fromisoformat(empresa['fecha_vencimiento'])
            if datetime.now() > venc:
                return jsonify({"success": False, "error": "La licencia de tu empresa ha expirado."}), 403
        except:
            pass  # Si falla el parseo, no bloqueamos por vencimiento
    
    # Guardar en sesión
    session['empresa_id'] = empresa['id']
    session['empresa_nombre'] = empresa['nombre']
    
    return jsonify({
        "success": True,
        "message": "Login correcto",
        "redirect": url_for('dashboard')
    })

@app.route('/api/planograma/upload', methods=['POST'])
def api_upload_planograma():
    empresa = get_current_empresa()
    if not empresa:
        return jsonify({"success": False, "error": "No hay sesión activa"}), 401

    empresa_id = empresa['id']

    if 'file' not in request.files:
        return jsonify({"success": False, "error": "No se envió ningún archivo"}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({"success": False, "error": "Nombre de archivo vacío"}), 400

    allowed_extensions = {'.jpg', '.jpeg', '.png'}
    if not any(file.filename.lower().endswith(ext) for ext in allowed_extensions):
        return jsonify({"success": False, "error": "Formato no permitido. Usa JPG o PNG"}), 400

    try:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        file_ext = os.path.splitext(file.filename)[1]
        file_name = f"planogramas/{empresa_id}/planograma_{timestamp}{file_ext}"

        # Subir archivo a Supabase Storage
        storage_url = f"{SUPABASE_URL}/storage/v1/object/visits_photos/{file_name}"
        storage_headers = {
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": file.content_type or "image/jpeg"
        }
        upload_response = requests.put(storage_url, headers=storage_headers, data=file.read())

        if upload_response.status_code not in (200, 201):
            return jsonify({
                "success": False,
                "error": f"Error al subir archivo: {upload_response.text}"
            }), 500

        # Actualizar campo en tabla empresas
        update_url = f"{SUPABASE_URL}/rest/v1/empresas?id=eq.{empresa_id}"
        update_payload = {"planogram_image": file_name}
        update_response = requests.patch(update_url, headers=headers, json=update_payload)

        if update_response.status_code not in (200, 204):
            return jsonify({
                "success": False,
                "error": "Archivo subido pero no se pudo actualizar la base de datos"
            }), 500

        public_url = f"{SUPABASE_URL}/storage/v1/object/public/visits_photos/{file_name}"
        return jsonify({
            "success": True,
            "message": "Planograma actualizado correctamente",
            "url": public_url
        })

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# ----------------------------------------------------------------------
# --- Rutas API existentes (sin cambios) ---
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

        try:
            visit_lat = float(record.get("latitude")) if record.get("latitude") not in [None, "None"] else None
            visit_lon = float(record.get("longitude")) if record.get("longitude") not in [None, "None"] else None
        except (ValueError, TypeError):
            visit_lat = visit_lon = None

        visit_coords_str = f"{visit_lat}, {visit_lon}" if visit_lat and visit_lon else "N/A"

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
            "state": estado,
            "zone": zona,
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
            "comments": record.get("comments", "N/A"),
            "before_photos": record.get("before_photos", []),
            "after_photos": record.get("after_photos", [])
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
# --- Rutas CRUD Productos Competencia ---
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


# --- INICIO ---
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8020))
    app.run(host='0.0.0.0', port=port)