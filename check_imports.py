import os
import ast
import sys

def get_imports(file_path):
    """Extract all imports from a Python file"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            tree = ast.parse(f.read())
        
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.add(alias.name.split('.')[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.add(node.module.split('.')[0])
        
        return imports
    except Exception as e:
        print(f"Error parsing {file_path}: {e}")
        return set()

def scan_directory(directory):
    """Scan all Python files in directory"""
    all_imports = set()
    
    for root, dirs, files in os.walk(directory):
        # Skip __pycache__ and venv directories
        dirs[:] = [d for d in dirs if d not in ['__pycache__', 'venv', 'node_modules', '.git']]
        
        for file in files:
            if file.endswith('.py'):
                file_path = os.path.join(root, file)
                imports = get_imports(file_path)
                all_imports.update(imports)
    
    return all_imports

if __name__ == '__main__':
    # Standard library modules (don't need pip install)
    stdlib = {
        'os', 'sys', 'time', 'json', 're', 'logging', 'threading', 
        'subprocess', 'pathlib', 'platform', 'socket', 'webbrowser',
        'traceback', 'gc', 'ctypes', 'hashlib', 'getpass', 'uuid',
        'collections', 'functools', 'itertools', 'datetime', 'secrets'
    }
    
    directory = 'dbdragoness'
    if len(sys.argv) > 1:
        directory = sys.argv[1]
    
    imports = scan_directory(directory)
    
    # Filter out standard library and local imports
    third_party = sorted(imports - stdlib - {'dbdragoness'})
    
    print("Third-party packages found:")
    for package in third_party:
        print(f"  - {package}")