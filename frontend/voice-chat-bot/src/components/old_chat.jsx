import React, { useState } from 'react';
import axios from 'axios';

const Chat = () => {
  const [messages, setMessages] = useState([]);
  const [userInput, setUserInput] = useState('');
  // const [audioSrc, setAudioSrc] = useState('');

  const sendMessage = async () => {
    const newMessage = { role: 'user', content: userInput };
    setMessages([...messages, newMessage]);
    setUserInput('');

    try {
      const response = await axios.post('http://localhost:5000/post-query', { newMessage });
      let responseData;

      // this handles the response from openAI

      try {
        // console.log(response.data, " is the response");
        // responseData = response.data.response;





      } catch (error) {
        console.log(error, " error");
        responseData = response.data.response; // Treat it as plain text
      }

      // TO handle to respond with the stream? of audio.
      // let ttsData = { content: responseData };
      // const tts_file_name = await axios.post('http://localhost:5000/generate-speech', { ttsData });
      // console.log(tts_file_name, " is audio filename");
      // THen after, also the timings for highlighting the text.


      if (Array.isArray(responseData)) {
        responseData.forEach((article, index) => {
          const sentence = `Title: ${article.title}, Author: ${article.author}`;
          const botResponse = { role: 'system', content: sentence };
          setTimeout(() => {
            setMessages(prevMessages => [...prevMessages, botResponse]);
          }, index * 1000); // Delay each sentence by 1 second
        });
      } else {
        const botResponse = { role: 'system', content: responseData };
        setMessages(prevMessages => [...prevMessages, botResponse]);
      }
    } catch (error) {
      console.error('Error sending message:', error);
      const errorMessage = { role: 'system', content: 'An error occurred while processing your request.' };
      setMessages(prevMessages => [...prevMessages, errorMessage]);
    }
  };
  
  
  
  return (
    <div className="chat-container">
      <div className="chat-messages">
        {messages.map((message, index) => (
          <div key={index} className={message.role}>
            {message.content}
          </div>
        ))}
      </div>
      <div className="input-container">
        <input
          type="text"
          value={userInput}
          onChange={(e) => setUserInput(e.target.value)}
          placeholder="Type a message..."
        />
        <button onClick={sendMessage}>Send</button>
      </div>
    </div>
  );
};

export default Chat;
