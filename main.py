import layer1
import asyncio
import datetime
import traceback
import objectpath
import asyncio
import datetime
import traceback

# Step 0 - Init
BUNDLEID_BRAVEBROWSER = 'com.brave.Browser'
BUNDLEID_CHROMEBROWSER = 'com.google.Chrome'
pollGoogleMeetTabInBraveBrowser = None

# Step 0.2 - Init for debug
DEBUG = False
callStartedOn = None
lastTimeCallLogWasPrinted = None

# Step 1 - Create a run loop and layer1MessageCenter instance
loop = asyncio.get_event_loop()
layer1MessageCenter = layer1.MessageCenter(loop)

#######################################################
# UTILS
#######################################################

def find_in_dict(obj, key, value):
    results = []
    
    if isinstance(obj, dict):
        if obj.get(key) == value:
            results.append(obj)
        for k, v in obj.items():
            results.extend(find_in_dict(obj[k], key, value))
    
    elif isinstance(obj, list):
        for item in obj:
            results.extend(find_in_dict(item, key, value))
    
    return results

def printInExtensionLog(msg):
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # layer1.log ('\n =============================== ')
    layer1.log (' - [{}] {}'.format(now, msg))
    # layer1.log (' =============================== \n')

def formatTimedelta(td):
    total_seconds = int(td.total_seconds())
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    # round off the values
    hours = round(hours)
    minutes = round(minutes)
    seconds = round(seconds)

    if hours > 0:
        return f"{hours} hour(s) and {minutes} minute(s)"
    elif minutes > 0:
        return f"{minutes} minute(s) and {seconds} second(s)"
    else:
        return f"{seconds} second(s)"

#######################################################
# SUMMARIZATION FUNCTIONS
#######################################################
    
async def handleCallDidEnd(msg):
    
    try:
        # Step 0.1 - Init check
        if 'startDate' not in msg or 'endDate' not in msg:
            return
        
        # Step 0.2 - Log
        startTime = datetime.datetime.fromtimestamp(msg['startDate'])
        endTime = datetime.datetime.fromtimestamp(msg['endDate'])
        durationStr = formatTimedelta(endTime - startTime)
        layer1.log(durationStr)
        printInExtensionLog(f'Call ended in {msg["appName"]} (callID= {msg["callID"]}) and it ran for {durationStr}')
        
        # Step 1 - Send message to get summary
        printInExtensionLog('Sending summary request')
        scriptMsg = {
            "event": "layerScript.run",
            "data": {
                "scriptID": "0FFC00D4-4535-405F-9C6F-B10936E595EE",
                "scriptInput": str(msg['callID'])
                # "scriptInput": "1706636386"
            }
        }
        summaryMsg = await layer1MessageCenter.send_message(scriptMsg)
        summaryObjStr = summaryMsg['summary']
        summaryObjList = eval(summaryObjStr)
        for summaryObj in summaryObjList:
            title = summaryObj['title']
            summaryStr = summaryObj['summary']
            printInExtensionLog(f'[Summary][{title}] : {summaryStr}')

        # Step 2 - Save summary
        save_msg = {
            "event": "edb.runEdgeQL",
            "data": {
                "query": "update Call filter .callID = <int64>$callID set { summary := <str>$summary };",
                "variables": {
                    "callID": msg['callID'],
                    "summary": summaryObjStr
                }
            }
        }
        summary_resp = await layer1MessageCenter.send_message(save_msg)
        printInExtensionLog('summary_resp: {}'.format(summary_resp))
    
    except:
        traceback.print_exc()
        layer1.log(' - Error in handleCallDidEnd()')

#######################################################
# BROWSER-BASED FUNCTIONS
#######################################################

async def showRecordingMsg(isRecording):
    text =  "Recording started" if isRecording else "Recording ended"
    html = """
    <html><body>
    <h1>Google Meet Recorder</h1>
    <p>{text}</p>
    </body></html>
    """.format(text=text)
    view_msg = {
        "event": "ui.renderHTML",
        "data": {
            "html": html
        }
    }
    status = await layer1MessageCenter.send_message(view_msg)

async def startRecordingGoogleMeet(pid):

    printInExtensionLog("Starting recording for Brave Browser")

    # Step 0 - Send message for recording
    msg = {
        "event": "recorder.startCallRecording",
        "data": {
            "pid": pid
        }
    }
    resp = await layer1MessageCenter.send_message(msg)

    # Step 1 - Process response
    if 'error' in resp:
        layer1.log(" - Error starting recording for Brave Browser: ", resp['error'])
    # else:
    #     await showRecordingMsg(True)

async def stopRecordingGoogleMeet(pid):
    
    printInExtensionLog("Stopping recording for Brave Browser")
    msg = {
        "event": "recorder.stopCallRecording",
        "data": {
            "pid": pid
        }
    }
    await layer1MessageCenter.send_message(msg)
    # await showRecordingMsg(False)

