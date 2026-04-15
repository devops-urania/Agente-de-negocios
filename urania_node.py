import time
import json
import os
import pandas as pd
from datetime import datetime, timezone, timedelta
from supabase import create_client, Client

# --- CONFIGURACIÓN (Pega tus datos de Supabase) ---
URL: str = "https://bbtospzgbfjketasvxem.supabase.co"
KEY: str = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImJidG9zcHpnYmZqa2V0YXN2eGVtIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzA3MzM4NjgsImV4cCI6MjA4NjMwOTg2OH0.Ka-9osphHovtN8yb68_TpNKbmRxhVAwijM6NhN8pNsk"

STORE_ID = "farmacia_demo"
EXCEL_FILE = r"C:\Users\franc\OneDrive\Escritorio\Urania\stock_local.xlsx"
STATE_FILE = "urania_state.json" # Aquí guardamos la memoria

supabase: Client = create_client(URL, KEY)

def cargar_ultima_sincronizacion():
    """Recupera la fecha del último trabajo exitoso."""
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            data = json.load(f)
            fecha = data.get("last_sync")
            print(f"🧠 Memoria recuperada: Última sincro fue {fecha}")
            return fecha
    else:
        # Si es la primera vez que corre, empezamos desde "ayer" para asegurar
        print("👶 Primer inicio: Creando memoria nueva...")
        return (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()

def guardar_estado():
    """Guarda la fecha actual en el disco."""
    with open(STATE_FILE, "w") as f:
        now = datetime.now(timezone.utc).isoformat()
        json.dump({"last_sync": now}, f)
        return now

def enviar_heartbeat():
    try:
        data = {
            "store_id": STORE_ID,
            "last_heartbeat": datetime.now(timezone.utc).isoformat(),
            "status": "online"
        }
        supabase.table("store_health").upsert(data).execute()
        #print("💓 Latido enviado...")
    except Exception as e:
        print(f"❌ Error Heartbeat: {e}")

def registrar_demanda_insatisfecha(termino_buscado):
    """Guarda en Supabase lo que la gente busca y no tenemos."""
    try:
        supabase.table("lost_sales_analytics").insert({
            "search_term": termino_buscado,
            "store_id": "farmacia_demo",
            "created_at": datetime.now(timezone.utc).isoformat()
        }).execute()
    except:
        pass # Que no trabe el flujo si falla

def sincronizar_stock_local_a_nube():
    """
    NUEVO: Lee el stock físico del Excel y lo sube a Supabase.
    Mantiene a la IA informada de las ventas hechas en el mostrador.
    """
    try:
        # 1. Leemos la pestaña de Stock del Excel local
        df_stock = pd.read_excel(EXCEL_FILE, sheet_name='Stock')
        
        registros_actualizados = []
        
        # 2. Preparamos el paquete de datos
        for index, row in df_stock.iterrows():
            registros_actualizados.append({
                "sku": str(row['sku']).strip().upper(),
                "stock": int(row['stock']),
                "store_id": STORE_ID # Asegura que es el stock de tu sucursal
            })
            
        # 3. Subimos masivamente a Supabase (Upsert actualiza si existe, inserta si no)
        if registros_actualizados:
            supabase.table("inventory").upsert(registros_actualizados).execute()
            # print("☁️ [SINCRO] Stock físico replicado en la Nube.") # Opcional: comentar para no saturar la consola
            
    except PermissionError:
        print("🚫 SINCRO STOCK FALLIDA: El Excel está abierto por un usuario. Se reintentará en el próximo ciclo.")
    except Exception as e:
        print(f"❌ Error sincronizando stock a la nube: {e}")

def procesar_ventas_pendientes(ultima_sincro):
    """
    Descarga ventas y actualiza el Excel local (Stock y Estado de Reservas).
    """
    response = supabase.table("sales_log")\
        .select("*, inventory(sku)")\
        .gt("sold_at", ultima_sincro)\
        .order("sold_at")\
        .execute()
    
    ventas = response.data
    
    if not ventas:
        return False 
    
    print(f"⚡ ¡ATENCIÓN! Encontré {len(ventas)} reservas pendientes.")

    # ---------------------------------------------------------
    # 2. PANDAS AVANZADO: Leemos el Excel con sus 2 hojas
    # ---------------------------------------------------------
    try:
        # Cargamos la hoja de inventario
        df_stock = pd.read_excel(EXCEL_FILE, sheet_name='Stock')
        df_stock['sku'] = df_stock['sku'].astype(str).str.strip().str.upper()
        # Cargamos la hoja de historial (o la creamos en memoria si está vacía)
        try:
            df_reservas = pd.read_excel(EXCEL_FILE, sheet_name='Reservas')
        except ValueError:
            df_reservas = pd.DataFrame(columns=['Fecha', 'SKU', 'Cantidad', 'Código', 'Estado'])
            
    except Exception as e:
        print(f"⚠️ ERROR CRÍTICO LEYENDO EXCEL: {e}")
        return False

    # 3. Procesamos la matemática y creamos el Log
    cambios_aplicados = False
    nuevas_reservas = [] # Lista para guardar las filas nuevas

    for venta in ventas:
        sku = venta['inventory']['sku']
        qty = venta['quantity']
        hora = venta['sold_at']
        codigo = venta.get('reservation_code', 'N/A')
        mask = df_stock['sku'] == sku
        if mask.any():
            # A. Restar stock del Inventario
            stock_antes = df_stock.loc[mask, 'stock'].values[0]
            df_stock.loc[mask, 'stock'] = stock_antes - qty
            
            # B. Crear el registro para la pestaña de Reservas con el STATUS
            nueva_reserva = {
                'Fecha': hora,
                'SKU': sku,
                'Cantidad': qty,
                "Código": codigo,
                'Estado': 'Pendiente en Caja' # <--- AQUÍ ESTÁ LA COLUMNA STATUS
            }
            nuevas_reservas.append(nueva_reserva)
            
            print(f"   ✅ Procesando: {sku} (-{qty}) | Estado: Pendiente en Caja")
            cambios_aplicados = True

        # --- NUEVO: ALERTA POR CONSOLA/SISTEMA ---
        print("\n" + "!"*40)
        print(f"🔔 ¡NUEVA RESERVA WEB! Código: {venta.get('reservation_code')}")
        print(f"📦 Producto: {sku} | Cantidad: {qty}")
        print("!"*40 + "\n")
        cambios_aplicados = True
    # ---------------------------------------------------------
    # 4. GUARDADO MULTI-HOJA
    # ---------------------------------------------------------
    if cambios_aplicados:
        try:
            # Agregamos las nuevas filas al DataFrame de reservas
            if nuevas_reservas:
                df_reservas = pd.concat([df_reservas, pd.DataFrame(nuevas_reservas)], ignore_index=True)
            
            # Usamos ExcelWriter para guardar ambas hojas sin borrar la otra
            with pd.ExcelWriter(EXCEL_FILE, engine='openpyxl') as writer:
                df_stock.to_excel(writer, sheet_name='Stock', index=False)
                df_reservas.to_excel(writer, sheet_name='Reservas', index=False)
                
            print("💾 Excel actualizado: Stock restado y Reserva anotada con Status.")
            return True 
        except PermissionError:
            print("🚫 EXCEL BLOQUEADO: Ciérralo para guardar.")
            return False
    
    return False

# --- BUCLE PRINCIPAL ---
print(f"🟢 Urania Node v2.0 Iniciado ({STORE_ID})")

# 1. Recuperar memoria (¿Cuándo fue la última vez que trabajé?)
ultima_sincro = cargar_ultima_sincronizacion()

while True:
    enviar_heartbeat()
    
    # 2. NUEVO: Subimos la realidad del mostrador a la nube
    sincronizar_stock_local_a_nube()

    # 3. Buscar ventas desde la última vez (sea hace 10 segundos o hace 5 horas)
    hubo_cambios = procesar_ventas_pendientes(ultima_sincro)
    
    # 4. Solo actualizamos la memoria si procesamos bien o si no hubo nada pendiente
    # (Si falló el Excel, NO guardamos, para reintentar procesar esas ventas luego)
    if hubo_cambios:
        ultima_sincro = guardar_estado()
    elif not hubo_cambios:
        # Si no hubo ventas, igual actualizamos el estado para no buscar desde el año pasado
        ultima_sincro = guardar_estado()
        
    time.sleep(10)