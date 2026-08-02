#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Descarga la carpeta de Dropbox, extrae el ULTIMO precio de compra de cada
# producto y escribe docs/catalogo.json (solo producto + precio + fecha).
# La URL de Dropbox se lee de la variable de entorno DROPBOX_URL (secreto de GitHub).

import os, sys, re, json, glob, zipfile, urllib.request, datetime, tempfile, shutil

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "docs", "catalogo.json")
DROPBOX_URL = os.environ.get("DROPBOX_URL", "").strip()

if not DROPBOX_URL:
    sys.exit("ERROR: falta la variable DROPBOX_URL (secreto de GitHub).")

DATE_RE = re.compile(r"^(\d{2})/(\d{2})/(\d{4})$")
# proveedores internos (traspasos/apuntes entre tiendas): "TIENDA 12", "TIENDA 2"…
# solo contienen etiquetas (APUNTAR, DESCONTAR, PAPEL, BANDEJAS), nunca pescado real.
INTERNO_RE = re.compile(r"^TIENDA\s*\d+$", re.IGNORECASE)

# --- reclasificacion de productos ambiguos -----------------------------------
# El proveedor usa el MISMO nombre para productos distintos; los separamos por
# precio (unica senal disponible). Editar los umbrales aqui si cambian los niveles.
def reclasificar(prod, precio):
    if prod == "CONGRIO":
        return None if precio >= 15 else "CONGRIO"          # descartar el atipico (~21)
    if prod == "MEJILLON":
        if precio <= 0: return None                          # apunte de 0
        return "MEJILLÓN GRANEL" if precio < 5.0 else "MEJILLÓN MEDIA CONCHA"
    if prod == "MERLUZA":
        return "PESCADILLA" if precio < 9.6 else "MERLUZA GORDA"
    if prod == "ALISTADO":
        return "ALISTADO PEQUEÑO" if precio < 38 else "ALISTADO GORDO"
    return prod
def num(s): return float(s.strip().replace(".", "").replace(",", "."))
def is_num(s):
    try: num(s); return True
    except ValueError: return False

# --- descargar y extraer PDFs a carpeta temporal -----------------------------
tmp = tempfile.mkdtemp(prefix="pesca_")
zip_path = os.path.join(tmp, "dropbox.zip")
print("Descargando carpeta de Dropbox…")
req = urllib.request.Request(DROPBOX_URL, headers={"User-Agent": "Mozilla/5.0"})
with urllib.request.urlopen(req, timeout=120) as r, open(zip_path, "wb") as f:
    shutil.copyfileobj(r, f)
pdf_dir = os.path.join(tmp, "pdfs")
os.makedirs(pdf_dir, exist_ok=True)
with zipfile.ZipFile(zip_path) as z:
    for m in z.namelist():
        if m.lower().endswith(".pdf"):
            with open(os.path.join(pdf_dir, os.path.basename(m)), "wb") as f:
                f.write(z.read(m))

import fitz  # pymupdf (instalado por requirements)
files = sorted(glob.glob(os.path.join(pdf_dir, "*.pdf")))  # orden determinista
print(f"{len(files)} PDFs. Extrayendo…")

records = []
for path in files:
    doc = fitz.open(path)
    lines = [ln.strip() for page in doc for ln in page.get_text().split("\n") if ln.strip()]
    doc.close()
    for i, ln in enumerate(lines):
        m = DATE_RE.match(ln)
        if not m or i-4 < 0 or i+3 >= len(lines): continue
        cant, precio, importe, total = lines[i-4], lines[i-3], lines[i-2], lines[i-1]
        iva, prov, producto = lines[i+1], lines[i+2], lines[i+3]
        if not all(is_num(x) for x in (cant, precio, importe, total, iva)): continue
        # excluir apuntes internos por PROVEEDOR (robusto ante nuevos nombres)
        if INTERNO_RE.match(prov.strip()): continue
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try: fecha = datetime.date(y, mo, d).isoformat()
        except ValueError: continue
        prod = reclasificar(producto.upper().strip(), num(precio))
        if prod is None: continue                            # fila descartada
        records.append({"prod": prod, "precio": num(precio), "fecha": fecha})

# ultimo precio por producto (fecha mas reciente; empate -> ultimo leido, orden determinista)
cat = {}
for r in records:
    c = cat.get(r["prod"])
    if c is None or r["fecha"] >= c["fecha"]:
        cat[r["prod"]] = r
items = sorted(cat.values(), key=lambda r: r["prod"])
fecha_max = max((r["fecha"] for r in items), default=None)

# marcar productos NUEVOS = los que NO estaban en el catalogo anterior.
# Se compara con docs/catalogo.json de la corrida previa (persistente en el repo).
# Cada producto guarda "alta" = fecha en que aparecio por primera vez en el catalogo
# (no cambia una vez asignada). Lleva la etiqueta NUEVO mientras esa alta sea de hace
# <= DIAS_NUEVO dias, para que el aviso dure hasta el cierre de inventario del mes.
DIAS_NUEVO = 60
prev = {}
if os.path.exists(OUT):
    try:
        with open(OUT, encoding="utf-8") as f:
            for p in json.load(f).get("productos", []):
                prev[p["n"]] = p
    except Exception:
        prev = {}
hoy = datetime.date.today()
hoy_iso = hoy.isoformat()
def alta_de(nombre):
    p = prev.get(nombre)
    if p is None:
        return hoy_iso            # nunca visto antes -> alta = hoy (es NUEVO)
    return p.get("alta")          # ya existia: conservar su alta (None si es pre-sistema)
def es_nuevo(alta):
    return alta is not None and (hoy - datetime.date.fromisoformat(alta)).days <= DIAS_NUEVO

# salvaguarda ANTES de escribir: no sobrescribir con un catalogo vacio/roto
# (p.ej. si Dropbox falla o cambia el formato del PDF)
if len(items) < 50:
    shutil.rmtree(tmp, ignore_errors=True)
    sys.exit(f"ERROR: solo {len(items)} productos, algo va mal. No se sobrescribe el catalogo.")

productos = []
for r in items:
    alta = alta_de(r["prod"])
    it = {"n": r["prod"], "p": round(r["precio"], 2), "f": r["fecha"]}
    if alta: it["alta"] = alta                 # persistir el alta para futuras corridas
    if es_nuevo(alta): it["nuevo"] = True
    productos.append(it)
n_nuevos = sum(1 for it in productos if it.get("nuevo"))

payload = {
    "actualizado": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
    "fecha_dato": fecha_max,
    "productos": productos,
}
os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, "w", encoding="utf-8") as f:
    json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
shutil.rmtree(tmp, ignore_errors=True)
print(f"OK · {len(records)} registros · {len(items)} productos · {n_nuevos} nuevos · dato mas reciente {fecha_max}")
print("Escrito:", OUT)
