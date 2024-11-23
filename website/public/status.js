// Constants
const API_ENDPOINT = '/statusapi';
const OFFLINE_SHARD = {
  id: 0,
  status: 'offline',
  uptime: '0',
  users: 'ALL',
  servers: 'ALL'
};

// State management
class ShardManager {
  constructor() {
    this.shards = [];
    this.gridElement = document.getElementById('shardGrid');
  }

  async initialize() {
    try {
      const response = await fetch(API_ENDPOINT);
      const data = await response.json();
      
      this.shards = this.processShardData(data);
      this.render();
    } catch (error) {
      console.error('Failed to fetch shard data:', error);
      this.handleError();
    }
  }

  processShardData(data) {
    if (data === 'OFFLINE') {
      return [OFFLINE_SHARD];
    }

    return data.flatMap(shardGroup => 
      shardGroup.map(shard => ({
        id: shard.shard,
        status: 'online',
        uptime: shard.uptime,
        users: shard.users,
        servers: shard.servers
      }))
    );
  }

  createShardElement(shard) {
    const shardSquare = document.createElement('div');
    shardSquare.classList.add('shard-square');

    shardSquare.innerHTML = `
      <div class="status-indicator status-${shard.status}"></div>
      <div class="shard-header">Shard ${shard.id}</div>
      <div class="shard-info">
        <p><strong>Uptime:</strong> ${shard.uptime}</p>
        <p><strong>Users:</strong> ${shard.users}</p>
        <p><strong>Servers:</strong> ${shard.servers}</p>
      </div>
    `;

    return shardSquare;
  }

  render() {
    if (!this.gridElement) return;
    
    this.gridElement.innerHTML = '';
    const sortedShards = [...this.shards].sort((a, b) => a.id - b.id);
    
    const fragment = document.createDocumentFragment();
    sortedShards.forEach(shard => {
      fragment.appendChild(this.createShardElement(shard));
    });
    
    this.gridElement.appendChild(fragment);
  }

  handleError() {
    if (this.gridElement) {
      this.gridElement.innerHTML = `
        <div class="error-message">
          Failed to load shard status. Please try again later.
        </div>
      `;
    }
  }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
  const manager = new ShardManager();
  manager.initialize();
});
