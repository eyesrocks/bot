const categoriesContainer = document.getElementById('categoriesContainer');
const commandsGrid = document.getElementById('commandsGrid');
const toastContainer = document.getElementById('toastContainer');
const leftArrow = document.querySelector('.scroll-arrow-container.left');
const rightArrow = document.querySelector('.scroll-arrow-container.right');

let activeCategory = 'All';
let isDragging = false;
let startX, scrollLeft;

categoriesContainer.addEventListener('mousedown', (e) => {
  isDragging = false;
  startX = e.pageX - categoriesContainer.offsetLeft;
  scrollLeft = categoriesContainer.scrollLeft;
  categoriesContainer.classList.add('dragging');
});

categoriesContainer.addEventListener('mousemove', (e) => {
  if (typeof startX !== 'number') return;
  const x = e.pageX - categoriesContainer.offsetLeft;
  const walk = x - startX;
  if (Math.abs(walk) > 5) isDragging = true;
  categoriesContainer.scrollLeft = scrollLeft - walk;
});

categoriesContainer.addEventListener('mouseup', () => {
  startX = null;
  categoriesContainer.classList.remove('dragging');
});

categoriesContainer.addEventListener('mouseleave', () => {
  startX = null;
  categoriesContainer.classList.remove('dragging');
});

categoriesContainer.addEventListener('click', (e) => {
  if (isDragging) {
    e.preventDefault();
    isDragging = false;
  }
});

function updateArrowVisibility() {
  if (categoriesContainer.scrollLeft <= 0) {
    leftArrow.classList.add('hidden');
  } else {
    leftArrow.classList.remove('hidden');
  }

  if (
    categoriesContainer.scrollWidth - categoriesContainer.clientWidth ===
    Math.round(categoriesContainer.scrollLeft)
  ) {
    rightArrow.classList.add('hidden');
  } else {
    rightArrow.classList.remove('hidden');
  }
}

categoriesContainer.addEventListener('scroll', updateArrowVisibility);


function scrollCategories(amount) {
  categoriesContainer.scrollBy({
    left: amount,
    behavior: 'smooth',
  });
}

async function fetchCommands() {
  try {
    const response = await fetch('/commands.json');
    const commandsData = await response.json();
    renderCategories(commandsData);
    renderCommands(commandsData);
  } catch (error) {
    console.error('Error fetching commands:', error);
  }
}

function renderCategories(commandsData) {
  const allCategories = Object.keys(commandsData);
  categoriesContainer.innerHTML = '';
  const categories = ['All', ...allCategories];
  categories.forEach((category) => {
    const categoryElement = document.createElement('div');
    categoryElement.className = `category${category === 'All' ? ' active' : ''}`;
    categoryElement.textContent = `${category} ${
      category === 'All' ? countCommands(commandsData) : commandsData[category].length
    }`;
    categoryElement.onclick = () => {
      if (!isDragging) filterCategory(category, commandsData);
    };
    categoriesContainer.appendChild(categoryElement);
  });
}

function renderCommands(commandsData, searchText = '') {
  commandsGrid.innerHTML = '';
  Object.entries(commandsData).forEach(([category, commands]) => {
    if (activeCategory === 'All' || activeCategory === category) {
      commands
        .filter((cmd) => cmd.name.toLowerCase().includes(searchText.toLowerCase()))
        .forEach((command) => {
          const commandCard = document.createElement('div');
          commandCard.className = 'command-card';
          commandCard.innerHTML = `
            <div class="card-content">
              <div class="card-header" style="display: flex; justify-content: space-between; align-items: center;">
                <p class="card-title">${command.name}</p>
                <button class="copy-button" title="Copy Command" onclick="copyToClipboard('${command.name}')">
                  <i class="fas fa-copy"></i>
                </button>
              </div>
              <p class="card-description">${command.brief || 'No description available.'}</p>
              <hr class="divider">
              <div class="card-details">
                <div class="detail-item">
                  <p class="detail-title">Example</p>
                  <p class="tag">${command.example || 'N/A'}</p>
                </div>
                <div class="detail-item">
                  <p class="detail-title">Aliases</p>
                  <p class="tag">${command.aliases?.length ? command.aliases.join(', ') : 'None'}</p>
                </div>
                <div class="detail-item">
                  <p class="detail-title">Permissions</p>
                  <p class="tag">${command.permissions || 'None required'}</p>
                </div>
              </div>
            </div>
          `;
          commandsGrid.appendChild(commandCard);
        });
    }
  });
}

function filterCategory(category, commandsData) {
  activeCategory = category;
  document.querySelectorAll('.category').forEach((el) => el.classList.remove('active'));
  Array.from(categoriesContainer.children)
    .find((el) => el.textContent.includes(category))
    .classList.add('active');
  renderCommands(commandsData);
}

function countCommands(data) {
  return Object.values(data).reduce((sum, commands) => sum + commands.length, 0);
}

function copyToClipboard(text) {
  if (!navigator.clipboard || !navigator.clipboard.writeText) {
    console.error('Clipboard API is not supported in this browser.');
    showToast('Failed to copy: Clipboard not supported');
    return;
  }

  navigator.clipboard.writeText(text)
    .then(() => showToast(`Copied "${text}" to clipboard!`))
    .catch(err => console.error('Failed to copy:', err));
}

function showToast(message) {
  const toast = document.createElement('div');
  toast.className = 'toast';
  toast.textContent = message;
  toastContainer.appendChild(toast);
  setTimeout(() => toast.remove(), 3000);
}



fetchCommands();
updateArrowVisibility();