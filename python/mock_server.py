from fastapi import FastAPI, Request, Query
from fastapi.responses import Response
import asyncio, json, xmltodict, uvicorn
from typing import Dict, Any

app = FastAPI(title="Mock Server (JSON/XML - Path-Centric)", version="3.0")
MOCKS: Dict[str, Dict[str, Any]] = {}

def cargar_mocks(archivo: str = "mocks.json"):
    global MOCKS
    try:
        with open(archivo, "r", encoding="utf-8") as f:
            MOCKS = json.load(f)
        print(f"✅ {len(MOCKS)} rutas cargadas desde {archivo}")
    except FileNotFoundError:
        print("⚠️ mocks.json no encontrado. Define tus rutas y métodos.")
        MOCKS = {}

@app.api_route("/mock/{ruta:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def mock_endpoint(ruta: str, request: Request, format: str = Query(None)):
    metodo = request.method.upper()
    path = f"/{ruta}"

    # 1️⃣ Validar existencia de ruta y método
    if path not in MOCKS or metodo not in MOCKS[path]:
        return Response(
            content=json.dumps({"error": f"Mock no configurado para {metodo} {path}"}),
            media_type="application/json", status_code=404
        )

    mock = MOCKS[path][metodo]
    delay = mock.get("delay", 0)
    if delay > 0:
        await asyncio.sleep(delay)

    body = mock.get("body", {})
    status = mock.get("status", 200)
    headers = mock.get("headers", {})
    tipo_configurado = mock.get("type", "json").lower()

    # 2️⃣ Resolver formato de respuesta
    accept = request.headers.get("accept", "").lower()
    usar_xml = (format == "xml") or ("application/xml" in accept or "text/xml" in accept)
    usar_json = (format == "json") or ("application/json" in accept)

    # Si no hay override, respetar el tipo declarado en el mock
    if not usar_xml and not usar_json:
        usar_xml = (tipo_configurado == "xml")

    # 3️⃣ Generar payload
    if usar_xml:
        media_type = "application/xml; charset=utf-8"
        if isinstance(body, str):
            content = body
        else:
            # xmltodict requiere dict raíz. Si es lista, se envuelve automáticamente
            root = "response" if isinstance(body, dict) else "items"
            content = xmltodict.unparse({root: body}, pretty=True, full_document=False)
    else:
        media_type = "application/json; charset=utf-8"
        content = json.dumps(body, ensure_ascii=False, indent=2) if isinstance(body, (dict, list)) else body

    return Response(content=content, media_type=media_type, status_code=status, headers=headers)

if __name__ == "__main__":
    cargar_mocks()
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)