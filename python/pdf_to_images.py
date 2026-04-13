#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import fitz  # PyMuPDF
import sys
import os
from datetime import datetime

def convertir_pdf_a_imagenes(archivo_pdf, carpeta_salida, formato='jpg', dpi=200):
    """
    Convierte un PDF a imágenes (JPG o PNG)
    
    Args:
        archivo_pdf: Ruta al archivo PDF
        carpeta_salida: Carpeta donde se guardarán las imágenes
        formato: 'jpg' o 'png' (default: 'jpg')
        dpi: Resolución de las imágenes (default: 200)
    """
    
    # Validar que el PDF existe
    if not os.path.isfile(archivo_pdf):
        print(f"❌ Error: El archivo '{archivo_pdf}' no existe.")
        input("\nPresiona Enter para salir...")
        sys.exit(1)
    
    # Validar formato
    formato = formato.lower()
    if formato not in ['jpg', 'jpeg', 'png']:
        print(f"❌ Error: Formato '{formato}' no soportado. Usa 'jpg' o 'png'.")
        input("\nPresiona Enter para salir...")
        sys.exit(1)
    
    # Normalizar formato
    if formato == 'jpeg':
        formato = 'jpg'
    
    # Crear carpeta de salida si no existe
    if not os.path.exists(carpeta_salida):
        os.makedirs(carpeta_salida)
        print(f"📁 Carpeta creada: {carpeta_salida}")
    
    try:
        print(f"\n📂 Abriendo PDF: {archivo_pdf}...")
        doc = fitz.open(archivo_pdf)
        total_paginas = len(doc)
        
        print(f"📊 Total de páginas: {total_paginas}")
        print(f"🖼️  Formato de salida: {formato.upper()}")
        print(f"📐 Resolución: {dpi} DPI")
        print(f"\n🚗 Iniciando conversión...\n")
        
        imagenes_generadas = 0
        
        for num_pagina in range(total_paginas):
            pagina = doc.load_page(num_pagina)
            
            # Configurar matriz de zoom para la resolución
            zoom = dpi / 72  # 72 DPI es el estándar de PDF
            mat = fitz.Matrix(zoom, zoom)
            
            # Renderizar página a imagen
            pix = pagina.get_pixmap(matrix=mat)
            
            # Generar nombre de archivo
            nombre_archivo = f"pagina_{num_pagina + 1:03d}.{formato}"
            ruta_salida = os.path.join(carpeta_salida, nombre_archivo)
            
            # Guardar imagen
            if formato == 'jpg':
                pix.save(ruta_salida, output='jpeg', jpg_quality=95)
            else:
                pix.save(ruta_salida, output='png')
            
            imagenes_generadas += 1
            print(f"  ✅ Página {num_pagina + 1}/{total_paginas} → {nombre_archivo}")
        
        doc.close()
        
        print("\n" + "="*60)
        print("✅ ¡CONVERSIÓN COMPLETADA EXITOSAMENTE!")
        print("="*60)
        print(f"📁 Carpeta de salida: {os.path.abspath(carpeta_salida)}")
        print(f"📊 Imágenes generadas: {imagenes_generadas}")
        print(f"🖼️  Formato: {formato.upper()}")
        print(f"📐 Resolución: {dpi} DPI")
        print("="*60)
        
    except Exception as e:
        print(f"\n❌ Error inesperado: {e}")
        import traceback
        traceback.print_exc()
        input("\nPresiona Enter para salir...")
        sys.exit(1)


def obtener_ruta_archivo(mensaje, extension='.pdf'):
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


def obtener_ruta_carpeta(mensaje, valor_por_defecto):
    """Solicita una ruta de carpeta al usuario"""
    ruta = input(mensaje).strip()
    
    if not ruta:
        ruta = valor_por_defecto
    
    ruta = os.path.expanduser(ruta)
    
    return ruta


def main():
    print("="*60)
    print("🖼️  CONVERTIDOR DE PDF A IMÁGENES (JPG/PNG)")
    print("="*60)
    print("\nInstrucciones:")
    print("1. Ingresa la ruta del archivo PDF")
    print("2. Ingresa la carpeta de salida para las imágenes")
    print("3. Elige el formato (JPG por defecto o PNG)")
    print("4. Elige la resolución (200 DPI por defecto)")
    print("\nNota: Puedes usar rutas completas de Windows")
    print("      o rutas relativas (ej: .\\archivo.pdf)")
    print("="*60)
    
    # Solicitar ruta del PDF
    archivo_pdf = obtener_ruta_archivo("\n📥 Ruta del archivo PDF: ", '.pdf')
    
    # Solicitar carpeta de salida
    nombre_por_defecto = os.path.join(
        os.path.dirname(archivo_pdf) or '.',
        'imagenes_pdf'
    )
    
    print(f"\n💡 Carpeta por defecto: {nombre_por_defecto}")
    carpeta_salida = obtener_ruta_carpeta("📤 Carpeta de salida: ", nombre_por_defecto)
    
    # Solicitar formato
    print("\n🖼️  Formatos disponibles: JPG, PNG")
    formato = input("📋 Formato de salida (presiona Enter para JPG): ").strip().lower()
    
    if not formato:
        formato = 'jpg'
        print("   → Usando formato por defecto: JPG")
    elif formato not in ['jpg', 'jpeg', 'png']:
        print(f"   ⚠️  Formato '{formato}' no reconocido. Usando JPG por defecto.")
        formato = 'jpg'
    else:
        print(f"   → Usando formato: {formato.upper()}")
    
    # Solicitar resolución
    print("\n📐 Resolución recomendada: 150-300 DPI")
    dpi_input = input("📋 Resolución en DPI (presiona Enter para 200): ").strip()
    
    if not dpi_input:
        dpi = 200
        print("   → Usando resolución por defecto: 200 DPI")
    else:
        try:
            dpi = int(dpi_input)
            if dpi < 72:
                print("   ⚠️  DPI muy bajo. Usando 200 DPI por defecto.")
                dpi = 200
            elif dpi > 600:
                print("   ⚠️  DPI muy alto. Usando 300 DPI como máximo recomendado.")
                dpi = 300
            else:
                print(f"   → Usando resolución: {dpi} DPI")
        except ValueError:
            print("   ⚠️  Valor inválido. Usando 200 DPI por defecto.")
            dpi = 200
    
    print("\n" + "="*60)
    print("🚗 Iniciando conversión...")
    print("="*60)
    
    convertir_pdf_a_imagenes(archivo_pdf, carpeta_salida, formato, dpi)
    
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