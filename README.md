# Template Layer 1 Extension
There are 4 files to include
- main.py
    - Extension logic
- layer1.py
    - Layer 1 base classes
- mainfest.json
    - 
- scripts.json
- README.md

1. main.py
    ```python
    import layer1
    import asyncio

    # Step 1 - Create a run loop and messageCenter instance
    loop = asyncio.get_event_loop()
    messageCenter = layer1.MessageCenter(loop)

    async def channelHandler(channel, event, msg):
        print('Received message on channel: ', channel)
        print('Event: ', event)
        print('Message: ', msg)

    # Step 99 - Subscribe to incoming events on the '{someChannel}' channel
    messageCenter.subscribe('{someChannel}', channelHandler()) # someChannel = ['recorder', 'calls', 'ui', 'messages', 'system']
    messageCenter.run()
    ```
2. 