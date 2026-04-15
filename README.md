# Agente-de-negocios
Daemon local en Python para sincronización bidireccional entre inventarios en Excel y Supabase. Gestiona reservas web y emite telemetría (heartbeat) en tiempo real.

Urania Edge Node > Un servicio ligero en segundo plano (Edge Computing) diseñado para modernizar puntos de venta físicos. Este script de Python actúa como un puente bidireccional que conecta un sistema de inventario local basado en Excel con una base de datos en la nube (Supabase).

Características principales:

Sincronización Bidireccional: Sube las ventas del mostrador físico a la nube y descarga las reservas web para actualizar el Excel local.

Telemetría (Heartbeat): Emite señales de vida constantes para informar a los sistemas en la nube si la sucursal tiene conectividad a internet.

Tolerancia a fallos: Cuenta con memoria de estados para evitar la pérdida de transacciones y manejo de errores ante bloqueos de lectura/escritura en archivos locales.
