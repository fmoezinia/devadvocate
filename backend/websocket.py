import asyncio
import websockets
import json
import base64
import shutil
import os
import subprocess
from openai import AsyncOpenAI

# Define API keys and voice ID
OPENAI_API_KEY = '<OPENAI_API_KEY>'
ELEVENLABS_API_KEY = 'sk_25694559a75916004707ec0d8fb3fa43d873e4bcf701aad3'
VOICE_ID = '21m00Tcm4TlvDq8ikWAM'

# Set OpenAI API key
aclient = AsyncOpenAI(api_key=OPENAI_API_KEY)

def is_installed(lib_name):
    return shutil.which(lib_name) is not None


async def text_chunker(chunks):
    """Split text into chunks, ensuring to not break sentences."""
    splitters = (".", ",", "?", "!", ";", ":", "—", "-", "(", ")", "[", "]", "}", " ")
    buffer = ""

    async for text in chunks:
        if buffer.endswith(splitters):
            yield buffer + " "
            buffer = text
        elif text.startswith(splitters):
            yield buffer + text[0] + " "
            buffer = text[1:]
        else:
            buffer += text

    if buffer:
        yield buffer + " "


async def stream(audio_stream):
    """Stream audio data using mpv player."""
    if not is_installed("mpv"):
        raise ValueError(
            "mpv not found, necessary to stream audio. "
            "Install instructions: https://mpv.io/installation/"
        )

    mpv_process = subprocess.Popen(
        ["mpv", "--no-cache", "--no-terminal", "--", "fd://0"],
        stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )

    print("Started streaming audio")
    async for chunk in audio_stream:
        if chunk:
            mpv_process.stdin.write(chunk)
            mpv_process.stdin.flush()

    if mpv_process.stdin:
        mpv_process.stdin.close()
    mpv_process.wait()



# async def listen():
#     """Listen to the websocket for audio data and write it to a file."""
#     audio_chunks = []
#     alignment_info = []
#     received_final_chunk = False
#     print("Listening for chunks from ElevenLabs...")
#     while not received_final_chunk:
#         try:
#             message = await websocket.recv()
#             data = json.loads(message)
#             if data.get("audio"):
#                 audio_chunks.append(base64.b64decode(data["audio"]))
#             if data.get("alignment"):
#                 alignment_info.append(data.get("alignment"))
#             if data.get('isFinal'):
#                 received_final_chunk = True
#                 break
#         except websockets.exceptions.ConnectionClosed:
#             print("Connection closed")
#             break
#     print("Writing audio to file")
#     with open("output_file.mp3", "wb") as f:        
#         f.write(b''.join(audio_chunks))

#     calculate_word_start_times(alignment_info)


async def text_to_speech_input_streaming(voice_id, text_iterator):
    """Send text to ElevenLabs API and stream the returned audio."""
    uri = f"wss://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream-input?model_id=eleven_turbo_v2_5"

    async with websockets.connect(uri) as websocket:
        await websocket.send(json.dumps({
            "text": " ",
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.8},
            "xi_api_key": ELEVENLABS_API_KEY,
        }))

        async def listen():
            """Listen to the websocket for audio data and stream it."""
            while True:
                try:
                    message = await websocket.recv()
                    data = json.loads(message)
                    if data.get("audio"):
                        yield base64.b64decode(data["audio"])
                    elif data.get('isFinal'):
                        break
                except websockets.exceptions.ConnectionClosed:
                    print("Connection closed")
                    break

        listen_task = asyncio.create_task(stream(listen()))

        async for text in text_chunker(text_iterator):
            await websocket.send(json.dumps({"text": text, "try_trigger_generation": True}))

        await websocket.send(json.dumps({"text": ""}))
        # await websocket.send(json.dumps({"text": " ", "flush": True}))

        await listen_task


async def chat_completion(query):
    """Retrieve text from OpenAI and pass it to the text-to-speech function."""
    response = await aclient.chat.completions.create(model='gpt-4', messages=[{'role': 'user', 'content': query}],
    temperature=1, stream=True)

    async def text_iterator():
        async for chunk in response:
            delta = chunk.choices[0].delta
            yield delta.content

    await text_to_speech_input_streaming(VOICE_ID, text_iterator())


def calculate_word_start_times(alignment_info):
    # Alignment start times are indexed from the start of the audio chunk that generated them
    # In order to analyse runtime over the entire response we keep a cumulative count of played audio
    full_alignment = {'chars': [], 'charStartTimesMs': [], 'charDurationsMs': []}
    cumulative_run_time = 0
    for old_dict in alignment_info:
        full_alignment['chars'].extend([" "] + old_dict['chars'])
        full_alignment['charDurationsMs'].extend([old_dict['charStartTimesMs'][0]] + old_dict['charDurationsMs'])
        full_alignment['charStartTimesMs'].extend([0] + [time+cumulative_run_time for time in old_dict['charStartTimesMs']])
        cumulative_run_time += sum(old_dict['charDurationsMs'])
    
    # We now have the start times of every character relative to the entire audio output
    zipped_start_times = list(zip(full_alignment['chars'], full_alignment['charStartTimesMs']))
    # Get the start time of every character that appears after a space and match this to the word
    words = ''.join(full_alignment['chars']).split(" ")
    word_start_times = list(zip(words, [0] + [zipped_start_times[i+1][1] for (i, (a,b)) in enumerate(zipped_start_times) if a == ' ']))
    print(f"total duration:{cumulative_run_time}")
    print(word_start_times)


