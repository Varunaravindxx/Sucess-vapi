
import requests
import time
import json
from datetime import datetime
import uuid
import webbrowser
import os

# Vapi API Configuration
VAPI_PUBLIC_KEY = "96019add-ebef-4162-b69e-39ca8987a594"
VAPI_PRIVATE_KEY = "ed03fc81-ec6f-4bc3-ba53-9b719e93e648"
VAPI_BASE_URL = "https://api.vapi.ai"

# Headers for API calls
public_headers = {
    "Authorization": f"Bearer {VAPI_PUBLIC_KEY}",
    "Content-Type": "application/json"
}
private_headers = {
    "Authorization": f"Bearer {VAPI_PRIVATE_KEY}",
    "Content-Type": "application/json"
}

def get_job_description():
    """Get job description dynamically from user input."""
    print("Enter the job description (press Enter twice to finish):")
    lines = []
    while True:
        line = input()
        if line == "":
            if lines and lines[-1] == "":
                break
            lines.append("")
        else:
            lines.append(line)
    return "\n".join(lines).strip()

def generate_questions(job_description):
    """Return an empty list as questions will be generated dynamically by the assistant."""
    return []

def create_assistant(job_description, questions):
    """Create a Vapi assistant for the interview with dynamic question generation."""
    assistant_config = {
        "name": "WebDev_Interview_Assistant",
        "firstMessage": "Hello! I'm conducting the interview for the web development position.",
        "model": {
            "provider": "openai",
            "model": "gpt-4o",
            "systemPrompt": f"""
            You are an interview assistant for a position with the following job description:
            {job_description}
            
            Your role is to:
            - Ask the candidate to begin the interview.
            - Ask the candidate to introduce themselves.
            - Generate 5 dynamic interview questions tailored to the job description. The questions should be relevant to the skills, experience, and responsibilities outlined in the job description. For example, if the job requires proficiency in JavaScript and React, ask about specific experiences or challenges with these technologies.
            - Ask the generated questions one by one, waiting for the candidate's response (up to 30 seconds) before proceeding to the next question.
            - Be polite, professional, and encouraging throughout the interview.
            - After all questions, thank the candidate and end the session.
            - Do not evaluate answers; only collect responses.
            """
        },
        "voice": {
            "provider": "11labs",
            "voiceId": "sarah"
        },
        "transcriber": {
            "provider": "deepgram",
            "model": "nova-2"
        }
    }
    
    response = requests.post(
        f"{VAPI_BASE_URL}/assistant",
        headers=public_headers,
        json=assistant_config
    )
    
    if response.status_code == 201:
        return response.json()["id"]
    else:
        raise Exception(f"Failed to create assistant: {response.text}")

def start_websocket_call(assistant_id):
    """Start a WebSocket-based interview call with retry logic."""
    call_config = {
        "assistantId": assistant_id,
        "transport": {
            "provider": "vapi.websocket",
            "audioFormat": {
                "format": "pcm_s16le",
                "container": "raw",
                "sampleRate": 16000
            }
        }
    }
    
    max_retries = 3
    max_status_checks = 15
    for attempt in range(max_retries):
        response = requests.post(
            f"{VAPI_BASE_URL}/call",
            headers=public_headers,
            json=call_config
        )
        
        if response.status_code == 201:
            call_data = response.json()
            call_id = call_data.get("id")
            websocket_url = call_data.get("transport", {}).get("websocketCallUrl")
            print(f"Created call {call_id} with WebSocket URL: {websocket_url}")
            
            # Check call status
            for check in range(max_status_checks):
                status_response = requests.get(
                    f"{VAPI_BASE_URL}/call/{call_id}",
                    headers=public_headers
                )
                if status_response.status_code == 200:
                    call_status = status_response.json().get("status")
                    ended_reason = status_response.json().get("endedReason", "")
                    print(f"Call {call_id} status: {call_status} (Check {check + 1}/{max_status_checks})")
                    if call_status == "active" or call_status == "queued":
                        return call_id, websocket_url
                    elif call_status in ["ended", "failed"]:
                        print(f"Call {call_id} terminated early with status: {call_status}, reason: {ended_reason}")
                        break
                else:
                    print(f"Failed to check call status: {status_response.text}")
                time.sleep(2)
            
            print(f"Call {call_id} did not become active. Retrying... (Attempt {attempt + 1}/{max_retries})")
        else:
            print(f"Failed to start WebSocket call: {response.text} (Attempt {attempt + 1}/{max_retries})")
        
        time.sleep(2)
    
    raise Exception("Failed to start WebSocket call after retries. Check Vapi Dashboard for call logs.")

