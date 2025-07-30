import React, { useEffect, useState } from 'react';

function App() {
  const [messages, setMessages] = useState([]);

  useEffect(() => {
    // Connect to WebSocket running on FastAPI backend
    const ws = new WebSocket("ws://localhost:8000/avalon");

    ws.onmessage = (event) => {
      // Parse the message as JSON
      const newMessage = JSON.parse(event.data);
      // Add the new parsed message to the list of messages
      setMessages((prevMessages) => [...prevMessages, newMessage]);
    };

    ws.onclose = () => {
      console.log("WebSocket connection closed");
    };

    return () => {
      ws.close();
    };
  }, []);

  return (
    <div>
      <h2>Messages from Backend:</h2>
      <ul>
        {messages.map((msg, index) => (
          <li key={index}>
            {msg.sender} to {msg.recipient}: {msg.content} (Turn: {msg.turn}, Timestamp: {msg.timestamp})
          </li>
        ))}
      </ul>
    </div>
  );
}

export default App;
