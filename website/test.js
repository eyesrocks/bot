const fs = require('fs');
const path = require('path');

// Directory path of your cogs folder
const cogsDirectory = path.join(__dirname, '../cogs');

// Enhanced regex patterns to match command decorators and their parameters
const commandRegex = /@(?:\w+\.)?command\(\s*(?:.|\n)*?name\s*=\s*['"](.+?)['"](.*?brief\s*=\s*['"](.+?)['"])?/g;
const groupRegex = /@(?:\w+\.)?group\(\s*name\s*=\s*['"](.+?)['"]/g;

// Function to load cogs and categorize commands
function loadCogs() {
  const categories = {}; // To store cogs as categories

  // Read all files from the cogs directory
  fs.readdirSync(cogsDirectory).forEach((file) => {
    if (file.endsWith('.py')) { // Ensure you are reading only Python files
      const category = path.basename(file, '.py'); // Get category name (file name without extension)
      categories[category] = []; // Initialize an empty array for commands

      // Read the file content
      const filePath = path.join(cogsDirectory, file);
      const fileContent = fs.readFileSync(filePath, 'utf-8');

      // Check for command groups in the file
      let groupName = null;
      let groupMatch = groupRegex.exec(fileContent);
      if (groupMatch) {
        groupName = groupMatch[1]; // Extract the group name if it exists
      }

      // Use the enhanced regex pattern to extract command names and briefs
      let match;
      while ((match = commandRegex.exec(fileContent)) !== null) {
        const commandName = match[1];
        const brief = match[3] || 'No brief provided'; // Use the brief if available, otherwise a default message

        // Prefix the command name with the group name if it exists
        const fullCommandName = groupName ? `${groupName} ${commandName}` : commandName;

        // Add the command as an array [name, brief] to the category
        categories[category].push([fullCommandName, brief]);
      }
    }
  });

  return categories;
}

// Example usage
const commandsByCategory = loadCogs();
console.log(commandsByCategory);
