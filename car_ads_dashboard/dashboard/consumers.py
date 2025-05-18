from channels.generic.websocket import AsyncWebsocketConsumer
import json

class SyncNotificationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        await self.channel_layer.group_add("sync_group", self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard("sync_group", self.channel_name)

    async def sync_message(self, event):
        await self.send(text_data=json.dumps(event["message"]))
