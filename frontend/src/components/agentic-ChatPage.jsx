import React, { useState, useEffect, useRef } from "react";
import { Link } from "react-router-dom";
import Markdown from 'markdown-parser-react';
import ReactMarkdown from 'react-markdown';

function ChatPage() {
  const [inputMessage, setInputMessage] = useState('');
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);
  const thinkingIntervalRef = useRef(null);
  const messageEndRef = useRef(null);

  // Scroll to bottom when messages change
  useEffect(() => {
    messageEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  // Prepare conversation history (exclude thinking messages)
  const getConversationHistory = () => {
    return messages
      .filter((m) => m.type === "user" || m.type === "system")
      .map((m) => ({
        role: m.type === "user" ? "user" : "assistant",
        // For system messages, send the final SQL (not the hidden chain‐of‐thought)
        content: m.sql ? m.sql : m.content 
      }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!inputMessage.trim() || loading) return;

    setLoading(true);
    // Append the new user message
    const newUserMessage = { 
      type: 'user', 
      content: inputMessage,
      id: Date.now()
    };
    setMessages(prev => [...prev, newUserMessage]);
    setInputMessage('');

    try {
      // Start a simple "thinking" animation (only shows a generic message)
      let thinkingStep = 0;
      thinkingIntervalRef.current = setInterval(() => {
        thinkingStep = (thinkingStep % 3) + 1;
        setMessages(prev => {
          // Remove any previous thinking message
          const filtered = prev.filter(m => m.type !== 'thinking');
          return [
            ...filtered,
            { type: 'thinking', content: `Analyzing${'.'.repeat(thinkingStep)}`, id: Date.now() }
          ];
        });
      }, 500);

      const res = await fetch('http://localhost:5000/api/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          question: inputMessage,
          history: getConversationHistory()
        }),
      });

      const data = await res.json();
      if (!res.ok) throw new Error(data.error);

      // Final answer received: remove thinking messages.
      clearInterval(thinkingIntervalRef.current);
      setMessages(prev => prev.filter(m => m.type !== 'thinking'));

      // Create a system message that includes:
      // - Generated SQL (to be rendered as Markdown)
      // - Query result (if any)
      // - Explanation (Markdown)
      // - Intermediate reasoning details (hidden by default; toggled via button)
      const newSystemMessage = {
        type: 'system',
        id: Date.now(),
        sql: data.sql_query,
        result: data.result,
        explanation: data.explanation,
        // Hide the detailed chain-of-thought by default.
        reasoning: data.reasoning || [],
        showDetails: false 
      };

      setMessages(prev => [...prev, newSystemMessage]);
    } catch (err) {
      clearInterval(thinkingIntervalRef.current);
      setMessages(prev => [
        ...prev.filter(m => m.type !== 'thinking'),
        { type: 'system', content: `Error: ${err.message}`, id: Date.now() }
      ]);
    } finally {
      setLoading(false);
    }
  };

  // Toggle the display of the intermediate reasoning (chain-of-thought)
  const toggleDetails = (messageId) => {
    setMessages(prev => prev.map(msg => 
      msg.id === messageId 
        ? { ...msg, showDetails: !msg.showDetails } 
        : msg
    ));
  };

  return (
    <div className="chat-container">
      <div className="chat-header">
        <h1>Database Chat Analyzer</h1>
        <Link to="/" className="upload-new-button">Upload New Database</Link>
      </div>

      <div className="chat-messages">
        {messages.map((message) => (
          <div key={message.id} className={`message ${message.type}`}>
            {message.type === 'user' ? (
              <div className="user-message">
                <div className="message-bubble">{message.content}</div>
              </div>
            ) : message.type === 'thinking' ? (
              <div className="system-thinking">
                <div className="message-bubble">{message.content}</div>
              </div>
            ) : message.type === 'system' && message.sql ? (
              <div className="system-response">
                <div className="sql-section">
                  <h4>Generated SQL:</h4>
                  <pre className="generated-sql">{message.sql}</pre>
                </div>

                <div className="result-section">
                  <h4>Result:</h4>
                  <div className="result-table-container">
                    {message.result?.columns?.length > 0 ? (
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
                      <div className="no-results">No results found</div>
                    )}
                  </div>
                </div>

                {message.explanation && (
                  <div className="explanation-section">
                    <h3>Explanation:</h3>
                    <ReactMarkdown>{message.explanation}</ReactMarkdown>
                  </div>
                )}

                {message.reasoning.length > 0 && (
                  <div className="reasoning-section">
                    <button
                      className="toggle-details-btn"
                      onClick={() => toggleDetails(message.id)}
                    >
                      {message.showDetails 
                        ? "Hide Thinking Process ᐯ" 
                        : "Show Thinking Process >"}
                    </button>
                    {(message.showDetails && message.reasoning.length > 0) && (
                      <div className="reasoning-output">
                        <h4>Thinking Process:</h4>
                        <Markdown content = {message.reasoning.join("\n")} />
                      </div>
                    )}
                  </div>
                )}
              </div>
            ) : (
              <div className="system-response">
                <div className="message-bubble">{message.content}</div>
              </div>
            )}
          </div>
        ))}
        <div ref={messageEndRef} />
      </div>

      <form onSubmit={handleSubmit} className="chat-input">
        <input
          value={inputMessage}
          onChange={(e) => setInputMessage(e.target.value)}
          placeholder="Ask your question about the data..."
          disabled={loading}
        />
        <button type="submit" disabled={loading}>
          {loading ? 'Processing...' : 'Send'}
        </button>
      </form>
    </div>
  );
}

export default ChatPage;
