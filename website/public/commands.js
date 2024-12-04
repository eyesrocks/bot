function hideLoader() {
    const loader = document.getElementById('loader');
    loader.classList.add('loader-hidden');
    setTimeout(() => {
        loader.style.display = 'none';
    }, 500);
}

class CommandManager {
    constructor() {
        this.commands = {};
        this.activeCategory = 'All';
        this.setupEventListeners();
    }

    async initialize() {
        try {
            const response = await fetch("/commands.json");
            this.commands = await response.json();
            this.hideLoader();
            this.renderCategories();
            this.renderCommands();
        } catch (error) {
            this.handleError(error);
        }
    }

    hideLoader() {
        document.getElementById("loader").classList.add("hidden");
    }

    handleError(error) {
        console.error('Error loading commands:', error);
        this.hideLoader();
        document.getElementById("commandCards").innerHTML = 
            '<div class="error-message">Failed to load commands. Please try again later.</div>';
    }

    renderCategories() {
        const categoriesContainer = document.getElementById("commandCategories");
        categoriesContainer.innerHTML = '<div class="category active" data-category="All">All</div>';
        
        Object.keys(this.commands).forEach(category => {
            const categoryElement = document.createElement("div");
            categoryElement.classList.add("category");
            categoryElement.dataset.category = category;
            categoryElement.textContent = category;
            categoriesContainer.appendChild(categoryElement);
        });
    }

    renderCommands(filterText = '', category = 'All') {
        const commandCards = document.getElementById("commandCards");
        commandCards.innerHTML = '';

        Object.entries(this.commands).forEach(([cat, commands]) => {
            if (category === 'All' || category === cat) {
                commands.forEach(command => {
                    if (command.name.toLowerCase().includes(filterText.toLowerCase())) {
                        commandCards.appendChild(this.createCommandCard(command, cat));
                    }
                });
            }
        });
    }

    createCommandCard(command, category) {
        const card = document.createElement("div");
        card.classList.add("command-card");
        card.innerHTML = `
            <div class="command-title">${command.name}</div>
            <div class="command-description">${command.brief}</div>
            <div class="details">
                ${command.example ? `<span class="usage">Usage: ${command.example}</span>` : ""}
                <span>Category: ${category}</span>
            </div>
        `;
        return card;
    }

    setupEventListeners() {
        document.querySelector(".search-bar input").addEventListener("input", (e) => {
            this.filterCommands(e.target.value);
        });

        document.getElementById("commandCategories").addEventListener("click", (e) => {
            if (e.target.classList.contains("category")) {
                this.setActiveCategory(e.target.dataset.category);
            }
        });
    }

    setActiveCategory(category) {
        this.activeCategory = category;
        document.querySelectorAll('.category').forEach(cat => {
            cat.classList.toggle('active', cat.dataset.category === category);
        });
        this.filterCommands(document.querySelector(".search-bar input").value);
    }

    filterCommands(searchText) {
        this.renderCommands(searchText, this.activeCategory);
    }

    scrollCategories(value) {
        const container = document.getElementById("commandCategories");
        container.scrollLeft += value * 100;
    }
}

// Initialize when the DOM is loaded
window.addEventListener("load", () => {
    const commandManager = new CommandManager();
    commandManager.initialize();
    
    // Expose scrollCategories to global scope for HTML button onclick
    window.scrollCategories = (value) => commandManager.scrollCategories(value);
});

document.addEventListener('DOMContentLoaded', () => {
    hideLoader();
});
