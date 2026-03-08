from flask import Flask, render_template, jsonify, request, session, redirect, url_for
import requests
import os
import time
from math import radians, sin, cos, sqrt, atan2
import json
from datetime import datetime, timedelta
from functools import wraps

app = Flask(__name__)

# ─── Configuración de seguridad ───────────────────────────────────────────────
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'tu-clave-secreta-super-larga-y-segura-2025-xyz123')

SUPABASE_URL = "https://djjylikkocemrlsjxscr.supabase.co"
SUPABASE_KEY = os.getenv('SUPABASE_KEY', 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImRqanlsaWtrb2NlbXJsc2p4c2NyIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjMxNjUyNDEsImV4cCI6MjA3ODc0MTI0MX0.fnv1BKn_o-PYEAPljG0V3dt3b2Uifwn8EEzkP8Aab3M')

headers = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "count=exact"
}

# ─── Caché en memoria con TTL ─────────────────────────────────────────────────
# { cache_key: { "data": ..., "ts": timestamp } }
_cache: dict = {}
CACHE_TTL_SECONDS = 120  # 2 minutos — configurable


def cache_get(key: str):
    entry = _cache.get(key)
    if entry and (time.time() - entry["ts"]) < CACHE_TTL_SECONDS:
        return entry["data"]
    return None


def cache_set(key: str, data):
    _cache[key] = {"data": data, "ts": time.time()}


def cache_invalidate_prefix(prefix: str):
    """Invalida todas las entradas que empiecen con prefix."""
    keys_to_del = [k for k in _cache if k.startswith(prefix)]
    for k in keys_to_del:
        del _cache[k]


