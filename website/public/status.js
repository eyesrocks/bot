// Array of shard data
const shards = [

];

// Function to create a shard box element
function createShardBox(shard) {
  const shardBox = document.createElement('div');
  shardBox.classList.add('status-box');

  // Create the shard header with online/offline indicator
  const header = document.createElement('div');
  header.classList.add('status-header');

  const indicator = document.createElement('span');
  indicator.classList.add('status-indicator');
  if (shard.online) indicator.classList.add('online');

  const shardId = document.createElement('span');
  shardId.classList.add('shard-id');
  shardId.textContent = `Shard ID: ${shard.id}`;

  header.appendChild(indicator);
  header.appendChild(shardId);

  // Create content for uptime, users, and servers
  const uptime = document.createElement('p');
  uptime.innerHTML = `Uptime: <span class="uptime">${shard.uptime}</span>`;

  const users = document.createElement('p');
  users.innerHTML = `Users: <span class="users">${shard.users}</span>`;

  const servers = document.createElement('p');
  servers.innerHTML = `Servers: <span class="servers">${shard.servers}</span>`;

  // Append all elements to the shard box
  shardBox.appendChild(header);
  shardBox.appendChild(uptime);
  shardBox.appendChild(users);
  shardBox.appendChild(servers);

  return shardBox;
}

function setupShards(){
  fetch('/statusapi')
    .then(response => response.json())
    .then(data => {
      if (data === 'OFFLINE') {
        document.getElementById('status-container').innerHTML = 'All shards are offline.';
        return;
      }
      data.forEach(shardsp => {
        console.log(shardsp);
        for (let i = 0; i < shardsp.length; i++) {
          shards.push({
            id: shardsp[i].shard,
            status: "online",
            uptime: shardsp[i].uptime,
            users: shardsp[i].users,
            servers: shardsp[i].servers
          });
        }
      });
      console.log(shards);
      renderShards(shards);
    });
}

function renderShards(shardData) {
  const shardGrid = document.getElementById('shardGrid');
  shardGrid.innerHTML = ''; // Clear existing shards

  // Sort shards by shard_id in ascending order
  const sortedShards = shardData.sort((a, b) => a.id - b.id);

  sortedShards.forEach(shard => {
    const shardSquare = document.createElement('div');
    shardSquare.classList.add('shard-square');

    // Status indicator
    const statusIndicator = document.createElement('div');
    statusIndicator.classList.add('status-indicator');
    statusIndicator.classList.add(shard.status === 'online' ? 'status-online' : 'status-offline');
    shardSquare.appendChild(statusIndicator);

    // Shard header
    const shardHeader = document.createElement('div');
    shardHeader.classList.add('shard-header');
    shardHeader.textContent = `Shard ${shard.id}`;
    shardSquare.appendChild(shardHeader);

    // Shard info
    const shardInfo = document.createElement('div');
    shardInfo.classList.add('shard-info');
    shardInfo.innerHTML = `
      <p><strong>Uptime:</strong> ${shard.uptime}</p>
      <p><strong>Users:</strong> ${shard.users}</p>
      <p><strong>Servers:</strong> ${shard.servers}</p>
    `;
    shardSquare.appendChild(shardInfo);

    shardGrid.appendChild(shardSquare);
  });
}

// Call the function to render shards on page load
setupShards();

