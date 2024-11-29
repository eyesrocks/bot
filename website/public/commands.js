window.addEventListener("load", () => {
  const loader = document.getElementById("loader");
  loader.classList.add("hidden");

  fetch("/commands.json")
    .then(response => {
      if (!response.ok) {
        throw new Error("Network response was not ok " + response.statusText);
      }
      return response.json();
    })
    .then(data => {
      console.log(data);
      const commandCategories = document.getElementById("commandCategories");
      const commandCards = document.getElementById("commandCards");

      for (const category in data) {
        const categoryCard = document.createElement("div");
        categoryCard.classList.add("category");
        categoryCard.textContent = category;
        categoryCard.addEventListener("click", showCommands);
        commandCategories.appendChild(categoryCard);

        data[category].forEach(command => {
          const commandCard = document.createElement("div");
          commandCard.classList.add("command-card");
          commandCard.innerHTML = `
            <div class="command-title">${command.name}</div>
            <div class="command-description">${command.brief}</div>
            <div class="details">
              ${command.example ? `<span class="usage">Usage: ${command.example}</span>` : ""}
              <span>Category: ${category}</span>
            </div>
          `;
          commandCards.appendChild(commandCard);
        });
      }
    });
});

function filterCommands() {
  const input = document.querySelector(".search-bar input").value.toLowerCase();
  document.querySelectorAll(".command-card").forEach(card => {
    const title = card.querySelector(".command-title").textContent.toLowerCase();
    card.style.display = title.includes(input) ? "block" : "none";
  });
}

function scrollCategories(value) {
  document.getElementById("commandCategories").scrollLeft += value;
}

function showCommands(event) {
  const category = event.target.textContent;
  document.querySelectorAll(".command-card").forEach(card => {
    const cardCategory = card.querySelector(".details span:last-child").textContent;
    card.style.display = cardCategory.includes(category) ? "block" : "none";
  });
}