def generate_websocket_html(websocket_url, call_id):
    """Generate an HTML page for WebSocket audio streaming with optimized audio playback."""
    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Vapi WebSocket Interview</title>
    </head>
    <body>
        <h1>Vapi WebSocket Interview</h1>
        <p>Call ID: {call_id}</p>
        <p>Status: <span id="status">Connecting...</span></p>
        <p>Audio Data Info: <span id="audioInfo">Waiting for data...</span></p>
        <button id="startBtn" onclick="startCall()">Start Interview</button>
        <button id="endBtn" onclick="endCall()" disabled>End Interview</button>
        <script>
            let socket;
            let audioContext;
            let processor;
            let source;
            let audioBufferQueue = [];
            let lastBufferEndTime = 0;

            function startCall() {{
                const startBtn = document.getElementById('startBtn');
                const endBtn = document.getElementById('endBtn');
                if (!startBtn || !endBtn) {{
                    console.error('Button elements not found: startBtn or endBtn missing');
                    document.getElementById('status').textContent = 'Error: Buttons not found';
                    return;
                }}
                startBtn.disabled = true;
                endBtn.disabled = false;
                document.getElementById('status').textContent = 'Connecting to WebSocket...';
                
                try {{
                    socket = new WebSocket('{websocket_url}');
                }} catch (err) {{
                    console.error('WebSocket initialization failed:', err);
                    document.getElementById('status').textContent = 'WebSocket error: ' + err.message;
                    return;
                }}

                socket.onopen = () => {{
                    document.getElementById('status').textContent = 'Connected. Speak to answer questions.';
                    console.log('WebSocket connection opened.');
                    startAudio();
                }};

                socket.onclose = (event) => {{
                    document.getElementById('status').textContent = 'Disconnected: Code ' + event.code + ', Reason: ' + event.reason;
                    console.log('WebSocket closed:', event);
                    stopAudio();
                }};

                socket.onerror = (error) => {{
                    document.getElementById('status').textContent = 'WebSocket error';
                    console.error('WebSocket error:', error);
                }};

                socket.onmessage = (event) => {{
                    const receiveTime = performance.now();
                    console.log('Received data at:', receiveTime, 'ms, Type:', typeof event.data, event.data);
                    if (event.data instanceof Blob) {{
                        const blobType = event.data.type ? event.data.type : 'unknown';
                        console.log('Blob type:', blobType, 'Size:', event.data.size, 'bytes');
                        const infoText = 'Audio Data: Blob, Type: ' + blobType + ', Size: ' + event.data.size + ' bytes';
                        document.getElementById('audioInfo').textContent = infoText;
                        event.data.arrayBuffer().then(buffer => {{
                            const audioData = new Int16Array(buffer);
                            console.log('Converted to Int16Array, Length:', audioData.length, 'samples');
                            console.log('Sample rate assumption: 16000 Hz, Expected bytes per sample: 2 (pcm_s16le)');
                            console.log('First few samples:', audioData.slice(0, 10));
                            document.getElementById('audioInfo').textContent = infoText + ', Samples: ' + audioData.length;
                            if (audioContext && audioContext.state !== 'closed') {{
                                playAudio(audioData, receiveTime);
                            }} else {{
                                console.log('AudioContext not ready, queuing audio data');
                                audioBufferQueue.push({{ audioData: audioData, receiveTime: receiveTime }});
                            }}
                        }}).catch(err => {{
                            console.error('Audio buffer error:', err);
                            document.getElementById('audioInfo').textContent = 'Error processing audio data';
                        }});
                    }} else {{
                        try {{
                            const message = JSON.parse(event.data);
                            console.log('Control message:', message);
                            document.getElementById('audioInfo').textContent = 'Control Message: ' + JSON.stringify(message);
                            if (message.type === 'hangup') {{
                                endCall();
                            }}
                        }} catch (error) {{
                            console.error('Failed to parse message:', error);
                            document.getElementById('audioInfo').textContent = 'Error parsing control message';
                        }}
                    }}
                }};
            }}

            function startAudio() {{
                navigator.mediaDevices.getUserMedia({{ audio: true }}).then(stream => {{
                    audioContext = new AudioContext({{ sampleRate: 16000 }});
                    console.log('AudioContext initialized with sample rate:', audioContext.sampleRate);
                    source = audioContext.createMediaStreamSource(stream);
                    processor = audioContext.createScriptProcessor(1024, 1, 1);

                    processor.onaudioprocess = (event) => {{
                        const pcmData = event.inputBuffer.getChannelData(0);
                        const int16Data = new Int16Array(pcmData.length);
                        for (let i = 0; i < pcmData.length; i++) {{
                            int16Data[i] = Math.max(-32768, Math.min(32767, pcmData[i] * 32768));
                        }}
                        if (socket.readyState === WebSocket.OPEN) {{
                            socket.send(int16Data.buffer);
                        }}
                    }};

                    source.connect(processor);
                    processor.connect(audioContext.destination);

                    // Process any queued audio data
                    while (audioBufferQueue.length > 0) {{
                        const queuedItem = audioBufferQueue.shift();
                        const audioData = queuedItem.audioData;
                        const receiveTime = queuedItem.receiveTime;
                        console.log('Playing queued audio data, samples:', audioData.length, 'received at:', receiveTime);
                        playAudio(audioData, receiveTime);
                    }}
                }}).catch(err => {{
                    console.error('Microphone error details:', err.name, err.message);
                    document.getElementById('status').textContent = 'Microphone error: ' + err.message;
                }});
            }}

            function playAudio(audioData, receiveTime) {{
                try {{
                    if (!audioContext || audioContext.state === 'closed') {{
                        console.error('AudioContext is undefined or closed');
                        return;
                    }}
                    const buffer = audioContext.createBuffer(1, audioData.length, 16000);
                    const channelData = buffer.getChannelData(0);
                    for (let i = 0; i < audioData.length; i++) {{
                        channelData[i] = audioData[i] / 32768;
                    }}
                    const source = audioContext.createBufferSource();
                    source.buffer = buffer;
                    source.connect(audioContext.destination);

                    // Schedule playback to avoid gaps
                    const currentTime = audioContext.currentTime;
                    const bufferDuration = audioData.length / 16000;
                    const startTime = Math.max(currentTime, lastBufferEndTime);
                    source.start(startTime);
                    lastBufferEndTime = startTime + bufferDuration;
                    console.log('Playing buffer, samples:', audioData.length, 'startTime:', startTime, 'duration:', bufferDuration, 'ms since received:', performance.now() - receiveTime);

                    // Check for buffer underrun or overrun
                    if (startTime > currentTime + 0.1) {{
                        console.warn('Potential buffer underrun, startTime:', startTime, 'currentTime:', currentTime);
                    }}
                }} catch (err) {{
                    console.error('Audio playback error:', err);
                }}
            }}

            function endCall() {{
                if (socket && socket.readyState === WebSocket.OPEN) {{
                    try {{
                        socket.send(JSON.stringify({{ type: "hangup" }}));
                        socket.close();
                    }} catch (err) {{
                        console.error('Error sending hangup:', err);
                    }}
                }}
                stopAudio();
                document.getElementById('startBtn').disabled = false;
                document.getElementById('endBtn').disabled = true;
                document.getElementById('status').textContent = 'Call ended.';
            }}

            function stopAudio() {{
                try {{
                    if (processor) processor.disconnect();
                    if (source) source.disconnect();
                    if (audioContext) audioContext.close();
                    audioContext = null; // Explicitly reset
                    lastBufferEndTime = 0; // Reset buffer timing
                }} catch (err) {{
                    console.error('Error stopping audio:', err);
                }}
            }}
        </script>
    </body>
    </html>
    """
    with open("interview_websocket.html", "w") as f:
        f.write(html_content)
    return os.path.abspath("interview_websocket.html")

def get_call_transcript(call_id):
    """Retrieve the call transcript."""
    max_attempts = 10
    for _ in range(max_attempts):
        response = requests.get(
            f"{VAPI_BASE_URL}/call/{call_id}",
            headers=private_headers
        )
        
        if response.status_code == 200:
            call_data = response.json()
            if call_data.get("transcript"):
                return call_data["transcript"]
            elif call_data.get("status") in ["ended", "failed"]:
                raise Exception(f"Call ended with status: {call_data['status']}, reason: {call_data.get('endedReason', 'Unknown')}")
        time.sleep(10)
    
    raise Exception("Failed to retrieve transcript after maximum attempts.")

def evaluate_answers(transcript, questions):
    """Evaluate candidate answers (hypothetical implementation)."""
    evaluation = {}
    for i, question in enumerate(questions):
        response = f"Sample response to: {question}"
        score = len(response) // 10
        feedback = f"Response was {'adequate' if score > 5 else 'brief'}. Needs more detail."
        evaluation[question] = {"response": response, "score": min(score, 10), "feedback": feedback}
    
    return evaluation

def generate_report(job_description, evaluation):
    """Generate a Markdown report of the interview."""
    report = f"# Interview Report\n\n"
    report += f"**Date**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
    report += f"**Job Description**:\n{job_description}\n\n"
    report += "## Candidate Responses and Evaluation\n"
    
    total_score = 0
    for question, data in evaluation.items():
        report += f"### Question: {question}\n"
        report += f"- **Response**: {data['response']}\n"
        report += f"- **Score**: {data['score']}/10\n"
        report += f"- **Feedback**: {data['feedback']}\n\n"
        total_score += data["score"]
    
    report += "## Summary\n"
    report += f"**Total Score**: {total_score}/{len(evaluation) * 10}\n"
    report += f"**Overall Feedback**: {'Strong candidate' if total_score > 30 else 'Needs improvement'}\n"
    
    return report

def main():
    try:
        # Step 1: Get dynamic job description
        print("Enter the job description for the position.")
        job_description = get_job_description()
        
        # Step 2: Generate questions
        print("Configuring assistant to generate dynamic questions...")
        questions = generate_questions(job_description)
        
        # Step 3: Create the assistant
        print("Creating interview assistant...")
        assistant_id = create_assistant(job_description, questions)
        print(f"Assistant created with ID: {assistant_id}")
        
        # Step 4: Start the WebSocket call
        print("Starting WebSocket-based interview call...")
        print("Ensure your microphone is enabled and browser permissions allow audio access.")
        call_id, websocket_url = start_websocket_call(assistant_id)
        print(f"Opening WebSocket interview page for Call ID: {call_id}")
        
        # Wait to ensure call is active
        time.sleep(5)
        
        # Generate and open HTML page
        html_path = generate_websocket_html(websocket_url, call_id)
        webbrowser.open(f"file://{html_path}")
        
        # Step 5: Wait for user to complete the call
        print("Complete the interview in the browser. Click 'Start Interview' and speak to answer questions.")
        input("Press Enter when the interview is complete...")
        
        # Step 6: Get transcript
        print("Retrieving call transcript...")
        transcript = get_call_transcript(call_id)
        
        # Step 7: Evaluate answers
        print("Evaluating responses...")
        evaluation = evaluate_answers(transcript, questions)
        
        # Step 8: Generate report
        print("Generating report...")
        report = generate_report(job_description, evaluation)
        
        # Save report to file
        with open("interview_report.md", "w") as f:
            f.write(report)
        print("Report saved as 'interview_report.md'")
        
    except Exception as e:
        print(f"Error: {str(e)}")
        print("Troubleshooting tips:")
        print("- Ensure VAPI_PUBLIC_KEY and VAPI_PRIVATE_KEY are correct in the script.")
        print("- Verify microphone permissions in your browser (allow for file:// and wss://phone-call-websocket.aws-us-west-2-backend-production2.vapi.ai).")
        print("- Check call status in Vapi Dashboard (_calls section) for the call ID.")
        print("- Test WebSocket call creation in Postman (POST /call with vapi.websocket).")
        print("- Contact Vapi support with call ID and error details.")

if __name__ == "__main__":
    main()
