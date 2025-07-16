from channels.generic.websocket import AsyncWebsocketConsumer
import json
import asyncio
import subprocess
import re

class SyncNotificationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        await self.channel_layer.group_add("sync_group", self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard("sync_group", self.channel_name)

    async def sync_message(self, event):
        await self.send(text_data=json.dumps(event["message"]))

class LogsConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.session_id = self.scope['url_route']['kwargs']['session_id']
        self.logs_group_name = f'logs_{self.session_id}'
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
        # Extract screen name from session_id
        match = re.match(r'\d+\.(.+)', self.session_id)
        if not match:
            await self.send(text_data=json.dumps({
                'error': f'Invalid session ID: {self.session_id}'
            }))
            return
        
        screen_name = match.group(1)
        
        # Send initial connection message
        await self.send(text_data=json.dumps({
            'message': f'Connected to log stream for {screen_name}',
            'type': 'info'
        }))
        
        # Create a process to stream the logs using screen -r
        try:
            # Initial log capture
            process = await asyncio.create_subprocess_exec(
                'screen', '-S', self.session_id, '-X', 'hardcopy', '/tmp/screen_log.txt',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            await process.communicate()
            
            # Read the log file
            with open('/tmp/screen_log.txt', 'r') as f:
                log_content = f.read()
                
            await self.send(text_data=json.dumps({
                'log': log_content,
                'type': 'initial'
            }))
            
            # Poll for updates every 2 seconds
            while not self.should_stop:
                process = await asyncio.create_subprocess_exec(
                    'screen', '-S', self.session_id, '-X', 'hardcopy', '/tmp/screen_log.txt',
                    stdout=asyncio.subprocess.PIPE
                )
                await process.communicate()
                
                with open('/tmp/screen_log.txt', 'r') as f:
                    log_content = f.read()
                
                await self.send(text_data=json.dumps({
                    'log': log_content,
                    'type': 'update'
                }))
                
                await asyncio.sleep(2)
                
        except Exception as e:
            await self.send(text_data=json.dumps({
                'error': str(e)
            }))
            
    async def receive(self, text_data):
        data = json.loads(text_data)
        
        if data.get('command') == 'stop':
            self.should_stop = True
            await self.send(text_data=json.dumps({
                'message': 'Stopped log streaming',
                'type': 'info'
            }))
