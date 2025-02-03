import React, { useState } from 'react';
import { BrowserRouter as Router, Routes, Route, Link, useNavigate } from 'react-router-dom';

function UploadPage() {
    const [file, setFile] = useState(null);
    const navigate = useNavigate();
  
    const handleUpload = async (e) => {
      e.preventDefault();
      const formData = new FormData();
      formData.append('file', file);
  
      try {
        const res = await fetch('http://localhost:5000/api/upload', {
          method: 'POST',
          body: formData,
        });
        const data = await res.json();
        if (res.ok) {
          navigate('/chat');
        }
        alert(data.message || data.error);
      } catch (err) {
        alert('Error uploading file');
      }
    };
  
    return (
      <div className="upload-container">
        <h1>Upload Database</h1>
        <form onSubmit={handleUpload} className="upload-form">
          <div className="file-input">
            <input 
              type="file" 
              onChange={(e) => setFile(e.target.files[0])} 
              accept=".db" 
            />
          </div>
          <button type="submit" className="upload-button">
            Upload & Continue
          </button>
        </form>
      </div>
    );
  }

export default UploadPage;