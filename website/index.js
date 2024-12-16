const express = require('express');
const path = require('path');
const app = express();
const fetch = (...args) => import('node-fetch').then(({default: fetch}) => fetch(...args));
const cors = require('cors');

app.use(cors());

app.get('/statusapi', async (_, res) => {
  const urls = [
    'http://localhost:8493/status',
    'http://localhost:8494/status',
    'http://localhost:8495/status'
  ];

  try {
    const responses = await Promise.all(
      urls.map(async (url) => {
        try {
          const response = await fetch(url, {
            timeout: 5000,
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
      })
    );

    const validResponses = responses.filter(r => r !== null);
    res.json(validResponses.length ? validResponses : "OFFLINE");
  } catch (error) {
    console.error('Fatal error in /statusapi:', error);
    res.status(500).json("OFFLINE");
  }
});

// Handle both root and page routes
app.get('/', (_, res) => {
  console.log('Root page accessed');
  res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

app.use(express.static('public'));

app.get('/:page', (req, res) => {
  const page = req.params.page;
  const ext = path.extname(page).toLowerCase();
  
  // List of allowed file extensions
  const allowedExts = ['.gif', '.png', '.json', '.js', '.ico', '.cur'];
  
  if (allowedExts.includes(ext)) {
    // If file has an allowed extension, serve it directly
    console.log(`Static file requested: ${page}`);
    res.sendFile(path.join(__dirname, 'public', page), (err) => {
      if (err) {
        console.error(`Error loading file ${page}:`, err);
        res.status(404).send('File not found');
      }
    });
  } else if (ext) {
    // If file has any other extension, return 404
    console.error(`Unsupported file type: ${page}`);
    res.status(404).send('File type not supported');
  } else {
    // If no extension, assume HTML page
    console.log(`Page requested: ${page}`);
    res.sendFile(path.join(__dirname, 'public', `${page}.html`), (err) => {
      if (err) {
        console.error(`Error loading page ${page}:`, err);
        res.status(404).send('Page not found');
      }
    });
  }
});

app.listen(3008, () => {
  console.log('Server running at http://localhost:3008/');
});
