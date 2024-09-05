import asyncio
import base64
from elevenlabs.client import ElevenLabs
from fastapi import FastAPI, WebSocket
from fastapi.responses import HTMLResponse
from openai import AsyncOpenAI
import logging
import websockets
import json


OPENAI_API_KEY = (
    "sk-proj-PN-T0uqyX1ws5ztl7"
    "-uo00oIfuedaJUzmStjQOMcVK980wRCJqhMYIhcw44dDvSfqrH5lsfVvYT3BlbkFJyaux0NWMkqbmmVr_Hp99B2FQdikDBvX90E2QBI8oQMZ2va_FygwuiMtCvnp8I-FnUSkUqteKAA"
)
ELEVENLABS_API_KEY = "sk_25694559a75916004707ec0d8fb3fa43d873e4bcf701aad3"
VOICE_ID = "21m00Tcm4TlvDq8ikWAM"
VOICE_ID2 = "2EiwWnXFnvU5JabPnv8n"
URI = f"wss://api.elevenlabs.io/v1/text-to-speech/nPczCjzI2devNBz1zQrb/stream-input?model_id=eleven_turbo_v2_5"

# Set up logging
# logging.basicConfig(level=logging.DEBUG)
# logger = logging.getLogger(__name__)


app = FastAPI()
client = ElevenLabs(api_key=ELEVENLABS_API_KEY)
aclient = AsyncOpenAI(api_key=OPENAI_API_KEY)


def calculate_word_start_times(alignment_info):
    # Alignment start times are indexed from the start of the audio chunk that generated them
    # In order to analyse runtime over the entire response we keep a cumulative count of played audio
    full_alignment = {"chars": [], "charStartTimesMs": [], "charDurationsMs": []}
    cumulative_run_time = 0
    for old_dict in alignment_info:
        full_alignment["chars"].extend([" "] + old_dict["chars"])
        full_alignment["charDurationsMs"].extend(
            [old_dict["charStartTimesMs"][0]] + old_dict["charDurationsMs"]
        )
        full_alignment["charStartTimesMs"].extend(
            [0] + [time + cumulative_run_time for time in old_dict["charStartTimesMs"]]
        )
        cumulative_run_time += sum(old_dict["charDurationsMs"])

    # We now have the start times of every character relative to the entire audio output
    zipped_start_times = list(
        zip(full_alignment["chars"], full_alignment["charStartTimesMs"])
    )
    # Get the start time of every character that appears after a space and match this to the word
    words = "".join(full_alignment["chars"]).split(" ")
    word_start_times = list(
        zip(
            words,
            [0]
            + [
                zipped_start_times[i + 1][1]
                for (i, (a, b)) in enumerate(zipped_start_times)
                if a == " "
            ],
        )
    )
    print(f"total duration:{cumulative_run_time}")
    print(word_start_times)
    return word_start_times


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    while True:
        user_query = await websocket.receive_text()
        asyncio.create_task(process_query(websocket, user_query))


async def process_query(websocket: WebSocket, user_query: str):
    response = await aclient.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": user_query}],
        temperature=1,
        stream=True,
    )

    full_text = ""

    async def process_text():
        nonlocal full_text
        async for chunk in response:
            text_content = chunk.choices[0].delta.content
            if text_content:
                full_text += text_content
                # send the openAI response straight away to client...
                await websocket.send_json({"type": "text", "content": text_content})
                if len(full_text) > 40:
                    text_to_gen = full_text
                    full_text = ""
                    # new method TODO
                    async with websockets.connect(URI) as tts_websocket:
                        print(" is this starting?")
                        await tts_websocket.send(
                            json.dumps(
                                {
                                    "text": " ",
                                    "voice_settings": {
                                        "stability": 0.5,
                                        "similarity_boost": 0.8,
                                        "use_speaker_boost": False,
                                    },
                                    "generation_config": {
                                        "chunk_length_schedule": [120, 160, 250, 290]
                                    },
                                    "xi_api_key": ELEVENLABS_API_KEY,
                                }
                            )
                        )

                        async def listen():
                            audio_chunks = []
                            alignment_info = []
                            received_final_chunk = False
                            print("Listening for chunks from ElevenLabs...")
                            while not received_final_chunk:
                                print(" listening here")
                                try:
                                    message = await tts_websocket.recv()
                                    # print(message, " is the message")
                                    data = json.loads(message)
                                    # print(data, " is the data")
                                    if data.get("audio"):
                                        audio_chunks.append(
                                            base64.b64decode(data["audio"])
                                        )
                                        base64_audio = base64.urlsafe_b64encode(
                                            data["audio"]
                                        ).decode("ascii")
                                        await websocket.send_json(
                                            {"type": "audio", "content": base64_audio}
                                        )
                                    if data.get("alignment"):
                                        alignment_info.append(data.get("alignment"))
                                    if data.get("isFinal"):
                                        received_final_chunk = True
                                        break
                                except websockets.exceptions.ConnectionClosed as e:
                                    print("Connection closed because of ", e)
                                    break

                            # base64_audio = base64.urlsafe_b64encode(audio_chunk).decode('ascii')
                            # await websocket.send_json({
                            #     'type': 'audio',
                            #     'content': base64_audio
                            # })
                            calculate_word_start_times(alignment_info)

                        listen_task = asyncio.create_task(listen())
                        print(" text to gen ", text_to_gen)
                        await tts_websocket.send(json.dumps({"text": text_to_gen}))
                        await tts_websocket.send(json.dumps({"text": " ", "flush": True}))
                        await listen_task

        if len(full_text):
            audio = client.generate(
                text=full_text,
                voice=VOICE_ID,
                model="eleven_multilingual_v2",
                stream=True,
                optimize_streaming_latency=2,
            )
            for audio_chunk in audio:
                # print("wenger ", audio_chunk)
                if audio_chunk:
                    base64_audio = base64.urlsafe_b64encode(audio_chunk).decode("ascii")
                    await websocket.send_json(
                        {"type": "audio", "content": base64_audio}
                    )

                    # this flushes and closes connection TODO add back
                    # await tts_websocket.send(json.dumps({"text": " ", "flush": True}))

    await process_text()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
