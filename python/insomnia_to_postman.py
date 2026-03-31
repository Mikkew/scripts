import json
import sys
import os
import uuid
from datetime import datetime

class InsomniaToPostman:
    def __init__(self):
        self.postman_collection = {
            "info": {
                "_postman_id": str(uuid.uuid4()),
                "name": "Insomnia Export",
                "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
                "description": "Convertido desde Insomnia v4",
                "exported_at": datetime.now().isoformat()
            },
            "item": [],
            "variable": [],
            "auth": None
        }
        self.workspace_name = "Workspace"
        self.folders = {}
        
    def convertir(self, archivo_entrada, archivo_salida):
        """Convierte archivo de Insomnia v4 JSON a Postman Collection"""
        
        if not os.path.isfile(archivo_entrada):
            print(f"❌ Error: El archivo '{archivo_entrada}' no existe.")
            input("\nPresiona Enter para salir...")
            sys.exit(1)
            
        try:
            print(f"\n📂 Leyendo archivo: {archivo_entrada}...")
            
            with open(archivo_entrada, 'r', encoding='utf-8') as f:
                insomnia_data = json.load(f)
            
            if not isinstance(insomnia_data, list):
                insomnia_data = [insomnia_data]
            
            print(f"📊 Procesando {len(insomnia_data)} recursos...")
            
            for recurso in insomnia_data:
                tipo = recurso.get('_type', '')
                
                if tipo == 'workspace':
                    self.workspace_name = recurso.get('name', 'Workspace')
                    self.postman_collection['info']['name'] = self.workspace_name
                    
                elif tipo == 'request_group':
                    self.folders[recurso.get('_id')] = {
                        'name': recurso.get('name', 'Sin nombre'),
                        'parent': recurso.get('parentId'),
                        'items': []
                    }
                    
                elif tipo == 'request':
                    postman_request = self._convertir_request(recurso)
                    if postman_request:
                        parent_id = recurso.get('parentId')
                        if parent_id and parent_id in self.folders:
                            self.folders[parent_id]['items'].append(postman_request)
                        else:
                            self.postman_collection['item'].append(postman_request)
                            
                elif tipo == 'environment':
                    env_vars = self._convertir_environment(recurso)
                    if env_vars:
                        self.postman_collection['variable'].extend(env_vars)
            
            for folder_id, folder_data in self.folders.items():
                if folder_data['items']:
                    postman_folder = {
                        "name": folder_data['name'],
                        "item": folder_data['items'],
                        "request": [],
                        "event": []
                    }
                    self.postman_collection['item'].append(postman_folder)
            
            print(f"\n💾 Guardando archivo: {archivo_salida}...")
            
            with open(archivo_salida, 'w', encoding='utf-8') as f:
                json.dump(self.postman_collection, f, indent=2, ensure_ascii=False)
            
            print("\n" + "="*60)
            print("✅ ¡CONVERSIÓN COMPLETADA EXITOSAMENTE!")
            print("="*60)
            print(f"📁 Archivo de salida: {os.path.abspath(archivo_salida)}")
            print(f"📊 Requests convertidos: {self._contar_requests()}")
            print(f"📋 Variables de entorno: {len(self.postman_collection['variable'])}")
            print("="*60)
            
        except json.JSONDecodeError as e:
            print(f"\n❌ Error al parsear JSON: {e}")
            input("\nPresiona Enter para salir...")
            sys.exit(1)
        except Exception as e:
            print(f"\n❌ Error inesperado: {e}")
            input("\nPresiona Enter para salir...")
            sys.exit(1)
    
    def _convertir_request(self, request):
        """Convierte un request de Insomnia a formato Postman"""
        try:
            postman_request = {
                "name": request.get('name', 'Sin nombre'),
                "request": {
                    "method": request.get('method', 'GET').upper(),
                    "header": self._convertir_headers(request.get('headers', [])),
                    "body": self._convertir_body(request.get('body', {})),
                    "url": self._convertir_url(request.get('url', '')),
                    "auth": self._convertir_auth(request.get('authentication', {}))
                },
                "response": [],
                "event": []
            }
            
            if request.get('description'):
                postman_request['request']['description'] = request.get('description')
            
            return postman_request
            
        except Exception as e:
            print(f"⚠️  Error convirtiendo request '{request.get('name', 'Unknown')}': {e}")
            return None
    
    def _convertir_headers(self, headers):
        """Convierte headers de Insomnia a Postman"""
        postman_headers = []
        for header in headers:
            if header.get('disabled', False):
                continue
            postman_headers.append({
                "key": header.get('name', ''),
                "value": header.get('value', ''),
                "type": "text",
                "disabled": header.get('disabled', False)
            })
        return postman_headers
    
    def _convertir_body(self, body):
        """Convierte el body de Insomnia a Postman"""
        if not body:
            return None
        
        body_type = body.get('mimeType', '')
        postman_body = {}
        
        if body_type == 'application/json':
            postman_body['mode'] = 'raw'
            postman_body['raw'] = body.get('text', '')
            postman_body['options'] = {"raw": {"language": "json"}}
        elif body_type == 'application/x-www-form-urlencoded':
            postman_body['mode'] = 'urlencoded'
            postman_body['urlencoded'] = [
                {"key": p.get('name', ''), "value": p.get('value', ''), "type": "text"}
                for p in body.get('params', [])
            ]
        elif body_type == 'multipart/form-data':
            postman_body['mode'] = 'formdata'
            postman_body['formdata'] = [
                {
                    "key": p.get('name', ''),
                    "value": p.get('value', ''),
                    "type": "text" if not p.get('fileName') else "file",
                    "src": p.get('fileName') if p.get('fileName') else None
                }
                for p in body.get('params', [])
            ]
        elif body_type == 'application/xml' or 'xml' in body_type:
            postman_body['mode'] = 'raw'
            postman_body['raw'] = body.get('text', '')
            postman_body['options'] = {"raw": {"language": "xml"}}
        else:
            postman_body['mode'] = 'raw'
            postman_body['raw'] = body.get('text', '')
        
        return postman_body if postman_body else None
    
    def _convertir_url(self, url):
        """Convierte URL de Insomnia a formato Postman"""
        if not url:
            return {"raw": "", "protocol": "", "host": [], "path": []}
        
        return {"raw": url, "protocol": "", "host": [], "path": []}
    
    def _convertir_auth(self, auth):
        """Convierte autenticación de Insomnia a Postman"""
        if not auth or auth.get('disabled', False):
            return None
        
        auth_type = auth.get('type', '')
        postman_auth = {}
        
        if auth_type == 'basic':
            postman_auth = {
                "type": "basic",
                "basic": [
                    {"key": "username", "value": auth.get('username', ''), "type": "string"},
                    {"key": "password", "value": auth.get('password', ''), "type": "string"}
                ]
            }
        elif auth_type == 'bearer':
            postman_auth = {
                "type": "bearer",
                "bearer": [
                    {"key": "token", "value": auth.get('token', ''), "type": "string"}
                ]
            }
        elif auth_type == 'apikey':
            postman_auth = {
                "type": "apikey",
                "apikey": [
                    {"key": "key", "value": auth.get('key', ''), "type": "string"},
                    {"key": "value", "value": auth.get('value', ''), "type": "string"},
                    {"key": "in", "value": auth.get('in', 'header'), "type": "string"}
                ]
            }
        elif auth_type == 'oauth2':
            postman_auth = {
                "type": "oauth2",
                "oauth2": [
                    {"key": "accessTokenUrl", "value": auth.get('accessTokenUrl', ''), "type": "string"},
                    {"key": "authUrl", "value": auth.get('authorizationUrl', ''), "type": "string"},
                    {"key": "clientId", "value": auth.get('clientId', ''), "type": "string"},
                    {"key": "clientSecret", "value": auth.get('clientSecret', ''), "type": "string"},
                    {"key": "scope", "value": auth.get('scope', ''), "type": "string"},
                    {"key": "grant_type", "value": auth.get('grantType', 'authorization_code'), "type": "string"}
                ]
            }
        elif auth_type == 'digest':
            postman_auth = {
                "type": "digest",
                "digest": [
                    {"key": "username", "value": auth.get('username', ''), "type": "string"},
                    {"key": "password", "value": auth.get('password', ''), "type": "string"}
                ]
            }
        else:
            return None
        
        return postman_auth
    
    def _convertir_environment(self, environment):
        """Convierte variables de entorno de Insomnia a Postman"""
        variables = []
        data = environment.get('data', {})
        
        for key, value in data.items():
            variables.append({
                "key": key,
                "value": str(value),
                "type": "default",
                "enabled": True
            })
        
        return variables
    
    def _contar_requests(self):
        """Cuenta el número total de requests en la colección"""
        count = 0
        for item in self.postman_collection['item']:
            if 'item' in item:
                count += len(item['item'])
            else:
                count += 1
        return count


