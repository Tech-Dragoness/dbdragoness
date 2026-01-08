<p align="center">
  <img src="assets/Logo.png" width="160" alt="DBDragoness Logo">
</p>

<h1 align="center">DBDragoness 🐉</h1>

<p align="center">
  A lightweight GUI manager for SQL & NoSQL databases
</p>

## Features

- 🎯 Support for multiple databases: SQLite, MySQL, PostgreSQL, DuckDB, TinyDB, MongoDB
- 🎨 Modern React UI
- 🔒 Secure credential management with keyring
- 📊 Data visualization with charts
- 🔄 Import/Export capabilities
- ⚡ Fast and lightweight

## Installation

### Best and easiest method

```bash
pip install --upgrade dbdragoness
```
Note: Latest version is 0.1.6

### Development Setup (For Developers & Academic Use)

This option is recommended if you want to explore, modify, or study the source code.

1. Clone the Repository
```bash
git clone https://github.com/tech-dragoness/dbdragoness.git
cd dbdragoness
```

2. Create and Activate a Virtual Environment (Recommended)
```bash
python -m venv venv
```

Windows
```bash
venv\Scripts\activate
```

macOS / Linux
```bash
source venv/bin/activate
```

3. Install the Project in Editable Mode

Editable mode ensures that any changes you make to the source code are immediately reflected when running the tool.
```bash
pip install -e .
```

4. Run DBDragoness
```bash
dbdragoness
```

5. (Optional) Verify Installation
```bash
dbdragoness --help
```

## Quick Start
```bash
# Start the GUI
dbdragoness

# Open specific database
dbdragoness --type sql --db mydb
```

## Requirements

- Python 3.8+
- Node.js 16+ (for React UI build)

## License

MIT License

Copyright (c) 2026 Tulika Thampi. All rights reserved.

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

Credit Requirement: The original author, Tulika Thampi, and the original work must be credited in all copies, distributions, or derivative works. This credit should be visible in documentation, UI, or other appropriate places where the Software is used or presented.

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
