from celery import shared_task
import asyncio
import os
from dotenv import load_dotenv
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

# Load .env agar variabel env bisa terbaca
load_dotenv()

def send_ws_message(message):
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        "sync_group",
        {
            "type": "sync.message",
            "message": message
        }
    )

@shared_task(bind=True)
def sync_data_task(self):
    from dashboard.services import sync_data_from_remote
    try:
        print("🟢 Memulai sinkronisasi data dari VPS...")
        # Jalankan coroutine async di sync context
        asyncio.run(sync_data_from_remote())
        print("✅ Sinkronisasi selesai.")
        send_ws_message({
            "status": "success",
            "detail": "✅ Sinkronisasi data dari VPS telah selesai!"
        })
    except Exception as e:
        print(f"❌ Sinkronisasi gagal: {e}")
        send_ws_message({
            "status": "error",
            "detail": f"❌ Sinkronisasi gagal: {str(e)}"
        })
        # Optional: raise agar Celery catat error dan retry jika perlu
        raise