async def findGoogleMeetCallTabInBraveBrowser(pid):

    # Step 1 - Setup message
    msg = {
        "event": "ax.getProcessTree",
        "data": {
            "pid": pid
        }
    }

    # Step 2 - Send message
    resp = await layer1MessageCenter.send_message(msg)

    # Step 3 - Process response
    results = find_in_dict(resp, 'role', 'AXRadioButton')
    for result in results:
        if DEBUG:
            layer1.log (' --------------------->>>>>>>')
            layer1.log (result)
            layer1.log (' - description: ', result['description'])
        if 'Google Meet' in result['description']:
            # layer1.log (' - Google Meet Tab is open')
            pass
        if 'Meet' in result['description'] and 'recording' in result['description']:
            if DEBUG:
                layer1.log (' - Google Meet Tab is open and recording')
            return result

async def pollForGoogleMeetTabInBraveBrowser(pid):
    
    # Step 0 - Init
    onGoogleMeetCall = False
    
    # Step 2 - Check for Google Meet call Tab
    while True:

        try:
            googleMeetCallFoundObj = await findGoogleMeetCallTabInBraveBrowser(pid)
            # layer1.log ('\n - Google Meet Call Found: ', googleMeetCallFoundObj)
            if googleMeetCallFoundObj is not None:
                if onGoogleMeetCall == False:
                    printInExtensionLog('Google Meet call has now started')
                    onGoogleMeetCall = True
                    global callStartedOn
                    callStartedOn = datetime.datetime.now()
                    global lastTimeCallLogWasPrinted
                    lastTimeCallLogWasPrinted = callStartedOn
                    await startRecordingGoogleMeet(pid)
                else:
                    lastTimeCallLogWasPrintedDeltaObj = datetime.datetime.now() - lastTimeCallLogWasPrinted
                    if lastTimeCallLogWasPrintedDeltaObj.total_seconds() > 10:
                        timeDeltaObjForCall = datetime.datetime.now() - callStartedOn
                        printInExtensionLog('Time Passed for {}: {} '.format(googleMeetCallFoundObj['description'], formatTimedelta(timeDeltaObjForCall)))
                        lastTimeCallLogWasPrinted = datetime.datetime.now()
            else:
                if onGoogleMeetCall == True:
                    printInExtensionLog('Google Meet call is now stopped')
                    onGoogleMeetCall = False
                    await stopRecordingGoogleMeet(pid)
                        
            await asyncio.sleep(2)

        except:
            traceback.print_exc()
            layer1.log(' - Error in pollForGoogleMeetTabInBraveBrowser()')
            break

#######################################################
# LAYER1-BASED FUNCTIONS
#######################################################

async def callHandler(channel, event, msg):
    if event == 'callRecordingStopped': #'callDidEnd'
        await handleCallDidEnd(msg)

# Handle for incoming events on the 'system' channel
## (If extension is already loaded), then check if Brave Browser was launched/terminated
async def systemHandler(channel, event, msg):
    if event == 'applicationDidLaunch':
        layer1.log (' - App launched: ', msg['bundleID'], msg['appName'], msg['pid'])
        if 'bundleId' in msg and msg['bundleID'] == BUNDLEID_BRAVEBROWSER:
            printInExtensionLog("Brave Browser has been launched")
            global pollGoogleMeetTabInBraveBrowser
            pollGoogleMeetTabInBraveBrowser = loop.create_task(pollForGoogleMeetTabInBraveBrowser(msg['pid']))
    
    if event == 'applicationDidTerminate':
        layer1.log (' - App terminated: ', msg['bundleID'], msg['appName'], msg['pid'])
        if 'bundleId' in msg and msg['bundleID'] == BUNDLEID_BRAVEBROWSER:
            pollGoogleMeetTabInBraveBrowser.cancel()

# Check for an open instance of Brave Browser (when this extension is loaded)
async def checkBraveBrowserRunning():

    # Step 0 - Init
    printInExtensionLog("Checking for existing Brave Browser instance ... Trial 3 ")
    def isBraveBrowser(app):
        return 'bundleID' in app and app['bundleID'] in [BUNDLEID_BRAVEBROWSER]

    # Step 1 - Send message to get running apps
    msg = {"event": "system.getRunningApps"}
    resp = await layer1MessageCenter.send_message(msg)

    # Step 2 - Process response
    apps = resp['runningApps']
    braveProc = next(filter(lambda app: isBraveBrowser(app), apps), None)
    if braveProc:
        printInExtensionLog("Brave Browser is currently running")
        global pollGoogleMeetTabInBraveBrowser
        pollGoogleMeetTabInBraveBrowser = loop.create_task(pollForGoogleMeetTabInBraveBrowser(braveProc['pid']))
    else:
        printInExtensionLog("Brave Browser is currently not running")

#######################################################
# main()
#######################################################

# Step 3.0 - Create tasks
loop.create_task(checkBraveBrowserRunning())

# Step 3.1 - Subscribe to incoming events on the 'recorder' channel
layer1MessageCenter.subscribe('system', systemHandler)
layer1MessageCenter.subscribe('calls', callHandler)
layer1MessageCenter.run()



"""
Channels
- system
- recorder
- calls
- ui
- messages
"""

"""
1. What does it mean if the folder is copied to "/Users/{username}/Library/Application Support/Move37/ScreenomeX/Extensions"
"""