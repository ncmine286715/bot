import subprocess
import time
import os
from datetime import datetime

print("🚀 Bot iniciado no Render")
print(f"📅 {datetime.now()}")

while True:
    print(f"\n{'='*50}")
    print(f"🔥 Executando coleta em {datetime.now()}")
    print(f"{'='*50}")
    
    try:
        # Executa o robô
        resultado = subprocess.run(
            ["python", "robo_hibrido.py"],
            capture_output=True,
            text=True,
            timeout=7200
        )
        
        # Mostra os logs
        print(resultado.stdout)
        if resultado.stderr:
            print("❌ ERROS:", resultado.stderr)
            
    except Exception as e:
        print(f"💥 Erro: {e}")
    
    print(f"\n⏳ Aguardando 4 horas...")
    time.sleep(4 * 60 * 60)  # 4 horas
