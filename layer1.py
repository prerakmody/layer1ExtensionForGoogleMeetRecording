import redis.asyncio as redis
import asyncio
import json
import uuid
from fnmatch import fnmatch
import os

class MessageCenter:
    queue = {}
    r = redis.Redis(host='localhost', port=6381, decode_responses=True)
    handlers = {}

    def __init__(self, loop):
        self.loop = loop
        self.extension_id = os.environ.get('EXTENSION_ID', str(uuid.uuid4()))
        self.pubsub = self.r.pubsub()

    def run(self):
        self.loop.run_until_complete(self.listen_for_messages())

    def subscribe(self, channel, handler):
        self.handlers[channel] = handler

    async def send_message(self, msg):
        responseID = str(uuid.uuid4())
        msg["responseID"] = responseID
        msg["extensionID"] = self.extension_id
        msg["origin"] = "extension"

        resp_future = asyncio.Future()
        self.queue[responseID] = resp_future
        await self.r.publish("messages", json.dumps(msg))
        result = await resp_future
        return result
    
    async def listen_for_messages(self):
        await self.pubsub.subscribe(*self.handlers.keys(), 'messages')
        while True:
            try:
                msg = await self.pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if msg:
                    self.triage_msg(msg['channel'], json.loads(msg['data']))
            except asyncio.CancelledError:
                raise
            except:
                log("Layer1 connection closed. Retrying...")
                await asyncio.sleep(1)

    def triage_msg(self, channel, msg):
        # Ignore messages for other extensions
        if 'extensionID' in msg and msg['extensionID'] != self.extension_id:
            return
        # Ignore any messages broadcast by ourself (origin)
        if msg.get('origin') != 'app':
            return
        
        if channel == 'messages' and msg.get('responseID'):
            # Only handle incoming messages directed at our extension
            self._handle_response(msg['responseID'], msg.get('data', {}))
        else:
            for chan, handler in self.handlers.items():
                if fnmatch(channel, chan):
                    try:
                        self.loop.create_task(handler(channel, msg['event'], msg.get('data', {})))
                    except Exception as e:
                        log("Event handler error raised: ", e)
                    break

    # Handles incoming responses on the 'messages' channel
    def _handle_response(self, responseID, msg):
        if responseID in self.queue:
            self.queue[responseID].set_result(msg)
            del self.queue[responseID]
        else:
            log("Warning: no response handler found for responseID: ", responseID)

class Dictionary:
    r = MessageCenter.r

    def __init__(self, extension_id):
        self.extension_id = extension_id

    async def set(self, key, value, ttl=None):
        rkey = f"{self.extension_id}:{key}"
        await self.r.set(rkey, value)
        if ttl:
            await self.r.expire(rkey, ttl)

    async def get(self, key):
        rkey = f"{self.extension_id}:{key}"
        return await self.r.get(rkey)

    async def set_int(self, key, value):
        await self.set(key, str(value))

    async def get_int(self, key):
        int_str = await self.get(key)
        return int(int_str or 0)

    async def increment(self, key, amount=1):
        rkey = f"{self.extension_id}:{key}"
        value = int(await self.r.incr(rkey, amount=amount))
        return value

    async def set_json(self, key, data):
        js_str = json.dumps(data)
        await self.set(key, js_str)

    async def get_json(self, key):
        js_str = await self.get(key)
        return json.loads(js_str or '{}')

    async def pop(self, key):
        rkey = f"{self.extension_id}:{key}"
        return await self.r.getdel(rkey)

    async def remove(self, key):
        rkey = f"{self.extension_id}:{key}"
        await self.r.delete(rkey)

# Log to stdout and flush after each line
def log(*str):
    print(*str, flush=True)