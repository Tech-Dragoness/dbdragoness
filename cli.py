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
    if os.path.exists(os.path.join(react_build_dir, 'index.html')):
        return True
    
    # If frontend source exists, try to build
    if os.path.exists(frontend_dir):
        print("📦 React frontend not built. Building now...")
        return build_react_frontend()
    
    # No React available
    print("⚠️ React frontend not available. Using HTML templates only.")
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
        print("⚠️  Continuing with HTML templates only...")
        return False
    except FileNotFoundError:
        print("❌ npm not found. Please install Node.js and add it to PATH")
        print("⚠️  Continuing with HTML templates only...")
        print("\nTo add Node.js to PATH:")
        print("1. Find Node.js installation (usually C:\\Program Files\\nodejs)")
        print("2. Add to System Environment Variables > Path")
        print("3. Restart terminal/VSCode")
        return False

@click.group(invoke_without_command=True)
@click.pass_context
@click.option('--type', 'db_type', type=click.Choice(['sql', 'nosql'], case_sensitive=False), 
              help='Database type (sql or nosql)')
@click.option('--handler', 'handler_name', help='Specific database handler (e.g., SQLite, TinyDB)')
@click.option('--db', 'db_name', help='Database name to open or create')
@click.option('--table', 'table_name', help='Table/collection name to open or create')
@click.option('--port', default=8000, help='Port to run on (default: 8000)')
@click.option('--no-react-build', is_flag=True, help='Skip React build (use existing build)')
@click.option('--use-react', is_flag=True, help='Open React UI instead of HTML')
def cli(ctx, db_type, handler_name, db_name, table_name, port, no_react_build, use_react):
    """DBDragoness - Database GUI Manager
    
    Examples:
        dbdragoness                          # Interactive mode (HTML UI)
        dbdragoness --use-react              # Use React UI
        dbdragoness --type sql               # Open SQL homepage
        dbdragoness --no-react-build         # Skip React build, faster startup
    """
    
    # If subcommand invoked, don't run main logic
    if ctx.invoked_subcommand is not None:
        return
    
    # Build React frontend unless skipped
    react_available = False
    if not no_react_build:
        react_available = ensure_react_built()  # ✅ Use new function
    else:
        # Check if React build exists at dbdragoness/static/react
        react_build_dir = os.path.join(os.path.dirname(__file__), 'static', 'react')
        react_available = os.path.exists(os.path.join(react_build_dir, 'index.html'))
        if react_available:
            print("✓ Using existing React build")
    
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
    
    # Determine handler
    if not handler_name:
        if db_type == 'sql':
            available = list(DBRegistry.get_sql_handlers().keys())
        else:
            available = list(DBRegistry.get_nosql_handlers().keys())
        
        if not available:
            click.echo(f"Error: No {db_type.upper()} handlers available.", err=True)
            sys.exit(1)
        
        handler_name = available[0]
        click.echo(f"Using handler: {handler_name}")
    
    # Find available port
    port = find_available_port(port)
    
    # Create app with specified type and handler
    app = create_app(db_type, handler_name)
    
    # Determine target URL - DEFAULT TO REACT if available
    if react_available:
        target_url = f"http://localhost:{port}/react/"
        click.echo("🚀 Using React UI (default)")
    else:
        target_url = f"http://localhost:{port}/dbdragoness"
        click.echo("⚠️  React not available, using HTML UI")
    
    # Handle database and table operations (keeping existing logic)
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
                            if use_react and react_available:
                                target_url = f"http://localhost:{port}/react/#/db/{db_name}/table/{table_name}"
                            else:
                                target_url = f"http://localhost:{port}/dbdragoness/db/{db_name}/table/{table_name}"
                        else:
                            if use_react and react_available:
                                target_url = f"http://localhost:{port}/react/#/db/{db_name}/collection/{table_name}"
                            else:
                                target_url = f"http://localhost:{port}/dbdragoness/db/{db_name}/collection/{table_name}"
                    else:
                        click.echo(f"Creating table '{table_name}' in database '{db_name}'...")
                        create_table_or_collection(handler, db_name, table_name, db_type)
                        if db_type == 'sql':
                            if use_react and react_available:
                                target_url = f"http://localhost:{port}/react/#/db/{db_name}/table/{table_name}"
                            else:
                                target_url = f"http://localhost:{port}/dbdragoness/db/{db_name}/table/{table_name}"
                        else:
                            if use_react and react_available:
                                target_url = f"http://localhost:{port}/react/#/db/{db_name}/collection/{table_name}"
                            else:
                                target_url = f"http://localhost:{port}/dbdragoness/db/{db_name}/collection/{table_name}"
                
                except Exception as e:
                    click.echo(f"Error accessing database: {e}", err=True)
                    sys.exit(1)
            else:
                if use_react and react_available:
                    target_url = f"http://localhost:{port}/react/#/db/{db_name}"
                else:
                    target_url = f"http://localhost:{port}/dbdragoness/db/{db_name}"
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
                            if use_react and react_available:
                                target_url = f"http://localhost:{port}/react/#/db/{db_name}/table/{table_name}"
                            else:
                                target_url = f"http://localhost:{port}/dbdragoness/db/{db_name}/table/{table_name}"
                        else:
                            if use_react and react_available:
                                target_url = f"http://localhost:{port}/react/#/db/{db_name}/collection/{table_name}"
                            else:
                                target_url = f"http://localhost:{port}/dbdragoness/db/{db_name}/collection/{table_name}"
                    else:
                        if use_react and react_available:
                            target_url = f"http://localhost:{port}/react/#/db/{db_name}"
                        else:
                            target_url = f"http://localhost:{port}/dbdragoness/db/{db_name}"
                
                except Exception as e:
                    click.echo(f"Error creating database: {e}", err=True)
                    sys.exit(1)
            else:
                if click.confirm("Open homepage instead?", default=True):
                    if use_react and react_available:
                        target_url = f"http://localhost:{port}/react/"
                    else:
                        target_url = f"http://localhost:{port}/dbdragoness"
                else:
                    click.echo("Exiting...")
                    sys.exit(0)
    
    def open_browser():
        webbrowser.open_new(target_url)
        click.echo(f"\n🚀 Opening {target_url}")
    
    threading.Timer(1, open_browser).start()
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