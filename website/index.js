const express = require('express');
const path = require('path');
const app = express();
const fetch = (...args) => import('node-fetch').then(({default: fetch}) => fetch(...args));
const cors = require('cors');

// Configuration constants
const CONFIG = {
  PORT: process.env.PORT || 3008,
  STATUS_ENDPOINTS: [
    'http://localhost:2027/status',
  ],
  ALLOWED_EXTENSIONS: ['.gif', '.png', '.json', '.js', '.ico', '.cur'],
  TIMEOUT_MS: 5000
};

app.use(cors());

// Status check helper function
const checkEndpointStatus = async (url) => {
  try {
    const response = await fetch(url, {
      timeout: CONFIG.TIMEOUT_MS,
      headers: {
        'Accept': 'application/json'
      }
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }
    
    return await response.json();
  } catch (err) {
    console.error(`Error fetching ${url}:`, err.message);
    return null;
  }
};

app.get('/statusapi', async (_, res) => {
  try {
    const responses = await Promise.all(
      CONFIG.STATUS_ENDPOINTS.map(checkEndpointStatus)
    );

    const validResponses = responses.filter(Boolean);
    res.json(validResponses.length ? validResponses : "OFFLINE");
  } catch (error) {
    console.error('Fatal error in /statusapi:', error);
    res.status(500).json("OFFLINE");
  }
});

// File serving helper function
const serveFile = (filePath, res) => {
  res.sendFile(filePath, (err) => {
    if (err) {
      console.error(`Error serving file: ${filePath}`, err);
      res.status(404).send('File not found');
    }
  });
};

// Handle both root and page routes
app.get('/', (_, res) => {
  console.log('Root page accessed');
  serveFile(path.join(__dirname, 'public', 'index.html'), res);
});

app.use(express.static('public'));

app.get('/:page', (req, res) => {
  const page = req.params.page;
  const ext = path.extname(page).toLowerCase();
  const filePath = path.join(__dirname, 'public', page);
  
  if (CONFIG.ALLOWED_EXTENSIONS.includes(ext)) {
    console.log(`Static file requested: ${page}`);
    serveFile(filePath, res);
  } else if (ext) {
    console.error(`Unsupported file type: ${page}`);
    res.status(404).send('File type not supported');
  } else {
    console.log(`Page requested: ${page}`);
    serveFile(path.join(__dirname, 'public', `${page}.html`), res);
  }
});

app.listen(CONFIG.PORT, () => {
  console.log(`Server running at http://localhost:${CONFIG.PORT}/`);
});