# ─── Decorador de sesión ──────────────────────────────────────────────────────
def require_session(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if 'empresa_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return wrapper


# ─── Utilidades ───────────────────────────────────────────────────────────────
def fetch_table(table_name, params=None, empresa_id=None, limit=1000):
    """Fetch paginado contra Supabase REST API."""
    url = f"{SUPABASE_URL}/rest/v1/{table_name}"
    all_data = []
    offset = 0
    query_params = list(params or [])

    if empresa_id is not None:
        query_params.append(("empresa_id", f"eq.{empresa_id}"))

    while True:
        h = {**headers, "Range": f"{offset}-{offset + limit - 1}"}
        try:
            resp = requests.get(url, headers=h, params=query_params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            if not data:
                break
            all_data.extend(data)
            if len(data) < limit:
                break
            offset += limit
        except requests.RequestException as e:
            print(f"[fetch_table] Error tabla {table_name}: {e}")
            break

    return all_data


def fetch_table_page(table_name, params, page: int, page_size: int):
    """
    Fetch de UNA página específica con count total.
    Retorna (data, total_count).
    """
    url = f"{SUPABASE_URL}/rest/v1/{table_name}"
    offset = (page - 1) * page_size
    h = {
        **headers,
        "Range": f"{offset}-{offset + page_size - 1}",
        "Prefer": "count=exact"
    }
    try:
        resp = requests.get(url, headers=h, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        # Supabase devuelve Content-Range: 0-24/1000
        content_range = resp.headers.get("Content-Range", "")
        total = 0
        if "/" in content_range:
            try:
                total = int(content_range.split("/")[1])
            except ValueError:
                total = len(data)
        return data, total
    except requests.RequestException as e:
        print(f"[fetch_table_page] Error: {e}")
        return [], 0


def calculate_distance(lat1, lon1, lat2, lon2) -> float:
    R = 6371000.0
    d_lat = radians(lat2 - lat1)
    d_lon = radians(lon2 - lon1)
    a = sin(d_lat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(d_lon / 2) ** 2
    return R * 2 * atan2(sqrt(a), sqrt(1 - a))


def get_week_date_range(year: int, week_number: int):
    jan4 = datetime(year, 1, 4)
    monday_w1 = jan4 - timedelta(days=jan4.weekday())
    start = monday_w1 + timedelta(weeks=week_number - 1)
    end = start + timedelta(days=6)
    return start.strftime('%Y-%m-%d'), end.strftime('%Y-%m-%d')


def safe_json_parse(value):
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
    return []


def safe_float(value, default=None):
    if value is None:
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def get_current_empresa():
    empresa_id = session.get('empresa_id')
    if not empresa_id:
        return None
    url = f"{SUPABASE_URL}/rest/v1/empresas?id=eq.{empresa_id}&select=id,nombre,planogram_image"
    resp = requests.get(url, headers=headers, timeout=5)
    if resp.status_code == 200 and resp.json():
        return resp.json()[0]
    return None


def process_record(record: dict, clientes_by_trade: dict) -> dict:
    """Convierte un raw record de Supabase al formato que espera el dashboard."""
    promoter_info = record.get('web_promotores') or {}
    visit_lat = safe_float(record.get("latitude"))
    visit_lon = safe_float(record.get("longitude"))

    trade_name = (record.get("trade") or "").strip().upper()
    cliente_data = clientes_by_trade.get(trade_name)

    distance = 0.0
    verified_status = "Cliente Desconocido"
    cliente_coords_str = "N/A"
    visit_coords_str = "N/A"

    if visit_lat is not None and visit_lon is not None:
        visit_coords_str = f"{visit_lat:.5f}, {visit_lon:.5f}"
        verified_status = "Sin Coordenadas Cliente"

    if cliente_data:
        c_lat = safe_float(cliente_data.get("latitude"), 0.0)
        c_lon = safe_float(cliente_data.get("longitude"), 0.0)
        if c_lat != 0.0:
            cliente_coords_str = f"{c_lat:.5f}, {c_lon:.5f}"
        if visit_lat is not None and visit_lon is not None and c_lat != 0.0:
            try:
                distance = calculate_distance(visit_lat, visit_lon, c_lat, c_lon)
                verified_status = "Confirmado" if distance <= 150 else "No Confirmado"
            except Exception:
                verified_status = "Error distancia"
        elif visit_lat is None or visit_lon is None:
            verified_status = "Sin GPS Visita"

    return {
        "id": record.get("id"),
        "created_at": record.get("created_at"),
        "promoter_name": promoter_info.get('promoter_name', "Sin Nombre"),
        "state": record.get("state", "N/A"),
        "zone": record.get("zone", "N/A"),
        "trade": record.get("trade", "N/A"),
        "distance": round(distance, 2),
        "verified": verified_status,
        "visit_coords": visit_coords_str,
        "client_coords": cliente_coords_str,
        "latitude": visit_lat,
        "longitude": visit_lon,
        "comments": record.get("comments", ""),
        "p_mayorista": record.get("p_mayorista", "No"),
        "cliente_cerrado": record.get("cliente_cerrado", "No"),
        "total_faces_before": record.get("total_faces_before"),
        "total_faces": record.get("total_faces"),
        "our_faces_before_manual": record.get("our_faces_before_manual"),
        "our_faces_after": record.get("our_faces_after"),
        "myitems": safe_json_parse(record.get("myitems")),
        "competitoritems": safe_json_parse(record.get("competitoritems")),
        "before_photos": safe_json_parse(record.get("before_photos")),
        "after_photos": safe_json_parse(record.get("after_photos")),
    }


def build_records_params(empresa_id, date_from=None, date_to=None,
                         promoter_id=None, week=None, year=None):
    """Construye la lista de params para query a web_precios."""
    year = year or datetime.now().year
    params = [
        ("select", "*,web_promotores!inner(promoter_name,promoter_id)"),
        ("order", "created_at.desc"),
        ("empresa_id", f"eq.{empresa_id}"),
    ]

    if week:
        try:
            d_from, d_to = get_week_date_range(int(year), int(week))
            params.append(("created_at", f"gte.{d_from}T00:00:00+00:00"))
            params.append(("created_at", f"lte.{d_to}T23:59:59+00:00"))
        except Exception as e:
            print(f"[build_params] Semana inválida {week}/{year}: {e}")
    else:
        if date_from:
            params.append(("created_at", f"gte.{date_from}T00:00:00+00:00"))
        if date_to:
            params.append(("created_at", f"lte.{date_to}T23:59:59+00:00"))

    if promoter_id and promoter_id != 'all':
        params.append(("promoter_id", f"eq.{promoter_id}"))

    return params


# ─── Rutas de vistas ──────────────────────────────────────────────────────────
@app.route('/')
def login():
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


@app.route('/dashboard')
@require_session
def dashboard():
    return render_template('dashboard.html')


@app.route('/gps')
@require_session
def gps():
    return render_template('GPS.html')


@app.route('/lineas')
@require_session
def lineas():
    return render_template('lineas.html')


@app.route('/clientes')
@require_session
def clientes():
    return render_template('clientes.html')


@app.route('/analisis')
@require_session
def analisis():
    return render_template('analisis.html')


@app.route('/promotores')
@require_session
def promotores():
    return render_template('promotores.html')


@app.route('/competencia')
@require_session
def productos_competencia():
    return render_template('competencia.html')


@app.route('/productos')
@require_session
def productos():
    return render_template('productos.html')


@app.route('/stock')
@require_session
def stock():
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
@require_session
def caras():
    return render_template('caras.html')


# ─── Login / Logout ───────────────────────────────────────────────────────────
@app.route('/login', methods=['POST'])
def do_login():
    data = request.get_json()
    nombre = (data.get('nombre') or '').strip()
    clave = (data.get('clave') or '').strip()

    if not nombre or not clave:
        return jsonify({"success": False, "error": "Completa ambos campos"}), 400

    url = f"{SUPABASE_URL}/rest/v1/empresas?nombre=eq.{nombre}&clave_acceso=eq.{clave}&select=id,nombre"
    resp = requests.get(url, headers=headers, timeout=5)
    if resp.status_code == 200 and resp.json():
        empresa = resp.json()[0]
        session['empresa_id'] = empresa['id']
        session['empresa_nombre'] = empresa['nombre']
        return jsonify({"success": True, "empresa_id": empresa['id'], "empresa_nombre": empresa['nombre']})
    return jsonify({"success": False, "error": "Credenciales incorrectas"}), 401


# ─── API: Configuración pública del dashboard (sin exponer SUPABASE_KEY) ──────
@app.route('/api/dashboard/config')
@require_session
def dashboard_config():
    """
    Retorna solo lo necesario para que el frontend inicialice.
    NUNCA expone SUPABASE_KEY.
    """
    return jsonify({
        "empresa_id": session['empresa_id'],
        "empresa_nombre": session.get('empresa_nombre', ''),
    })


# ─── API: Records con paginación server-side ──────────────────────────────────
@app.route('/api/records', methods=['GET'])
def get_records():
    empresa_id = request.args.get('empresa_id')
    if not empresa_id:
        return jsonify({"error": "empresa_id es requerido"}), 400

    date_from   = request.args.get('date_from')
    date_to     = request.args.get('date_to')
    promoter_id = request.args.get('promoter_id')
    week        = request.args.get('week')
    year        = request.args.get('year', str(datetime.now().year))
    page        = max(1, int(request.args.get('page', 1)))
    page_size   = min(200, max(10, int(request.args.get('page_size', 50))))

    # ── Caché key ─────────────────────────────────────────────────────────────
    cache_key = f"records:{empresa_id}:{date_from}:{date_to}:{promoter_id}:{week}:{year}:{page}:{page_size}"
    cached = cache_get(cache_key)
    if cached:
        return jsonify({**cached, "from_cache": True})

    # ── Query params ──────────────────────────────────────────────────────────
    try:
        params = build_records_params(empresa_id, date_from, date_to, promoter_id, week, year)
    except Exception as e:
        return jsonify({"error": str(e)}), 400

    # ── Fetch paginado + catálogos en paralelo (via requests secuencial — simple y robusto) ──
    records_raw, total_count = fetch_table_page("web_precios", params, page, page_size)

    # Catálogos — cacheados por empresa separadamente para mayor reuso
    cat_key = f"catalogs:{empresa_id}"
    catalogs = cache_get(cat_key)
    if not catalogs:
        clientes   = fetch_table("web_clientes",   empresa_id=empresa_id)
        promotores = fetch_table("web_promotores", empresa_id=empresa_id)
        estados    = fetch_table("web_estados",    empresa_id=empresa_id)
        zonas      = fetch_table("web_zonas",      empresa_id=empresa_id)
        catalogs = {
            "clientes": clientes,
            "promotores": promotores,
            "estados": estados,
            "zonas": zonas,
        }
        cache_set(cat_key, catalogs)

    # ── Índice de clientes por trade_name (upper) ─────────────────────────────
    clientes_by_trade: dict = {}
    for c in catalogs["clientes"]:
        trade = (c.get("trade_name") or "").strip().upper()
        if trade:
            clientes_by_trade[trade] = c

    # ── Procesar registros ────────────────────────────────────────────────────
    formatted = []
    for record in records_raw:
        try:
            formatted.append(process_record(record, clientes_by_trade))
        except Exception as e:
            print(f"[get_records] Error en registro {record.get('id')}: {e}")
            continue

    result = {
        "records": formatted,
        "total_count": total_count,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, -(-total_count // page_size)),  # ceil division
        "promoters": catalogs["promotores"],
        "estados": catalogs["estados"],
        "zonas": catalogs["zonas"],
        "total_promoters_in_db": len(catalogs["promotores"]),
    }
    cache_set(cache_key, result)
    return jsonify(result)


# ─── API: Stats rápidos (KPIs del top del dashboard) ─────────────────────────
@app.route('/api/records/stats')
def get_records_stats():
    """
    Devuelve conteos agregados SIN traer todos los registros.
    Usado por los KPI cards y el realtime polling.
    """
    empresa_id = request.args.get('empresa_id')
    date_from  = request.args.get('date_from')
    date_to    = request.args.get('date_to')
    if not empresa_id:
        return jsonify({"error": "empresa_id requerido"}), 400

    cache_key = f"stats:{empresa_id}:{date_from}:{date_to}"
    cached = cache_get(cache_key)
    if cached:
        return jsonify({**cached, "from_cache": True})

    params = [
        ("select", "id,verified,promoter_id,created_at"),
        ("empresa_id", f"eq.{empresa_id}"),
    ]
    if date_from:
        params.append(("created_at", f"gte.{date_from}T00:00:00+00:00"))
    if date_to:
        params.append(("created_at", f"lte.{date_to}T23:59:59+00:00"))

    # Solo traemos los campos ligeros para contar
    records = fetch_table("web_precios", params=params)

    total = len(records)
    # Confirmados = distancia calculada en tiempo real pero para stats usamos proxy
    # (si el frontend ya tiene los records, que cuente él; este endpoint es para el header)
    result = {
        "total_visits": total,
        "last_updated": datetime.utcnow().isoformat(),
    }
    cache_set(cache_key, result)
    return jsonify(result)


# ─── API: Weeks with visits ───────────────────────────────────────────────────
@app.route('/api/weeks_with_visits', methods=['GET'])
def get_weeks_with_visits():
    empresa_id = request.args.get('empresa_id')
    if not empresa_id:
        return jsonify({"error": "empresa_id requerido"}), 400

    year = request.args.get('year', str(datetime.now().year))
    cache_key = f"weeks:{empresa_id}:{year}"
    cached = cache_get(cache_key)
    if cached:
        return jsonify(cached)

    params = [
        ("select", "created_at"),
        ("empresa_id", f"eq.{empresa_id}"),
        ("created_at", f"gte.{year}-01-01T00:00:00+00:00"),
    ]
    records = fetch_table("web_precios", params=params)
    weeks = set()
    for r in records:
        try:
            dt = datetime.fromisoformat((r.get('created_at') or '').replace('Z', '+00:00'))
            weeks.add(dt.isocalendar()[1])
        except Exception:
            continue

    result = {"weeks": sorted(list(weeks), reverse=True)}
    cache_set(cache_key, result)
    return jsonify(result)


# ─── API: Delete records (invalida caché automáticamente) ────────────────────
@app.route('/delete_records', methods=['POST'])
def delete_records():
    data = request.json or {}
    ids = data.get("ids", [])
    empresa_id = data.get("empresa_id")
    if not empresa_id or not ids:
        return jsonify({"success": False, "error": "Parámetros inválidos"}), 400

    id_list = ",".join(map(str, ids))
    url = f"{SUPABASE_URL}/rest/v1/web_precios?id=in.({id_list})&empresa_id=eq.{empresa_id}"
    res = requests.delete(url, headers=headers, timeout=10)

    if res.ok:
        # Invalida caché de esta empresa
        cache_invalidate_prefix(f"records:{empresa_id}")
        cache_invalidate_prefix(f"stats:{empresa_id}")
        cache_invalidate_prefix(f"weeks:{empresa_id}")

    return jsonify({"success": res.ok})


# ─── API: Competitor products ─────────────────────────────────────────────────
@app.route('/api/competitorproducts', methods=['GET', 'POST'])
def handle_competitor_products():
    if request.method == 'GET':
        empresa_id = request.args.get('empresa_id')
        products = fetch_table("web_competidor",
                               params=[("order", "presentation.asc")],
                               empresa_id=empresa_id)
        return jsonify({"products": products})

    if not request.is_json:
        return jsonify({"error": "Se esperaba JSON"}), 400
    data = request.json
    res = requests.post(
        f"{SUPABASE_URL}/rest/v1/web_competidor",
        headers=headers,
        json={"presentation": data.get("presentation"), "empresa_id": data.get("empresa_id")},
        timeout=10
    )
    return jsonify({"success": res.ok}), 201


@app.route('/api/competitorproducts/<int:product_id>', methods=['PATCH', 'DELETE'])
def update_delete_competitor(product_id):
    url = f"{SUPABASE_URL}/rest/v1/web_competidor?id=eq.{product_id}"
    if request.method == 'PATCH':
        res = requests.patch(url, headers=headers, json=request.json, timeout=10)
    else:
        res = requests.delete(url, headers=headers, timeout=10)
    return jsonify({"success": res.ok})


# ─── API: My products ────────────────────────────────────────────────────────
@app.route('/api/myproducts', methods=['GET', 'POST'])
def handle_my_products():
    if request.method == 'GET':
        empresa_id = request.args.get('empresa_id')
        if not empresa_id:
            return jsonify({"error": "empresa_id es requerido"}), 400
        products = fetch_table("web_myproductos",
                               params=[("order", "presentation.asc")],
                               empresa_id=empresa_id)
        return jsonify({"products": products})

    if not request.is_json:
        return jsonify({"error": "Se esperaba JSON"}), 400
    data = request.json
    presentation = (data.get("presentation") or "").strip()
    empresa_id = data.get("empresa_id")
    if not presentation or not empresa_id:
        return jsonify({"error": "presentation y empresa_id son requeridos"}), 400

    res = requests.post(
        f"{SUPABASE_URL}/rest/v1/web_myproductos",
        headers=headers,
        json={"presentation": presentation.upper(), "empresa_id": empresa_id},
        timeout=10
    )
    if res.status_code in (200, 201):
        return jsonify({"success": True}), 201
    return jsonify({"error": res.text}), res.status_code


@app.route('/api/myproducts/<int:product_id>', methods=['PATCH', 'DELETE'])
def update_delete_my_product(product_id):
    url = f"{SUPABASE_URL}/rest/v1/web_myproductos?id=eq.{product_id}"
    if request.method == 'PATCH':
        res = requests.patch(url, headers=headers, json=request.json, timeout=10)
    else:
        res = requests.delete(url, headers=headers, timeout=10)
    return jsonify({"success": res.ok})


# ─── API: Planograma upload ───────────────────────────────────────────────────
@app.route('/api/upload_planogram', methods=['POST'])
def upload_planogram():
    empresa_id = session.get('empresa_id')
    if not empresa_id:
        return jsonify({"success": False, "error": "Sin sesión"}), 401

    file = request.files.get('file')
    if not file:
        return jsonify({"success": False, "error": "No se recibió archivo"}), 400

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ('.jpg', '.jpeg', '.png'):
        return jsonify({"success": False, "error": "Usa JPG o PNG"}), 400

    try:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        file_name = f"planogramas/{empresa_id}/planograma_{timestamp}{ext}"
        storage_url = f"{SUPABASE_URL}/storage/v1/object/visits_photos/{file_name}"
        upload_resp = requests.put(
            storage_url,
            headers={"Authorization": f"Bearer {SUPABASE_KEY}",
                     "Content-Type": file.content_type or "image/jpeg"},
            data=file.read(),
            timeout=30
        )
        if upload_resp.status_code not in (200, 201):
            return jsonify({"success": False, "error": "Error al subir al storage"}), 500

        update_resp = requests.patch(
            f"{SUPABASE_URL}/rest/v1/empresas?id=eq.{empresa_id}",
            headers=headers,
            json={"planogram_image": file_name},
            timeout=10
        )
        if update_resp.status_code not in (200, 204):
            return jsonify({"success": False, "error": "Error al actualizar BD"}), 500

        public_url = f"{SUPABASE_URL}/storage/v1/object/public/visits_photos/{file_name}"
        return jsonify({"success": True, "url": public_url})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ─── Entrypoint ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port, debug=False)