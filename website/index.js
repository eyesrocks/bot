const express = require('express');
const app = express();
const fetch = (...args) => import('node-fetch').then(({default: fetch}) => fetch(...args));
app.use(express.static('public'));
app.get('/statusapi', async(req, res) => {
  resarray = [];
  const response1 = await fetch('http://localhost:8493/status');
  if(response1.status !== 200) {
    res.json("OFFLINE");
    return
  }
  const data1 = await response1.json();
  resarray.push(data1);
  const response2 = await fetch('http://localhost:8494/status');
  const data2 = await response2.json();
  resarray.push(data2);
  const response3 = await fetch('http://localhost:8495/status');
  const data3 = await response3.json();
  resarray.push(data3);
  res.json(resarray);
});
app.listen(3008, () => {
  console.log('Server running at http://localhost:3008/');
});
