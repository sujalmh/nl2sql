import React, { useState, useEffect } from 'react';
import { BrowserRouter as Router, Routes, Route, Link, useNavigate } from 'react-router-dom';
import ChatPage from './components/ChatPage';
import UploadPage from './components/UploadPage';
import AgentPage from './components/agentic-ChatPage';
import './App.css';

function App() {
  return (
    <Router>
      <Routes>
        <Route path="/" element={<UploadPage />} />
        <Route path="/chat" element={<ChatPage />} />
        <Route path="/agent" element={<AgentPage />} />
      </Routes>
    </Router>
  );
}

export default App;