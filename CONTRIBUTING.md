# Contributing to dbdragoness

First off, thank you for considering contributing to dbdragoness! This is a beginner project, so please bear with any questionable coding practices you might encounter. Your help in improving the codebase, fixing bugs, and expanding the library is highly appreciated!

## Roadmap & Current Priorities

I am looking for help with the following specific goals, though any beneficial addition or suggestion is welcome:

### 1. Achieving Database Agnosticism

I want to move toward a truly decoupled architecture.

#### The Goal: 
Remove specific database names (e.g., "MySQL", "MongoDB", "PostgreSQL") from all files except for that specific database's own handler file.

#### The Constraint: 
This must be done without breaking the existing conversion or connection logic.

### 2. Fixing Conversion Logic

The automated conversion between SQL and NoSQL databases sometimes fails.

#### The Issue: 
Errors occur during certain conversions, particularly when handling complex metadata (like triggers or specific constraints), though the exact triggers for these failures are still being identified.

#### The Task: 
Help me identify these edge cases and make the conversion engine more robust.

### 3. Global Undo-Redo

I need a more forgiving user experience.

#### The Task: 
Implement a global Undo/Redo system that allows users to revert or re-apply actions across the application.

### 4. Local AI Assistant (No APIs)

I want a "Natural Language to Code" feature that respects user privacy and offline usage.

#### The Constraint: 
This must be a basic, local-only AI assistant. It should not depend on external APIs (like OpenAI or Anthropic).

#### The Goal: 
Convert human language queries into the specific code/query language of the currently active database.

### 5. Customization & Themes

Help me make the GUI more personal.

#### The Task: 
Add a system for different theme templates so users can choose a visual style that fits their workflow.

## How to Get Involved

### Refactor: 
If you see "bad code," don't just work around it—feel free to refactor it to follow better practices.

### New Handlers: 
Feel free to add support for new database types by creating new handler files.

### Bug Reports: 
If you find a specific conversion that fails, please open an issue with the schema or query that caused the crash.

dbdragoness is a learning project, and your expertise helps it grow. I look forward to your pull requests!