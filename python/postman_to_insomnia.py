#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import sys
import os
import uuid
from datetime import datetime

class PostmanToInsomnia:
    def __init__(self):
        self.insomnia_data = []
        self.workspace_id = self._generate_id()
        self.folder_map = {}  # Para mapear carpetas de Postman a Insomnia
        
    def _generate_id(self):
        """Genera un ID único compatible con Insomnia"""
        return f"wrk_{uuid.uuid4().hex[:12]}"
    
    def _generate_request_id(self):
        return f"req_{uuid.uuid4().hex[:12]}"
    
    def _generate_folder_id(self):
        return f"fld_{uuid.uuid4().hex[:12]}"
    
    def _generate_env_id(self):
        return f"env_{uuid.uuid4().hex[:12]}"
    
    def convertir(self, archivo_entrada, archivo_salida):
        """Convierte archivo de Postman Collection a Insomnia v4 JSON"""
        
        if not os.path.isfile(archivo_entrada):
            print(f"❌ Error: El archivo '{archivo_entrada}' no existe.")
            input("\nPresiona Enter para salir...")
            sys.exit(1)
            
        try:
            print(f"\n📂 Leyendo archivo Postman: {archivo_entrada}...")
            
            with open(archivo_entrada, 'r', encoding='utf-8') as f:
                postman_data = json.load(f)
            
            # Validar que es una colección de Postman
            if not self._validar_postman_collection(postman_data):
                print("❌ Error: El archivo no parece ser una colección válida de Postman.")
                input("\nPresiona Enter para salir...")
                sys.exit(1)
            
            print(f"📊 Procesando colección: {postman_data['info'].get('name', 'Sin nombre')}...")
            
            # 1. Crear Workspace
            workspace = self._crear_workspace(postman_data)
            self.insomnia_data.append(workspace)
            
            # 2. Crear Environment (si existen variables)
            if postman_data.get('variable'):
                environment = self._crear_environment(postman_data)
                self.insomnia_data.append(environment)
            
            # 3. Procesar items (requests y carpetas)
            if postman_data.get('item'):
                self._procesar_items(postman_data['item'], self.workspace_id)
            
            # Guardar archivo Insomnia
            print(f"\n💾 Guardando archivo Insomnia: {archivo_salida}...")
            
            with open(archivo_salida, 'w', encoding='utf-8') as f:
                json.dump(self.insomnia_data, f, indent=2, ensure_ascii=False)
            
            print("\n" + "="*60)
            print("✅ ¡CONVERSIÓN COMPLETADA EXITOSAMENTE!")
            print("="*60)
            print(f"📁 Archivo de salida: {os.path.abspath(archivo_salida)}")
            print(f"📊 Requests convertidos: {self._contar_requests()}")
            print(f"📋 Carpetas convertidas: {len(self.folder_map)}")
            print(f"📋 Variables de entorno: {len(postman_data.get('variable', []))}")
            print("="*60)
            
        except json.JSONDecodeError as e:
            print(f"\n❌ Error al parsear JSON: {e}")
            input("\nPresiona Enter para salir...")
            sys.exit(1)
        except Exception as e:
            print(f"\n❌ Error inesperado: {e}")
            import traceback
            traceback.print_exc()
            input("\nPresiona Enter para salir...")
            sys.exit(1)
    
    def _validar_postman_collection(self, data):
        """Valida que el archivo sea una colección de Postman válida"""
        if not isinstance(data, dict):
            return False
        if 'info' not in data:
            return False
        if 'schema' not in data['info']:
            return False
        if 'postman' not in data['info'].get('schema', '').lower():
            return False
        return True
    
    def _crear_workspace(self, postman_data):
        """Crea el workspace de Insomnia"""
        return {
            "_id": self.workspace_id,
            "_type": "workspace",
            "name": postman_data['info'].get('name', 'Postman Import'),
            "description": postman_data['info'].get('description', 'Importado desde Postman'),
            "scope": "collection",
            "created": datetime.now().isoformat(),
            "modified": datetime.now().isoformat(),
            "parentId": None
        }
    
    def _crear_environment(self, postman_data):
        """Crea el environment de Insomnia desde variables de Postman"""
        env_data = {}
        for var in postman_data.get('variable', []):
            if var.get('enabled', True):
                env_data[var.get('key', '')] = var.get('value', '')
        
        return {
            "_id": self._generate_env_id(),
            "_type": "environment",
            "name": f"{postman_data['info'].get('name', 'Workspace')} Environment",
            "data": env_data,
            "color": "#4d90fe",
            "isPrivate": False,
            "metaSortKey": -1,
            "created": datetime.now().isoformat(),
            "modified": datetime.now().isoformat(),
            "parentId": self.workspace_id
        }
    
    def _procesar_items(self, items, parent_id, depth=0):
        """Procesa recursivamente los items de Postman (requests y carpetas)"""
        for item in items:
            if 'item' in item:
                # Es una carpeta/folder
                folder_id = self._generate_folder_id()
                folder = {
                    "_id": folder_id,
                    "_type": "request_group",
                    "name": item.get('name', 'Sin nombre'),
                    "description": item.get('description', ''),
                    "environment": {},
                    "environmentPropertyOrder": None,
                    "metaSortKey": -1,
                    "created": datetime.now().isoformat(),
                    "modified": datetime.now().isoformat(),
                    "parentId": parent_id
                }
                self.insomnia_data.append(folder)
                self.folder_map[item.get('name', '')] = folder_id
                
                # Procesar items dentro de la carpeta
                if item.get('item'):
                    self._procesar_items(item['item'], folder_id, depth + 1)
            else:
                # Es un request
                request = self._convertir_request(item, parent_id)
                if request:
                    self.insomnia_data.append(request)
    
    def _convertir_request(self, postman_request, parent_id):
        """Convierte un request de Postman a formato Insomnia"""
        try:
            req_data = postman_request.get('request', {})
            
            insomnia_request = {
                "_id": self._generate_request_id(),
                "_type": "request",
                "name": postman_request.get('name', 'Sin nombre'),
                "method": req_data.get('method', 'GET').upper(),
                "url": self._extraer_url(req_data.get('url', {})),
                "headers": self._convertir_headers(req_data.get('header', [])),
                "body": self._convertir_body(req_data.get('body', {})),
                "authentication": self._convertir_auth(req_data.get('auth', {})),
                "description": req_data.get('description', ''),
                "parameters": [],
                "settingFollowRedirects": "global",
                "settingRebuildPath": True,
                "settingEncodeUrl": True,
                "settingDisableRenderRequestBody": False,
                "settingSendCookies": True,
                "settingStoreCookies": True,
                "created": datetime.now().isoformat(),
                "modified": datetime.now().isoformat(),
                "parentId": parent_id
            }
            
            return insomnia_request
            
        except Exception as e:
            print(f"⚠️  Error convirtiendo request '{postman_request.get('name', 'Unknown')}': {e}")
            return None
    
    def _extraer_url(self, url_data):
        """Extrae la URL de formato Postman a string simple"""
        if isinstance(url_data, str):
            return url_data
        
        if isinstance(url_data, dict):
            raw = url_data.get('raw', '')
            if raw:
                return raw
            
            # Construir URL desde componentes
            protocol = url_data.get('protocol', 'https')
            host = '.'.join(url_data.get('host', []))
            path = '/'.join(url_data.get('path', []))
            query = url_data.get('query', [])
            
            url = f"{protocol}://{host}"
            if path:
                url += f"/{path}"
            
            if query:
                query_string = '&'.join([f"{q.get('key', '')}={q.get('value', '')}" for q in query])
                if query_string:
                    url += f"?{query_string}"
            
            return url
        
        return ""
    
    def _convertir_headers(self, headers):
        """Convierte headers de Postman a formato Insomnia"""
        insomnia_headers = []
        for header in headers:
            if header.get('disabled', False):
                continue
            insomnia_headers.append({
                "name": header.get('key', ''),
                "value": header.get('value', ''),
                "description": header.get('description', ''),
                "disabled": header.get('disabled', False)
            })
        return insomnia_headers
    
    def _convertir_body(self, body):
        """Convierte el body de Postman a formato Insomnia"""
        if not body:
            return {}
        
        mode = body.get('mode', '')
        insomnia_body = {}
        
        if mode == 'raw':
            insomnia_body['mimeType'] = 'application/json'
            insomnia_body['text'] = body.get('raw', '')
            
            # Detectar el tipo de contenido desde options
            options = body.get('options', {})
            raw_options = options.get('raw', {})
            language = raw_options.get('language', 'json')
            
            if language == 'json':
                insomnia_body['mimeType'] = 'application/json'
            elif language == 'xml':
                insomnia_body['mimeType'] = 'application/xml'
            elif language == 'text':
                insomnia_body['mimeType'] = 'text/plain'
            elif language == 'html':
                insomnia_body['mimeType'] = 'text/html'
                
        elif mode == 'urlencoded':
            insomnia_body['mimeType'] = 'application/x-www-form-urlencoded'
            insomnia_body['params'] = [
                {
                    "name": p.get('key', ''),
                    "value": p.get('value', ''),
                    "description": p.get('description', ''),
                    "disabled": p.get('disabled', False)
                }
                for p in body.get('urlencoded', [])
            ]
            
        elif mode == 'formdata':
            insomnia_body['mimeType'] = 'multipart/form-data'
            insomnia_body['params'] = [
                {
                    "name": p.get('key', ''),
                    "value": p.get('value', ''),
                    "description": p.get('description', ''),
                    "disabled": p.get('disabled', False),
                    "fileName": p.get('src', '') if p.get('type') == 'file' else None
                }
                for p in body.get('formdata', [])
            ]
        
        return insomnia_body
    
    def _convertir_auth(self, auth):
        """Convierte autenticación de Postman a formato Insomnia"""
        if not auth:
            return {}
        
        auth_type = auth.get('type', '')
        insomnia_auth = {"type": auth_type}
        
        if auth_type == 'basic':
            basic_data = self._buscar_auth_key(auth.get('basic', []))
            insomnia_auth['username'] = basic_data.get('username', '')
            insomnia_auth['password'] = basic_data.get('password', '')
            
        elif auth_type == 'bearer':
            bearer_data = self._buscar_auth_key(auth.get('bearer', []))
            insomnia_auth['token'] = bearer_data.get('token', '')
            
        elif auth_type == 'apikey':
            apikey_data = self._buscar_auth_key(auth.get('apikey', []))
            insomnia_auth['key'] = apikey_data.get('key', '')
            insomnia_auth['value'] = apikey_data.get('value', '')
            insomnia_auth['in'] = apikey_data.get('in', 'header')
            
        elif auth_type == 'oauth2':
            oauth_data = self._buscar_auth_key(auth.get('oauth2', []))
            insomnia_auth['accessTokenUrl'] = oauth_data.get('accessTokenUrl', '')
            insomnia_auth['authorizationUrl'] = oauth_data.get('authUrl', '')
            insomnia_auth['clientId'] = oauth_data.get('clientId', '')
            insomnia_auth['clientSecret'] = oauth_data.get('clientSecret', '')
            insomnia_auth['scope'] = oauth_data.get('scope', '')
            insomnia_auth['grantType'] = oauth_data.get('grant_type', 'authorization_code')
            
        elif auth_type == 'digest':
            digest_data = self._buscar_auth_key(auth.get('digest', []))
            insomnia_auth['username'] = digest_data.get('username', '')
            insomnia_auth['password'] = digest_data.get('password', '')
        
        return insomnia_auth
    
    def _buscar_auth_key(self, auth_list):
        """Busca valores en la lista de autenticación de Postman"""
        result = {}
        for item in auth_list:
            key = item.get('key', '')
            value = item.get('value', '')
            result[key] = value
        return result
    
    def _contar_requests(self):
        """Cuenta el número total de requests en la colección"""
        count = 0
        for item in self.insomnia_data:
            if item.get('_type') == 'request':
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
    print("🔄 CONVERTIDOR DE POSTMAN A INSOMNIA V4 (JSON)")
    print("="*60)
    print("\nInstrucciones:")
    print("1. Exporta tu colección desde Postman como 'Collection JSON v2.1'")
    print("2. Ingresa la ruta del archivo exportado")
    print("3. Ingresa la ruta donde quieres guardar el archivo de Insomnia")
    print("\nNota: Puedes usar rutas completas de Windows (ej: C:\\Users\\...)")
    print("      o rutas relativas (ej: .\\archivo.json)")
    print("="*60)
    
    archivo_entrada = obtener_ruta_archivo("\n📥 Ruta del archivo de Postman (JSON): ")
    
    nombre_por_defecto = os.path.join(
        os.path.dirname(archivo_entrada) or '.',
        "insomnia_export.json"
    )
    
    print(f"\n💡 Valor por defecto: {nombre_por_defecto}")
    archivo_salida = obtener_ruta_salida("📤 Ruta del archivo de salida (Insomnia JSON): ", nombre_por_defecto)
    
    print("\n" + "="*60)
    print("🚗 Iniciando conversión...")
    print("="*60)
    
    converter = PostmanToInsomnia()
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