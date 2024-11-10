window.addEventListener("load", function() {
    const loader = document.getElementById("loader");
    loader.classList.add("hidden");
    // Get categories from commands.json and then create category cards
    fetch("/commands.json").then(response => response.json()).then(data => {
      console.log(data)
      for(const category in data){
        const categoryCard = document.createElement("div");
        categoryCard.classList.add("category");
        categoryCard.textContent = category;
        categoryCard.addEventListener("click", showCommands);
        document.getElementById("commandCategories").appendChild(categoryCard);
        const commands = data[category];
        commands.forEach(command => {
          const commandCard = document.createElement("div");
          commandCard.classList.add("command-card");
          if(command.example == null){
            commandCard.innerHTML = `
            <div class="command-title">${command.name}</div>
            <div class="command-description">${command.brief}</div>
            <div class="details">
            <span>Category: ${category}</span>
            </div>
          `;
          }else{
            commandCard.innerHTML = `
            <div class="command-title">${command.name}</div>
            <div class="command-description">${command.brief}</div>
            <div class="details">
            <span class="usage">Usage: ${command.example}</span>
            <span>Category: ${category}</span>
            </div>
          `;
          }
          
          document.getElementById("commandCards").appendChild(commandCard);
      })
    }
  });
  });

  function filterCommands() {
    const input = document.querySelector(".search-bar input").value.toLowerCase();
    const cards = document.querySelectorAll(".command-card");

    cards.forEach(card => {
      const title = card.querySelector(".command-title").textContent.toLowerCase();
      if (title.includes(input)) {
        card.style.display = "block";
      } else {
        card.style.display = "none";
      }
    });
  }

  function scrollCategories(value) {
    const categories = document.getElementById("commandCategories");
    categories.scrollLeft += value;
  }

  function showCommands(category) {
    const cards = document.querySelectorAll(".command-card");
    cards.forEach(card => {
      if (card.querySelector(".details span:last-child").textContent.includes(category.target.textContent)) {
        card.style.display = "block";
      } else {
        card.style.display = "none";
      }
    });
  }