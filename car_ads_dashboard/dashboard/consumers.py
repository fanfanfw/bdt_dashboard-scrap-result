from channels.generic.websocket import AsyncWebsocketConsumer
import json
import asyncio
import subprocess
import re
import os
import base64

class SyncNotificationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        await self.channel_layer.group_add("sync_group", self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard("sync_group", self.channel_name)

    async def sync_message(self, event):
        await self.send(text_data=json.dumps(event["message"]))
        
class CronLogConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.log_file_id = self.scope['url_route']['kwargs']['log_file_id']
        self.logs_group_name = f'cronlog_{self.log_file_id}'
        self.should_stop = False
        
        # Join logs group
        await self.channel_layer.group_add(
            self.logs_group_name,
            self.channel_name
        )
        await self.accept()
        
        # Start the background task to stream logs
        asyncio.create_task(self.stream_logs())

    async def disconnect(self, close_code):
        # Stop the streaming logs task
        self.should_stop = True
        
        # Leave logs group
        await self.channel_layer.group_discard(
            self.logs_group_name,
            self.channel_name
        )
    
    async def stream_logs(self):
        # Decode the base64 filename
        try:
            log_path = base64.b64decode(self.log_file_id).decode('utf-8')
            log_name = os.path.basename(log_path)
            
            # Validate that the log file exists and is a valid log file
            if not os.path.exists(log_path) or not os.path.isfile(log_path):
                await self.send(text_data=json.dumps({
                    'error': f'Log file not found: {log_name}'
                }))
                return
                
            # Only allow files with .log extension for security
            if not log_path.endswith('.log'):
                await self.send(text_data=json.dumps({
                    'error': 'Invalid log file format'
                }))
                return
                
            # Send initial connection message
            await self.send(text_data=json.dumps({
                'message': f'Connected to log stream for {log_name}',
                'type': 'info'
            }))
            
            # Initial log fetch - get the last 100 lines to start
            try:
                process = await asyncio.create_subprocess_exec(
                    '/usr/bin/tail', '-n', '100', log_path,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                
                stdout, stderr = await process.communicate()
                
                if process.returncode != 0:
                    await self.send(text_data=json.dumps({
                        'error': f'Error reading log file: {stderr.decode()}'
                    }))
                    return
                    
                log_content = stdout.decode('utf-8', errors='replace')
                
                await self.send(text_data=json.dumps({
                    'log': log_content,
                    'type': 'initial'
                }))
                
                # Get file size to track changes
                last_size = os.path.getsize(log_path)
                
                # Poll for updates every 2 seconds
                while not self.should_stop:
                    await asyncio.sleep(2)
                    
                    current_size = os.path.getsize(log_path)
                    
                    if current_size > last_size:
                        # File has new content, get only the new lines
                        process = await asyncio.create_subprocess_exec(
                            '/usr/bin/tail', '-c', f'+{last_size+1}', log_path,
                            stdout=asyncio.subprocess.PIPE
                        )
                        stdout, _ = await process.communicate()
                        
                        new_content = stdout.decode('utf-8', errors='replace')
                        
                        # Get full log (limited to last 500 lines to prevent browser overload)
                        process = await asyncio.create_subprocess_exec(
                            '/usr/bin/tail', '-n', '500', log_path,
                            stdout=asyncio.subprocess.PIPE
                        )
                        stdout, _ = await process.communicate()
                        full_content = stdout.decode('utf-8', errors='replace')
                        
                        await self.send(text_data=json.dumps({
                            'log': full_content,
                            'new_content': new_content,
                            'type': 'update'
                        }))
                        
                        last_size = current_size
                    
            except Exception as e:
                await self.send(text_data=json.dumps({
                    'error': f'Error streaming logs: {str(e)}'
                }))
                
        except Exception as e:
            await self.send(text_data=json.dumps({
                'error': f'Invalid log file ID: {str(e)}'
            }))
            
    async def receive(self, text_data):
        data = json.loads(text_data)
        
        if data.get('command') == 'stop':
            self.should_stop = True
            await self.send(text_data=json.dumps({
                'message': 'Stopped log streaming',
                'type': 'info'
            }))

