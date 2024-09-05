import React, { useEffect, useState, useRef } from 'react';

function urlsafeBase64Decode(str) {
    try {
        str = str.replace(/-/g, '+').replace(/_/g, '/');
        while (str.length % 4) {
            str += '=';
        }
        return atob(str);
    } catch(e) {
        console.log(e);
        console.log(str);
        return null;
    }
}

function base64ToUint8Array(base64) {
    const binaryString = urlsafeBase64Decode(base64);
    const len = binaryString.length;
    const bytes = new Uint8Array(len);
    for (let i = 0; i < len; i++) {
        bytes[i] = binaryString.charCodeAt(i);
    }
    return bytes;
}

const Chat = () => {
    const [messages, setMessages] = useState([]);
    const [input, setInput] = useState('');
    const audioRef = useRef(null);
    const mediaSourceRef = useRef(null);
    const sourceBufferRef = useRef(null);
    const websocketRef = useRef(null);
    const audioQueueRef = useRef([]);
    const isPlayingRef = useRef(false);

    useEffect(() => {
        websocketRef.current = new WebSocket('ws://localhost:8000/ws');

        websocketRef.current.onmessage = async (event) => {
            const data = JSON.parse(event.data);
            if (data.type === 'text') {
                console.log("got some text back ", data.content);
                setMessages((prevMessages) => [...prevMessages, { role: 'bot', type: 'text', content: data.content }]);

            } else if (data.type === 'audio') {
                try {
                    const audioData = base64ToUint8Array(data.content);
                    audioQueueRef.current.push(audioData);
                    if (sourceBufferRef.current && !sourceBufferRef.current.updating) {
                        appendNextAudioChunk();
                    }
                } catch(e) {
                    console.log(data);
                    console.log(e);
                }
            }
        };

        mediaSourceRef.current = new MediaSource();
        audioRef.current.src = URL.createObjectURL(mediaSourceRef.current);

        mediaSourceRef.current.addEventListener('sourceopen', () => {
            sourceBufferRef.current = mediaSourceRef.current.addSourceBuffer('audio/mpeg');
            sourceBufferRef.current.addEventListener('updateend', appendNextAudioChunk);
        });

        return () => {
            if (websocketRef.current) {
                websocketRef.current.close();
            }
        };
    }, []);

    const appendNextAudioChunk = () => {
        if (audioQueueRef.current.length > 0 && sourceBufferRef.current && !sourceBufferRef.current.updating) {
            const chunk = audioQueueRef.current.shift();
            sourceBufferRef.current.appendBuffer(chunk);

            if (!isPlayingRef.current) {
                audioRef.current.play().then(() => {
                    isPlayingRef.current = true;
                }).catch(error => {
                    console.error("Error playing audio:", error);
                });
            }
        }
    };

    const sendMessage = () => {
        if (websocketRef.current && websocketRef.current.readyState === WebSocket.OPEN) {
            setMessages([...messages, { role: 'user', type: 'text', content: input }]);
            websocketRef.current.send(input);
            setInput('');
        } else {
            console.error('WebSocket is not open');
        }
    };

    return (
        <div className="chat-container">
          <div className="chat-messages">
              {messages.map((message, index) => (
                  <div key={index} className={message.role} style={{ color: getColor(message.role) }}>
                      {message.content}
                  </div>
              ))}
          </div>
            <div className="input-container">
                <input
                    type="text"
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    placeholder="Type a message..."
                />
                <button onClick={sendMessage}>Send</button>
            </div>
            <audio ref={audioRef} />
        </div>
    );
};

const getColor = (role) => {
  switch (role) {
      case 'user':
          return 'blue'; // User messages in blue
      case 'bot':
          return 'green'; // System messages in green
      default:
          return 'black'; // Default color
  }
};

export default Chat;