# mysql_handler.py - UNIVERSAL VERSION
# Works with: XAMPP, Standalone MySQL, MySQL Workbench, Docker MySQL, Remote MySQL, etc.
import re
import os
import time
import logging
from venv import logger
import keyring
import struct
from sqlalchemy import create_engine, text, pool
from sqlalchemy.exc import IntegrityError, OperationalError
from .db_handler import DBHandler

class MySQLHandler(DBHandler):
    
    DB_TYPE = 'sql'
    DB_NAME = 'MySQL'
    
    KEYRING_SERVICE = 'dbdragoness_mysql'
    KEYRING_USERNAME_KEY = 'mysql_username'
    KEYRING_PASSWORD_KEY = 'mysql_password'
    KEYRING_HOST_KEY = 'mysql_host'
    KEYRING_PORT_KEY = 'mysql_port'
    
    def __init__(self):
        self.current_db = None
        self.engine = None
        self.base_path = 'sql_dbs/mysql'
        self.logger = logging.getLogger(__name__)
        os.makedirs(self.base_path, exist_ok=True)
        
        # Connection settings with sensible defaults
        self.username = None
        self.password = None
        self.host = 'localhost'  # Will be auto-detected
        self.port = 3306
        self._credentials_valid = False
        
        # Load saved credentials
        self._load_credentials()

    def _load_credentials(self):
        """Load credentials from secure storage"""
        try:
            self.username = keyring.get_password(self.KEYRING_SERVICE, self.KEYRING_USERNAME_KEY)
            self.password = keyring.get_password(self.KEYRING_SERVICE, self.KEYRING_PASSWORD_KEY)
            
            # Load custom host/port if saved
            saved_host = keyring.get_password(self.KEYRING_SERVICE, self.KEYRING_HOST_KEY)
            saved_port = keyring.get_password(self.KEYRING_SERVICE, self.KEYRING_PORT_KEY)
            
            if saved_host:
                self.host = saved_host
            if saved_port:
                try:
                    self.port = int(saved_port)
                except:
                    self.port = 3306
            
            # Convert None to empty string
            if self.username is None:
                self.username = ''
            if self.password is None:
                self.password = ''
            
            if self.username:
                self._credentials_valid = True
                self.logger.info(f"MySQL credentials loaded: {self.username}@{self.host}:{self.port}")
                return
            
            self.logger.warning("MySQL credentials missing from keyring")
            
        except Exception as e:
            self.logger.error(f"Error loading credentials: {e}")

    def get_credential_status(self):
        """Return whether this handler needs credentials"""
        try:
            username = keyring.get_password(self.KEYRING_SERVICE, self.KEYRING_USERNAME_KEY)
            password = keyring.get_password(self.KEYRING_SERVICE, self.KEYRING_PASSWORD_KEY)
            
            has_creds = bool(username and password)
            needs = not has_creds
            
            self.logger.debug(f"MySQL credential status: has_creds={has_creds}, needs={needs}")
            
            return {
                "needs_credentials": needs,
                "handler": self.DB_NAME
            }
        except Exception as e:
            self.logger.error(f"Failed to check MySQL credentials: {e}")
            return {
                "needs_credentials": True,   # Be safe – assume needed if error
                "handler": self.DB_NAME
            }

    def validate_and_store_credentials(self, username, password, host=None, port=None):
        """Validate and store credentials with optional custom host/port"""
        self.username = username
        self.password = password if password else ''
        
        # Use custom host/port if provided
        if host:
            self.host = host
        if port:
            try:
                self.port = int(port)
            except:
                self.port = 3306
    
        # TEST CREDENTIALS with auto-detection
        test_result = self._test_credentials_universal()
    
        if test_result['success']:
            try:
                # Store all connection details
                keyring.set_password(self.KEYRING_SERVICE, self.KEYRING_USERNAME_KEY, username)
                keyring.set_password(self.KEYRING_SERVICE, self.KEYRING_PASSWORD_KEY, password if password else '')
                keyring.set_password(self.KEYRING_SERVICE, self.KEYRING_HOST_KEY, self.host)
                keyring.set_password(self.KEYRING_SERVICE, self.KEYRING_PORT_KEY, str(self.port))
                
                self._credentials_valid = True
                self.logger.info(f"MySQL credentials saved: {username}@{self.host}:{self.port}")
                
                return {
                    'success': True, 
                    'message': f'Connected successfully to {self.host}:{self.port}!',
                    'detected_host': self.host,
                    'detected_port': self.port
                }
            except Exception as e:
                self.logger.error(f"Failed to store credentials: {e}")
                return {'success': False, 'message': f'Failed to save credentials: {str(e)}'}
        else:
            error_msg = test_result.get('error', 'Unknown error')
            self.logger.error(f"Credential test failed: {error_msg}")
            return {'success': False, 'message': f'Connection failed: {error_msg}'}

    def _test_credentials_universal(self):
        """
        UNIVERSAL connection test - tries ALL common MySQL configurations
        Works with: XAMPP, Standalone MySQL, Workbench, Docker, Remote, etc.
        """
        import pymysql
        
        password = self.password if self.password else ''
        
        # Build comprehensive strategy list with protocol variations
        strategies = []
        
        # 1. Try provided host/port with different protocol options
        for charset in ['utf8mb4', 'utf8', 'latin1']:
            for use_unicode in [True, False]:
                for client_flag in [0, 2]:  # 0 = default, 2 = FOUND_ROWS
                    strategies.append({
                        'host': self.host,
                        'port': self.port,
                        'charset': charset,
                        'use_unicode': use_unicode,
                        'client_flag': client_flag,
                        'name': f'{self.host}:{self.port} ({charset}, unicode={use_unicode}, flag={client_flag})'
                    })
        
        # 2. If localhost, try common variations
        if self.host in ['localhost', '127.0.0.1', None]:
            for host in ['127.0.0.1', 'localhost']:
                for port in [3306, 3307]:
                    for charset in ['utf8mb4', 'utf8']:
                        strategies.append({
                            'host': host,
                            'port': port,
                            'charset': charset,
                            'use_unicode': True,
                            'client_flag': 0,
                            'name': f'{host}:{port} ({charset})'
                        })
        
        last_error = None
        tested_count = 0
        
        for strategy in strategies:
            tested_count += 1
            
            try:
                self.logger.debug(f"Testing [{tested_count}]: {strategy['name']}")
                
                # CRITICAL: Attempt connection with protocol-safe settings
                conn = pymysql.connect(
                    host=strategy['host'],
                    port=strategy['port'],
                    user=self.username,
                    password=password,
                    charset=strategy['charset'],
                    # Timeouts
                    connect_timeout=5,
                    read_timeout=5,
                    write_timeout=5,
                    # CRITICAL: Protocol settings to prevent handshake errors
                    use_unicode=strategy.get('use_unicode', True),
                    # Compatibility flags
                    autocommit=True,
                    client_flag=strategy.get('client_flag', 0),
                    # Packet settings
                    max_allowed_packet=16*1024*1024,
                    # Disable problematic features
                    local_infile=False,
                    ssl=None,
                    # CRITICAL: Force protocol version
                    defer_connect=False,  # Connect immediately to catch errors
                    # Encoding
                    binary_prefix=True
                )
                
                # Quick validation query with error handling
                cursor = conn.cursor()
                
                # Test with simplest query first
                try:
                    cursor.execute("SELECT 1")
                    cursor.fetchone()
                except Exception as e:
                    # If even SELECT 1 fails, this connection is bad
                    cursor.close()
                    conn.close()
                    raise Exception(f"Query test failed: {e}")
                
                # Now try getting version info
                try:
                    cursor.execute("SELECT VERSION()")
                    result = cursor.fetchone()
                    version = result[0] if result else "Unknown"
                except:
                    version = "Unknown"
                
                cursor.close()
                
                # Success! Update connection settings
                self.host = strategy['host']
                self.port = strategy['port']
                
                # Close immediately
                conn.close()
                
                self.logger.info(f"✅ MySQL connection successful via {strategy['name']}")
                self.logger.info(f"   MySQL Version: {version}")
                
                return {
                    'success': True, 
                    'error': None,
                    'host': self.host,
                    'port': self.port,
                    'version': version
                }
                
            except pymysql.err.OperationalError as e:
                error_code = e.args[0] if e.args else 0
                error_msg = str(e)
                
                # Categorize errors
                if error_code == 2013:
                    last_error = "Connection lost during handshake (protocol mismatch)"
                elif error_code == 1045:
                    last_error = f"Access denied for user '{self.username}'"
                elif error_code == 2003:
                    last_error = f"Cannot connect to {strategy['host']}:{strategy['port']}"
                elif error_code == 2002:
                    last_error = f"Cannot resolve host {strategy['host']}"
                elif error_code == 1049:
                    # Database doesn't exist - but connection works!
                    self.host = strategy['host']
                    self.port = strategy['port']
                    self.logger.info(f"✅ MySQL connection successful (no default DB)")
                    return {'success': True, 'error': None}
                else:
                    last_error = f"MySQL Error {error_code}: {error_msg}"
                
                self.logger.debug(f"   ❌ {last_error}")
                
            except struct.error as e:
                # CRITICAL: Catch the "unpack requires a buffer of 4 bytes" error
                last_error = f"Protocol error (struct.error): {str(e)} - MySQL handshake failed"
                self.logger.debug(f"   ❌ {last_error}")
                
            except Exception as e:
                last_error = f"{type(e).__name__}: {str(e)}"
                self.logger.debug(f"   ❌ {last_error}")
        
        # All strategies failed
        self.logger.error(f"All {tested_count} connection strategies failed")
        
        # Provide helpful error message
        if 'struct.error' in str(last_error) or 'unpack requires a buffer' in str(last_error):
            helpful_msg = (
                f"Protocol handshake error. This usually means:\n"
                f"1. XAMPP MySQL is corrupted/misconfigured\n"
                f"2. MySQL version mismatch between client and server\n"
                f"3. Network packet corruption\n\n"
                f"RECOMMENDED FIX:\n"
                f"• Install standalone MySQL Server (see installation guide)\n"
                f"• Or restart XAMPP MySQL service completely\n"
                f"• Or update PyMySQL: pip install --upgrade pymysql"
            )
        elif '1045' in str(last_error) or 'Access denied' in str(last_error):
            helpful_msg = (
                f"Access denied for user '{self.username}'. "
                f"Check your username and password. "
                f"For new MySQL installations, try username='root' with empty password."
            )
        elif '2003' in str(last_error) or 'Cannot connect' in str(last_error):
            helpful_msg = (
                f"Cannot connect to MySQL server. "
                f"Make sure MySQL is running (check XAMPP/services/Task Manager). "
                f"Tried hosts: localhost, 127.0.0.1 on ports: 3306, 3307"
            )
        else:
            helpful_msg = last_error
        
        return {
            'success': False,
            'error': helpful_msg
        }

    def _ensure_credentials(self):
        """Ensure credentials are valid before operations"""
        if not self._credentials_valid:
            raise ValueError("MySQL credentials required. Please configure credentials first.")

    def _quote_identifier(self, identifier):
        """Quote identifier to preserve case sensitivity in MySQL"""
        return f"`{identifier}`"
    
    def get_connection_info(self, db_name):
        """Return MySQL connection information"""
        return {
            'connection_string': f'mysql+pymysql://YOUR_USERNAME:YOUR_PASSWORD@localhost:3306/{db_name}',
            'test_code': f'''from sqlalchemy import create_engine, text

# ⚠️ REPLACE THESE WITH YOUR ACTUAL CREDENTIALS
username = "YOUR_USERNAME"  # Often "root" for local MySQL
password = "YOUR_PASSWORD"  # Your MySQL password (can be empty: "")
port = 3306  # Default MySQL port

engine = create_engine(f'mysql+pymysql://{{username}}:{{password}}@localhost:{{port}}/{db_name}')
with engine.connect() as conn:
    result = conn.execute(text("SHOW TABLES"))
    tables = [row[0] for row in result]
    print(f"Tables: {{tables}}")''',
        'notes': [
            'Replace YOUR_USERNAME and YOUR_PASSWORD with your actual MySQL credentials',
            'Default username is often "root" for local MySQL installations',
            'Ensure MySQL server is running before testing'
        ]
        }

    def _get_connection(self):
        """Return a connection context manager for executing queries"""
        if not self.engine:
            raise Exception("No database selected. Please switch to a database first.")
        return self.engine.connect()

    def _get_db_url(self, db_name):
        """Generate connection URL with proper settings"""
        self._ensure_credentials()
        password = self.password if self.password else ''
        
        # URL-encode password to handle special characters
        from urllib.parse import quote_plus
        encoded_password = quote_plus(password)
        
        return (
            f"mysql+pymysql://{self.username}:{encoded_password}@{self.host}:{self.port}/{db_name}"
            f"?charset=utf8mb4&connect_timeout=10"
        )

    def _get_master_engine(self):
        """Get engine for mysql master database with optimal settings"""
        self._ensure_credentials()
        password = self.password if self.password else ''
        
        from urllib.parse import quote_plus
        encoded_password = quote_plus(password)
        
        return create_engine(
            f"mysql+pymysql://{self.username}:{encoded_password}@{self.host}:{self.port}/mysql?charset=utf8mb4",
            poolclass=pool.NullPool,  # No connection pooling for admin operations
            connect_args={
                'connect_timeout': 10,
                'read_timeout': 30,
                'write_timeout': 30,
                'charset': 'utf8mb4',
                'autocommit': False  # Let SQLAlchemy manage transactions
            },
            execution_options={
                'isolation_level': 'AUTOCOMMIT'
            }
        )

    def _handle_auth_error(self, operation_name, error):
        """Handle authentication errors by invalidating credentials"""
        error_str = str(error).lower()
        if any(word in error_str for word in ['password', 'authentication', 'access denied', 'auth']):
            self._credentials_valid = False
            self.logger.warning(f"Authentication failed during {operation_name}")
            raise ValueError("MySQL credentials expired or invalid. Please re-enter credentials.")
        raise error

    def create_db(self, db_name):
        """Create database - works with any MySQL installation"""
        try:
            self._ensure_credentials()
            
            existing_dbs = [db.lower() for db in self.list_dbs()]
            if db_name.lower() in existing_dbs:
                raise ValueError(f"Database '{db_name}' already exists.")
            
            master_engine = self._get_master_engine()
            
            try:
                with master_engine.connect() as conn:
                    conn.execute(text(f"CREATE DATABASE {self._quote_identifier(db_name)} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"))
                    conn.commit()
            finally:
                master_engine.dispose()
            
            actual_db_name = self._get_actual_db_name(db_name)
            self.switch_db(actual_db_name)
            
        except (OperationalError, ValueError) as e:
            self._handle_auth_error('create_db', e)

    def delete_db(self, db_name):
        """Delete database - works with any MySQL installation"""
        try:
            self._ensure_credentials()
            
            if self.current_db == db_name:
                if self.engine:
                    self.engine.dispose()
                self.engine = None
                self.current_db = None
            
            master_engine = self._get_master_engine()
            
            try:
                with master_engine.connect() as conn:
                    conn.execute(text(f"DROP DATABASE IF EXISTS {self._quote_identifier(db_name)}"))
                    conn.commit()
            finally:
                master_engine.dispose()
            
        except (OperationalError, ValueError) as e:
            self._handle_auth_error('delete_db', e)

    def switch_db(self, db_name):
        """Switch database with proper connection handling"""
        try:
            self._ensure_credentials()
            
            actual_db_name = self._get_actual_db_name(db_name)
            
            if actual_db_name not in self.list_dbs():
                raise FileNotFoundError(f"Database '{db_name}' not found.")
            
            if self.engine:
                self.engine.dispose()
            
            # Create engine with NullPool for better connection management
            self.engine = create_engine(
                self._get_db_url(actual_db_name),
                poolclass=pool.NullPool,
                connect_args={
                    'connect_timeout': 10,
                    'read_timeout': 30,
                    'write_timeout': 30,
                    'charset': 'utf8mb4',
                    'autocommit': False
                }
            )
            self.current_db = actual_db_name
            
        except (OperationalError, ValueError) as e:
            self._handle_auth_error('switch_db', e)

    def _get_actual_db_name(self, db_name):
        """Get the actual database name as stored by MySQL"""
        existing_dbs = self.list_dbs()
        
        if db_name in existing_dbs:
            return db_name
        
        for existing in existing_dbs:
            if existing.lower() == db_name.lower():
                return existing
        
        return db_name.lower()

    def list_dbs(self):
        """List databases - works with any MySQL installation"""
        try:
            self._ensure_credentials()
            
            engine = self._get_master_engine()
            try:
                with engine.connect() as conn:
                    result = conn.execute(text("SHOW DATABASES"))
                    dbs = [row[0] for row in result if row[0] not in [
                        'information_schema', 'mysql', 'performance_schema', 'sys', 'phpmyadmin'
                    ]]
                return dbs
            finally:
                engine.dispose()
                
        except (OperationalError, ValueError) as e:
            if 'credentials required' in str(e).lower():
                return []
            self._handle_auth_error('list_dbs', e)
            return []
        except Exception as e:
            self.logger.error(f"Error listing databases: {e}")
            return []

    def list_tables(self):
        """List tables"""
        if not self.engine:
            return []
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text("SHOW TABLES"))
                return [row[0] for row in result]
        except Exception as e:
            self.logger.error(f"Error listing tables: {e}")
            return []

    def list_tables_for_db(self, db_name):
        """List tables in a specific database"""
        try:
            if db_name not in self.list_dbs():
                return []
            
            temp_engine = create_engine(
                self._get_db_url(db_name),
                poolclass=pool.NullPool
            )
            try:
                with temp_engine.connect() as conn:
                    result = conn.execute(text("SHOW TABLES"))
                    tables = [row[0] for row in result]
                return tables
            finally:
                temp_engine.dispose()
                
        except Exception as e:
            self.logger.error(f"Error listing tables for {db_name}: {e}")
            return []

    def _get_actual_table_name(self, table_name):
        """Get the actual table name as stored by MySQL"""
        if not self.engine:
            return table_name.lower()
        
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text("SHOW TABLES"))
                existing_tables = [row[0] for row in result]
            
            if table_name in existing_tables:
                return table_name
            
            for existing in existing_tables:
                if existing.lower() == table_name.lower():
                    return existing
            
            return table_name.lower()
        except Exception:
            return table_name.lower()

    def get_supported_types(self):
        return [
            'INT', 'BIGINT', 'SMALLINT', 'TINYINT', 'MEDIUMINT',
            'DECIMAL', 'FLOAT', 'DOUBLE',
            'CHAR', 'VARCHAR', 'TEXT', 'MEDIUMTEXT', 'LONGTEXT',
            'DATE', 'DATETIME', 'TIMESTAMP', 'TIME', 'YEAR',
            'BLOB', 'MEDIUMBLOB', 'LONGBLOB',
            'BOOLEAN', 'ENUM', 'SET', 'JSON'
        ]

    def _get_primary_keys(self, table_name):
        """Get primary key columns"""
        if not self.engine:
            return set()
        
        actual_table_name = self._get_actual_table_name(table_name)
        
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text(f"""
                    SELECT COLUMN_NAME
                    FROM information_schema.KEY_COLUMN_USAGE
                    WHERE TABLE_SCHEMA = DATABASE()
                    AND TABLE_NAME = :t
                    AND CONSTRAINT_NAME = 'PRIMARY'
                """), {'t': actual_table_name})
                
                pk_cols = {row[0] for row in result}
                return pk_cols
                
        except Exception as e:
            self.logger.error(f"Error in _get_primary_keys: {e}")
            return set()

    def get_table_schema(self, table_name):
        """Get table schema with unique and autoincrement detection - INCLUDES CHECK constraints"""
        if not self.engine:
            return []

        actual_table_name = self._get_actual_table_name(table_name)

        try:
            with self.engine.connect() as conn:
                # ✅ Get column information
                result = conn.execute(text(f"""
                    SELECT 
                        COLUMN_NAME, 
                        COLUMN_TYPE,
                        IS_NULLABLE, 
                        COLUMN_DEFAULT, 
                        EXTRA, 
                        COLUMN_KEY
                    FROM information_schema.COLUMNS 
                    WHERE TABLE_SCHEMA = DATABASE()
                    AND TABLE_NAME = :t
                    ORDER BY ORDINAL_POSITION
                """), {'t': actual_table_name})
        
                rows = result.fetchall()
                pk_columns = self._get_primary_keys(table_name)
            
                # Get UNIQUE constraints
                unique_result = conn.execute(text(f"""
                    SELECT COLUMN_NAME
                    FROM information_schema.STATISTICS
                    WHERE TABLE_SCHEMA = DATABASE()
                    AND TABLE_NAME = :t
                    AND NON_UNIQUE = 0
                    AND INDEX_NAME != 'PRIMARY'
                """), {'t': actual_table_name})
            
                unique_columns = {row[0] for row in unique_result.fetchall()}

                # ✅ Get CHECK constraints per column
                check_constraints = {}
                try:
                    check_result = conn.execute(text("""
                        SELECT cc.CHECK_CLAUSE, tc.CONSTRAINT_NAME
                        FROM INFORMATION_SCHEMA.CHECK_CONSTRAINTS cc
                        JOIN INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
                            ON cc.CONSTRAINT_NAME = tc.CONSTRAINT_NAME
                            AND cc.CONSTRAINT_SCHEMA = tc.CONSTRAINT_SCHEMA
                        WHERE tc.TABLE_SCHEMA = DATABASE()
                            AND tc.TABLE_NAME = :t
                    """), {'t': actual_table_name})
                    
                    for row in check_result.fetchall():
                        check_expr = row[0]
                        constraint_name = row[1]
                        
                        if not check_expr:
                            continue
                        
                        # Extract column name from CHECK expression
                        # MySQL CHECK format: (`column_name` > 18) or (column_name > 18)
                        
                        # Try backtick-quoted column first
                        col_match = re.search(r'`([^`]+)`', check_expr)
                        if not col_match:
                            # Try unquoted column (word at start after opening paren)
                            col_match = re.search(r'\(?\s*([a-zA-Z_][a-zA-Z0-9_]*)\s+', check_expr)
                        
                        if col_match:
                            col_name = col_match.group(1)
                            
                            # CRITICAL: Deep clean MySQL's verbose CHECK expression for GUI display
                            clean_expr = check_expr.strip()
                            
                            # Remove outermost parentheses
                            if clean_expr.startswith('(') and clean_expr.endswith(')'):
                                clean_expr = clean_expr[1:-1].strip()
                            
                            # Remove backticks around identifiers
                            clean_expr = re.sub(r'`([^`]+)`', r'\1', clean_expr)
                            
                            # âœ… REMOVE MySQL's _utf8mb4 prefix and escaped quotes in string literals
                            clean_expr = re.sub(r"_utf8mb4\\'", "'", clean_expr)   # _utf8mb4\'name\' → 'name'
                            clean_expr = re.sub(r"\\'", "'", clean_expr)           # any leftover \'

                            # Final safety trim
                            clean_expr = clean_expr.strip()

                            if clean_expr and col_name:
                                # Keep the richest (longest) CHECK expression for this column
                                current = check_constraints.get(col_name, "")
                                if len(clean_expr) > len(current):
                                    check_constraints[col_name] = clean_expr
                                    self.logger.debug(f"Updated richer CHECK for {col_name}: {clean_expr}")
                                else:
                                    self.logger.debug(f"Kept existing CHECK for {col_name} (richer or equal)")
                                self.logger.debug(f"Cleaned CHECK for {col_name}: {clean_expr}")
                            else:
                                self.logger.debug(f"Skipped invalid/empty CHECK for column {col_name}")
                            
                except Exception as e:
                    self.logger.debug(f"Could not fetch CHECK constraints: {e}")

                schema = []
                for row in rows:
                    col_name, col_type_full, nullable, col_default, extra, column_key = row

                    col_type_upper = col_type_full.upper()
                    is_pk = col_name in pk_columns
                    is_auto_increment = bool(extra and 'auto_increment' in str(extra).lower())
                
                    is_unique = (col_name in unique_columns) or (column_key == 'UNI')
                    
                    # ✅ Get CHECK constraint for this column
                    check_constraint = check_constraints.get(col_name)

                    self.logger.debug(f"MySQL column {col_name}: type='{col_type_upper}', is_auto={is_auto_increment}, is_unique={is_unique}, check={check_constraint}")

                    schema.append({
                        'name': col_name,
                        'type': col_type_upper,
                        'pk': is_pk,
                        'notnull': nullable == 'NO',
                        'autoincrement': is_auto_increment,
                        'unique': is_unique or is_pk,
                        'check_constraint': check_constraint  # ✅ ADD CHECK
                    })

                return schema
            
        except Exception as e:
            self.logger.error(f"Error in table structure of {table_name}: {e}")
            return []

    def read(self, table_name):
        """Read all data - with clean date/datetime formatting for the GUI"""
        if not self.engine:
            return []
        
        try:
            actual_table_name = self._get_actual_table_name(table_name)
            quoted_table = self._quote_identifier(actual_table_name)
            
            with self.engine.connect() as conn:
                result = conn.execute(text(f"SELECT * FROM {quoted_table}"))
                rows = [dict(row._mapping) for row in result.fetchall()]
            
            # Clean date/datetime/time values for frontend
            from datetime import date, datetime, time  # Add this import at top if missing
            
            for row in rows:
                for key, value in row.items():
                    if isinstance(value, date) and not isinstance(value, datetime):
                        # Pure DATE — no time part
                        row[key] = value.strftime('%Y-%m-%d')
                    elif isinstance(value, datetime):
                        # DATETIME or TIMESTAMP — include time
                        row[key] = value.strftime('%Y-%m-%d %H:%M:%S')
                    elif isinstance(value, time):
                        # Pure TIME — no date
                        row[key] = value.strftime('%H:%M:%S')
            
            return rows
            
        except Exception as e:
            self.logger.error(f"Error reading from {table_name}: {e}")
            return []

    def execute_query(self, query):
        """Execute query"""
        if not self.engine:
            raise Exception("No database selected")
        
        try:
            statements = self._smart_split(query)
            
            if len(statements) == 1:
                with self.engine.connect() as conn:
                    result = conn.execute(text(statements[0]))
                    if statements[0].strip().upper().startswith('SELECT'):
                        return [dict(row._mapping) for row in result.fetchall()]
                    else:
                        conn.commit()
                        return {"rows_affected": result.rowcount}
            else:
                results = []
                with self.engine.connect() as conn:
                    for stmt in statements:
                        result = conn.execute(text(stmt))
                        if stmt.strip().upper().startswith('SELECT'):
                            results.append([dict(row._mapping) for row in result.fetchall()])
                        else:
                            results.append({"rows_affected": result.rowcount})
                    conn.commit()
                return results
        except Exception as e:
            self.logger.error(f"Query execution error: {e}")
            raise

    def _smart_split(self, query):
        """Split query by semicolons"""
        statements = []
        current = []
        in_string = False
        string_char = None
        
        for char in query:
            if char in ('"', "'", '`') and not in_string:
                in_string = True
                string_char = char
            elif in_string and char == string_char:
                in_string = False
            elif char == ';' and not in_string:
                statements.append(''.join(current).strip())
                current = []
                continue
            current.append(char)
        
        if current:
            statements.append(''.join(current).strip())
        
        return [s for s in statements if s]

    def insert(self, table_name, data):
        """Insert with quoted identifiers - handle empty strings as NULL"""
        if not self.engine:
            raise Exception("No database selected")
    
        # Convert empty strings to None (NULL) for numeric/non-text columns
        schema = self.get_table_schema(table_name)
        cleaned_data = {}
    
        for key, value in data.items():
            col_info = next((c for c in schema if c['name'] == key), None)
            if col_info:
                # Skip autoincrement columns entirely
                if col_info.get('autoincrement', False):
                    continue
            
                # Convert empty strings to None for numeric types
                if value == '':
                    if col_info['type'].upper() in ['INT', 'INTEGER', 'BIGINT', 'SMALLINT', 'TINYINT', 'MEDIUMINT', 'DECIMAL', 'FLOAT', 'DOUBLE', 'REAL', 'NUMERIC']:
                        cleaned_data[key] = None
                    else:
                        cleaned_data[key] = value
                else:
                    cleaned_data[key] = value
    
        actual_table_name = self._get_actual_table_name(table_name)
        quoted_table = self._quote_identifier(actual_table_name)
        quoted_cols = ', '.join([self._quote_identifier(k) for k in cleaned_data.keys()])
        placeholders = ', '.join([f':{k}' for k in cleaned_data.keys()])
        query = f"INSERT INTO {quoted_table} ({quoted_cols}) VALUES ({placeholders})"
    
        try:
            with self.engine.connect() as conn:
                conn.execute(text(query), cleaned_data)
                conn.commit()
        except IntegrityError as e:
            raise ValueError(f"Integrity constraint violation: {str(e)}")

    def update(self, table_name, data, condition):
        """Update data"""
        if not self.engine:
            raise Exception("No database selected")
        
        actual_table_name = self._get_actual_table_name(table_name)
        quoted_table = self._quote_identifier(actual_table_name)
        sets = ', '.join([f'{self._quote_identifier(k)}=:{k}' for k in data.keys()])
        query = f"UPDATE {quoted_table} SET {sets} WHERE {condition}"
        
        try:
            with self.engine.connect() as conn:
                conn.execute(text(query), data)
                conn.commit()
        except IntegrityError as e:
            raise ValueError(f"Integrity constraint violation: {str(e)}")

    def delete(self, table_name, condition):
        """Delete data"""
        if not self.engine:
            raise Exception("No database selected")
        
        actual_table_name = self._get_actual_table_name(table_name)
        quoted_table = self._quote_identifier(actual_table_name)
        query = f"DELETE FROM {quoted_table} WHERE {condition}"
        
        try:
            with self.engine.connect() as conn:
                conn.execute(text(query))
                conn.commit()
        except Exception as e:
            self.logger.error(f"Delete error: {e}")
            raise

    def delete_table(self, table_name):
        """Drop table"""
        if not self.engine:
            raise Exception("No database selected")
        
        actual_table_name = self._get_actual_table_name(table_name)
        quoted_table = self._quote_identifier(actual_table_name)
        
        try:
            with self.engine.connect() as conn:
                conn.execute(text(f"DROP TABLE IF EXISTS {quoted_table}"))
                conn.commit()
        except Exception as e:
            self.logger.error(f"Drop table error: {e}")
            raise

    def can_convert_column(self, table_name, column, new_type):
        return True
    
    def supports_non_pk_autoincrement(self):
        """DuckDB supports sequences on any integer column"""
        return True

    def modify_table(self, old_table_name, new_table_name, new_columns):
        """Modify table - PRESERVES CHECK constraints"""
        if not self.engine:
            raise Exception("No database selected")

        try:
            with self.engine.connect() as conn:
                actual_old_table_name = self._get_actual_table_name(old_table_name)
            
                self.logger.info(f"=== MODIFY TABLE DEBUG ===")
                self.logger.info(f"Old table: {old_table_name} -> {actual_old_table_name}")
                self.logger.info(f"New table: {new_table_name}")
                self.logger.info(f"New columns: {new_columns}")
            
                old_schema = self.get_table_schema(old_table_name)
                old_columns = {col['name']: col for col in old_schema}
                
                temp_table_name = f"temp_{old_table_name}_{os.urandom(4).hex()}"
            
                quoted_new_columns = []
                new_column_info = {}

                # ✅ CRITICAL: Extract CHECK constraints properly
                for col_def in new_columns:
                    parts = col_def.split(maxsplit=1)
                    if len(parts) >= 2:
                        col_name = parts[0]
                        rest = parts[1]
                        rest_upper = rest.upper()

                        # Ensure VARCHAR has a size specification
                        if rest_upper.startswith('VARCHAR'):
                            if '(' not in rest:
                                rest = 'VARCHAR(255)' + rest[7:]

                        # âœ… Extract CHECK constraint - handle partial CHECK syntax
                        check_constraint = None
                        rest_without_check = rest
                        if 'CHECK' in rest_upper:
                            check_start = rest.upper().find('CHECK')
                            if check_start != -1:
                                # Find the opening parenthesis after CHECK
                                paren_start = rest.find('(', check_start)
                                if paren_start != -1:
                                    # Count balanced parentheses
                                    depth = 0
                                    paren_end = -1
                                    for i in range(paren_start, len(rest)):
                                        if rest[i] == '(':
                                            depth += 1
                                        elif rest[i] == ')':
                                            depth -= 1
                                            if depth == 0:
                                                paren_end = i
                                                break
                                    
                                    if paren_end != -1:
                                        # Extract the CHECK expression (content between parentheses)
                                        raw_check = rest[paren_start + 1:paren_end].strip()
                                        
                                        # CRITICAL FIX: Remove ALL type casts more aggressively
                                        # Pattern 1: ::identifier (e.g., ::text, ::integer)
                                        cleaned_check = re.sub(r'::\s*[a-zA-Z_][a-zA-Z0-9_]*', '', raw_check)
                                        # Pattern 2: ::identifier[] (e.g., ::text[])
                                        cleaned_check = re.sub(r'::\s*[a-zA-Z_][a-zA-Z0-9_]*\s*\[\s*\]', '', cleaned_check)
                                        # Pattern 3: Any remaining :: followed by anything up to space/paren/bracket
                                        cleaned_check = re.sub(r'::[^\s\),\]]+', '', cleaned_check)
                                        
                                        # âœ… Convert PostgreSQL ARRAY syntax to MySQL IN syntax
                                        if 'ARRAY[' in cleaned_check or '= ANY' in cleaned_check.upper():
                                            # Match ARRAY[...] with any var(--primaryText)space/casts
                                            array_match = re.search(r'ARRAY\s*\[\s*(.*?)\s*\]', cleaned_check, re.DOTALL)
                                            if array_match:
                                                array_content = array_match.group(1)
                                                
                                                # Extract just the quoted string values (already cleaned of type casts above)
                                                values = re.findall(r"'([^']*)'", array_content)
                                                
                                                if values:
                                                    # Build MySQL IN clause
                                                    mysql_in = "IN (" + ", ".join([f"'{v}'" for v in values]) + ")"
                                                    
                                                    # Replace the entire = ANY (ARRAY[...]) construct
                                                    cleaned_check = re.sub(
                                                        r'=\s*ANY\s*\(\s*\(?\s*ARRAY\s*\[.*?\]\s*\)?\s*\)',
                                                        mysql_in,
                                                        cleaned_check,
                                                        flags=re.DOTALL | re.IGNORECASE
                                                    )
                                                    
                                                    logger.debug(f"âœ… Converted PostgreSQL ARRAY to MySQL IN: {cleaned_check}")
                                        
                                        check_constraint = cleaned_check
                                        # Remove the entire CHECK clause from rest
                                        rest_without_check = rest[:check_start].strip() + ' ' + rest[paren_end + 1:].strip()
                                        rest_without_check = rest_without_check.strip()
                                    else:
                                        # Malformed CHECK - remove what we can
                                        rest_without_check = rest[:check_start].strip()
                                else:
                                    # No opening paren found - remove CHECK keyword
                                    rest_without_check = rest[:check_start].strip()

                        # Build column definition WITHOUT CHECK first
                        quoted_col_def = f'{self._quote_identifier(col_name)} {rest_without_check}'

                        # ✅ Add CHECK constraint at the end - ENSURE proper spacing and no duplicate constraints
                        if check_constraint:
                            # Remove any trailing incomplete CHECK syntax from rest_without_check

                            quoted_col_def = re.sub(r'\s+CHECK\s*$', '', quoted_col_def.strip())
                            # Add the complete CHECK constraint
                            quoted_col_def = quoted_col_def + f' CHECK ({check_constraint})'

                        quoted_new_columns.append(quoted_col_def)

                        new_column_info[col_name] = {
                            'definition': rest,
                            'has_pk': 'PRIMARY KEY' in rest_upper,
                            'has_not_null': 'NOT NULL' in rest_upper,
                            'has_autoincrement': 'AUTO_INCREMENT' in rest_upper,
                            'has_unique': 'UNIQUE' in rest_upper,
                            'type': rest_without_check.split()[0] if rest_without_check else 'VARCHAR(255)',
                            'check_constraint': check_constraint
                        }
                    else:
                        quoted_new_columns.append(self._quote_identifier(col_def))
                        new_column_info[col_def] = {
                            'definition': 'VARCHAR(255)',
                            'has_pk': False,
                            'has_not_null': False,
                            'type': 'VARCHAR(255)',
                            'check_constraint': None
                        }
            
                col_def = ', '.join(quoted_new_columns)
                quoted_temp = self._quote_identifier(temp_table_name)
            
                # ✅ Validate column definitions for MySQL
                for col_name, col_info in new_column_info.items():
                    if col_info.get('has_autoincrement', False):
                        if not col_info['has_pk'] and not col_info['has_unique']:
                            self.logger.error(f"Column {col_name} has AUTO_INCREMENT but no PRIMARY KEY or UNIQUE")
                            raise ValueError(f"AUTO_INCREMENT column '{col_name}' must have PRIMARY KEY or UNIQUE constraint")

                # Create temp table
                try:
                    self.logger.debug(f"Creating temp table: CREATE TABLE {quoted_temp} ({col_def})")
                    conn.execute(text(f"CREATE TABLE {quoted_temp} ({col_def})"))
                except Exception as e:
                    self.logger.error(f"Failed to create temp table with definition: {col_def}")
                    self.logger.error(f"Error: {str(e)}")
                    raise Exception(f"Failed to create table structure: {str(e)}")
            
                new_column_names = list(new_column_info.keys())
                old_column_names = list(old_columns.keys())
            
                column_mapping = {}
                used_old_columns = set()
            
                for new_col in new_column_names:
                    if new_col in old_columns:
                        column_mapping[new_col] = new_col
                        used_old_columns.add(new_col)
            
                unmapped_new = [c for c in new_column_names if c not in column_mapping]
                unmapped_old = [c for c in old_column_names if c not in used_old_columns]
            
                for i, new_col in enumerate(unmapped_new):
                    if i < len(unmapped_old):
                        column_mapping[new_col] = unmapped_old[i]
            
                select_parts = []
                insert_cols = []
            
                for new_col_name, old_col_name in column_mapping.items():
                    new_col_info = new_column_info[new_col_name]

                    # Skip AUTO_INCREMENT columns
                    if new_col_info.get('has_autoincrement', False):
                        self.logger.debug(f"Skipping AUTO_INCREMENT column {new_col_name} in copy")
                        continue

                    insert_cols.append(self._quote_identifier(new_col_name))
                    quoted_old = self._quote_identifier(old_col_name)

                    # Handle NOT NULL with COALESCE
                    if new_col_info['has_not_null'] and not new_col_info['has_pk'] and not new_col_info.get('has_autoincrement', False):
                        new_col_type = new_col_info['type'].upper()
                        if 'INT' in new_col_type:
                            select_parts.append(f"COALESCE({quoted_old}, 0)")
                        elif 'DOUBLE' in new_col_type or 'FLOAT' in new_col_type or 'DECIMAL' in new_col_type:
                            select_parts.append(f"COALESCE({quoted_old}, 0.0)")
                        else:
                            select_parts.append(f"COALESCE({quoted_old}, '')")
                    else:
                        select_parts.append(quoted_old)
            
                # ✅ Copy data with CHECK constraint error handling
                if select_parts:
                    select_cols = ', '.join(select_parts)
                    insert_cols_str = ', '.join(insert_cols)
                    quoted_old_table = self._quote_identifier(old_table_name)
                
                    copy_query = f"INSERT INTO {quoted_temp} ({insert_cols_str}) SELECT {select_cols} FROM {quoted_old_table}"
                    
                    try:
                        conn.execute(text(copy_query))
                    except Exception as copy_error:
                        # ✅ Better error message for CHECK constraint failures
                        if 'Check constraint' in str(copy_error) or 'constraint failed' in str(copy_error).lower():
                            failed_checks = []
                            for col_name, col_info in new_column_info.items():
                                if col_info.get('check_constraint'):
                                    failed_checks.append(f"{col_name}: {col_info['check_constraint']}")
                            
                            if failed_checks:
                                constraints_str = ', '.join(failed_checks)
                                raise Exception(
                                    f"Cannot apply CHECK constraint(s): {constraints_str}\n\n"
                                    f"Existing data violates the constraint. Please either:\n"
                                    f"1. Remove/modify the CHECK constraint\n"
                                    f"2. Delete or update rows that violate the constraint\n"
                                    f"3. Use a less restrictive constraint\n\n"
                                    f"Original error: {str(copy_error)}"
                                )
                        raise
            
                quoted_old = self._quote_identifier(old_table_name)
                quoted_new = self._quote_identifier(new_table_name)
                conn.execute(text(f"DROP TABLE {quoted_old}"))
                conn.execute(text(f"RENAME TABLE {quoted_temp} TO {quoted_new}"))
            
                conn.commit()
            
        except Exception as e:
            if self.engine:
                with self.engine.connect() as conn:
                    conn.rollback()
            raise Exception(f"Failed to modify table: {str(e)}")

    def create_default_table(self, table_name):
        """Create default table"""
        if not self.engine:
            raise Exception("No database selected")
        
        quoted_table = self._quote_identifier(table_name)
        try:
            with self.engine.connect() as conn:
                conn.execute(text(f"CREATE TABLE IF NOT EXISTS {quoted_table} (id INT AUTO_INCREMENT PRIMARY KEY)"))
                conn.commit()
        except Exception as e:
            self.logger.error(f"Error creating default table: {e}")
            raise
        
    def supports_joins(self):
        return True

    def supports_triggers(self):
        return True

    def supports_plsql(self):
        return False

    def execute_join(self, join_query):
        return self.execute_query(join_query)

    def create_trigger(self, trigger_name, table_name, trigger_timing, trigger_event, trigger_body):
        """Create trigger - FIXED to handle MySQL syntax properly"""
        with self.engine.connect() as conn:
            # Clean the trigger body - remove any trailing semicolons
            body = trigger_body.strip().rstrip(';')
            
            # Add semicolon to the body content
            body_with_semicolon = body + ';'
            
            # Build the complete trigger SQL
            trigger_sql = f"""
    CREATE TRIGGER {self._quote_identifier(trigger_name)}
    {trigger_timing} {trigger_event}
    ON {self._quote_identifier(table_name)}
    FOR EACH ROW
    BEGIN
        {body_with_semicolon}
    END
    """
            
            # Execute without text() wrapper to avoid escaping issues
            conn.connection.connection.cursor().execute(trigger_sql)
            conn.commit()
            
    def create_trigger_in_transaction(self, conn, trigger_name, table_name, timing, event, body):
        """
        Create trigger within an existing transaction (no commit).
        Used during imports/conversions to avoid closing the transaction.
        
        Args:
            conn: Active SQLAlchemy connection object
            trigger_name: Name of trigger
            table_name: Table to attach trigger to
            timing: BEFORE/AFTER
            event: INSERT/UPDATE/DELETE
            body: Trigger body (SQL statements)
        """
        logger.debug(f"[TRIGGER IN TRANSACTION] Creating: {trigger_name} on {table_name}")
        
        # Quote identifiers with backticks
        quoted_table = f"`{table_name}`"
        quoted_trigger = f"`{trigger_name}`"
        
        # Drop existing trigger first
        drop_sql = f"DROP TRIGGER IF EXISTS {quoted_trigger}"
        conn.execute(text(drop_sql))
        
        # Build trigger SQL
        trigger_sql = f"""CREATE TRIGGER {quoted_trigger}
        {timing.upper()} {event.upper()} ON {quoted_table}
        FOR EACH ROW
        BEGIN
            {body}
        END"""
        
        logger.debug(f"[TRIGGER IN TRANSACTION] SQL:\n{trigger_sql}")
        
        # Execute within provided transaction - NO COMMIT
        conn.execute(text(trigger_sql))
        
        logger.debug(f"[TRIGGER IN TRANSACTION] Created {trigger_name} (within transaction)")
        # DO NOT COMMIT - let the caller handle it

    def list_triggers(self, table_name=None):
        """List triggers with proper result handling"""
        if not self.engine:
            return []
    
        try:
            with self.engine.connect() as conn:
                if table_name:
                    result = conn.execute(text("""
                        SELECT TRIGGER_NAME, EVENT_OBJECT_TABLE, ACTION_STATEMENT, ACTION_TIMING, EVENT_MANIPULATION
                        FROM information_schema.TRIGGERS
                        WHERE TRIGGER_SCHEMA = DATABASE() AND EVENT_OBJECT_TABLE = :table
                    """), {'table': table_name})
                else:
                    result = conn.execute(text("""
                        SELECT TRIGGER_NAME, EVENT_OBJECT_TABLE, ACTION_STATEMENT, ACTION_TIMING, EVENT_MANIPULATION
                        FROM information_schema.TRIGGERS
                        WHERE TRIGGER_SCHEMA = DATABASE()
                    """))
            
                return [{
                    'name': r[0], 
                    'table': r[1], 
                    'sql': r[2], 
                    'timing': r[3], 
                    'event': r[4]
                } for r in result]
        except Exception as e:
            self.logger.error(f"Error listing triggers: {e}")
            return []

    def get_trigger_details(self, trigger_name):
        with self.engine.connect() as conn:
            result = conn.execute(text("""
                SELECT TRIGGER_NAME, EVENT_OBJECT_TABLE, ACTION_STATEMENT, ACTION_TIMING, EVENT_MANIPULATION
                FROM information_schema.TRIGGERS
                WHERE TRIGGER_SCHEMA = DATABASE() AND TRIGGER_NAME = :name
            """), {'name': trigger_name})
            row = result.fetchone()
            if row:
                return {'name': row[0], 'table': row[1], 'sql': row[2], 'timing': row[3], 'event': row[4]}
            return None

    def delete_trigger(self, trigger_name, table_name=None):
        with self.engine.connect() as conn:
            conn.execute(text(f"DROP TRIGGER IF EXISTS {self._quote_identifier(trigger_name)}"))
            conn.commit()
            
    def supports_aggregation(self):
        """Return True if database supports aggregation (GROUP BY, SUM, AVG, etc.)"""
        return True  # SQL databases support GROUP BY aggregation
            
    def supports_procedures(self):
        """MySQL supports stored procedures"""
        return True

    def get_procedure_placeholder_example(self):
        """Return MySQL-specific example"""
        return """-- MySQL Stored Procedure Examples

    -- Example 1: Simple procedure
    DELIMITER $
    CREATE PROCEDURE GetTopStudents()
    BEGIN
        SELECT name, marks FROM students WHERE marks > 85;
    END$
    DELIMITER ;

    -- Call it:
    CALL GetTopStudents();

    -- Example 2: Procedure with parameters
    DELIMITER $
    CREATE PROCEDURE UpdateMarks(IN student_id INT, IN new_marks INT)
    BEGIN
        UPDATE students SET marks = new_marks WHERE id = student_id;
    END$
    DELIMITER ;

    CALL UpdateMarks(1, 95);

    -- Example 3: Function (returns value)
    DELIMITER $
    CREATE FUNCTION GetAverageMarks() RETURNS DECIMAL(5,2)
    BEGIN
        DECLARE avg_marks DECIMAL(5,2);
        SELECT AVG(marks) INTO avg_marks FROM students;
        RETURN avg_marks;
    END$
    DELIMITER ;

    SELECT GetAverageMarks();"""
    
    def get_procedure_call_syntax(self):
        """Return the SQL syntax to call this type of object"""
        return "CALL {name}()"

    def execute_procedure(self, procedure_code):
        """
        Execute MySQL stored procedure code.
        Handles DELIMITER statements and CALL statements.
        """
        import re
        from sqlalchemy.sql import text
    
        try:
            # Remove comments
            procedure_code = re.sub(r'--.*', '', procedure_code, flags=re.MULTILINE)
            procedure_code = re.sub(r'/\*.*?\*/', '', procedure_code, flags=re.DOTALL)
        
            # Extract delimiter if specified
            delimiter_match = re.search(r'DELIMITER\s+(\S+)', procedure_code, re.IGNORECASE)
            custom_delimiter = delimiter_match.group(1) if delimiter_match else None

            # Remove DELIMITER declarations but keep the code
            procedure_code = re.sub(r'DELIMITER\s+\S+\s*[\r\n]*', '', procedure_code, flags=re.IGNORECASE)
        
            # Split by custom delimiter or semicolon
            if custom_delimiter:
                statements = [s.strip() for s in procedure_code.split(custom_delimiter) if s.strip()]
            else:
                statements = [s.strip() for s in procedure_code.split(';') if s.strip()]
        
            results = []
            call_results = []
        
            with self._get_connection() as conn:
                for stmt in statements:
                    if not stmt:
                        continue
                
                    stmt_upper = stmt.upper()
                
                    # Handle CALL statements (execute procedure)
                    if stmt_upper.startswith('CALL'):
                        try:
                            result = conn.execute(text(stmt))
                        
                            # Fetch results if any
                            if result.returns_rows:
                                rows = [dict(row._mapping) for row in result.fetchall()]
                                call_results.extend(rows)
                        
                            conn.commit()
                        except Exception as e:
                            # Some procedures don't return result sets
                            conn.commit()
                
                    # Handle CREATE PROCEDURE
                    elif 'CREATE PROCEDURE' in stmt_upper or 'CREATE FUNCTION' in stmt_upper:
                        # Drop existing procedure first (if exists)
                        proc_name_match = re.search(r'CREATE\s+(?:PROCEDURE|FUNCTION)\s+(\w+)', stmt, re.IGNORECASE)
                        if proc_name_match:
                            proc_name = proc_name_match.group(1)
                            try:
                                if 'PROCEDURE' in stmt_upper:
                                    conn.execute(text(f"DROP PROCEDURE IF EXISTS {proc_name}"))
                                else:
                                    conn.execute(text(f"DROP FUNCTION IF EXISTS {proc_name}"))
                            except:
                                pass
                    
                        conn.execute(text(stmt))
                        conn.commit()
                        results.append({'status': f'Procedure/Function created successfully'})
                
                    # Handle DROP statements
                    elif stmt_upper.startswith('DROP'):
                        conn.execute(text(stmt))
                        conn.commit()
                        results.append({'status': 'Dropped successfully'})
                
                    # Other statements (SELECT, UPDATE, etc.)
                    else:
                        result = conn.execute(text(stmt))
                        
                        if result.returns_rows:
                            rows = [dict(row._mapping) for row in result.fetchall()]
                            results.append(rows)
                        else:
                            conn.commit()
                            results.append({'rows_affected': result.rowcount})
        
            # If we have CALL results, return those
            if call_results:
                return call_results
        
            # Otherwise return creation status
            return results if results else [{'status': 'Procedure executed successfully'}]
        
        except Exception as e:
            import logging
            logging.error(f"MySQL procedure execution error: {str(e)}")
            raise Exception(f"Procedure execution failed: {str(e)}")

    def list_procedures(self):
        """List all stored procedures in current database"""
        try:
            with self._get_connection() as conn:
                result = conn.execute(text("""
                    SELECT 
                        ROUTINE_NAME as name,
                        ROUTINE_TYPE as type,
                        CREATED as created,
                        LAST_ALTERED as modified
                    FROM information_schema.ROUTINES
                    WHERE ROUTINE_SCHEMA = DATABASE()
                    ORDER BY ROUTINE_NAME
                """))
            
                procedures = []
                for row in result.fetchall():
                    procedures.append({
                        'name': row[0],
                        'type': row[1],  # PROCEDURE or FUNCTION
                        'created': str(row[2]) if row[2] else None,
                        'modified': str(row[3]) if row[3] else None
                    })
            
                return procedures
        except Exception as e:
            import logging
            logging.error(f"Error listing procedures: {str(e)}")
            return []

    def get_procedure_definition(self, procedure_name):
        """Get the definition of a stored procedure - CLEANED for re-execution"""
        try:
            with self._get_connection() as conn:
                # Try PROCEDURE first
                try:
                    result = conn.execute(text(f"SHOW CREATE PROCEDURE {procedure_name}"))
                    row = result.fetchone()
                    if row:
                        raw_def = row[2]  # Third column is the definition
                        
                        # ✅ CRITICAL: Clean up the definition for re-execution
                        cleaned_def = self._clean_procedure_definition(raw_def)
                        return cleaned_def
                except:
                    pass
                
                # Try FUNCTION
                try:
                    result = conn.execute(text(f"SHOW CREATE FUNCTION {procedure_name}"))
                    row = result.fetchone()
                    if row:
                        raw_def = row[2]
                        cleaned_def = self._clean_procedure_definition(raw_def)
                        return cleaned_def
                except:
                    pass
                    
            return None
        except Exception as e:
            self.logger.error(f"Error getting procedure definition: {e}")
            return None

    def _clean_procedure_definition(self, raw_definition):
        """
        Clean MySQL procedure definition for re-execution:
        - Remove DEFINER clause (causes permission issues)
        - Ensure proper END delimiter
        - Add DELIMITER statements if needed
        """
        import re
        
        # Remove DEFINER clause (e.g., DEFINER=`root`@`localhost`)
        cleaned = re.sub(r'DEFINER\s*=\s*`[^`]+`@`[^`]+`\s+', '', raw_definition, flags=re.IGNORECASE)
        
        # Ensure it ends with END and semicolon
        cleaned = cleaned.rstrip()
        if not cleaned.upper().endswith('END'):
            cleaned += '\nEND'
        
        # Wrap with DELIMITER statements for safety
        result = f"""DELIMITER $$
    {cleaned}$$
    DELIMITER ;"""
        
        return result

    def drop_procedure(self, procedure_name, is_function=False):
        """Drop a stored procedure or function"""
        try:
            with self._get_connection() as conn:
                if is_function:
                    conn.execute(text(f"DROP FUNCTION IF EXISTS {procedure_name}"))
                else:
                    conn.execute(text(f"DROP PROCEDURE IF EXISTS {procedure_name}"))
                conn.commit()
            return True
        except Exception as e:
            import logging
            logging.error(f"Error dropping procedure: {str(e)}")
            raise
        
    def convert_trigger_syntax(self, trigger_body, trigger_event, table_name):
        """
        Convert PostgreSQL trigger syntax to MySQL.
        
        PostgreSQL → MySQL conversions:
        - variable := value → SET variable = value
        - Remove RETURN NEW/OLD (not needed in MySQL)
        """
        import re
        
        # Convert PostgreSQL assignment to MySQL SET
        # Pattern: NEW.column := value
        converted = re.sub(
            r'(NEW\.\w+)\s*:=\s*',
            r'SET \1 = ',
            trigger_body,
            flags=re.IGNORECASE
        )
        
        # Remove RETURN statements (MySQL doesn't need them)
        converted = re.sub(r'\bRETURN\s+(NEW|OLD)\s*;?', '', converted, flags=re.IGNORECASE)
        
        return converted.strip()
        
    def convert_procedure_syntax(self, procedure_code, proc_name, proc_type):
        """Enhanced conversion with proper RETURNS TABLE handling"""
        import re
        
        code_upper = procedure_code.upper()
        
        if 'LANGUAGE PLPGSQL' in code_upper or '$$ LANGUAGE' in code_upper:
            # PostgreSQL → MySQL conversion
            cleaned = procedure_code
            
            # Remove PostgreSQL-specific syntax
            cleaned = re.sub(r'LANGUAGE\s+plpgsql\s*;?', '', cleaned, flags=re.IGNORECASE)
            cleaned = re.sub(r'\$\$', '', cleaned)
            
            # Extract RETURNS TABLE clause
            returns_table_match = re.search(
                r'RETURNS\s+TABLE\s*\(([^)]+)\)',
                cleaned,
                re.IGNORECASE | re.DOTALL
            )
            
            if returns_table_match:
                # Extract body
                body_match = re.search(r'BEGIN\s+(.*?)\s+END', cleaned, re.DOTALL | re.IGNORECASE)
                if body_match:
                    body = body_match.group(1).strip()
                    
                    # Convert RETURN QUERY SELECT to just SELECT
                    body = re.sub(r'RETURN\s+QUERY\s+', '', body, flags=re.IGNORECASE)
                    
                    # Build MySQL procedure
                    mysql_proc = f"""DELIMITER $$
    CREATE PROCEDURE {proc_name}()
    BEGIN
        {body}
    END$$
    DELIMITER ;"""
                    return mysql_proc
            
            # Fallback
            return procedure_code
        
        # Already MySQL format
        return procedure_code

    def _convert_postgresql_to_mysql(self, pg_code, proc_name, proc_type):
        """
        Convert PostgreSQL function to MySQL procedure/function.
        
        PostgreSQL → MySQL conversions:
        - RETURNS TABLE(...) → OUT parameters or result set
        - RETURN QUERY SELECT → SELECT statement
        - $$ delimiters → MySQL DELIMITER syntax
        - LANGUAGE plpgsql → Remove (not needed)
        - :: type casts → CAST() or remove
        """
        import re
        
        # Remove PostgreSQL-specific syntax
        cleaned = pg_code
        
        # Remove LANGUAGE clause
        cleaned = re.sub(r'LANGUAGE\s+plpgsql\s*;?', '', cleaned, flags=re.IGNORECASE)
        
        # Remove dollar-quote delimiters
        cleaned = re.sub(r'\$\$', '', cleaned)
        
        # ✅ CRITICAL FIX: Remove ALL type casts MORE AGGRESSIVELY
        # This handles chained casts like ::TEXT::TEXT
        # Pattern 1: Remove all chained type casts (::type::type::type...)
        while re.search(r'::\s*[a-zA-Z_][a-zA-Z0-9_]*(?:\s*\[\s*\])?', cleaned):
            cleaned = re.sub(r'::\s*[a-zA-Z_][a-zA-Z0-9_]*(?:\s*\[\s*\])?', '', cleaned)
        
        # Pattern 2: Clean up any remaining :: followed by anything
        cleaned = re.sub(r'::[^\s\),\]]+', '', cleaned)
        
        # Convert RETURNS TABLE to procedure with SELECT
        returns_table_match = re.search(
            r'RETURNS\s+TABLE\s*\(([^)]+)\)',
            cleaned,
            re.IGNORECASE | re.DOTALL
        )
        
        if returns_table_match:
            # This is a table-returning function - convert to PROCEDURE
            table_cols = returns_table_match.group(1)
            
            # Extract function body
            body_match = re.search(
                r'BEGIN\s+(.*?)\s+END',
                cleaned,
                re.DOTALL | re.IGNORECASE
            )
            
            if body_match:
                body = body_match.group(1).strip()
                
                # Convert RETURN QUERY SELECT to just SELECT
                body = re.sub(r'RETURN\s+QUERY\s+', '', body, flags=re.IGNORECASE)
                
                # Remove standalone RETURN statements (not followed by QUERY)
                body = re.sub(r'\bRETURN\s+(?!QUERY\b)[^;]+;', '', body, flags=re.IGNORECASE)

                # Remove standalone RETURN statements (not followed by QUERY)
                body = re.sub(r'\bRETURN\s+(?!QUERY\b)[^;]+;', '', body, flags=re.IGNORECASE)
                
                # Extract parameters (before RETURNS)
                param_match = re.search(
                    r'CREATE\s+(?:OR\s+REPLACE\s+)?FUNCTION\s+\w+\s*\(([^)]*)\)',
                    cleaned,
                    re.IGNORECASE
                )
                params = param_match.group(1).strip() if param_match else ''
                
                # Convert parameter types (PostgreSQL → MySQL)
                if params:
                    # Remove DEFAULT clauses (MySQL uses different syntax)
                    params = re.sub(r'DEFAULT\s+[^,)]+', '', params, flags=re.IGNORECASE)
                    # Convert TEXT to VARCHAR(255)
                    params = re.sub(r'\bTEXT\b', 'VARCHAR(255)', params, flags=re.IGNORECASE)
                    # Convert type casts (:: → nothing, handled in body)
                    params = re.sub(r'::\w+', '', params)
                
                # Build MySQL procedure
                mysql_proc = f"""DELIMITER $$
    CREATE PROCEDURE {proc_name}({params})
    BEGIN
        {body}
    END$$
    DELIMITER ;"""
                
                return mysql_proc
        
        # Convert RETURNS scalar type to FUNCTION
        returns_scalar_match = re.search(
            r'RETURNS\s+(\w+)',
            cleaned,
            re.IGNORECASE
        )
        
        if returns_scalar_match and 'TABLE' not in returns_scalar_match.group(0).upper():
            return_type = returns_scalar_match.group(1)
            
            # Convert PostgreSQL types to MySQL types
            type_mapping = {
                'TEXT': 'VARCHAR(255)',
                'INTEGER': 'INT',
                'BOOLEAN': 'TINYINT(1)',
                'TIMESTAMP': 'DATETIME'
            }
            return_type = type_mapping.get(return_type.upper(), return_type)
            
            # Extract function body
            body_match = re.search(
                r'BEGIN\s+(.*?)\s+END',
                cleaned,
                re.DOTALL | re.IGNORECASE
            )
            
            if body_match:
                body = body_match.group(1).strip()
                
                # Convert RETURN to MySQL format
                body = re.sub(
                    r'RETURN\s+([^;]+);',
                    r'RETURN \1;',
                    body,
                    flags=re.IGNORECASE
                )
                
                # Extract parameters
                param_match = re.search(
                    r'CREATE\s+(?:OR\s+REPLACE\s+)?FUNCTION\s+\w+\s*\(([^)]*)\)',
                    cleaned,
                    re.IGNORECASE
                )
                params = param_match.group(1).strip() if param_match else ''
                
                # Convert parameter types
                if params:
                    params = re.sub(r'DEFAULT\s+[^,)]+', '', params, flags=re.IGNORECASE)
                    params = re.sub(r'\bTEXT\b', 'VARCHAR(255)', params, flags=re.IGNORECASE)
                    params = re.sub(r'::\w+', '', params)
                
                # Build MySQL function
                mysql_func = f"""DELIMITER $$
    CREATE FUNCTION {proc_name}({params}) RETURNS {return_type}
    BEGIN
        {body}
    END$$
    DELIMITER ;"""
                
                return mysql_func
        
        # Fallback: wrap in DELIMITER and clean up
        mysql_code = f"""DELIMITER $$
    {cleaned.strip()}$$
    DELIMITER ;"""
        
        return mysql_code

    def execute_plsql(self, plsql_code):
        raise NotImplementedError("MySQL doesn't support PL/SQL (use stored procedures instead)")
    
    def supports_user_management(self):
        """MySQL supports user management"""
        return True

    def list_users(self):
        """List all MySQL users"""
        if not self.engine:
            return []
    
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text("""
                    SELECT User, Host 
                    FROM mysql.user 
                    WHERE User != '' 
                    ORDER BY User
                """))
            
                users = []
                for row in result.fetchall():
                    username = f"{row[0]}@{row[1]}"
                
                    # Get privileges
                    priv_result = conn.execute(text(f"""
                        SHOW GRANTS FOR '{row[0]}'@'{row[1]}'
                    """))
                
                    privileges = []
                    has_password = False
                
                    for priv_row in priv_result.fetchall():
                        grant_text = priv_row[0]
                        if 'ALL PRIVILEGES' in grant_text:
                            privileges = ['ALL']
                            break
                        if 'SELECT' in grant_text:
                            privileges.append('SELECT')
                        if 'INSERT' in grant_text:
                            privileges.append('INSERT')
                        if 'UPDATE' in grant_text:
                            privileges.append('UPDATE')
                        if 'DELETE' in grant_text:
                            privileges.append('DELETE')
                        if 'CREATE' in grant_text:
                            privileges.append('CREATE')
                        if 'DROP' in grant_text:
                            privileges.append('DROP')
                    
                        pwd_result = conn.execute(text(f"""
                            SELECT authentication_string 
                            FROM mysql.user 
                            WHERE User = '{row[0]}' AND Host = '{row[1]}'
                        """))
                        pwd = pwd_result.fetchone()[0]
                        has_password = pwd is not None and pwd.strip() != ''

                
                    users.append({
                        'username': username,
                        'host': row[1],
                        'has_password': has_password,
                        'privileges': list(set(privileges)) or ['USAGE']
                    })
            
                return users
        except Exception as e:
            import logging
            logging.error(f"Error listing MySQL users: {str(e)}")
            return []

    def create_user(self, username, password, privileges):
        """Create a new MySQL user"""
        if not self.engine:
            raise Exception("No database connected")
    
        # Parse username@host format
        if '@' in username:
            user, host = username.split('@', 1)
        else:
            user = username
            host = '%'  # Allow from any host
    
        with self.engine.connect() as conn:
            # Create user
            if password:
                conn.execute(text(f"CREATE USER '{user}'@'{host}' IDENTIFIED BY '{password}'"))
            else:
                conn.execute(text(f"CREATE USER '{user}'@'{host}'"))
        
            # Grant privileges
            if 'ALL' in privileges:
                conn.execute(text(f"GRANT ALL PRIVILEGES ON *.* TO '{user}'@'{host}'"))
            else:
                if privileges:
                    priv_str = ', '.join(privileges)
                    conn.execute(text(f"GRANT {priv_str} ON *.* TO '{user}'@'{host}'"))
        
            conn.execute(text("FLUSH PRIVILEGES"))
            conn.commit()

    def update_user(self, username, password, privileges):
        """Update MySQL user credentials/privileges"""
        if not self.engine:
            raise Exception("No database connected")
    
        # Parse username@host
        if '@' in username:
            user, host = username.split('@', 1)
        else:
            user = username
            host = '%'
    
        with self.engine.connect() as conn:
            # Update password if provided
            if password:
                conn.execute(text(f"ALTER USER '{user}'@'{host}' IDENTIFIED BY '{password}'"))
        
            # Revoke all privileges first
            conn.execute(text(f"REVOKE ALL PRIVILEGES ON *.* FROM '{user}'@'{host}'"))
        
            # Grant new privileges
            if 'ALL' in privileges:
                conn.execute(text(f"GRANT ALL PRIVILEGES ON *.* TO '{user}'@'{host}'"))
            else:
                if privileges:
                    priv_str = ', '.join(privileges)
                    conn.execute(text(f"GRANT {priv_str} ON *.* TO '{user}'@'{host}'"))
        
            conn.execute(text("FLUSH PRIVILEGES"))
            conn.commit()

    def delete_user(self, username):
        """Delete a MySQL user"""
        if not self.engine:
            raise Exception("No database connected")
    
        # Parse username@host
        if '@' in username:
            user, host = username.split('@', 1)
        else:
            user = username
            host = '%'
    
        with self.engine.connect() as conn:
            conn.execute(text(f"DROP USER '{user}'@'{host}'"))
            conn.execute(text("FLUSH PRIVILEGES"))
            conn.commit()

    def get_user_privileges(self, username):
        """Get privileges for a specific user"""
        if not self.engine:
            return []
    
        # Parse username@host
        if '@' in username:
            user, host = username.split('@', 1)
        else:
            user = username
            host = '%'
    
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text(f"SHOW GRANTS FOR '{user}'@'{host}'"))
            
                privileges = []
                for row in result.fetchall():
                    grant_text = row[0]
                    if 'ALL PRIVILEGES' in grant_text:
                        return ['ALL']
                    if 'SELECT' in grant_text:
                        privileges.append('SELECT')
                    if 'INSERT' in grant_text:
                        privileges.append('INSERT')
                    if 'UPDATE' in grant_text:
                        privileges.append('UPDATE')
                    if 'DELETE' in grant_text:
                        privileges.append('DELETE')
                    if 'CREATE' in grant_text:
                        privileges.append('CREATE')
                    if 'DROP' in grant_text:
                        privileges.append('DROP')
            
                return list(set(privileges))
        except:
            return []

    def get_user_connection_info(self, username):
        """Return connection info for a specific user"""
        # Parse username@host
        if '@' in username:
            user, host = username.split('@', 1)
        else:
            user = username
            host = 'localhost'
    
        current_db = self.current_db or 'your_database'
    
        return {
            'connection_string': f'mysql://{user}:YOUR_PASSWORD@{host}/{current_db}',
            'test_code': f'''import pymysql

    # Replace YOUR_PASSWORD with the actual password
    conn = pymysql.connect(
        host='{host}',
        user='{user}',
        password='YOUR_PASSWORD',
        database='{current_db}'
    )

    cursor = conn.cursor()
    cursor.execute("SELECT DATABASE()")
    print(f"Connected to: {{cursor.fetchone()[0]}}")

    cursor.execute("SHOW TABLES")
    tables = [row[0] for row in cursor.fetchall()]
    print(f"Tables: {{tables}}")

    conn.close()''',
            'notes': [
                'Replace YOUR_PASSWORD with the actual password for this user',
                'Ensure MySQL server is running and accessible from your host'
            ]
        }
        
    def clear_credentials(self):
        """Clear stored credentials from keyring"""
        try:
            keyring.delete_password(self.KEYRING_SERVICE, self.KEYRING_USERNAME_KEY)
            keyring.delete_password(self.KEYRING_SERVICE, self.KEYRING_PASSWORD_KEY)
            keyring.delete_password(self.KEYRING_SERVICE, self.KEYRING_HOST_KEY)
            keyring.delete_password(self.KEYRING_SERVICE, self.KEYRING_PORT_KEY)
            self._credentials_valid = False
            self.username = None
            self.password = None
            self.logger.info("MySQL credentials cleared successfully")
        except Exception as e:
            self.logger.error(f"Failed to clear credentials: {e}")
            
    def build_column_definitions(self, schema, quote=True):
        """Build column definition strings for table creation"""
        columns_def = []
        for col in schema:
            col_name = self._quote_identifier(col['name']) if quote else col['name']
            col_type = col['type']
            
            # Ensure VARCHAR has size specification
            if col_type.upper().startswith('VARCHAR'):
                if '(' not in col_type:
                    col_type = 'VARCHAR(255)'
            
            col_def = f"{col_name} {col_type}"
            
            if col.get('pk'):
                if col.get('autoincrement'):
                    col_def += " AUTO_INCREMENT PRIMARY KEY"
                else:
                    col_def += " PRIMARY KEY"
            else:
                if col.get('autoincrement'):
                    col_def += " AUTO_INCREMENT UNIQUE NOT NULL"
                elif col.get('notnull'):
                    col_def += " NOT NULL"
                if col.get('unique') and not col.get('autoincrement'):
                    col_def += " UNIQUE"
            
            # ✅ ADD CHECK CONSTRAINT
            if col.get('check_constraint'):
                check_expr = col['check_constraint']
                # Ensure column reference uses backticks for MySQL
                check_with_backticks = re.sub(
                    r'\b' + re.escape(col['name']) + r'\b',
                    f'`{col["name"]}`',
                    check_expr
                )
                col_def += f' CHECK ({check_with_backticks})'
                self.logger.debug(f"Added CHECK constraint: {col['name']} CHECK ({check_with_backticks})")

            columns_def.append(col_def)
        
        return columns_def
    
    def build_column_definition_for_create(self, quoted_name, type_with_length, is_pk, is_not_null, is_autoincrement, is_unique, table_name=None, has_composite_pk=False):
        """Build column definition for CREATE TABLE"""
        col_def = f"{quoted_name} {type_with_length}"
                
        if is_pk and not has_composite_pk:
            if is_autoincrement:
                col_def += " AUTO_INCREMENT PRIMARY KEY"
            else:
                col_def += " PRIMARY KEY"
        elif is_pk and has_composite_pk:
            # Part of composite key - don't add PRIMARY KEY here, it will be added as a table constraint
            col_def += " NOT NULL"  # PK columns are always NOT NULL
        else:
            if is_autoincrement:
                col_def += " AUTO_INCREMENT UNIQUE NOT NULL"
            elif is_not_null:
                col_def += " NOT NULL"
            if is_unique and not is_autoincrement:
                col_def += " UNIQUE"
        
        return col_def
    
    def reset_sequence_after_copy(self, table_name, column_name):
        """Reset AUTO_INCREMENT to max value + 1 after copying data"""
        try:
            quoted_table = self._quote_identifier(table_name)
            quoted_col = self._quote_identifier(column_name)
            
            with self.engine.connect() as conn:
                # Get max value
                max_val_query = f"SELECT MAX({quoted_col}) FROM {quoted_table}"
                result = conn.execute(text(max_val_query)).fetchone()
                max_val = result[0] if result and result[0] else 0
                
                # Reset AUTO_INCREMENT
                conn.execute(text(f"ALTER TABLE {quoted_table} AUTO_INCREMENT = {max_val + 1}"))
                conn.commit()
                
                self.logger.debug(f"Reset AUTO_INCREMENT for {table_name}.{column_name} to {max_val + 1}")
        except Exception as e:
            self.logger.warning(f"Failed to reset AUTO_INCREMENT: {e}")
            raise
        
    def get_foreign_keys(self, table_name):
        """Get foreign key constraints for a table"""
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text("""
                    SELECT
                        CONSTRAINT_NAME,
                        COLUMN_NAME,
                        REFERENCED_TABLE_NAME,
                        REFERENCED_COLUMN_NAME,
                        UPDATE_RULE,
                        DELETE_RULE
                    FROM information_schema.KEY_COLUMN_USAGE
                    WHERE TABLE_SCHEMA = DATABASE()
                        AND TABLE_NAME = :table_name
                        AND REFERENCED_TABLE_NAME IS NOT NULL
                """), {'table_name': table_name})
                
                return [{
                    'constraint_name': row[0],
                    'column_name': row[1],
                    'foreign_table': row[2],
                    'foreign_column': row[3],
                    'on_update': row[4] or 'NO ACTION',
                    'on_delete': row[5] or 'NO ACTION'
                } for row in result.fetchall()]
        except Exception as e:
            self.logger.error(f"Failed to get foreign keys: {e}")
            return []

    def create_foreign_key(self, table_name, constraint_name, column_name,
                        foreign_table, foreign_column, on_update, on_delete):
        """Create a foreign key constraint"""
        quoted_table = self._quote_identifier(table_name)
        quoted_col = self._quote_identifier(column_name)
        quoted_fk_table = self._quote_identifier(foreign_table)
        quoted_fk_col = self._quote_identifier(foreign_column)
        
        sql = f"""
            ALTER TABLE {quoted_table}
            ADD CONSTRAINT {constraint_name}
            FOREIGN KEY ({quoted_col})
            REFERENCES {quoted_fk_table}({quoted_fk_col})
            ON UPDATE {on_update}
            ON DELETE {on_delete}
        """
        
        with self.engine.connect() as conn:
            conn.execute(text(sql))
            conn.commit()
            
    def get_views(self):
        """Get all views in current database"""
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text("""
                    SELECT TABLE_NAME, VIEW_DEFINITION
                    FROM information_schema.VIEWS
                    WHERE TABLE_SCHEMA = DATABASE()
                """))
                
                return [{'name': row[0], 'definition': row[1]} for row in result.fetchall()]
        except Exception as e:
            self.logger.error(f"Failed to get views: {e}")
            return []

    def create_view(self, view_name, view_definition):
        """Create a view"""
        quoted_view = self._quote_identifier(view_name)
        sql = f"CREATE VIEW {quoted_view} AS {view_definition}"
        
        with self.engine.connect() as conn:
            conn.execute(text(sql))
            conn.commit()
            
    def _validation_to_check(validation_rules, column_name):
        """
        Convert NoSQL validation rules to SQL CHECK constraint expression.
        ENHANCED: Database-agnostic output, handles all validation types
        
        Outputs generic SQL that works across databases (uses standard SQL functions)
        """
        constraints = []
        
        bson_type = validation_rules.get('bsonType')
        is_numeric = (isinstance(bson_type, list) and 
                    any(t in ['int', 'long', 'double', 'decimal'] for t in bson_type) or 
                    bson_type in ['int', 'long', 'double', 'decimal'])
        is_string = bson_type == 'string'
        
        logger.debug(f"[Validation→CHECK] Converting for '{column_name}': {validation_rules}")
        logger.debug(f"[Validation→CHECK] Type detection: is_numeric={is_numeric}, is_string={is_string}")
        
        # 1. Required (NOT NULL)
        if validation_rules.get('required'):
            constraints.append(f'{column_name} IS NOT NULL')
            logger.debug(f"[Validation→CHECK] Added: NOT NULL")
        
        # 2. Numeric constraints (minimum/maximum)
        if 'minimum' in validation_rules:
            min_val = validation_rules['minimum']
            if is_numeric:
                constraints.append(f'{column_name} >= {min_val}')
                logger.debug(f"[Validation→CHECK] Added: >= {min_val}")
            elif is_string:
                # Ambiguous: might mean string length
                constraints.append(f'CHAR_LENGTH({column_name}) >= {int(min_val)}')
                logger.debug(f"[Validation→CHECK] Added: CHAR_LENGTH >= {int(min_val)}")
        
        if 'maximum' in validation_rules:
            max_val = validation_rules['maximum']
            if is_numeric:
                constraints.append(f'{column_name} <= {max_val}')
                logger.debug(f"[Validation→CHECK] Added: <= {max_val}")
            elif is_string:
                constraints.append(f'CHAR_LENGTH({column_name}) <= {int(max_val)}')
                logger.debug(f"[Validation→CHECK] Added: CHAR_LENGTH <= {int(max_val)}")
        
        # 3. String length constraints (explicit)
        if 'minLength' in validation_rules:
            constraints.append(f'CHAR_LENGTH({column_name}) >= {validation_rules["minLength"]}')
            logger.debug(f"[Validation→CHECK] Added: minLength={validation_rules['minLength']}")
        
        if 'maxLength' in validation_rules:
            constraints.append(f'CHAR_LENGTH({column_name}) <= {validation_rules["maxLength"]}')
            logger.debug(f"[Validation→CHECK] Added: maxLength={validation_rules['maxLength']}")
        
        # 4. Enum constraint
        if 'enum' in validation_rules:
            enum_values = validation_rules['enum']
            quoted_values = []
            for val in enum_values:
                if isinstance(val, str):
                    escaped = val.replace("'", "''")
                    quoted_values.append(f"'{escaped}'")
                else:
                    quoted_values.append(str(val))
            enum_str = ', '.join(quoted_values)
            constraints.append(f'{column_name} IN ({enum_str})')
            logger.debug(f"[Validation→CHECK] Added: IN ({enum_str})")
        
        # 5. Pattern constraint (use standard SQL LIKE for compatibility)
        if 'pattern' in validation_rules:
            pattern = validation_rules['pattern']
            # Convert regex to SQL LIKE pattern if possible
            # Remove anchors (^ and $)
            like_pattern = pattern.strip('^$')
            # Convert .* → % and . → _
            like_pattern = like_pattern.replace('.*', '%').replace('.', '_')
            constraints.append(f"{column_name} LIKE '{like_pattern}'")
            logger.debug(f"[Validation→CHECK] Added: LIKE '{like_pattern}'")
        
        # Skip non-SQL types (array, object, date)
        if bson_type in ['array', 'object', 'date'] and not constraints:
            logger.debug(f"[Validation→CHECK] Skipping - type {bson_type} not enforceable in SQL")
            return None
        
        result = ' AND '.join(constraints) if constraints else None
        logger.debug(f"[Validation→CHECK] Final CHECK expression: {result}")
        return result
            
    def apply_validation_rules(self, table_name, validation_rules):
        """
        Apply structured validation rules as MySQL CHECK constraints during import.
        Now with LOUD debugging to see exactly what's happening.
        """
        if not validation_rules:
            self.logger.info("No validation rules to apply — skipping.")
            return

        self.logger.info(f"🔮 APPLYING VALIDATION RULES TO TABLE '{table_name}'")
        self.logger.info(f"Rules received: {validation_rules}")

        successful = 0
        failed = 0

        for col_name, rules in validation_rules.items():
            self.logger.debug(f"Processing column '{col_name}' with rules: {rules}")

            try:
                # Convert to SQL CHECK expression
                check_expr = self._validation_to_check(rules, col_name)

                if not check_expr:
                    self.logger.debug(f"No enforceable CHECK expression generated for '{col_name}' — skipping")
                    continue

                self.logger.info(f"✅ Generated CHECK expression for '{col_name}': {check_expr}")

                # NOW CALL THE ACTUAL CONSTRAINT ADDER
                self.logger.info(f"Calling add_check_constraint_to_existing_table('{table_name}', '{col_name}', '{check_expr}')")
                self.add_check_constraint_to_existing_table(table_name, col_name, check_expr)

                successful += 1
                self.logger.info(f"🎉 Successfully applied CHECK constraint on '{col_name}'")

            except Exception as e:
                failed += 1
                self.logger.error(f"💥 FAILED to apply rule on '{col_name}': {str(e)}")
                import traceback
                self.logger.error(f"Traceback:\n{traceback.format_exc()}")

        self.logger.info(f"🏁 Validation rules complete: {successful} succeeded, {failed} failed")

        if failed > 0:
            self.logger.warning("Some validation rules could not be applied — possibly due to existing data violating them")
            
    def add_check_constraint_to_existing_table(self, table_name, column_name, expression, conn=None):
        """Add CHECK constraint to an existing table via ALTER TABLE"""
        if not self.engine:
            raise Exception("No database selected")
        
        self.logger.info(f"🔥 STARTING ADD CHECK CONSTRAINT on {table_name}.{column_name}")
        self.logger.info(f"Expression: {expression}")
        
        try:
            # Validate expression syntax
            if not self.validate_check_constraint(expression):
                raise ValueError("Invalid CHECK constraint expression")
            
            quoted_table = self._quote_identifier(table_name)
            constraint_name = f"chk_{table_name}_{column_name}_{os.urandom(4).hex()}"
            
            # Add CHECK constraint directly
            alter_sql = f"""
                ALTER TABLE {quoted_table}
                ADD CONSTRAINT {constraint_name}
                CHECK ({expression})
            """
            self.logger.info(f"SQL: {alter_sql.strip()}")
            
            # ✅ CRITICAL FIX: Use provided connection OR create new one with longer timeout
            if conn:
                conn.execute(text(alter_sql))
                conn.commit()
            else:
                # Create new connection with extended timeout for ALTER TABLE
                with self.engine.connect() as new_conn:
                    # Set longer timeout for this specific operation
                    new_conn.execute(text("SET SESSION wait_timeout = 300"))
                    new_conn.execute(text("SET SESSION interactive_timeout = 300"))
                    new_conn.execute(text(alter_sql))
                    new_conn.commit()

            self.logger.info(f"SUCCESS: Added CHECK constraint on {column_name}")
            
        except Exception as e:
            error_str = str(e).lower()
            
            # If constraint violates existing data, provide helpful message
            if 'check constraint' in error_str or 'constraint fails' in error_str:
                self.logger.error(f"CHECK constraint violates existing data: {expression}")
                raise Exception(
                    f"Cannot apply CHECK constraint on '{column_name}': {expression}\n"
                    f"Existing data violates this constraint. Please fix the data first."
                )
            
            # Other errors
            self.logger.error(f"FAILED to add CHECK constraint: {e}")
            import traceback
            self.logger.error(f"Full traceback:\n{traceback.format_exc()}")
            raise
            
    def copy_table(self, source_table, dest_table):
        """Copy table structure, data, and triggers - CHECK constraints applied AFTER data"""
        schema = self.get_table_schema(source_table)
        data_rows = self.read(source_table)
        
        # ✅ STEP 1: Extract CHECK constraints and build columns WITHOUT them
        check_constraints_to_apply = []
        columns_def = []
        
        for col in schema:
            # Save CHECK constraint if present
            if col.get('check_constraint'):
                check_constraints_to_apply.append({
                    'column': col['name'],
                    'expression': col['check_constraint']
                })
            
            # Build column definition WITHOUT CHECK constraint
            col_name = self._quote_identifier(col['name'])
            col_type = col['type'].upper()  # Make it uppercase for easy matching

            # === MAP COMMON SQL TYPES TO MYSQL EQUIVALENTS ===
            if col_type == 'INTEGER':
                col_type = 'INT'
            elif col_type == 'BOOLEAN':
                col_type = 'TINYINT(1)'
            elif col_type in ['TEXT', 'MEDIUMTEXT', 'LONGTEXT', 'TINYTEXT'] and col.get('pk'):
                col_type = 'VARCHAR(255)'  # Our previous fix for TEXT PK
                self.logger.info(f"Converted TEXT primary key to VARCHAR(255) for MySQL")
            # ================================================
            
            # Ensure VARCHAR has size specification
            if col_type.upper().startswith('VARCHAR') and '(' not in col_type:
                col_type = 'VARCHAR(255)'
                
            # === FIX TEXT PRIMARY KEY FOR MYSQL ===
            if col.get('pk') and col_type.upper() in ['TEXT', 'MEDIUMTEXT', 'LONGTEXT', 'TINYTEXT']:
                col_type = 'VARCHAR(255)'  # Safe length for MySQL indexes (utf8mb4 compatible)
                self.logger.info(f"Auto-converted TEXT PK column '{col['name']}' to VARCHAR(255) for MySQL compatibility")
            # ======================================
            
            col_def = f"{col_name} {col_type}"
            
            if col.get('pk'):
                if col.get('autoincrement'):
                    col_def += " AUTO_INCREMENT PRIMARY KEY"
                else:
                    col_def += " PRIMARY KEY"
            else:
                if col.get('autoincrement'):
                    col_def += " AUTO_INCREMENT UNIQUE NOT NULL"
                elif col.get('notnull'):
                    col_def += " NOT NULL"
                if col.get('unique') and not col.get('autoincrement'):
                    col_def += " UNIQUE"
            
            # ✅ DO NOT ADD CHECK CONSTRAINT HERE
            columns_def.append(col_def)
        
        self.logger.debug(f"Found {len(check_constraints_to_apply)} CHECK constraints to apply after data copy")
        
        # ✅ STEP 2: Create table WITHOUT CHECK constraints
        col_def_str = ', '.join(columns_def)
        quoted_dest = self._quote_identifier(dest_table)
        
        with self.engine.connect() as conn:
            create_sql = f"CREATE TABLE {quoted_dest} ({col_def_str})"
            conn.execute(text(create_sql))
            conn.commit()
        
        # ✅ STEP 3: Copy data (skip AUTO_INCREMENT columns)
        for row in data_rows:
            filtered_row = {k: v for k, v in row.items() 
                        if not any(col['name'] == k and col.get('autoincrement') 
                                    for col in schema)}
            if filtered_row:
                self.insert(dest_table, filtered_row)
        
        # ✅ STEP 4: Reset AUTO_INCREMENT
        for col in schema:
            if col.get('autoincrement'):
                try:
                    self.reset_sequence_after_copy(dest_table, col['name'])
                except Exception as e:
                    self.logger.warning(f"Failed to reset AUTO_INCREMENT: {e}")
        
        # ✅ STEP 5: Apply CHECK constraints AFTER data is copied
        if check_constraints_to_apply:
            self.logger.info(f"Applying {len(check_constraints_to_apply)} CHECK constraints to {dest_table}")
            successful_checks = 0
            failed_checks = 0
            
            for check_info in check_constraints_to_apply:
                try:
                    # Add CHECK constraint via ALTER TABLE
                    constraint_name = f"chk_{dest_table}_{check_info['column']}"
                    quoted_col = self._quote_identifier(check_info['column'])
                    
                    with self.engine.connect() as conn:
                        alter_sql = f"""
                            ALTER TABLE {quoted_dest}
                            ADD CONSTRAINT {constraint_name}
                            CHECK ({check_info['expression']})
                        """
                        conn.execute(text(alter_sql))
                        conn.commit()
                    
                    self.logger.info(f"✅ Applied CHECK on {check_info['column']}: {check_info['expression']}")
                    successful_checks += 1
                    
                except Exception as check_err:
                    failed_checks += 1
                    self.logger.warning(f"⚠️ Could not apply CHECK on {check_info['column']}: {check_err}")
                    self.logger.warning(f"   Expression: {check_info['expression']}")
                    self.logger.warning(f"   Existing data may violate the constraint")
            
            if successful_checks > 0:
                self.logger.info(f"✅ Successfully applied {successful_checks} CHECK constraints")
            if failed_checks > 0:
                self.logger.warning(f"⚠️ {failed_checks} CHECK constraints could not be applied due to data violations")
        
        # ✅ STEP 6: Reapply CHECK constraints AFTER data copy
        check_constraints_from_schema = []
        for col in schema:
            if col.get('check_constraint'):
                check_constraints_from_schema.append({
                    'column': col['name'],
                    'expression': col['check_constraint']
                })
        
        if check_constraints_from_schema:
            self.logger.info(f"Reapplying {len(check_constraints_from_schema)} CHECK constraints to {dest_table}")
            successful_checks = 0
            failed_checks = 0
            
            for check_info in check_constraints_from_schema:
                try:
                    # Add CHECK constraint via ALTER TABLE
                    constraint_name = f"chk_{dest_table}_{check_info['column']}"
                    quoted_col = self._quote_identifier(check_info['column'])
                    
                    with self.engine.connect() as conn:
                        alter_sql = f"""
                            ALTER TABLE {quoted_dest}
                            ADD CONSTRAINT {constraint_name}
                            CHECK ({check_info['expression']})
                        """
                        conn.execute(text(alter_sql))
                        conn.commit()
                    
                    self.logger.info(f"✅ Reapplied CHECK on {check_info['column']}: {check_info['expression']}")
                    successful_checks += 1
                    
                except Exception as check_err:
                    failed_checks += 1
                    self.logger.warning(f"⚠️ Could not reapply CHECK on {check_info['column']}: {check_err}")
                    self.logger.warning(f"   Expression: {check_info['expression']}")
                    self.logger.warning(f"   Existing data may violate the constraint")
            
            if successful_checks > 0:
                self.logger.info(f"✅ Successfully reapplied {successful_checks} CHECK constraints")
            if failed_checks > 0:
                self.logger.warning(f"⚠️ {failed_checks} CHECK constraints could not be reapplied due to data violations")
        
        # ✅ STEP 7: Copy triggers
        self.copy_triggers(source_table, dest_table)

    def copy_triggers(self, source_table, dest_table):
        """Copy triggers from source to destination table - FIXED VERSION"""
        if not self.engine:
            return
        
        with self.engine.connect() as conn:
            # Get triggers
            result = conn.execute(text("""
                SELECT TRIGGER_NAME, ACTION_STATEMENT, ACTION_TIMING, EVENT_MANIPULATION
                FROM information_schema.TRIGGERS
                WHERE TRIGGER_SCHEMA = DATABASE() AND EVENT_OBJECT_TABLE = :table
            """), {'table': source_table})
            
            triggers = result.fetchall()
            
            if not triggers:
                self.logger.debug(f"No triggers for {source_table}")
                return
            
            for row in triggers:
                trigger_name = row[0]
                trigger_body = row[1]
                timing = row[2]
                event = row[3]
                
                new_trigger_name = f"{dest_table}_{trigger_name}"
                
                try:
                    # ✅ CRITICAL FIX: Clean up trigger body
                    # Remove any existing BEGIN...END wrapper
                    clean_body = trigger_body.strip()
                    
                    # If body starts with BEGIN and ends with END, extract the content
                    if clean_body.upper().startswith('BEGIN') and clean_body.upper().endswith('END'):
                        # Extract content between BEGIN and END
                        import re
                        match = re.search(r'BEGIN\s+(.*)\s+END', clean_body, re.DOTALL | re.IGNORECASE)
                        if match:
                            clean_body = match.group(1).strip()
                    
                    # Replace table references
                    new_trigger_body = clean_body.replace(
                        f'`{source_table}`',
                        f'`{dest_table}`'
                    ).replace(
                        source_table,
                        dest_table
                    )
                    
                    quoted_trigger = self._quote_identifier(new_trigger_name)
                    quoted_table = self._quote_identifier(dest_table)
                    
                    # Create trigger with single BEGIN...END block
                    conn.execute(text(f"""
                        CREATE TRIGGER {quoted_trigger}
                        {timing} {event}
                        ON {quoted_table}
                        FOR EACH ROW
                        BEGIN
                            {new_trigger_body}
                        END
                    """))
                    
                    conn.commit()
                    self.logger.info(f"✅ Copied trigger {trigger_name}")
                    
                except Exception as e:
                    self.logger.error(f"❌ Trigger copy failed: {e}")
                    import traceback
                    self.logger.error(traceback.format_exc())
                    
    def get_table_connection_info(self, db_name, table_name):
        """Return table-specific connection information"""
        base_conn = self.get_connection_info(db_name)
        quoted_table = self._quote_identifier(table_name)
        
        test_code = f'''from sqlalchemy import create_engine, text

username = "YOUR_USERNAME"
password = "YOUR_PASSWORD"
engine = create_engine(f'mysql+pymysql://{{username}}:{{password}}@localhost:3306/{db_name}')

with engine.connect() as conn:
    result = conn.execute(text("SELECT * FROM {quoted_table} LIMIT 10"))
    rows = [dict(row._mapping) for row in result.fetchall()]
    print(f"Rows: {{len(rows)}}")'''
        
        return {
            'connection_string': base_conn['connection_string'],
            'test_code': test_code,
            'notes': base_conn.get('notes', [])
        }
        
    def supports_check_constraints(self):
        """MySQL 8.0.16+ supports CHECK constraints"""
        return True

    def get_check_constraints(self, table_name):
        """Get CHECK constraints for a table"""
        if not self.engine:
            return []
        
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text("""
                    SELECT CHECK_CLAUSE, COLUMN_NAME
                    FROM INFORMATION_SCHEMA.CHECK_CONSTRAINTS cc
                    JOIN INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
                        ON cc.CONSTRAINT_NAME = tc.CONSTRAINT_NAME
                        AND cc.CONSTRAINT_SCHEMA = tc.CONSTRAINT_SCHEMA
                    WHERE tc.TABLE_SCHEMA = DATABASE()
                        AND tc.TABLE_NAME = :t
                """), {'t': table_name})
                
                checks = []
                for row in result.fetchall():
                    expression = row[0]
                    column = row[1]
                    
                    checks.append({
                        'expression': expression,
                        'column': column
                    })
                
                return checks
        except Exception as e:
            self.logger.error(f"Failed to get CHECK constraints: {e}")
            return []

    def validate_check_constraint(self, constraint_expression):
        """Validate a CHECK constraint expression for MySQL"""
        dangerous_keywords = ['DROP', 'DELETE', 'INSERT', 'UPDATE', 'CREATE', 'ALTER']
        upper_expr = constraint_expression.upper()
        
        for keyword in dangerous_keywords:
            if keyword in upper_expr:
                return False
        
        return True
    
    # === VIEWS SUPPORT ===
    def supports_views(self):
        """Check if database supports views"""
        return True  # All major SQL databases support views

    def list_views(self):
        """List all views in current database"""
        with self._get_connection() as conn:
            if self.DB_NAME == 'SQLite':
                result = conn.execute(text(
                    "SELECT name FROM sqlite_master WHERE type='view'"
                ))
            elif self.DB_NAME == 'MySQL':
                result = conn.execute(text(
                    "SELECT TABLE_NAME as name FROM information_schema.VIEWS "
                    "WHERE TABLE_SCHEMA = DATABASE()"
                ))
            elif self.DB_NAME == 'PostgreSQL':
                result = conn.execute(text(
                    "SELECT table_name as name FROM information_schema.views "
                    "WHERE table_schema = 'public'"
                ))
            elif self.DB_NAME == 'DuckDB':
                result = conn.execute(text(
                    "SELECT view_name as name FROM duckdb_views()"
                ))
            else:
                return []
            
            return [{'name': row[0]} for row in result.fetchall()]

    def create_view(self, view_name, view_query):
        """Create a new view"""
        quoted_name = self._quote_identifier(view_name)
        
        # Clean the query - remove any existing CREATE VIEW
        clean_query = view_query.strip()
        if clean_query.upper().startswith('CREATE VIEW'):
            # Extract just the SELECT part
            match = re.search(r'AS\s+(SELECT.+)', clean_query, re.IGNORECASE | re.DOTALL)
            if match:
                clean_query = match.group(1)
        
        create_sql = f"CREATE VIEW {quoted_name} AS {clean_query}"
        
        with self._get_connection() as conn:
            conn.execute(text(create_sql))
            conn.commit()
        
        return True

    def drop_view(self, view_name):
        """Drop a view"""
        quoted_name = self._quote_identifier(view_name)
        
        with self._get_connection() as conn:
            conn.execute(text(f"DROP VIEW IF EXISTS {quoted_name}"))
            conn.commit()
        
        return True

    def get_view_definition(self, view_name):
        """Get the SQL definition of a view"""
        with self._get_connection() as conn:
            if self.DB_NAME == 'SQLite':
                result = conn.execute(text(
                    "SELECT sql FROM sqlite_master WHERE type='view' AND name = :name"
                ), {'name': view_name})
                row = result.fetchone()
                return row[0] if row else None
                
            elif self.DB_NAME == 'MySQL':
                result = conn.execute(text(
                    "SELECT VIEW_DEFINITION FROM information_schema.VIEWS "
                    "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :name"
                ), {'name': view_name})
                row = result.fetchone()
                if row:
                    # Clean up MySQL's verbose view definition
                    definition = row[0]
                    # Remove backticks and schema prefixes
                    definition = re.sub(r'`[^`]+`\.`[^`]+`\.', '', definition)
                    definition = re.sub(r'`([^`]+)`', r'\1', definition)
                    # Add SELECT if not present
                    if not definition.strip().upper().startswith('SELECT'):
                        definition = f"SELECT {definition}"
                    return definition
                return None
                
            elif self.DB_NAME == 'PostgreSQL':
                result = conn.execute(text(
                    "SELECT view_definition FROM information_schema.views "
                    "WHERE table_schema = 'public' AND table_name = :name"
                ), {'name': view_name})
                row = result.fetchone()
                return row[0] if row else None
                
            elif self.DB_NAME == 'DuckDB':
                result = conn.execute(text(
                    "SELECT sql FROM duckdb_views() WHERE view_name = :name"
                ), {'name': view_name})
                row = result.fetchone()
                return row[0] if row else None
            
            return None
        
    # === PARTITIONS SUPPORT ===
    def supports_partitions(self):
        """Check if database supports table partitions"""
        # Only MySQL and PostgreSQL support partitions
        return True
    
    def supports_partition_listing(self):
        return True

    def supports_partition_creation(self):
        return True

    def supports_partition_deletion(self):
        return True

    def list_partitions(self, table_name):
        """List all partitions for a table"""
        if not self.supports_partitions():
            return []
        
        with self._get_connection() as conn:
            if self.DB_NAME == 'MySQL':
                result = conn.execute(text("""
                    SELECT 
                        PARTITION_NAME as name,
                        PARTITION_METHOD as type,
                        PARTITION_EXPRESSION as expression
                    FROM information_schema.PARTITIONS
                    WHERE TABLE_SCHEMA = DATABASE() 
                        AND TABLE_NAME = :table_name
                        AND PARTITION_NAME IS NOT NULL
                """), {'table_name': table_name})
                
            elif self.DB_NAME == 'PostgreSQL':
                result = conn.execute(text("""
                    SELECT 
                        c.relname as name,
                        'RANGE' as type,
                        pg_get_expr(c.relpartbound, c.oid) as expression
                    FROM pg_class c
                    JOIN pg_inherits i ON c.oid = i.inhrelid
                    JOIN pg_class p ON i.inhparent = p.oid
                    WHERE p.relname = :table_name
                """), {'table_name': table_name})
            
            return [dict(row._mapping) for row in result.fetchall()]
        
    def _get_column_type(self, table_name, column_name):
        """Get the data type of a column"""
        try:
            schema = self.get_table_schema(table_name)
            for col in schema:
                if col['name'] == column_name:
                    return col.get('type', '')
            return None
        except Exception as e:
            logger.error(f"Failed to get column type: {e}")
            return None

    def create_partition(self, table_name, partition_config):
        """Create a partition on a table"""
        if not self.supports_partitions():
            raise NotImplementedError("Partitions not supported")
        
        partition_type = partition_config.get('type', 'RANGE').upper()
        column = partition_config.get('column')
        definitions = partition_config.get('definitions', [])
        
        if not column:
            raise ValueError("Partition column is required")
        
        # HASH partitions don't require definitions (just partition count)
        if partition_type != 'HASH' and not definitions:
            raise ValueError("Partition definitions are required for RANGE and LIST partitions")
        
        with self._get_connection() as conn:
            quoted_table = self._quote_identifier(table_name)
            quoted_column = self._quote_identifier(column)
            
            partition_defs = []
            
            if partition_type == 'RANGE':
                # MySQL requires INTEGER expression for RANGE
                # Auto-detect if column is DATE/DATETIME and wrap with YEAR()
                col_type = self._get_column_type(table_name, column)
                
                if col_type and any(dt in col_type.upper() for dt in ['DATE', 'DATETIME', 'TIMESTAMP']):
                    # Date column - use YEAR() function
                    partition_expr = f"YEAR({quoted_column})"
                else:
                    # Numeric column - use directly
                    partition_expr = quoted_column
                
                for part_def in definitions:
                    name = part_def['name']
                    value = part_def['value']
                    partition_defs.append(f"PARTITION {name} VALUES LESS THAN ({value})")
            
            elif partition_type == 'LIST':
                # MySQL LIST partitions require INTEGER values
                # Check if column is numeric or string
                col_type = self._get_column_type(table_name, column)
                partition_expr = quoted_column
                
                for part_def in definitions:
                    name = part_def['name']
                    value = part_def['value']
                    
                    # Parse comma-separated values
                    values = [v.strip().strip("'\"") for v in value.split(',')]
                    
                    # Check if values are numeric
                    try:
                        # Try to convert first value to int
                        int(values[0])
                        # Numeric values - don't quote
                        quoted_values = ', '.join(values)
                    except (ValueError, IndexError):
                        # String values - MySQL doesn't support this for LIST
                        # Convert to numeric mapping or raise error
                        raise ValueError(
                            f"MySQL LIST partitioning requires INTEGER values. "
                            f"For string values like '{value}', consider using:\n"
                            f"1. HASH partitioning instead, or\n"
                            f"2. Create a mapping column (e.g., region_id: North=1, South=2, etc.)"
                        )
                    
                    partition_defs.append(f"PARTITION {name} VALUES IN ({quoted_values})")
            
            elif partition_type == 'HASH':
                # HASH partitions - use partition count
                partition_expr = quoted_column
                
                # If definitions provided, use their count; otherwise default to 4
                partition_count = len(definitions) if definitions else 4
                
                for i in range(partition_count):
                    if definitions and i < len(definitions):
                        name = definitions[i]['name']
                    else:
                        name = f"p{i}"
                    partition_defs.append(f"PARTITION {name}")
            
            alter_sql = f"""
                ALTER TABLE {quoted_table}
                PARTITION BY {partition_type}({partition_expr})
                ({', '.join(partition_defs)})
            """
            
            conn.execute(text(alter_sql))
            conn.commit()
        
        return True

    def drop_partition(self, table_name, partition_name):
        """Drop a partition from a table"""
        if not self.supports_partitions():
            raise NotImplementedError("Partitions not supported")
        
        with self._get_connection() as conn:
            quoted_table = self._quote_identifier(table_name)
            
            if self.DB_NAME == 'MySQL':
                conn.execute(text(
                    f"ALTER TABLE {quoted_table} DROP PARTITION {partition_name}"
                ))
                conn.commit()
                
            elif self.DB_NAME == 'PostgreSQL':
                quoted_partition = self._quote_identifier(partition_name)
                conn.execute(text(f"DROP TABLE {quoted_partition}"))
                conn.commit()
        
        return True
    
    # === NORMALIZATION SUPPORT ===
    def analyze_for_normalization(self):
        """Analyze database structure for normalization opportunities"""
        tables = self.list_tables()
        issues = []
        
        for table in tables:
            schema = self.get_table_schema(table)
            
            # Check for potential repeating groups
            for col in schema:
                col_type = col['type'].upper()
                if 'TEXT' in col_type or 'VARCHAR' in col_type:
                    issues.append(f"Table '{table}', column '{col['name']}': Check for multi-valued attributes")
            
            # Check for composite keys
            pk_cols = [col for col in schema if col.get('pk')]
            if len(pk_cols) > 1:
                issues.append(f"Table '{table}': Has composite primary key - check for partial dependencies")
        
        return {
            'tables': tables,
            'issues': issues,
            'total_tables': len(tables)
        }

    def normalize_database(self, normal_form, analysis_data):
        """
        Normalize database to specified normal form.
        This is a simplified implementation - real normalization requires deep analysis.
        """
        changes = []
        new_tables = []
        
        user_answers = analysis_data.get('user_answers', {})
        
        # 1NF: Remove repeating groups
        if normal_form in ['1NF', '2NF', '3NF', 'BCNF']:
            if user_answers.get('repeating_groups') == 'yes':
                changes.append("Identified repeating groups - manual intervention required")
                # Real implementation would create separate tables
        
        # 2NF: Remove partial dependencies
        if normal_form in ['2NF', '3NF', 'BCNF']:
            if user_answers.get('partial_dependencies') == 'yes':
                changes.append("Identified partial dependencies - manual intervention required")
        
        # 3NF: Remove transitive dependencies
        if normal_form in ['3NF', 'BCNF']:
            if user_answers.get('transitive_dependencies') == 'yes':
                changes.append("Identified transitive dependencies - manual intervention required")
        
        # BCNF: Ensure all determinants are candidate keys
        if normal_form == 'BCNF':
            candidate_keys = user_answers.get('candidate_keys', '')
            if candidate_keys:
                changes.append(f"Analyzing candidate keys: {candidate_keys}")
        
        return {
            'changes': changes if changes else [f"Database analyzed for {normal_form} - no automated changes made"],
            'new_tables': new_tables
        }