def obtener_ruta_archivo(mensaje, extension_defecto=".json"):
    """Solicita una ruta de archivo al usuario y la valida"""
    while True:
        ruta = input(mensaje).strip()
        
        if not ruta:
            print("⚠️  La ruta no puede estar vacía. Inténtalo de nuevo.")
            continue
        
        ruta = os.path.expanduser(ruta)
        
        if os.path.isfile(ruta):
            return ruta
        else:
            print(f"⚠️  El archivo '{ruta}' no existe. Inténtalo de nuevo.")


def obtener_ruta_salida(mensaje, valor_por_defecto):
    """Solicita una ruta de salida al usuario"""
    ruta = input(mensaje).strip()
    
    if not ruta:
        ruta = valor_por_defecto
    
    ruta = os.path.expanduser(ruta)
    
    directorio = os.path.dirname(ruta)
    if directorio and not os.path.exists(directorio):
        print(f"📁 Creando directorio: {directorio}")
        os.makedirs(directorio, exist_ok=True)
    
    return ruta


def main():
    print("="*60)
    print("🔄 CONVERTIDOR DE INSOMNIA V4 (JSON) A POSTMAN")
    print("="*60)
    print("\nInstrucciones:")
    print("1. Exporta tu workspace desde Insomnia como 'Insomnia v4 (JSON)'")
    print("2. Ingresa la ruta del archivo exportado")
    print("3. Ingresa la ruta donde quieres guardar el archivo de Postman")
    print("\nNota: Puedes usar rutas completas de Windows (ej: C:\\Users\\...)")
    print("      o rutas relativas (ej: .\\archivo.json)")
    print("="*60)
    
    archivo_entrada = obtener_ruta_archivo("\n📥 Ruta del archivo de Insomnia (JSON): ")
    
    nombre_por_defecto = os.path.join(
        os.path.dirname(archivo_entrada) or '.',
        "postman_collection.json"
    )
    
    print(f"\n💡 Valor por defecto: {nombre_por_defecto}")
    archivo_salida = obtener_ruta_salida("📤 Ruta del archivo de salida (Postman JSON): ", nombre_por_defecto)
    
    print("\n" + "="*60)
    print("🚗 Iniciando conversión...")
    print("="*60)
    
    converter = InsomniaToPostman()
    converter.convertir(archivo_entrada, archivo_salida)
    
    input("\n👉 Presiona Enter para salir...")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Proceso cancelado por el usuario.")
        input("Presiona Enter para salir...")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Error crítico: {e}")
        input("Presiona Enter para salir...")
        sys.exit(1)