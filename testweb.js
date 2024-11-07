const http = require('http');
const fs = require('fs');
const path = require('path');

const hostname = 'localhost';
const port = 3008;

const server = http.createServer((req, res) => {
  // Construct the file path
  let filePath = path.join(__dirname+"/website", req.url === '/' ? '/root/greed/website/public/index.html' : req.url);

  // Get the file extension
  const extname = String(path.extname(filePath)).toLowerCase();

  // Set the content type based on the file extension
  const mimeTypes = {
    '.html': 'text/html',
    '.js': 'application/javascript',
    '.css': 'text/css',
    '.json': 'application/json',
    '.png': 'image/png',
    '.jpg': 'image/jpg',
    '.gif': 'image/gif',
    '.svg': 'image/svg+xml',
    '.wav': 'audio/wav',
    '.mp4': 'video/mp4',
    '.woff': 'application/font-woff',
    '.ttf': 'application/font-ttf',
    '.eot': 'application/vnd.ms-fontobject',
    '.otf': 'application/font-otf',
    '.wasm': 'application/wasm'
  };

  const contentType = mimeTypes[extname] || 'application/octet-stream';

  // Read the requested file
  fs.readFile(filePath, (error, content) => {
    if (error) {
      if (error.code === 'ENOENT') {
        // File not found, return 404
        res.writeHead(404, { 'Content-Type': 'text/html' });
        res.end('<h1>404 Not Found</h1>', 'utf-8');
      } else {
        // Some server error
        res.writeHead(500);
        res.end(`Sorry, there was an error: ${error.code}`);
      }
    } else {
      // Serve the file
      res.writeHead(200, { 'Content-Type': contentType });
      res.end(content, 'utf-8');
    }
  });
});

server.listen(port, hostname, () => {
  console.log(`Server running at http://${hostname}:${port}/`);
});
