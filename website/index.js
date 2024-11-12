const express = require('express');
const app = express();
const fetch = (...args) => import('node-fetch').then(({default: fetch}) => fetch(...args));

app.use(express.static('public'));

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
