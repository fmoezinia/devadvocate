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


app = FastAPI()
client = ElevenLabs(api_key=ELEVENLABS_API_KEY)
aclient = AsyncOpenAI(api_key=OPENAI_API_KEY)


def calculate_word_start_times(alignment_info):
    # Alignment start times are indexed from the start of the audio chunk that generated them
    # In order to analyse runtime over the entire response we keep a cumulative count of played audio
    # print(" alignment info ", alignment_info)
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
    # print(word_start_times, " word start times")
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

    async def process_text():

        async with websockets.connect(URI) as tts_websocket:
            # establish
            print("establish connection once")
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
                all_alignment_info = []
                received_final_chunk = False
                latest_alignment = []
                print("Listening for chunks from ElevenLabs...")
                while not received_final_chunk:
                    print(" listening here")
                    try:
                        message = await tts_websocket.recv()
                        data = json.loads(message)
                        # print(data, " is the data")
                        if data.get("audio"):
                            audio_chunk = data["audio"] # this is valid b64
                            await websocket.send_json(
                                {"type": "audio", "content": audio_chunk}
                            )
                            audio_chunks.append(audio_chunk)
                        if data.get("alignment"):
                            al = data.get("alignment")
                            all_alignment_info.append(al)
                            word_start_times = calculate_word_start_times(all_alignment_info)
                            aligment_to_send = list(set(word_start_times) - set(latest_alignment))
                            latest_alignment = word_start_times
                            print(aligment_to_send, " alignment to send")
                            await websocket.send_json(
                                {"type": "alignment", "content": aligment_to_send}
                            )
                        if data.get("isFinal"):
                            received_final_chunk = True
                            break
                    except websockets.exceptions.ConnectionClosed as e:
                        print("Connection closed because of ", e)
                        break
                


            listen_task = asyncio.create_task(listen())
            text_to_gen = ""
            async for chunk in response:
                text_content = chunk.choices[0].delta.content
                await websocket.send_json({"type": "text", "content": text_content})
                if text_content:
                    text_to_gen += text_content
                    # print(text_to_gen, " text to gen ")
                    if len(text_to_gen) > 20:
                        await tts_websocket.send(json.dumps({"text": text_to_gen}))
                        text_to_gen = ""
            # any left over audio
            if len(text_to_gen):
                await tts_websocket.send(json.dumps({"text": text_to_gen}))
                text_to_gen = ""

            await tts_websocket.send(json.dumps({"text": " ", "flush": True}))
            await listen_task

    await process_text()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
