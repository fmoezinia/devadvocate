import asyncio
import websockets
import json
import base64

# Define API keys and voice ID
ELEVENLABS_API_KEY = "sk_25694559a75916004707ec0d8fb3fa43d873e4bcf701aad3"
VOICE_ID = 'nPczCjzI2devNBz1zQrb' #Brian

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


async def text_to_speech_alignment_example(voice_id, text_to_send):
    """Send text to ElevenLabs API and stream the returned audio and alignment information."""
    uri = f"wss://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream-input?model_id=eleven_turbo_v2_5"
    async with websockets.connect(uri) as websocket:
        await websocket.send(json.dumps({
            "text": " ",
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.8, "use_speaker_boost": False},
            "generation_config": {
                "chunk_length_schedule": [120, 160, 250, 290]
            },
            "xi_api_key": ELEVENLABS_API_KEY,
        }))

        async def text_iterator(text):
            """Split text into chunks to mimic streaming from an LLM or similar"""
            split_text = text.split(" ")
            words = 0
            to_send = ""
            for chunk in split_text:
                to_send += chunk  + ' '
                words += 1
                if words >= 10:
                    # print(to_send)
                    yield to_send
                    words = 0
                    to_send = ""
            yield to_send

        async def listen():
            """Listen to the websocket for audio data and write it to a file."""
            audio_chunks = []
            alignment_info = []
            received_final_chunk = False
            print("Listening for chunks from ElevenLabs...")
            while not received_final_chunk:
                try:
                    message = await websocket.recv()
                    data = json.loads(message)
                    # print("receiving data here?", data)
                    if data.get("audio"):
                        audio_chunks.append(base64.b64decode(data["audio"]))
                    if data.get("alignment"):
                        alignment_info.append(data.get("alignment"))
                    if data.get('isFinal'):
                        received_final_chunk = True
                        break
                except websockets.exceptions.ConnectionClosed:
                    print("Connection closed")
                    break
            print("Writing audio to file")
            with open("output_file.mp3", "wb") as f:        
                f.write(b''.join(audio_chunks))

            calculate_word_start_times(alignment_info)


        listen_task = asyncio.create_task(listen())

        async for text in text_iterator(text_to_send):
            print(f"text to gen is , {text},  DONE\n")
            await websocket.send(json.dumps({"text": text}))
        await websocket.send(json.dumps({"text": " ", "flush": True}))
        await listen_task


# Main execution
if __name__ == "__main__":
    text_to_send = "The twilight sun cast its warm golden hues upon the vast rolling fields, saturating the landscape with an ethereal glow."
    asyncio.run(text_to_speech_alignment_example(VOICE_ID, text_to_send))
