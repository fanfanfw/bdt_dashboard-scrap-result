from celery import shared_task
import asyncio
import os
from dotenv import load_dotenv
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from django.utils import timezone

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

def update_sync_status(task_id, status, message=None, progress=0, current_step=None):
    """Update sync status in database and send WebSocket notification"""
    from .models import SyncStatus
    
    try:
        sync_status, created = SyncStatus.objects.get_or_create(
            task_id=task_id,
            defaults={
                'status': status,
                'message': message,
                'progress_percentage': progress,
                'current_step': current_step
            }
        )
        
        if not created:
            sync_status.status = status
            sync_status.message = message
            sync_status.progress_percentage = progress
            sync_status.current_step = current_step
            
            if status in ['success', 'failure']:
                sync_status.completed_at = timezone.now()
            
            sync_status.save()
        
        # Send WebSocket message
        ws_message = {
            "status": status,
            "detail": message or f"Sync {status}",
            "progress": progress,
            "current_step": current_step,
            "task_id": task_id
        }
        send_ws_message(ws_message)
        
    except Exception as e:
        print(f"Error updating sync status: {e}")

@shared_task(bind=True)
def sync_data_task(self):
    from dashboard.services import sync_data_from_remote
    
    task_id = self.request.id
    
    try:
        print(f"🟢 Memulai sinkronisasi data dari VPS... (Task ID: {task_id})")
        
        # Update status to in_progress
        update_sync_status(
            task_id=task_id,
            status='in_progress',
            message='🟢 Memulai sinkronisasi data dari VPS...',
            progress=10,
            current_step='Initializing sync process'
        )
        
        # Update progress during sync
        update_sync_status(
            task_id=task_id,
            status='in_progress',
            message='⏳ Mengunduh data dari server remote...',
            progress=30,
            current_step='Downloading data from remote server'
        )
        
        # Jalankan coroutine async di sync context
        asyncio.run(sync_data_from_remote())
        
        # Update progress before completion
        update_sync_status(
            task_id=task_id,
            status='in_progress',
            message='⏳ Memproses dan menyimpan data...',
            progress=90,
            current_step='Processing and saving data'
        )
        
        print("✅ Sinkronisasi selesai.")
        
        # Update status to success
        update_sync_status(
            task_id=task_id,
            status='success',
            message='✅ Sinkronisasi data dari VPS telah selesai!',
            progress=100,
            current_step='Completed successfully'
        )
        
    except Exception as e:
        print(f"❌ Sinkronisasi gagal: {e}")
        
        # Update status to failure
        update_sync_status(
            task_id=task_id,
            status='failure',
            message=f'❌ Sinkronisasi gagal: {str(e)}',
            progress=0,
            current_step='Failed'
        )
        
        # Optional: raise agar Celery catat error dan retry jika perlu
        raise
