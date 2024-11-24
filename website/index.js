const express = require('express');
const path = require('path'); // Import 'path' to work with file paths
const app = express();
const fetch = (...args) => import('node-fetch').then(({default: fetch}) => fetch(...args));

// Serve static files without needing .html extensions
app.use(express.static('public'));

// Route to serve clean URLs for static .html files
app.get('/:page', (req, res) => {
  const page = req.params.page;
  const filePath = path.join(__dirname, 'public', `${page}.html`);
  res.sendFile(filePath, (err) => {
    if (err) {
      res.status(404).send('Page not found');
    }
  });
});

app.get('/statusapi', async (req, res) => {
  const urls = [
    'http://localhost:8493/status',
    'http://localhost:8494/status',
    'http://localhost:8495/status'
  ];

  try {
    const responses = await Promise.all(urls.map(url => fetch(url).then(res => res.json())));
    res.json(responses);
  } catch (error) {
    res.json("OFFLINE");
  }
});

app.listen(3008, () => {
  console.log('Server running at http://localhost:3008/');
});
