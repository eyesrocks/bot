const express = require('express');
const path = require('path');
const app = express();
const fetch = (...args) => import('node-fetch').then(({default: fetch}) => fetch(...args));
const cors = require('cors');

app.use(cors());

app.get('/statusapi', async (req, res) => {
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
app.get('/', (req, res) => {
  res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

app.get('/:page', (req, res) => {
  const page = req.params.page;
  const filePath = path.join(__dirname, 'public', `${page}.html`);
  res.sendFile(filePath, (err) => {
    if (err) {
      res.status(404).send('Page not found');
    }
  });
});

// Move static middleware after routes
app.use(express.static('public', {
  extensions: ['html']
}));

app.listen(3008, () => {
  console.log('Server running at http://localhost:3008/');
});
