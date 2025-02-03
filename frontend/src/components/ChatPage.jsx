import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";

function ChatPage() {
    const [inputMessage, setInputMessage] = useState('');
    const [messages, setMessages] = useState([]);
    const [loading, setLoading] = useState(false);
  
    const handleSubmit = async (e) => {
      e.preventDefault();
      if (!inputMessage.trim() || loading) return;
  
      setLoading(true);
      try {
        const res = await fetch('http://localhost:5000/api/ask', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ 
            question: inputMessage,
            history: messages.filter(m => m.type === 'user').map(m => m.content) 
          }),
        });
        
        const data = await res.json();
        if (!res.ok) throw new Error(data.error);
        console.log(data.result);
        setMessages(prev => [
          ...prev,
          {
            type: 'user',
            content: inputMessage,
          },
          {
            type: 'system',
            sql: data.sql_query,
            result: data.result,
          }
        ]);
        setInputMessage('');
      } catch (err) {
        alert(err.message || 'Error processing question');
      } finally {
        setLoading(false);
      }
    };
  
    return (
      <div className="chat-container">
        <div className="chat-header">
          <h1>Database Chat Analyzer</h1>
          <Link to="/" className="upload-new-button">Upload New Database</Link>
        </div>
  
        <div className="chat-messages">
          {messages.map((message, index) => (
            <div key={index} className={`message ${message.type}`}>
              {message.type === 'user' ? (
                <div className="user-message">
                  <div className="message-bubble">{message.content}</div>
                </div>
              ) : (
                <div className="system-response">
                  <div className="sql-section">
                    <h4>Generated SQL: </h4>
                    <pre>{message.sql}</pre>
                  </div>
                  <div className="result-section">
                    <h4>Result: </h4>
                        <div className="result-table-container">
                        {message.result.columns && message.result.columns.length > 0 ? (
                            <table className="result-table">
                                <thead>
                                <tr>
                                    {message.result.columns.map((col, i) => (
                                    <th key={i}>{col}</th>
                                    ))}
                                </tr>
                                </thead>
                                <tbody>
                                {message.result.data.map((row, i) => (
                                    <tr key={i}>
                                    {message.result.columns.map((col, j) => (
                                        <td key={j}>
                                        {typeof row[col] === 'object' 
                                            ? JSON.stringify(row[col]) 
                                            : row[col] || 'N/A'}
                                        </td>
                                    ))}
                                    </tr>
                                ))}
                                </tbody>
                            </table>
                            ) : (
                            <div className="no-columns-warning">
                                No column information available
                            </div>
                        )}
                        </div>
                    </div>
                </div>
              )}
            </div>
          ))}
        </div>
  
        <form onSubmit={handleSubmit} className="chat-input">
          <input
            value={inputMessage}
            onChange={(e) => setInputMessage(e.target.value)}
            placeholder="Ask your question about the data..."
            disabled={loading}
          />
          <button type="submit" disabled={loading}>
            {loading ? 'Sending...' : 'Send'}
          </button>
        </form>
      </div>
    );
  }

export default ChatPage;