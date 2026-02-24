from flask import Flask, render_template, jsonify, request, session, redirect, url_for
import requests
import os
from math import radians, sin, cos, sqrt, atan2
import re
import json
from datetime import datetime, timedelta

app = Flask(__name__)

# Configuración de Seguridad para sesiones
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'tu-clave-secreta-super-larga-y-segura-2025-xyz123')

# Credenciales de Supabase
SUPABASE_URL = "https://djjylikkocemrlsjxscr.supabase.co"
SUPABASE_KEY = os.getenv('SUPABASE_KEY', 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImRqanlsaWtrb2NlbXJsc2p4c2NyIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjMxNjUyNDEsImV4cCI6MjA3ODc0MTI0MX0.fnv1BKn_o-PYEAPljG0V3dt3b2Uifwn8EEzkP8Aab3M')

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
    """Cálculo de distancia entre dos puntos (Haversine)"""
    R = 6371000
    d_lat = radians(lat2 - lat1)
    d_lon = radians(lon2 - lon1)
    a = sin(d_lat / 2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(d_lon / 2)**2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return R * c


def get_week_date_range(year, week_number):
    """Obtiene el rango de fechas para una semana ISO específica"""
    jan4 = datetime(year, 1, 4)
    jan4_weekday = jan4.weekday()
    monday_week1 = jan4 - timedelta(days=jan4_weekday)
    start_of_week = monday_week1 + timedelta(weeks=week_number - 1)
    end_of_week = start_of_week + timedelta(days=6)
    return start_of_week.strftime('%Y-%m-%d'), end_of_week.strftime('%Y-%m-%d')


def safe_json_parse(value):
    """Convierte jsonb/string a lista de forma segura. Devuelve [] si falla."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except (json.JSONDecodeError, TypeError, ValueError):
            return []
    if isinstance(value, (dict, list)):
        return value
    return []


def safe_float(value, default=None):
    """Convierte a float de forma segura"""
    if value is None:
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def get_current_empresa():
    """Valida la sesión actual y devuelve datos de la empresa"""
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


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


@app.route('/dashboard')
def dashboard():
    if 'empresa_id' not in session:
        return redirect(url_for('login'))
    return render_template('dashboard.html')


@app.route('/gps')
def gps():
    if 'empresa_id' not in session:
        return redirect(url_for('login'))
    return render_template('GPS.html')


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


@app.route('/caras')
def caras():
    if 'empresa_id' not in session:
        return redirect(url_for('login'))
    return render_template('caras.html')

# ----------------------------------------------------------------------
# --- Lógica de Login ---
# ----------------------------------------------------------------------

@app.route('/login', methods=['POST'])
def do_login():
    data = request.get_json()
    nombre = data.get('nombre', '').strip()
    clave = data.get('clave', '').strip()
    
    if not nombre or not clave:
        return jsonify({"success": False, "error": "Completa ambos campos"}), 400

    url = f"{SUPABASE_URL}/rest/v1/empresas?nombre=eq.{nombre}&select=id,nombre,clave_acceso,estatus,fecha_vencimiento"
    
    try:
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            return jsonify({"success": False, "error": "Error de conexión con la base de datos"}), 500
        
        empresas = response.json()
        if not empresas:
            return jsonify({"success": False, "error": "Empresa no encontrada"}), 401

        empresa = empresas[0]

        if empresa.get('clave_acceso') == clave:
            if empresa.get('estatus') != 'activa':
                return jsonify({"success": False, "error": "La cuenta no está activa"}), 403
            
            session.clear()
            session['empresa_id'] = empresa['id']
            session['empresa_nombre'] = empresa['nombre']
            
            return jsonify({
                "success": True, 
                "empresa_id": empresa['id'],
                "empresa_nombre": empresa['nombre']
            })
        else:
            return jsonify({"success": False, "error": "Clave incorrecta"}), 401

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

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

        storage_url = f"{SUPABASE_URL}/storage/v1/object/visits_photos/{file_name}"
        storage_headers = {
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": file.content_type or "image/jpeg"
        }
        upload_response = requests.put(storage_url, headers=storage_headers, data=file.read())

        if upload_response.status_code not in (200, 201):
            return jsonify({"success": False, "error": "Error al subir al storage"}), 500

        update_url = f"{SUPABASE_URL}/rest/v1/empresas?id=eq.{empresa_id}"
        update_response = requests.patch(update_url, headers=headers, json={"planogram_image": file_name})

        if update_response.status_code not in (200, 204):
            return jsonify({"success": False, "error": "Error al actualizar base de datos"}), 500

        public_url = f"{SUPABASE_URL}/storage/v1/object/public/visits_photos/{file_name}"
        return jsonify({"success": True, "url": public_url})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# ----------------------------------------------------------------------
# --- API Registros (versión corregida y robusta) ---
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
    year_str = request.args.get('year', str(datetime.now().year))

    params = [
        ("select", "*,web_promotores!inner(promoter_name, promoter_id)"),
        ("order", "created_at.desc"),
        ("empresa_id", f"eq.{empresa_id}")
    ]

    # Manejo seguro del año
    try:
        year = int(year_str)
    except:
        year = datetime.now().year

    if week:
        try:
            week_num = int(week)
            date_from, date_to = get_week_date_range(year, week_num)
            params.append(("created_at", f"gte.{date_from}T00:00:00+00:00"))
            params.append(("created_at", f"lte.{date_to}T23:59:59+00:00"))
        except Exception as e:
            print(f"Error calculando semana {week}/{year}: {str(e)}")
            return jsonify({"error": "Rango de semana inválido"}), 400
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

    # Mapa de clientes más seguro
    clientes_by_id = {}
    for c in clientes:
        cid = c.get("id")
        if cid is not None:
            try:
                clientes_by_id[int(cid)] = c
            except:
                continue

    formatted_records = []

    for record in records_raw:
        try:
            promoter_info = record.get('web_promotores') or {}

            # Coordenadas visita - seguro
            visit_lat = safe_float(record.get("latitude"))
            visit_lon = safe_float(record.get("longitude"))

            # Cliente
            cliente_id_raw = record.get("cliente_id")
            cliente_id = None
            if cliente_id_raw is not None:
                try:
                    cliente_id = int(cliente_id_raw)
                except:
                    pass

            cliente_data = clientes_by_id.get(cliente_id)

            distance = 0.0
            verified_status = "Cliente Desconocido"
            cliente_coords_str = "N/A"

            if cliente_data:
                c_lat = safe_float(cliente_data.get("latitude"), 0.0)
                c_lon = safe_float(cliente_data.get("longitude"), 0.0)

                if c_lat != 0.0:
                    cliente_coords_str = f"{c_lat:.5f}, {c_lon:.5f}"

                if visit_lat is not None and visit_lon is not None and c_lat != 0.0:
                    try:
                        distance = calculate_distance(visit_lat, visit_lon, c_lat, c_lon)
                        verified_status = "Confirmado" if distance <= 150 else "No Confirmado"
                    except Exception as dist_err:
                        print(f"Error distancia registro {record.get('id')}: {dist_err}")
                        verified_status = "Error cálculo distancia"
                elif visit_lat is None or visit_lon is None:
                    verified_status = "Sin GPS Visita"

            formatted_records.append({
                "id": record.get("id"),
                "created_at": record.get("created_at"),
                "promoter_name": promoter_info.get('promoter_name', "Sin Nombre"),
                "state": record.get("state", "N/A"),
                "zone": record.get("zone", "N/A"),
                "trade": record.get("trade", "N/A"),
                "distance": round(distance, 2) if distance else 0,
                "verified": verified_status,
                "latitude": visit_lat,
                "longitude": visit_lon,
                "client_coords": cliente_coords_str,
                "myitems": safe_json_parse(record.get("myitems")),
                "competitoritems": safe_json_parse(record.get("competitoritems")),
                "before_photos": safe_json_parse(record.get("before_photos")),
                "after_photos": safe_json_parse(record.get("after_photos"))
            })

        except Exception as e:
            print(f"Error procesando registro {record.get('id', 'sin-id')}: {str(e)}")
            continue  # No dejamos que un registro malo rompa todo

    return jsonify({
        "records": formatted_records,
        "promoters": promotores,
        "estados": estados,
        "zonas": zonas
    })


@app.route('/api/weeks_with_visits', methods=['GET'])
def get_weeks_with_visits():
    empresa_id = request.args.get('empresa_id')
    if not empresa_id:
        return jsonify({"error": "empresa_id requerido"}), 400
    
    year = request.args.get('year', str(datetime.now().year))
    params = [
        ("select", "created_at"),
        ("empresa_id", f"eq.{empresa_id}"),
        ("created_at", f"gte.{year}-01-01T00:00:00+00:00")
    ]
    records = fetch_table("web_precios", params=params)
    weeks = set()
    for r in records:
        try:
            dt_str = r.get('created_at')
            if dt_str:
                dt = datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
                weeks.add(dt.isocalendar()[1])
        except Exception as e:
            print(f"Error parseando fecha en weeks: {str(e)} - registro: {r}")
            continue
    return jsonify({"weeks": sorted(list(weeks), reverse=True)})


@app.route('/delete_records', methods=['POST'])
def delete_records():
    data = request.json or {}
    ids = data.get("ids", [])
    empresa_id = data.get("empresa_id")
    if not empresa_id or not ids:
        return jsonify({"success": False}), 400
    
    id_list = ",".join(map(str, ids))
    url = f"{SUPABASE_URL}/rest/v1/web_precios?id=in.({id_list})&empresa_id=eq.{empresa_id}"
    res = requests.delete(url, headers=headers)
    return jsonify({"success": res.ok})

# ----------------------------------------------------------------------
# --- Rutas CRUD Productos Competencia ---
# ----------------------------------------------------------------------

@app.route('/api/competitorproducts', methods=['GET', 'POST'])
def handle_competitor_products():
    if request.method == 'GET':
        products = fetch_table("web_competidor", params=[("order", "presentation.asc")])
        return jsonify({"products": products})
    
    data = request.json
    res = requests.post(f"{SUPABASE_URL}/rest/v1/web_competidor", headers=headers, json={"presentation": data.get("presentation")})
    return jsonify({"success": res.ok}), 201


@app.route('/api/competitorproducts/<int:product_id>', methods=['PATCH', 'DELETE'])
def update_delete_competitor(product_id):
    url = f"{SUPABASE_URL}/rest/v1/web_competidor?id=eq.{product_id}"
    if request.method == 'PATCH':
        res = requests.patch(url, headers=headers, json=request.json)
    else:
        res = requests.delete(url, headers=headers)
    return jsonify({"success": res.ok})


# ----------------------------------------------------------------------
# --- Rutas CRUD Productos Propios ---
# ----------------------------------------------------------------------

from flask import Flask, render_template, jsonify, request, session, redirect, url_for
import requests
import os
from math import radians, sin, cos, sqrt, atan2
import re
import json
from datetime import datetime, timedelta

app = Flask(__name__)

# Configuración de Seguridad para sesiones
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'tu-clave-secreta-super-larga-y-segura-2025-xyz123')

# Credenciales de Supabase
SUPABASE_URL = "https://djjylikkocemrlsjxscr.supabase.co"
SUPABASE_KEY = os.getenv('SUPABASE_KEY', 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImRqanlsaWtrb2NlbXJsc2p4c2NyIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjMxNjUyNDEsImV4cCI6MjA3ODc0MTI0MX0.fnv1BKn_o-PYEAPljG0V3dt3b2Uifwn8EEzkP8Aab3M')

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
    """Cálculo de distancia entre dos puntos (Haversine)"""
    R = 6371000
    d_lat = radians(lat2 - lat1)
    d_lon = radians(lon2 - lon1)
    a = sin(d_lat / 2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(d_lon / 2)**2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return R * c


def get_week_date_range(year, week_number):
    """Obtiene el rango de fechas para una semana ISO específica"""
    jan4 = datetime(year, 1, 4)
    jan4_weekday = jan4.weekday()
    monday_week1 = jan4 - timedelta(days=jan4_weekday)
    start_of_week = monday_week1 + timedelta(weeks=week_number - 1)
    end_of_week = start_of_week + timedelta(days=6)
    return start_of_week.strftime('%Y-%m-%d'), end_of_week.strftime('%Y-%m-%d')


def safe_json_parse(value):
    """Convierte jsonb/string a lista de forma segura. Devuelve [] si falla."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except (json.JSONDecodeError, TypeError, ValueError):
            return []
    if isinstance(value, (dict, list)):
        return value
    return []


def safe_float(value, default=None):
    """Convierte a float de forma segura"""
    if value is None:
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def get_current_empresa():
    """Valida la sesión actual y devuelve datos de la empresa"""
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


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


@app.route('/dashboard')
def dashboard():
    if 'empresa_id' not in session:
        return redirect(url_for('login'))
    return render_template('dashboard.html')


@app.route('/gps')
def gps():
    if 'empresa_id' not in session:
        return redirect(url_for('login'))
    return render_template('GPS.html')


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


@app.route('/caras')
def caras():
    if 'empresa_id' not in session:
        return redirect(url_for('login'))
    return render_template('caras.html')

# ----------------------------------------------------------------------
# --- Lógica de Login ---
# ----------------------------------------------------------------------

@app.route('/login', methods=['POST'])
def do_login():
    data = request.get_json()
    nombre = data.get('nombre', '').strip()
    clave = data.get('clave', '').strip()
    
    if not nombre or not clave:
        return jsonify({"success": False, "error": "Completa ambos campos"}), 400

    url = f"{SUPABASE_URL}/rest/v1/empresas?nombre=eq.{nombre}&select=id,nombre,clave_acceso,estatus,fecha_vencimiento"
    
    try:
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            return jsonify({"success": False, "error": "Error de conexión con la base de datos"}), 500
        
        empresas = response.json()
        if not empresas:
            return jsonify({"success": False, "error": "Empresa no encontrada"}), 401

        empresa = empresas[0]

        if empresa.get('clave_acceso') == clave:
            if empresa.get('estatus') != 'activa':
                return jsonify({"success": False, "error": "La cuenta no está activa"}), 403
            
            session.clear()
            session['empresa_id'] = empresa['id']
            session['empresa_nombre'] = empresa['nombre']
            
            return jsonify({
                "success": True, 
                "empresa_id": empresa['id'],
                "empresa_nombre": empresa['nombre']
            })
        else:
            return jsonify({"success": False, "error": "Clave incorrecta"}), 401

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

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

        storage_url = f"{SUPABASE_URL}/storage/v1/object/visits_photos/{file_name}"
        storage_headers = {
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": file.content_type or "image/jpeg"
        }
        upload_response = requests.put(storage_url, headers=storage_headers, data=file.read())

        if upload_response.status_code not in (200, 201):
            return jsonify({"success": False, "error": "Error al subir al storage"}), 500

        update_url = f"{SUPABASE_URL}/rest/v1/empresas?id=eq.{empresa_id}"
        update_response = requests.patch(update_url, headers=headers, json={"planogram_image": file_name})

        if update_response.status_code not in (200, 204):
            return jsonify({"success": False, "error": "Error al actualizar base de datos"}), 500

        public_url = f"{SUPABASE_URL}/storage/v1/object/public/visits_photos/{file_name}"
        return jsonify({"success": True, "url": public_url})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# ----------------------------------------------------------------------
# --- API Registros (versión corregida y robusta) ---
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
    year_str = request.args.get('year', str(datetime.now().year))

    params = [
        ("select", "*,web_promotores!inner(promoter_name, promoter_id)"),
        ("order", "created_at.desc"),
        ("empresa_id", f"eq.{empresa_id}")
    ]

    # Manejo seguro del año
    try:
        year = int(year_str)
    except:
        year = datetime.now().year

    if week:
        try:
            week_num = int(week)
            date_from, date_to = get_week_date_range(year, week_num)
            params.append(("created_at", f"gte.{date_from}T00:00:00+00:00"))
            params.append(("created_at", f"lte.{date_to}T23:59:59+00:00"))
        except Exception as e:
            print(f"Error calculando semana {week}/{year}: {str(e)}")
            return jsonify({"error": "Rango de semana inválido"}), 400
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

    # Mapa de clientes más seguro
    clientes_by_id = {}
    for c in clientes:
        cid = c.get("id")
        if cid is not None:
            try:
                clientes_by_id[int(cid)] = c
            except:
                continue

    formatted_records = []

    for record in records_raw:
        try:
            promoter_info = record.get('web_promotores') or {}

            # Coordenadas visita - seguro
            visit_lat = safe_float(record.get("latitude"))
            visit_lon = safe_float(record.get("longitude"))

            # Cliente
            cliente_id_raw = record.get("cliente_id")
            cliente_id = None
            if cliente_id_raw is not None:
                try:
                    cliente_id = int(cliente_id_raw)
                except:
                    pass

            cliente_data = clientes_by_id.get(cliente_id)

            distance = 0.0
            verified_status = "Cliente Desconocido"
            cliente_coords_str = "N/A"

            if cliente_data:
                c_lat = safe_float(cliente_data.get("latitude"), 0.0)
                c_lon = safe_float(cliente_data.get("longitude"), 0.0)

                if c_lat != 0.0:
                    cliente_coords_str = f"{c_lat:.5f}, {c_lon:.5f}"

                if visit_lat is not None and visit_lon is not None and c_lat != 0.0:
                    try:
                        distance = calculate_distance(visit_lat, visit_lon, c_lat, c_lon)
                        verified_status = "Confirmado" if distance <= 150 else "No Confirmado"
                    except Exception as dist_err:
                        print(f"Error distancia registro {record.get('id')}: {dist_err}")
                        verified_status = "Error cálculo distancia"
                elif visit_lat is None or visit_lon is None:
                    verified_status = "Sin GPS Visita"

            formatted_records.append({
                "id": record.get("id"),
                "created_at": record.get("created_at"),
                "promoter_name": promoter_info.get('promoter_name', "Sin Nombre"),
                "state": record.get("state", "N/A"),
                "zone": record.get("zone", "N/A"),
                "trade": record.get("trade", "N/A"),
                "distance": round(distance, 2) if distance else 0,
                "verified": verified_status,
                "latitude": visit_lat,
                "longitude": visit_lon,
                "client_coords": cliente_coords_str,
                "myitems": safe_json_parse(record.get("myitems")),
                "competitoritems": safe_json_parse(record.get("competitoritems")),
                "before_photos": safe_json_parse(record.get("before_photos")),
                "after_photos": safe_json_parse(record.get("after_photos"))
            })

        except Exception as e:
            print(f"Error procesando registro {record.get('id', 'sin-id')}: {str(e)}")
            continue  # No dejamos que un registro malo rompa todo

    return jsonify({
        "records": formatted_records,
        "promoters": promotores,
        "estados": estados,
        "zonas": zonas
    })


@app.route('/api/weeks_with_visits', methods=['GET'])
def get_weeks_with_visits():
    empresa_id = request.args.get('empresa_id')
    if not empresa_id:
        return jsonify({"error": "empresa_id requerido"}), 400
    
    year = request.args.get('year', str(datetime.now().year))
    params = [
        ("select", "created_at"),
        ("empresa_id", f"eq.{empresa_id}"),
        ("created_at", f"gte.{year}-01-01T00:00:00+00:00")
    ]
    records = fetch_table("web_precios", params=params)
    weeks = set()
    for r in records:
        try:
            dt_str = r.get('created_at')
            if dt_str:
                dt = datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
                weeks.add(dt.isocalendar()[1])
        except Exception as e:
            print(f"Error parseando fecha en weeks: {str(e)} - registro: {r}")
            continue
    return jsonify({"weeks": sorted(list(weeks), reverse=True)})


@app.route('/delete_records', methods=['POST'])
def delete_records():
    data = request.json or {}
    ids = data.get("ids", [])
    empresa_id = data.get("empresa_id")
    if not empresa_id or not ids:
        return jsonify({"success": False}), 400
    
    id_list = ",".join(map(str, ids))
    url = f"{SUPABASE_URL}/rest/v1/web_precios?id=in.({id_list})&empresa_id=eq.{empresa_id}"
    res = requests.delete(url, headers=headers)
    return jsonify({"success": res.ok})

# ----------------------------------------------------------------------
# --- Rutas CRUD Productos Competencia ---
# ----------------------------------------------------------------------
@app.route('/api/competitorproducts', methods=['GET', 'POST'])
def handle_competitor_products():
    if request.method == 'GET':
        empresa_id = request.args.get('empresa_id')
        if not empresa_id:
            return jsonify({"error": "empresa_id es requerido"}), 400

        products = fetch_table(
            "web_competidor",
            params=[("order", "presentation.asc")],
            empresa_id=empresa_id
        )
        return jsonify({"products": products})

    # POST - creación
    if not request.is_json:
        return jsonify({"error": "Se esperaba contenido JSON"}), 400

    data = request.json
    presentation = data.get("presentation", "").strip()
    empresa_id = data.get("empresa_id")

    if not presentation:
        return jsonify({"error": "El campo 'presentation' es requerido"}), 400
    if not empresa_id:
        return jsonify({"error": "empresa_id es requerido"}), 400

    payload = {
        "presentation": presentation.upper(),     # o .strip().upper() si prefieres
        "empresa_id": empresa_id
    }

    res = requests.post(
        f"{SUPABASE_URL}/rest/v1/web_competidor",
        headers=headers,
        json=payload
    )

    if res.status_code in (200, 201):
        return jsonify({"success": True}), 201
    else:
        try:
            error_detail = res.json()
        except:
            error_detail = {"message": res.text or "Error desconocido"}
        return jsonify({"error": error_detail.get("message", "No se pudo crear el producto")}), res.status_code
    

@app.route('/api/competitorproducts/<product_id>', methods=['PATCH', 'DELETE'])
def update_delete_competitor(product_id):
    empresa_id = None

    # Obtener empresa_id según el método
    if request.method == 'PATCH':
        if not request.is_json:
            return jsonify({"error": "Se esperaba JSON"}), 400
        empresa_id = request.json.get('empresa_id')
    else:  # DELETE
        empresa_id = request.args.get('empresa_id')

    # Depuración detallada
    print("\n" + "=" * 70)
    print(f"[COMPETITOR {request.method}] product_id: {product_id}")
    print(f"[COMPETITOR {request.method}] empresa_id recibido: '{empresa_id}'")
    print(f"[COMPETITOR {request.method}] tipo: {type(empresa_id)} | longitud: {len(empresa_id) if empresa_id else 'None'}")

    if not empresa_id:
        return jsonify({"error": "empresa_id es requerido"}), 400

    # URL de verificación (más selectivo para depurar)
    check_url = f"{SUPABASE_URL}/rest/v1/web_competidor?id=eq.{product_id}&empresa_id=eq.{empresa_id}&select=id,presentation,empresa_id,created_at"

    print(f"[CHECK] URL: {check_url}")

    try:
        check_response = requests.get(check_url, headers=headers, timeout=10)
        print(f"[CHECK] Status: {check_response.status_code}")
        print(f"[CHECK] Contenido: {check_response.text[:500]}{'...' if len(check_response.text) > 500 else ''}")
        
        check_data = check_response.json() if check_response.ok else []
        
        if not check_response.ok or len(check_data) == 0:
            return jsonify({
                "error": "No se encontró el producto de competidor o no pertenece a esta empresa",
                "status_check": check_response.status_code,
                "body_check": check_response.text,
                "product_id_usado": product_id,
                "empresa_id_usado": empresa_id
            }), 403

    except Exception as e:
        print(f"[CHECK] Excepción al verificar: {str(e)}")
        return jsonify({"error": f"Error al verificar existencia: {str(e)}"}), 500

    # URL para la operación real
    operation_url = f"{SUPABASE_URL}/rest/v1/web_competidor?id=eq.{product_id}&empresa_id=eq.{empresa_id}"

    print(f"[OPERACIÓN] URL: {operation_url}")

    try:
        if request.method == 'PATCH':
            if not request.is_json:
                return jsonify({"error": "Se esperaba JSON"}), 400
            payload = {k: v for k, v in request.json.items() if k != 'empresa_id'}
            print(f"[PATCH] Payload enviado: {payload}")
            res = requests.patch(operation_url, headers=headers, json=payload, timeout=10)
        else:
            res = requests.delete(operation_url, headers=headers, timeout=10)

        print(f"[OPERACIÓN] Status: {res.status_code}")
        if not res.ok:
            print(f"[OPERACIÓN] Error: {res.text}")

        if res.status_code in (200, 204):
            return jsonify({"success": True, "message": "Operación exitosa"}), 200 if request.method == 'PATCH' else 204

        return jsonify({
            "error": "Error al ejecutar la operación en Supabase",
            "status": res.status_code,
            "detail": res.text
        }), res.status_code

    except Exception as e:
        print(f"[OPERACIÓN] Excepción: {str(e)}")
        return jsonify({"error": f"Error en la operación: {str(e)}"}), 500


@app.route('/api/myproducts/<product_id>', methods=['PATCH', 'DELETE'])
def update_delete_myproduct(product_id):
    empresa_id = None

    # Obtener empresa_id según el método
    if request.method == 'PATCH':
        if not request.is_json:
            return jsonify({"error": "Se esperaba JSON"}), 400
        empresa_id = request.json.get('empresa_id')
    else:  # DELETE
        empresa_id = request.args.get('empresa_id')

    # Depuración detallada
    print("\n" + "=" * 70)
    print(f"[MYPRODUCTS {request.method}] product_id: {product_id}")
    print(f"[MYPRODUCTS {request.method}] empresa_id recibido: '{empresa_id}'")
    print(f"[MYPRODUCTS {request.method}] tipo: {type(empresa_id)} | longitud: {len(empresa_id) if empresa_id else 'None'}")

    if not empresa_id:
        return jsonify({"error": "empresa_id es requerido"}), 400

    # URL de verificación (más selectivo para depurar)
    check_url = f"{SUPABASE_URL}/rest/v1/web_myproductos?id=eq.{product_id}&empresa_id=eq.{empresa_id}&select=id,presentation,empresa_id,created_at"

    print(f"[CHECK] URL: {check_url}")

    try:
        check_response = requests.get(check_url, headers=headers, timeout=10)
        print(f"[CHECK] Status: {check_response.status_code}")
        print(f"[CHECK] Contenido: {check_response.text[:500]}{'...' if len(check_response.text) > 500 else ''}")
        
        check_data = check_response.json() if check_response.ok else []
        
        if not check_response.ok or len(check_data) == 0:
            return jsonify({
                "error": "No se encontró el producto o no pertenece a esta empresa",
                "status_check": check_response.status_code,
                "body_check": check_response.text,
                "product_id_usado": product_id,
                "empresa_id_usado": empresa_id
            }), 403

    except Exception as e:
        print(f"[CHECK] Excepción al verificar: {str(e)}")
        return jsonify({"error": f"Error al verificar existencia: {str(e)}"}), 500

    # URL para la operación real
    operation_url = f"{SUPABASE_URL}/rest/v1/web_myproductos?id=eq.{product_id}&empresa_id=eq.{empresa_id}"

    print(f"[OPERACIÓN] URL: {operation_url}")

    try:
        if request.method == 'PATCH':
            if not request.is_json:
                return jsonify({"error": "Se esperaba JSON"}), 400
            payload = {k: v for k, v in request.json.items() if k != 'empresa_id'}
            print(f"[PATCH] Payload enviado: {payload}")
            res = requests.patch(operation_url, headers=headers, json=payload, timeout=10)
        else:
            res = requests.delete(operation_url, headers=headers, timeout=10)

        print(f"[OPERACIÓN] Status: {res.status_code}")
        if not res.ok:
            print(f"[OPERACIÓN] Error: {res.text}")

        if res.status_code in (200, 204):
            return jsonify({"success": True, "message": "Operación exitosa"}), 200 if request.method == 'PATCH' else 204

        return jsonify({
            "error": "Error al ejecutar la operación en Supabase",
            "status": res.status_code,
            "detail": res.text
        }), res.status_code

    except Exception as e:
        print(f"[OPERACIÓN] Excepción: {str(e)}")
        return jsonify({"error": f"Error en la operación: {str(e)}"}), 500

# ----------------------------------------------------------------------
# --- Rutas CRUD Productos Propios ---
# ----------------------------------------------------------------------

@app.route('/api/myproducts', methods=['GET', 'POST'])
def handle_my_products():
    if request.method == 'GET':
        empresa_id = request.args.get('empresa_id')
        
        if not empresa_id:
            return jsonify({"error": "empresa_id es requerido"}), 400

        # ← Aquí agregamos el filtro por empresa
        products = fetch_table(
            "web_myproductos",
            params=[("order", "presentation.asc")],
            empresa_id=empresa_id           # Esto usa el mecanismo que ya tienes en fetch_table
        )
        return jsonify({"products": products})
    
    # POST (lo dejamos casi igual, pero mejoramos un poco)
    if not request.is_json:
        return jsonify({"error": "Se esperaba JSON"}), 400
        
    data = request.json
    presentation = data.get("presentation", "").strip()
    empresa_id = data.get("empresa_id")   # ← importante: el frontend lo está enviando

    if not presentation:
        return jsonify({"error": "presentation es requerido"}), 400
    if not empresa_id:
        return jsonify({"error": "empresa_id es requerido"}), 400

    payload = {
        "presentation": presentation.upper(),  # o .strip().upper() según prefieras
        "empresa_id": empresa_id
    }

    res = requests.post(
        f"{SUPABASE_URL}/rest/v1/web_myproductos",
        headers=headers,
        json=payload
    )

    if res.status_code in (200, 201):
        return jsonify({"success": True}), 201
    else:
        try:
            error_info = res.json()
        except:
            error_info = {"message": res.text}
        return jsonify({"error": error_info.get("message", "Error al crear")}), res.status_code

# --- INICIO ---
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8020))
    app.run(host='0.0.0.0', port=port, debug=True)


