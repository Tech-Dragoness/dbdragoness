import sys
import socket
import webbrowser
import threading
import subprocess
import os
import platform
import click
from .app import create_app
from .db_registry import DBRegistry

def find_available_port(start_port=8000):
    port = start_port
    while True:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(('localhost', port)) != 0:
                return port
            print(f"Port {port} is busy. Trying {port + 1}? (y/n)")
            if input().lower() != 'y':
                sys.exit("Okay, exiting—no port for us today!")
            port += 1
            
def ensure_react_built():
    """Ensure React frontend is built on first run after pip install"""
    frontend_dir = os.path.join(os.path.dirname(__file__), 'frontend')
    react_build_dir = os.path.join(os.path.dirname(__file__), 'static', 'react')
    
    # Check if React build exists
    if os.path.exists(os.path.join(react_build_dir)):
        return True
    
    # If frontend source exists, try to build
    if os.path.exists(frontend_dir):
        print("📦 React frontend not built. Building now...")
        return build_react_frontend()
    
    # No React available
    return False

def build_react_frontend():
    """Build React frontend before starting Flask"""
    # frontend folder is inside dbdragoness folder
    frontend_dir = os.path.join(os.path.dirname(__file__), 'frontend')
    
    if not os.path.exists(frontend_dir):
        print("⚠️  No React frontend found at dbdragoness/frontend/. Skipping build...")
        return False
    
    print("🔨 Building React frontend...")
    
    # Try to find npm in common locations
    npm_cmd = 'npm'

    possible_npm_paths = ['npm']  # Start with PATH

    # Add platform-specific paths
    if platform.system() == 'Windows':
        possible_npm_paths.extend([
            'npm.cmd',
            r'C:\Program Files\nodejs\npm.cmd',
            r'C:\Program Files (x86)\nodejs\npm.cmd',
            os.path.expanduser('~\\AppData\\Roaming\\npm\\npm.cmd'),
        ])
    elif platform.system() == 'Darwin':  # macOS
        possible_npm_paths.extend([
            '/usr/local/bin/npm',
            '/opt/homebrew/bin/npm',
            os.path.expanduser('~/.nvm/versions/node/*/bin/npm'),
        ])
    else:  # Linux and others
        possible_npm_paths.extend([
            '/usr/bin/npm',
            '/usr/local/bin/npm',
            os.path.expanduser('~/.nvm/versions/node/*/bin/npm'),
        ])
    
    # Find working npm command
    for npm_path in possible_npm_paths:
        try:
            result = subprocess.run(
                [npm_path, '--version'], 
                capture_output=True, 
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                npm_cmd = npm_path
                print(f"✓ Found npm at: {npm_cmd}")
                break
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    
    try:
        # Check if node_modules exists, if not run npm install
        if not os.path.exists(os.path.join(frontend_dir, 'node_modules')):
            print("📦 Installing npm dependencies...")
            # Use shell=True only on Windows for .cmd files
            use_shell = platform.system() == 'Windows' and npm_cmd.endswith('.cmd')

            subprocess.run([npm_cmd, 'install'], cwd=frontend_dir, check=True, shell=use_shell)

        # Build React app
        subprocess.run([npm_cmd, 'run', 'build'], cwd=frontend_dir, check=True, shell=use_shell)
        print("✅ React frontend built successfully!")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ React build failed: {e}")
        return False
    except FileNotFoundError:
        print("❌ npm not found. Please install Node.js and add it to PATH")
        print("\nTo add Node.js to PATH:")
        print("1. Find Node.js installation (usually C:\\Program Files\\nodejs)")
        print("2. Add to System Environment Variables > Path")
        print("3. Restart terminal/VSCode")
        return False

def _resolve_handler_name(handler_name, available_handlers):
    """
    Match handler_name to available_handlers case-insensitively.
    If no exact case-insensitive match is found, suggest the closest
    name and ask the user to confirm or fall back to the default.
    Returns the correctly-cased handler name from the registry, or None
    to signal 'use default'.
    """
    import difflib

    # Case-insensitive exact match
    for h in available_handlers:
        if h.lower() == handler_name.lower():
            return h

    # No match — find the closest candidate
    matches = difflib.get_close_matches(
        handler_name.lower(),
        [h.lower() for h in available_handlers],
        n=1,
        cutoff=0.5,
    )

    if matches:
        # Map the lowercased match back to the real cased name
        suggestion = next(h for h in available_handlers if h.lower() == matches[0])
        answer = input(
            f"Handler '{handler_name}' not found. Did you mean '{suggestion}'? "
            f"[Y/n/Enter] "
        ).strip().lower()
        if answer in ('', 'y', 'yes'):
            return suggestion
        else:
            click.echo(f"Using default handler instead.")
            return None
    else:
        click.echo(
            f"Handler '{handler_name}' not found and no close match exists. "
            f"Using default handler instead."
        )
        return None


@click.group(invoke_without_command=True)
@click.pass_context
@click.option('--type', 'db_type', type=click.Choice(['sql', 'nosql'], case_sensitive=False), 
              help='Database type (sql or nosql)')
@click.option('--handler', 'handler_name', help='Specific database handler (e.g., SQLite, TinyDB)')
@click.option('--db', 'db_name', help='Database name to open or create')
@click.option('--table', 'table_name', help='Table/collection name to open or create')
@click.option('--port', default=8000, help='Port to run on (default: 8000)')
def cli(ctx, db_type, handler_name, db_name, table_name, port):
    """DBDragoness - Database GUI Manager
    
    Examples:
        dbdragoness                      # Interactive mode
        dbdragoness --type sql                    # Open SQL homepage
        dbdragoness --type sql --handler SQLite   # Open directly into a DB
    """
    
    # If subcommand invoked, don't run main logic
    if ctx.invoked_subcommand is not None:
        return
    
    react_available = ensure_react_built()
    
    # Discover handlers first
    DBRegistry.discover_handlers()
    
    # Determine database type
    if not db_type:
        if db_name or table_name:
            db_type = infer_db_type_from_existing(db_name)
            if not db_type:
                db_type = click.prompt(
                    "Choose your realm: sql or nosql?", 
                    type=click.Choice(['sql', 'nosql'], case_sensitive=False)
                ).lower()
        else:
            db_type = click.prompt(
                "Choose your realm: sql or nosql?", 
                type=click.Choice(['sql', 'nosql'], case_sensitive=False)
            ).lower()
    
    # Normalise db_type (click's case_sensitive=False already lowercases it,
    # but guard here in case it arrives mixed-case from a subcommand path)
    if db_type:
        db_type = db_type.lower()

    # Determine handler
    if db_type == 'sql':
        available_handlers = list(DBRegistry.get_sql_handlers().keys())
    else:
        available_handlers = list(DBRegistry.get_nosql_handlers().keys())

    if not available_handlers:
        click.echo(f"Error: No {db_type.upper()} handlers available.", err=True)
        sys.exit(1)

    if handler_name:
        # Resolve case-insensitively, with typo suggestion
        resolved = _resolve_handler_name(handler_name, available_handlers)
        handler_name = resolved if resolved else available_handlers[0]
    else:
        handler_name = available_handlers[0]

    click.echo(f"Using handler: {handler_name}")

    # Find available port
    port = find_available_port(port)

    # Create app with specified type and handler
    app = create_app(db_type, handler_name)

    # Default URL — always open to React home if available
    if react_available:
        target_url = f"http://localhost:{port}/react/"
        click.echo("🚀 Using React UI (default)")
    else:
        target_url = f"http://localhost:{port}/"

    # Handle --db and --table: navigate directly to the right page
    if db_name:
        handler = app.config['HANDLER']
        existing_dbs = handler.list_dbs()

        if db_name in existing_dbs:
            click.echo(f"✓ Database '{db_name}' exists")

            if table_name:
                try:
                    handler.switch_db(db_name)
                    existing_tables = handler.list_tables()

                    if table_name in existing_tables:
                        click.echo(f"✓ Table '{table_name}' exists")
                        if db_type == 'sql':
                            target_url = f"http://localhost:{port}/react/db/{db_name}/table/{table_name}"
                        else:
                            target_url = f"http://localhost:{port}/react/db/{db_name}/collection/{table_name}"
                    else:
                        click.echo(f"Table '{table_name}' does not exist in database '{db_name}'.")
                        if click.confirm(f"Create table '{table_name}'?", default=True):
                            create_table_or_collection(handler, db_name, table_name, db_type)
                            if db_type == 'sql':
                                target_url = f"http://localhost:{port}/react/db/{db_name}/table/{table_name}"
                            else:
                                target_url = f"http://localhost:{port}/react/db/{db_name}/collection/{table_name}"
                        else:
                            if click.confirm(f"Open database '{db_name}' instead?", default=True):
                                target_url = f"http://localhost:{port}/react/db/{db_name}"
                            else:
                                if click.confirm("Open homepage instead?", default=True):
                                    target_url = f"http://localhost:{port}/react/"
                                else:
                                    click.echo("Exiting...")
                                    sys.exit(0)

                except Exception as e:
                    click.echo(f"Error accessing database: {e}", err=True)
                    sys.exit(1)
            else:
                # --db only: open the database details page
                target_url = f"http://localhost:{port}/react/db/{db_name}"

        else:
            if click.confirm(f"Database '{db_name}' does not exist. Create it?", default=True):
                click.echo(f"Creating database '{db_name}'...")
                try:
                    handler.create_db(db_name)
                    click.echo(f"✓ Database '{db_name}' created")

                    if table_name:
                        click.echo(f"Creating table '{table_name}'...")
                        create_table_or_collection(handler, db_name, table_name, db_type)
                        if db_type == 'sql':
                            target_url = f"http://localhost:{port}/react/db/{db_name}/table/{table_name}"
                        else:
                            target_url = f"http://localhost:{port}/react/db/{db_name}/collection/{table_name}"
                    else:
                        target_url = f"http://localhost:{port}/react/db/{db_name}"

                except Exception as e:
                    click.echo(f"Error creating database: {e}", err=True)
                    sys.exit(1)
            else:
                if click.confirm("Open homepage instead?", default=True):
                    target_url = f"http://localhost:{port}/react/"
                else:
                    click.echo("Exiting...")
                    sys.exit(0)

    def open_browser():
        webbrowser.open_new(target_url)
        click.echo(f"\n🚀 Opening {target_url}")

    threading.Timer(2, open_browser).start()
    click.echo(f"Starting server on port {port}...")
    app.run(debug=True, port=port, use_reloader=False)

def infer_db_type_from_existing(db_name):
    """Try to infer database type from existing files"""
    import os
    
    sql_paths = ['sql_dbs/sqlite', 'sql_dbs/duckdb', 'sql_dbs/postgresql']
    for path in sql_paths:
        if os.path.exists(path):
            files = os.listdir(path)
            if any(db_name in f for f in files):
                return 'sql'
    
    nosql_paths = ['nosql_dbs/tinydb', 'nosql_dbs/mongodb']
    for path in nosql_paths:
        if os.path.exists(path):
            files = os.listdir(path)
            if any(db_name in f for f in files):
                return 'nosql'
    
    return None

def create_table_or_collection(handler, db_name, table_name, db_type):
    """Create a table or collection"""
    try:
        handler.switch_db(db_name)
        
        if db_type == 'sql':
            if hasattr(handler, '_get_connection'):
                with handler._get_connection() as conn:
                    from sqlalchemy.sql import text
                    
                    if hasattr(handler, 'create_default_table'):
                        handler.create_default_table(table_name)
                    elif hasattr(handler, 'handler') and hasattr(handler.handler, 'create_default_table'):
                        handler.handler.create_default_table(table_name)
                    else:
                        create_stmt = f"CREATE TABLE IF NOT EXISTS {table_name} (id INTEGER PRIMARY KEY)"
                        conn.execute(text(create_stmt))
                        conn.commit()
                    
                    click.echo(f"✓ Table '{table_name}' created")
        else:
            handler.create_collection(table_name)
            click.echo(f"✓ Collection '{table_name}' created")
    
    except Exception as e:
        click.echo(f"Error creating {'table' if db_type == 'sql' else 'collection'}: {e}", err=True)
        raise

def main():
    """Entry point for CLI"""
    cli(obj={})

if __name__ == "__main__":
    main()