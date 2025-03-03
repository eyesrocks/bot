document.addEventListener('DOMContentLoaded', function () {
    const tabs = document.querySelectorAll('.tab-link');
    const tabContents = document.querySelectorAll('.tab-content');

    tabs.forEach(tab => {
        tab.addEventListener('click', () => {
            tabs.forEach(t => t.classList.remove('active'));
            tabContents.forEach(content => content.classList.remove('active'));

            tab.classList.add('active');
            const tabContent = document.getElementById(tab.getAttribute('data-tab'));
            tabContent.classList.add('active');
        });
    });

    const firstTab = document.querySelector('.tab-link');
    if (firstTab) {
        firstTab.classList.add('active');
        document.getElementById(firstTab.getAttribute('data-tab')).classList.add('active');
    }

    fetch('assets/commands.json')
        .then(response => response.json())
        .then(data => {
            const antinukeCategory = data.AntiNuke;
            const voicemasterCategory = data.Voicemaster;

            if (antinukeCategory && Array.isArray(antinukeCategory)) {
                const mainContent = document.getElementById('tab1');
                mainContent.innerHTML = '';

                const navButtons = document.createElement('div');
                navButtons.classList.add('nav-buttons');
                navButtons.innerHTML = `
                    <button id="prev-command" class="nav-btn">Previous</button>
                    <button id="next-command" class="nav-btn">Next</button>
                `;

                let currentCommandIndex = 0;

                const displayCommand = () => {
                    const commandSection = document.createElement('div');
                    commandSection.classList.add('command-section');
                    const command = antinukeCategory[currentCommandIndex];
                    commandSection.innerHTML = `
                        <h3>${command.name}</h3>
                        <p>${command.brief}</p>
                        <pre><code>${command.example}</code></pre>
                    `;
                    mainContent.appendChild(commandSection);
                    mainContent.appendChild(navButtons);
                };

                displayCommand();

                const prevButton = document.getElementById('prev-command');
                const nextButton = document.getElementById('next-command');

                nextButton.addEventListener('click', () => {
                    if (currentCommandIndex < antinukeCategory.length - 1) {
                        currentCommandIndex++;
                        mainContent.innerHTML = '';
                        displayCommand();
                    }
                });

                prevButton.addEventListener('click', () => {
                    if (currentCommandIndex > 0) {
                        currentCommandIndex--;
                        mainContent.innerHTML = '';
                        displayCommand();
                    }
                });
            }

            if (voicemasterCategory && Array.isArray(voicemasterCategory)) {
                const mainContent = document.getElementById('tab2');
                mainContent.innerHTML = '';

                const navButtons = document.createElement('div');
                navButtons.classList.add('nav-buttons');
                navButtons.innerHTML = `
                    <button id="pre-command" class="nav-btn">Previous</button>
                    <button id="nex-command" class="nav-btn">Next</button>
                `;

                let currentCommandIndex = 0;

                const displayCommand = () => {
                    const commandSection = document.createElement('div');
                    commandSection.classList.add('command-section');
                    const command = voicemasterCategory[currentCommandIndex];
                    commandSection.innerHTML = `
                        <h3>${command.name}</h3>
                        <p>${command.brief}</p>
                        <pre><code>${command.example}</code></pre>
                    `;
                    mainContent.appendChild(commandSection);
                    mainContent.appendChild(navButtons);
                };

                displayCommand();

                const prevButton = document.getElementById('pre-command');
                const nextButton = document.getElementById('nex-command');

                nextButton.addEventListener('click', () => {
                    if (currentCommandIndex < voicemasterCategory.length - 1) {
                        currentCommandIndex++;
                        mainContent.innerHTML = '';
                        displayCommand();
                    }
                });

                prevButton.addEventListener('click', () => {
                    if (currentCommandIndex > 0) {
                        currentCommandIndex--;
                        mainContent.innerHTML = '';
                        displayCommand();
                    }
                });
            }
        })
        .catch(error => {
            console.error("Error loading commands.json:", error);
        });

    const lastFMVariables = [
        { variable: "{track}", definition: "Name of the track." },
        { variable: "{artist}", definition: "Name of the artist." },
        { variable: "{user}", definition: "Username of the author." },
        { variable: "{avatar}", definition: "URL of the author's avatar." },
        { variable: "{track.url}", definition: "URL of the track." },
        { variable: "{artist.url}", definition: "URL of the artist." },
        { variable: "{scrobbles}", definition: "Number of scrobbles for the user." },
        { variable: "{track.image}", definition: "Image associated with the track." },
        { variable: "{username}", definition: "Last.FM Username." },
        { variable: "{artist.plays}", definition: "Number of plays for the artist." },
        { variable: "{track.plays}", definition: "Number of plays for the track." },
        { variable: "{track.lower}", definition: "Lowercase name of the track." },
        { variable: "{artist.lower}", definition: "Lowercase name of the artist." },
        { variable: "{track.hyperlink}", definition: "Hyperlink to the track with the track name as the text." },
        { variable: "{track.hyperlink_bold}", definition: "Hyperlink to the track with bold track name as the text." },
        { variable: "{artist.hyperlink}", definition: "Hyperlink to the artist with the artist name as the text." },
        { variable: "{artist.hyperlink_bold}", definition: "Hyperlink to the artist with bold artist name as the text." },
        { variable: "{track.color}", definition: "Dominant color of the track image." },
        { variable: "{artist.color}", definition: "Dominant color of the artist image." },
        { variable: "{date}", definition: "Date the track was played on." },
    ];

    const guildVariables = [
        { variable: "{guild.name}", definition: "Name of the guild." },
        { variable: "{guild.count}", definition: "Number of members in the guild." },
        { variable: "{guild.count.format}", definition: "Formatted number of members in ordinal format." },
        { variable: "{guild.id}", definition: "ID of the guild." },
        { variable: "{guild.created_at}", definition: "Formatted creation date of the guild (relative time)." },
        { variable: "{guild.boost_count}", definition: "Number of boosts the guild has." },
        { variable: "{guild.booster_count}", definition: "Number of boosters in the guild." },
        { variable: "{guild.boost_count.format}", definition: "Formatted number of guild boosts in ordinal format." },
        { variable: "{guild.booster_count.format}", definition: "Formatted number of guild boosters in ordinal format." },
        { variable: "{guild.boost_tier}", definition: "Boost tier level of the guild." },
        { variable: "{guild.icon}", definition: "URL of the guild's icon, if available." },
        { variable: "{guild.vanity}", definition: "Guild's vanity URL, if available." },
    ];

    const userVariables = [
        { variable: "{user}", definition: "Returns a user" },
        { variable: "{user.mention}", definition: "Mention a user" },
        { variable: "{user.name}", definition: "Username of a user." },
        { variable: "{user.joined_at}", definition: "Join date of a user" },
        { variable: "{user.created_at}", definition: "Account creation date of a user" },
    ];

    const generateVariableTable = (variablesArray) => {
        const table = document.createElement("table");
        table.innerHTML = `
            <tr>
                <th>Variable</th>
                <th>Description</th>
            </tr>
        `;

        variablesArray.forEach(variableData => {
            const row = document.createElement("tr");

            const variableCell = document.createElement("td");
            variableCell.textContent = variableData.variable;
            row.appendChild(variableCell);

            const descriptionCell = document.createElement("td");
            descriptionCell.textContent = variableData.definition;
            row.appendChild(descriptionCell);

            table.appendChild(row);
        });

        return table;
    };

    const toggleDropdown = (categoryId, categoryHeaderId) => {
        const table = document.getElementById(categoryId);
        const allTables = document.querySelectorAll('.variable-table');
        const headers = document.querySelectorAll('.variable-box');

        allTables.forEach(t => t.style.display = "none");
        headers.forEach(h => h.classList.remove('expanded'));

        if (table.style.display === "none" || !table.style.display) {
            table.style.display = "table";
            document.getElementById(categoryHeaderId).classList.add('expanded');
        } else {
            table.style.display = "none";
            document.getElementById(categoryHeaderId).classList.remove('expanded');
        }
    };

    document.getElementById("guild-header").addEventListener("click", function () {
        toggleDropdown("guild-table", "guild-header");
    });

    document.getElementById("lastfm-header").addEventListener("click", function () {
        toggleDropdown("lastfm-table", "lastfm-header");
    });
    document.getElementById("user-header").addEventListener("click", function () {
        toggleDropdown("user-table", "user-header");
    });

    document.getElementById("guild-table").appendChild(generateVariableTable(guildVariables));
    document.getElementById("lastfm-table").appendChild(generateVariableTable(lastFMVariables));
    document.getElementById("user-table").appendChild(generateVariableTable(userVariables));
    document.getElementById("guild-table").style.display = "none";
    document.getElementById("lastfm-table").style.display = "none";
    document.getElementById("user-table").style.display = "none";
});
