import hashlib
import re
import os
import time
import logging
import keyring
import getpass
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError, OperationalError
from .db_handler import DBHandler

logger = logging.getLogger(__name__)  # Global logger for this file

class PostgreSQLHandler(DBHandler):
    
    DB_TYPE = 'sql'
    DB_NAME = 'PostgreSQL'
    
    KEYRING_SERVICE = 'dbdragoness_postgresql'
    KEYRING_USERNAME_KEY = 'postgresql_username'
    KEYRING_PASSWORD_KEY = 'postgresql_password'
    
    def __init__(self):
        self.current_db = None
        self.engine = None
        self.base_path = 'sql_dbs/postgresql'
        self.logger = logging.getLogger(__name__)
        os.makedirs(self.base_path, exist_ok=True)
        
        self.username = None
        self.password = None
        self._credentials_valid = False
        self._load_credentials()

    def _load_credentials(self):
        """Load credentials from secure storage"""
        try:
            self.username = keyring.get_password(self.KEYRING_SERVICE, self.KEYRING_USERNAME_KEY)
            self.password = keyring.get_password(self.KEYRING_SERVICE, self.KEYRING_PASSWORD_KEY)
            
            if self.username and self.password:
                if self._test_credentials():
                    self._credentials_valid = True
                    self.logger.info("PostgreSQL credentials loaded successfully")
                    return
            
            self.logger.warning("PostgreSQL credentials missing or invalid")
            
        except Exception as e:
            self.logger.error(f"Error loading credentials: {e}")

    def get_credential_status(self):
        """Return whether this handler needs credentials"""
        try:
            username = keyring.get_password(self.KEYRING_SERVICE, self.KEYRING_USERNAME_KEY)
            password = keyring.get_password(self.KEYRING_SERVICE, self.KEYRING_PASSWORD_KEY)
            
            has_creds = (
                username is not None and
                password is not None
            )
            
            return {
                "needs_credentials": not has_creds,
                "handler": self.DB_NAME
            }
        except Exception as e:
            self.logger.error(f"Failed to check PostgreSQL credentials: {e}")
            return {"needs_credentials": True, "handler": self.DB_NAME}

    def clear_credentials(self):
        """Clear stored credentials from keyring"""
        try:
            keyring.delete_password(self.KEYRING_SERVICE, self.KEYRING_USERNAME_KEY)
            keyring.delete_password(self.KEYRING_SERVICE, self.KEYRING_PASSWORD_KEY)
            self._credentials_valid = False
            self.username = None
            self.password = None
            self.logger.info("PostgreSQL credentials cleared successfully")
        except Exception as e:
            self.logger.error(f"Failed to clear credentials: {e}")

    def validate_and_store_credentials(self, username, password):
        """Validate and store credentials - ALLOW EMPTY PASSWORDS"""
        # Don't reject empty passwords - they're valid for some MySQL/PostgreSQL setups
        self.username = username
        self.password = password if password else ''  # Ensure it's a string, not None
    
        if self._test_credentials():
            try:
                keyring.set_password(self.KEYRING_SERVICE, self.KEYRING_USERNAME_KEY, username)
                keyring.set_password(self.KEYRING_SERVICE, self.KEYRING_PASSWORD_KEY, password if password else '')
                self._credentials_valid = True
                self.logger.info(f"{self.DB_NAME} credentials saved successfully")
                return {'success': True, 'message': 'Credentials saved successfully!'}
            except Exception as e:
                self.logger.error(f"Failed to store credentials: {e}")
                return {'success': False, 'message': f'Failed to save credentials: {str(e)}'}
    
        return {'success': False, 'message': 'Invalid credentials. Please check username and password.'}

    def _test_credentials(self):
        """Test if credentials work"""
        try:
            test_url = f"postgresql://{self.username}:{self.password}@localhost/postgres"
            test_engine = create_engine(test_url)
            with test_engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            test_engine.dispose()
            return True
        except Exception as e:
            self.logger.debug(f"Credential test failed: {e}")
            return False

    def _ensure_credentials(self):
        """Ensure credentials are valid before operations"""
        if not self._credentials_valid:
            raise ValueError("PostgreSQL credentials required. Please configure credentials first.")

    def _quote_identifier(self, identifier):
        """Quote identifier to preserve case sensitivity in PostgreSQL"""
        return f'"{identifier}"'
    
    def _clean_check_expression(self, expression):
        """
        Clean up PostgreSQL CHECK constraint expressions for GUI display.
        Removes redundant NOT NULL checks, unnecessary type casts, and simplifies syntax.
        """
        import re
        
        original = expression
        
        # Step 1: Remove leading "column IS NOT NULL AND (" pattern
        expression = re.sub(r'^\s*\(?\w+\s+IS\s+NOT\s+NULL\s+AND\s+', '', expression, flags=re.IGNORECASE)
        
        # Step 2: Remove type casts from column names: (age)::numeric -> age
        expression = re.sub(r'\((\w+)\)::\w+', r'\1', expression)
        
        # Step 3: Simplify char_length with type cast: char_length((name)::text) -> char_length(name)
        expression = re.sub(r'char_length\(\((\w+)\)::\w+\)', r'char_length(\1)', expression, flags=re.IGNORECASE)
        
        # Step 4: Clean up ANY array syntax
        # From: ((name)::text = ANY ((ARRAY['a'::character varying, 'b'::character varying])::text[]))
        # To: name IN ('a', 'b')
        array_match = re.search(
            r"\(\((\w+)\)::text\s+=\s+ANY\s+\(\(ARRAY\[(.*?)\]\)::text\[\]\)\)",
            expression,
            re.IGNORECASE | re.DOTALL
        )
        if array_match:
            col_name = array_match.group(1)
            array_content = array_match.group(2)
            # Extract just the string values, removing type casts
            values = re.findall(r"'([^']+)'", array_content)
            if values:
                in_clause = ', '.join([f"'{v}'" for v in values])
                expression = re.sub(
                    r"\(\((\w+)\)::text\s+=\s+ANY\s+\(\(ARRAY\[.*?\]\)::text\[\]\)\)",
                    f"{col_name} IN ({in_clause})",
                    expression,
                    flags=re.IGNORECASE | re.DOTALL
                )
        
        # Step 5: Balance parentheses - remove unmatched closing parentheses
        open_count = expression.count('(')
        close_count = expression.count(')')
        if close_count > open_count:
            # Remove trailing extra closing parentheses
            diff = close_count - open_count
            for _ in range(diff):
                # Remove last closing parenthesis
                last_close = expression.rfind(')')
                if last_close != -1:
                    expression = expression[:last_close] + expression[last_close+1:]
        
        # Step 6: Remove outer parentheses if entire expression is wrapped
        expression = expression.strip()
        if expression.startswith('(') and expression.endswith(')'):
            # Check if these are balanced outer parens
            depth = 0
            can_remove = True
            for i, char in enumerate(expression):
                if char == '(':
                    depth += 1
                elif char == ')':
                    depth -= 1
                # If depth reaches 0 before the end, these aren't outer parens
                if depth == 0 and i < len(expression) - 1:
                    can_remove = False
                    break
            if can_remove:
                expression = expression[1:-1].strip()
        
        self.logger.info(f"🔍 _clean_check_expression OUTPUT: '{expression}'")
        self.logger.debug(f"Cleaned CHECK: '{original}' -> '{expression}'")
        
        # ✅ CRITICAL SAFETY CHECK: Don't return empty string
        if not expression or not expression.strip():
            self.logger.error(f"⚠️ WARNING: _clean_check_expression returned EMPTY for input: '{original}'")
            return original  # Return original if cleaning resulted in empty
        
        return expression
    
    def get_connection_info(self, db_name):
        """Return PostgreSQL connection information"""
        return {
            'connection_string': f'postgresql://YOUR_USERNAME:YOUR_PASSWORD@localhost/{db_name}',
            'test_code': f'''from sqlalchemy import create_engine, text

# ⚠️ REPLACE THESE WITH YOUR ACTUAL CREDENTIALS
username = "YOUR_USERNAME"  # e.g., "postgres"
password = "YOUR_PASSWORD"  # Your PostgreSQL password

engine = create_engine(f'postgresql://{{username}}:{{password}}@localhost/{db_name}')
with engine.connect() as conn:
    result = conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public'"))
    tables = [row[0] for row in result]
    print(f"Tables: {{tables}}")''',
        'notes': [
            'Replace YOUR_USERNAME and YOUR_PASSWORD with your actual PostgreSQL credentials',
            'Ensure PostgreSQL server is running before testing'
        ]
        }
    
    def _get_connection(self):
        """Compatibility shim for generic code expecting this method"""
        return self.engine.connect()

    def _get_db_url(self, db_name):
        """Generate connection URL with credentials"""
        self._ensure_credentials()
        return f"postgresql://{self.username}:{self.password}@localhost/{db_name}"
    
    def _get_master_engine(self):
        """Get engine for postgres master database"""
        return create_engine(self._get_db_url('postgres'))

    def _handle_auth_error(self, operation_name, error):
        """Handle authentication errors by invalidating credentials"""
        error_str = str(error).lower()
        if 'password' in error_str or 'authentication' in error_str or 'auth' in error_str:
            self._credentials_valid = False
            self.logger.warning(f"Authentication failed during {operation_name}")
            raise ValueError("PostgreSQL credentials expired or invalid. Please re-enter credentials.")
        raise error

    def create_db(self, db_name):
        """Create database with case-sensitive name"""
        try:
            self._ensure_credentials()
            
            if db_name in self.list_dbs():
                raise ValueError(f"Database '{db_name}' already exists.")
            
            master_engine = self._get_master_engine()
            with master_engine.connect() as conn:
                conn.execute(text("COMMIT"))
                conn.execute(text(f"CREATE DATABASE {self._quote_identifier(db_name)}"))
            master_engine.dispose()
            
            self.switch_db(db_name)
            
        except (OperationalError, ValueError) as e:
            self._handle_auth_error('create_db', e)

    def delete_db(self, db_name):
        """Delete database"""
        try:
            self._ensure_credentials()
            
            if self.current_db == db_name:
                if self.engine:
                    self.engine.dispose()
                self.engine = None
                self.current_db = None
            
            master_engine = self._get_master_engine()
            with master_engine.connect() as conn:
                conn.execute(text("COMMIT"))
                conn.execute(text(f"""
                    SELECT pg_terminate_backend(pg_stat_activity.pid)
                    FROM pg_stat_activity
                    WHERE pg_stat_activity.datname = '{db_name}'
                    AND pid <> pg_backend_pid()
                """))
                conn.execute(text(f"DROP DATABASE IF EXISTS {self._quote_identifier(db_name)}"))
            master_engine.dispose()
            
        except (OperationalError, ValueError) as e:
            self._handle_auth_error('delete_db', e)

    def switch_db(self, db_name):
        """Switch database"""
        try:
            self._ensure_credentials()
            
            if db_name not in self.list_dbs():
                raise FileNotFoundError(f"Database '{db_name}' not found.")
            
            if self.engine:
                self.engine.dispose()
            
            self.engine = create_engine(self._get_db_url(db_name))
            self.current_db = db_name
            
        except (OperationalError, ValueError) as e:
            self._handle_auth_error('switch_db', e)

    def list_dbs(self):
        """List databases - preserves case"""
        try:
            self._ensure_credentials()
            
            engine = self._get_master_engine()
            with engine.connect() as conn:
                result = conn.execute(text("SELECT datname FROM pg_database WHERE datistemplate = false"))
                dbs = [row[0] for row in result if row[0] not in ['postgres', 'template0', 'template1']]
            engine.dispose()
            return dbs
        except (OperationalError, ValueError) as e:
            if 'credentials required' in str(e).lower():
                return []
            self._handle_auth_error('list_dbs', e)
            return []
        except Exception as e:
            self.logger.error(f"Error listing databases: {e}")
            return []

    def list_tables(self):
        """List tables - preserves case"""
        if not self.engine:
            return []
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text("""
                    SELECT tablename FROM pg_tables 
                    WHERE schemaname = 'public'
                """))
                return [row[0] for row in result]
        except Exception as e:
            self.logger.error(f"Error listing tables: {e}")
            return []

    def list_tables_for_db(self, db_name):
        """List tables in a specific database"""
        try:
            if db_name not in self.list_dbs():
                return []
            
            temp_engine = create_engine(self._get_db_url(db_name))
            with temp_engine.connect() as conn:
                result = conn.execute(text("""
                    SELECT tablename FROM pg_tables 
                    WHERE schemaname = 'public'
                """))
                tables = [row[0] for row in result]
            temp_engine.dispose()
            return tables
        except Exception as e:
            self.logger.error(f"Error listing tables for {db_name}: {e}")
            return []

    def get_supported_types(self):
        return [
            'INTEGER', 'BIGINT', 'SMALLINT',
            'DECIMAL', 'NUMERIC', 'REAL', 'DOUBLE PRECISION',
            'VARCHAR', 'TEXT', 'CHAR',
            'BOOLEAN',
            'DATE', 'TIMESTAMP', 'TIMESTAMPTZ', 'TIME', 'TIMETZ',
            'UUID', 'JSON', 'JSONB',
            'BYTEA', 'ARRAY', 'HSTORE'
        ]

    def _get_primary_keys(self, table_name):
        """Get primary key columns - ROBUST version with multiple fallbacks"""
        if not self.engine:
            return set()
        
        try:
            with self.engine.connect() as conn:
                # Method 1: Use information_schema (most reliable for quoted tables)
                try:
                    result = conn.execute(text("""
                        SELECT kcu.column_name
                        FROM information_schema.table_constraints tc
                        JOIN information_schema.key_column_usage kcu 
                          ON tc.constraint_name = kcu.constraint_name
                          AND tc.table_schema = kcu.table_schema
                        WHERE tc.constraint_type = 'PRIMARY KEY'
                          AND tc.table_schema = 'public'
                          AND tc.table_name = :t
                    """), {'t': table_name})
                    
                    pk_cols = {row[0] for row in result}
                    if pk_cols:
                        self.logger.debug(f"✓ Found PKs via information_schema for '{table_name}': {pk_cols}")
                        return pk_cols
                except Exception as e:
                    self.logger.debug(f"Method 1 (information_schema) failed: {e}")
                
                # Method 2: Try information_schema with lowercase
                try:
                    result = conn.execute(text("""
                        SELECT kcu.column_name
                        FROM information_schema.table_constraints tc
                        JOIN information_schema.key_column_usage kcu 
                          ON tc.constraint_name = kcu.constraint_name
                          AND tc.table_schema = kcu.table_schema
                        WHERE tc.constraint_type = 'PRIMARY KEY'
                          AND tc.table_schema = 'public'
                          AND tc.table_name = :t
                    """), {'t': table_name.lower()})
                    
                    pk_cols = {row[0] for row in result}
                    if pk_cols:
                        self.logger.debug(f"✓ Found PKs via information_schema lowercase for '{table_name}': {pk_cols}")
                        return pk_cols
                except Exception as e:
                    self.logger.debug(f"Method 2 (information_schema lowercase) failed: {e}")
                
                # Method 3: Try pg_index with schema-qualified name
                try:
                    # Use schema.table format for case-sensitive tables
                    qualified_name = f'public.{self._quote_identifier(table_name)}'
                    result = conn.execute(text("""
                        SELECT a.attname
                        FROM pg_index i
                        JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
                        WHERE i.indrelid = :t::regclass AND i.indisprimary
                    """), {'t': qualified_name})
                    
                    pk_cols = {row[0] for row in result}
                    if pk_cols:
                        self.logger.debug(f"✓ Found PKs via pg_index qualified for '{table_name}': {pk_cols}")
                        return pk_cols
                except Exception as e:
                    self.logger.debug(f"Method 3 (pg_index qualified) failed: {e}")
                
                # Method 4: Try pg_index with lowercase
                try:
                    result = conn.execute(text("""
                        SELECT a.attname
                        FROM pg_index i
                        JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
                        WHERE i.indrelid = :t::regclass AND i.indisprimary
                    """), {'t': table_name.lower()})
                    
                    pk_cols = {row[0] for row in result}
                    if pk_cols:
                        self.logger.debug(f"✓ Found PKs via pg_index lowercase for '{table_name}': {pk_cols}")
                        return pk_cols
                except Exception as e:
                    self.logger.debug(f"Method 4 (pg_index lowercase) failed: {e}")
                
                self.logger.warning(f"✗ No primary keys found for table '{table_name}' using any method")
                return set()
                
        except Exception as e:
            self.logger.error(f"Error in _get_primary_keys: {e}")
            return set()
        
    def supports_non_pk_autoincrement(self):
        """PostGreSQL supports sequences on any integer column"""
        return True

    def get_table_schema(self, table_name):
        """Get table schema with unique and autoincrement detection - INCLUDES CHECK constraints"""
        if not self.engine:
            return []

        try:
            with self.engine.connect() as conn:
                # Get column information
                result = conn.execute(text("""
                    SELECT 
                        column_name, 
                        data_type,
                        character_maximum_length,
                        numeric_precision,
                        numeric_scale,
                        is_nullable, 
                        column_default
                    FROM information_schema.columns 
                    WHERE table_name = :t AND table_schema = 'public'
                    ORDER BY ordinal_position
                """), {'t': table_name})
        
                rows = result.fetchall()
        
                # If no results, try lowercase
                if not rows:
                    result = conn.execute(text("""
                        SELECT 
                            column_name, 
                            data_type,
                            character_maximum_length,
                            numeric_precision,
                            numeric_scale,
                            is_nullable, 
                            column_default
                        FROM information_schema.columns 
                        WHERE table_name = :t AND table_schema = 'public'
                        ORDER BY ordinal_position
                    """), {'t': table_name.lower()})
                    rows = result.fetchall()
        
                # Get PRIMARY KEY columns
                pk_columns = self._get_primary_keys(table_name)
                self.logger.debug(f"Schema for {table_name}: PK columns = {pk_columns}")
            
                # Get UNIQUE constraints - use simpler query to avoid regclass issues
                unique_columns = set()
                try:
                    # Use information_schema instead of pg_index to avoid regclass problems
                    unique_result = conn.execute(text("""
                        SELECT column_name
                        FROM information_schema.table_constraints tc
                        JOIN information_schema.key_column_usage kcu 
                            ON tc.constraint_name = kcu.constraint_name
                            AND tc.table_schema = kcu.table_schema
                        WHERE tc.constraint_type = 'UNIQUE'
                            AND tc.table_schema = 'public'
                            AND tc.table_name = :t
                    """), {'t': table_name})

                    for row in unique_result.fetchall():
                        unique_columns.add(row[0])
                    
                except Exception as e:
                    self.logger.debug(f"Unique constraint query failed (trying lowercase): {e}")
                    try:
                        unique_result = conn.execute(text("""
                            SELECT column_name
                            FROM information_schema.table_constraints tc
                            JOIN information_schema.key_column_usage kcu 
                                ON tc.constraint_name = kcu.constraint_name
                                AND tc.table_schema = kcu.table_schema
                            WHERE tc.constraint_type = 'UNIQUE'
                                AND tc.table_schema = 'public'
                                AND tc.table_name = :t
                        """), {'t': table_name.lower()})
                    
                        for row in unique_result.fetchall():
                            unique_columns.add(row[0])
                    except Exception as e2:
                        self.logger.debug(f"Unique constraint query failed completely: {e2}")

                self.logger.debug(f"Unique columns for {table_name}: {unique_columns}")

                # ✅ Get CHECK constraints per column - IMPROVED PARSING
                check_constraints = {}
                try:
                    # Get all CHECK constraints for this table
                    check_result = conn.execute(text("""
                        SELECT 
                            cc.check_clause as definition,
                            tc.constraint_name,
                            kcu.column_name
                        FROM information_schema.check_constraints cc
                        JOIN information_schema.table_constraints tc
                            ON cc.constraint_name = tc.constraint_name
                            AND cc.constraint_schema = tc.constraint_schema
                        LEFT JOIN information_schema.key_column_usage kcu
                            ON tc.constraint_name = kcu.constraint_name
                            AND tc.constraint_schema = kcu.constraint_schema
                        WHERE tc.table_schema = 'public'
                            AND tc.table_name = :t
                            AND tc.constraint_type = 'CHECK'
                    """), {'t': table_name})
                    
                    for row in check_result.fetchall():
                        definition = row[0]
                        constraint_name = row[1]
                        explicit_column = row[2]
                        
                        if not definition:
                            continue
                        
                        # Clean up the expression (remove outer parentheses if present)
                        raw_expression = definition.strip()
                        if raw_expression.startswith('(') and raw_expression.endswith(')'):
                            raw_expression = raw_expression[1:-1].strip()
                            
                        self.logger.debug(f"📋 Raw CHECK from DB: constraint={constraint_name}, definition={definition}, explicit_col={explicit_column}")
                        
                        # ✅ CRITICAL: Extract column name BEFORE cleaning the expression
                        column_name = explicit_column
                                                
                        if not column_name:
                            # Parse from RAW expression - handle multiple patterns
                            import re
                            
                            # Pattern 1: Quoted identifier at start: "column_name" ...
                            match = re.search(r'^\s*"([^"]+)"', raw_expression)
                            if match:
                                column_name = match.group(1)
                            else:
                                # Pattern 2: Parenthesized column with type cast: ((column_name)::type ...)
                                match = re.search(r'^\s*\(\(([a-zA-Z_][a-zA-Z0-9_]*)\)::(?:numeric|text|integer|character varying)', raw_expression, re.IGNORECASE)
                                if match:
                                    column_name = match.group(1)
                                else:
                                    # Pattern 3: Simple parenthesized column: (column_name) ...
                                    match = re.search(r'^\s*\(([a-zA-Z_][a-zA-Z0-9_]*)\)', raw_expression)
                                    if match:
                                        column_name = match.group(1)
                                    else:
                                        # Pattern 4: Unquoted identifier: column_name ...
                                        match = re.search(r'^\s*([a-zA-Z_][a-zA-Z0-9_]*)', raw_expression)
                                        if match:
                                            column_name = match.group(1)
                                        else:
                                            # Pattern 5: Complex expression starting with (column IS NOT NULL) AND ...
                                            match = re.search(r'\(\s*([a-zA-Z_][a-zA-Z0-9_]*)\s+IS\s+NOT\s+NULL\s*\)', raw_expression, re.IGNORECASE)
                                            if match:
                                                column_name = match.group(1)
                                            else:
                                                # Pattern 6: Find any column name mentioned in the expression
                                                # Look for function calls like length(column_name) or column_name = ANY
                                                all_matches = re.findall(r'\b([a-zA-Z_][a-zA-Z0-9_]*)\s*(?:\(|=|>|<|IN|IS)', raw_expression, re.IGNORECASE)
                                                if all_matches:
                                                    # Filter out SQL keywords
                                                    keywords = {'AND', 'OR', 'NOT', 'NULL', 'ANY', 'ARRAY', 'LENGTH', 'CHAR_LENGTH', 'IS', 'NUMERIC', 'TEXT', 'INTEGER', 'CHARACTER', 'VARYING'}
                                                    candidates = [m for m in all_matches if m.upper() not in keywords]
                                                    if candidates:
                                                        column_name = candidates[0]  # Use first non-keyword identifier
                        
                        if column_name:
                            # ✅ NOW clean the expression AFTER extracting column name
                            cleaned_expression = self._clean_check_expression(raw_expression)
                            
                            cleaned_expression = self._clean_check_expression(raw_expression)

                            # ✅ ADD THIS DEBUG
                            self.logger.info(f"🔍 CRITICAL DEBUG:")
                            self.logger.info(f"   Column: {column_name}")
                            self.logger.info(f"   Raw expression: '{raw_expression}'")
                            self.logger.info(f"   Cleaned expression: '{cleaned_expression}'")
                            self.logger.info(f"   Cleaned is empty: {not cleaned_expression or not cleaned_expression.strip()}")
                            
                            self.logger.debug(f"🧹 After cleaning: column={column_name}, raw='{raw_expression}' -> cleaned='{cleaned_expression}'")
                            
                            # ✅ FIXED: Only skip if the ENTIRE constraint is JUST "column IS NOT NULL" with nothing else
                            cleaned_upper = cleaned_expression.strip().upper()
                            is_just_not_null = (
                                cleaned_upper == f'{column_name.upper()} IS NOT NULL' or
                                cleaned_upper == 'IS NOT NULL'
                            )
                            
                            # ✅ CRITICAL FIX: Also check if cleaned_expression is empty or None
                            if not cleaned_expression or not cleaned_expression.strip():
                                self.logger.debug(f"⚠️ Skipped empty CHECK constraint for column '{column_name}'")
                            elif not is_just_not_null:
                                # Store cleaned expression
                                if column_name in check_constraints:
                                    # Multiple CHECK constraints on same column - combine with AND
                                    check_constraints[column_name] = f'{check_constraints[column_name]} AND {cleaned_expression}'
                                else:
                                    check_constraints[column_name] = cleaned_expression
                                
                                self.logger.debug(f"✅ Stored CHECK constraint for column '{column_name}': {cleaned_expression}")
                            else:
                                self.logger.debug(f"⏭️ Skipped redundant NOT NULL check for column '{column_name}'")
                        else:
                            self.logger.warning(f"Could not extract column name from CHECK: {raw_expression}")
                            
                except Exception as e:
                    self.logger.debug(f"Could not fetch CHECK constraints: {e}")
                    # Try with lowercase table name
                    try:
                        check_result = conn.execute(text("""
                            SELECT 
                                cc.check_clause as definition,
                                tc.constraint_name,
                                kcu.column_name
                            FROM information_schema.check_constraints cc
                            JOIN information_schema.table_constraints tc
                                ON cc.constraint_name = tc.constraint_name
                                AND cc.constraint_schema = tc.constraint_schema
                            LEFT JOIN information_schema.key_column_usage kcu
                                ON tc.constraint_name = kcu.constraint_name
                                AND tc.constraint_schema = kcu.constraint_schema
                            WHERE tc.table_schema = 'public'
                                AND tc.table_name = :t
                                AND tc.constraint_type = 'CHECK'
                        """), {'t': table_name.lower()})
                        
                        for row in check_result.fetchall():
                            definition = row[0]
                            constraint_name = row[1]
                            explicit_column = row[2]
                            
                            if not definition:
                                continue
                            
                            expression = definition.strip()
                            if expression.startswith('(') and expression.endswith(')'):
                                expression = expression[1:-1].strip()
                            
                            column_name = explicit_column
                            
                            if not column_name:
                                import re
                                match = re.search(r'^\s*"([^"]+)"', expression)
                                if match:
                                    column_name = match.group(1)
                                else:
                                    match = re.search(r'^\s*([a-zA-Z_][a-zA-Z0-9_]*)', expression)
                                    if match:
                                        column_name = match.group(1)
                                    else:
                                        match = re.search(r'\(\(([a-zA-Z_][a-zA-Z0-9_]*)\)', expression)
                                        if match:
                                            column_name = match.group(1)
                            
                            if column_name:
                                if column_name in check_constraints:
                                    check_constraints[column_name] += f' AND {expression}'
                                else:
                                    check_constraints[column_name] = expression
                                self.logger.debug(f"Found CHECK constraint for column '{column_name}': {expression}")
                            
                    except Exception as e2:
                        self.logger.debug(f"CHECK constraint query failed completely: {e2}")
        
                schema = []
                for row in rows:
                    col_name = row[0]
                    col_type = row[1]
                    char_max_length = row[2]
                    numeric_precision = row[3]
                    numeric_scale = row[4]
                    nullable = row[5]
                    col_default = row[6]

                    # Build proper type with length
                    mapped_type = col_type.upper()
                    
                    if mapped_type in ['CHARACTER VARYING', 'VARCHAR'] and char_max_length:
                        mapped_type = f'VARCHAR({char_max_length})'
                    elif mapped_type == 'CHARACTER' and char_max_length:
                        mapped_type = f'CHAR({char_max_length})'
                    elif mapped_type in ['NUMERIC', 'DECIMAL'] and numeric_precision:
                        if numeric_scale:
                            mapped_type = f'{mapped_type}({numeric_precision},{numeric_scale})'
                        else:
                            mapped_type = f'{mapped_type}({numeric_precision})'

                    is_pk = col_name in pk_columns
                    is_serial = False
                    if col_default:
                        col_default_str = str(col_default).lower()
                        is_serial = 'nextval' in col_default_str

                    is_unique = col_name in unique_columns

                    # ✅ Get CHECK constraint for this column
                    check_constraint = check_constraints.get(col_name)

                    self.logger.debug(f"  Column {col_name}: type={mapped_type}, is_pk={is_pk}, is_serial={is_serial}, is_unique={is_unique}, check={check_constraint}")

                    schema.append({
                        'name': col_name,
                        'type': mapped_type,
                        'pk': is_pk,
                        'notnull': nullable == 'NO',
                        'autoincrement': is_serial,
                        'unique': is_unique or is_pk,
                        'check_constraint': check_constraint  # ✅ ADD CHECK
                    })

                return schema
        except Exception as e:
            self.logger.error(f"Error getting schema for {table_name}: {e}")
            return []

    def read(self, table_name):
        """Read all data - quote table name with case fallback, format dates consistently"""
        if not self.engine:
            return []
        
        try:
            with self.engine.connect() as conn:
                # Try with quotes first (for case-sensitive tables)
                try:
                    result = conn.execute(text(f"SELECT * FROM {self._quote_identifier(table_name)}"))
                    rows = []
                    for row in result.fetchall():
                        row_dict = dict(row._mapping)
                        # ✅ Format date/time values to ISO standard strings
                        for key, value in row_dict.items():
                            if value is not None:
                                # Convert date objects to ISO format strings
                                if hasattr(value, 'isoformat'):
                                    row_dict[key] = value.isoformat()
                        rows.append(row_dict)
                    return rows
                except Exception as e:
                    # If quoted fails, try lowercase (PostgreSQL default)
                    if 'does not exist' in str(e).lower():
                        result = conn.execute(text(f"SELECT * FROM {self._quote_identifier(table_name.lower())}"))
                        rows = []
                        for row in result.fetchall():
                            row_dict = dict(row._mapping)
                            # ✅ Format date/time values to ISO standard strings
                            for key, value in row_dict.items():
                                if value is not None:
                                    if hasattr(value, 'isoformat'):
                                        row_dict[key] = value.isoformat()
                            rows.append(row_dict)
                        return rows
                    raise
        except Exception as e:
            self.logger.error(f"Error reading from {table_name}: {e}")
            return []

    def execute_query(self, query):
        """Execute query - PostgreSQL handles quoting in raw SQL"""
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
            if char in ('"', "'") and not in_string:
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
        """Insert data - quote table and column names, skip autoincrement"""
        if not self.engine:
            raise Exception("No database selected")

        # Get schema to detect autoincrement columns
        schema = self.get_table_schema(table_name)
        cleaned_data = {}

        for key, value in data.items():
            col_info = next((c for c in schema if c['name'] == key), None)
            if col_info:
                # Skip autoincrement/SERIAL columns
                if col_info.get('autoincrement', False):
                    continue
        
                # Convert empty strings to None for numeric types
                if value == '':
                    if col_info['type'].upper() in ['INTEGER', 'INT', 'BIGINT', 'SMALLINT', 'DECIMAL', 'NUMERIC', 'REAL', 'DOUBLE PRECISION', 'FLOAT']:
                        cleaned_data[key] = None
                    else:
                        cleaned_data[key] = value
                else:
                    cleaned_data[key] = value

        # Quote all identifiers
        quoted_table = self._quote_identifier(table_name)
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
        """Update data - quote identifiers"""
        if not self.engine:
            raise Exception("No database selected")
        
        # Quote table name and column names in SET clause
        quoted_table = self._quote_identifier(table_name)
        sets = ', '.join([f'{self._quote_identifier(k)}=:{k}' for k in data.keys()])
        query = f"UPDATE {quoted_table} SET {sets} WHERE {condition}"
        
        try:
            with self.engine.connect() as conn:
                conn.execute(text(query), data)
                conn.commit()
        except IntegrityError as e:
            raise ValueError(f"Integrity constraint violation: {str(e)}")

    def delete(self, table_name, condition):
        """Delete data - quote table name"""
        if not self.engine:
            raise Exception("No database selected")
        
        quoted_table = self._quote_identifier(table_name)
        query = f"DELETE FROM {quoted_table} WHERE {condition}"
        
        try:
            with self.engine.connect() as conn:
                conn.execute(text(query))
                conn.commit()
        except Exception as e:
            self.logger.error(f"Delete error: {e}")
            raise

    def delete_table(self, table_name):
        """Drop table - quote name"""
        if not self.engine:
            raise Exception("No database selected")
        
        quoted_table = self._quote_identifier(table_name)
        try:
            with self.engine.connect() as conn:
                conn.execute(text(f"DROP TABLE IF EXISTS {quoted_table} CASCADE"))
                conn.commit()
        except Exception as e:
            self.logger.error(f"Drop table error: {e}")
            raise

    def can_convert_column(self, table_name, column, new_type):
        return True

    def modify_table(self, old_table_name, new_table_name, new_columns):
        """Modify table - FIXED VERSION with proper constraint handling"""
        if not self.engine:
            raise Exception("No database selected")
    
        try:
            with self.engine.connect() as conn:
                old_schema = self.get_table_schema(old_table_name)
                old_columns = {col['name']: col for col in old_schema}
            
                import secrets
                temp_table_name = f"temp_{old_table_name}_{secrets.token_hex(4)}"
            
                self.logger.info(f"="*80)
                self.logger.info(f"POSTGRESQL MODIFY TABLE DEBUG")
                self.logger.info(f"Old table: {old_table_name}")
                self.logger.info(f"New table: {new_table_name}")
                self.logger.info(f"Incoming column definitions:")
                for i, col_def in enumerate(new_columns):
                    self.logger.info(f"  [{i}] {col_def}")
                self.logger.info(f"="*80)
            
                # === STEP 1: Parse new column definitions ===
                quoted_new_columns = []
                new_column_info = {}
                composite_pk_cols = []  # Track columns that belong to a composite PK

                for col_def in new_columns:
                    # ── Handle table-level PRIMARY KEY (...) constraint ──
                    # These arrive when the frontend/modify_table sends a composite PK clause
                    # e.g. "PRIMARY KEY (col1, col2)"
                    stripped = col_def.strip()
                    if re.match(r'^PRIMARY\s+KEY\s*\(', stripped, re.IGNORECASE):
                        # Keep as-is; will be appended after column defs
                        quoted_new_columns.append(stripped)
                        # Parse the column names out so we can mark them as PK below
                        pk_match = re.search(r'PRIMARY\s+KEY\s*\(([^)]+)\)', stripped, re.IGNORECASE)
                        if pk_match:
                            composite_pk_cols = [c.strip().strip('"') for c in pk_match.group(1).split(',')]
                        self.logger.info(f"Detected table-level PRIMARY KEY clause: {stripped}")
                        continue

                    parts = col_def.split(maxsplit=1)
                    if len(parts) >= 2:
                        col_name = parts[0]
                        rest = parts[1]
                        rest_upper = rest.upper()
                    
                        self.logger.info(f"Parsing column: {col_name}")
                        self.logger.info(f"  Definition: {rest}")
                    
                        # ✅ Extract CHECK constraint
                        check_constraint = None
                        rest_without_check = rest
                        if 'CHECK' in rest_upper:
                            check_match = re.search(r'CHECK\s*\((.+?)\)\s*$', rest, re.IGNORECASE | re.DOTALL)
                            if check_match:
                                raw_check = check_match.group(1).strip()
                                # Clean the CHECK expression before storing
                                check_constraint = self._clean_check_expression(raw_check)
                                # Remove CHECK clause from rest
                                rest_without_check = re.sub(r'CHECK\s*\(.+?\)\s*$', '', rest, flags=re.IGNORECASE | re.DOTALL).strip()
                        
                        # Quote the column name to preserve case
                        quoted_col_def = f'{self._quote_identifier(col_name)} {rest_without_check}'
                        
                        # ✅ Add CHECK constraint at the end
                        if check_constraint:
                            quoted_col_def += f' CHECK ({check_constraint})'
                        
                        quoted_new_columns.append(quoted_col_def)

                        # Track column info
                        has_pk = 'PRIMARY KEY' in rest_upper
                        has_not_null = 'NOT NULL' in rest_upper
                        has_unique = 'UNIQUE' in rest_upper
                        is_serial = 'SERIAL' in rest_upper or 'BIGSERIAL' in rest_upper
                    
                        self.logger.info(f"  Constraints: PK={has_pk}, NOT_NULL={has_not_null}, UNIQUE={has_unique}, SERIAL={is_serial}, CHECK={check_constraint}")
                    
                        new_column_info[col_name] = {
                            'has_pk': has_pk,
                            'has_not_null': has_not_null,
                            'has_unique': has_unique,
                            'is_serial': is_serial,
                            'type': rest_without_check.split()[0] if rest_without_check else 'TEXT',
                            'definition': rest,
                            'check_constraint': check_constraint
                        }
                    else:
                        self.logger.warning(f"Column definition too short: {col_def}")
                        quoted_new_columns.append(self._quote_identifier(col_def))
                        new_column_info[col_def] = {
                            'has_pk': False, 
                            'has_not_null': False,
                            'has_unique': False,
                            'is_serial': False,
                            'type': 'TEXT',
                            'definition': 'TEXT',
                            'check_constraint': None
                        }
            
                # === STEP 2: Create temp table ===
                col_def = ', '.join(quoted_new_columns)
                quoted_temp = self._quote_identifier(temp_table_name)
            
                self.logger.info(f"Creating temp table: {temp_table_name}")
                self.logger.info(f"SQL: CREATE TABLE {quoted_temp} ({col_def})")
            
                try:
                    conn.execute(text(f"CREATE TABLE {quoted_temp} ({col_def})"))
                    self.logger.info(f"  ✓ Temp table created successfully")
                except Exception as e:
                    self.logger.error(f"  ✗ Failed to create temp table")
                    self.logger.error(f"  Definition: {col_def}")
                    self.logger.error(f"  Error: {str(e)}")
                    raise Exception(f"Failed to create table structure: {str(e)}")
            
                # === STEP 3: Build intelligent column mapping ===
                new_column_names = list(new_column_info.keys())
                old_column_names = list(old_columns.keys())
            
                column_mapping = {}  # new_name -> old_name
                used_old_columns = set()
            
                # First pass: Match by exact name (no rename)
                for new_col in new_column_names:
                    if new_col in old_columns:
                        column_mapping[new_col] = new_col
                        used_old_columns.add(new_col)
            
                # Second pass: Map remaining columns by position (handles renames)
                unmapped_new = [c for c in new_column_names if c not in column_mapping]
                unmapped_old = [c for c in old_column_names if c not in used_old_columns]
            
                for i, new_col in enumerate(unmapped_new):
                    if i < len(unmapped_old):
                        column_mapping[new_col] = unmapped_old[i]
                        self.logger.debug(f"Mapped renamed column: {unmapped_old[i]} -> {new_col}")
            
                # === STEP 4: Copy data with proper handling ===
                if column_mapping:
                    select_parts = []
                    insert_cols = []

                    for new_col_name, old_col_name in column_mapping.items():
                        new_col_info = new_column_info[new_col_name]

                        # ✅ CRITICAL: Skip SERIAL columns - they're auto-generated!
                        if new_col_info['is_serial']:
                            self.logger.debug(f"Skipping SERIAL column {new_col_name} in copy")
                            continue

                        insert_cols.append(self._quote_identifier(new_col_name))
                        quoted_old = self._quote_identifier(old_col_name)
                        
                        new_col_type = new_col_info['type'].upper()

                        # ✅ CRITICAL: Handle type conversions with explicit casting
                        needs_type_cast = False
                        cast_expression = quoted_old
                        
                        # Check if we need to cast for date/time types
                        if any(dt in new_col_type for dt in ['DATE', 'TIMESTAMP', 'TIME']):
                            # Get old column type to determine if casting is needed
                            old_col_info = old_columns.get(old_col_name, {})
                            old_col_type = old_col_info.get('type', '').upper() if old_col_info else ''
                            
                            # Cast if converting from VARCHAR/TEXT to date/time types
                            if 'VARCHAR' in old_col_type or 'TEXT' in old_col_type or 'CHAR' in old_col_type:
                                needs_type_cast = True
                                # Use PostgreSQL's flexible casting with error handling
                                if 'TIMESTAMP' in new_col_type:
                                    cast_expression = f"NULLIF({quoted_old}, '')::TIMESTAMP"
                                elif 'DATE' in new_col_type:
                                    cast_expression = f"NULLIF({quoted_old}, '')::DATE"
                                elif 'TIME' in new_col_type:
                                    cast_expression = f"NULLIF({quoted_old}, '')::TIME"

                        # Handle NOT NULL constraint with COALESCE (only for non-PK, non-serial)
                        if new_col_info['has_not_null'] and not new_col_info['has_pk'] and not new_col_info['is_serial']:
                            if 'INT' in new_col_type or 'SERIAL' in new_col_type:
                                select_parts.append(f"COALESCE({cast_expression if needs_type_cast else quoted_old}, 0)")
                            elif 'REAL' in new_col_type or 'DOUBLE' in new_col_type or 'FLOAT' in new_col_type or 'NUMERIC' in new_col_type or 'DECIMAL' in new_col_type:
                                select_parts.append(f"COALESCE({cast_expression if needs_type_cast else quoted_old}, 0.0)")
                            elif 'DATE' in new_col_type:
                                select_parts.append(f"COALESCE({cast_expression}, CURRENT_DATE)")
                            elif 'TIMESTAMP' in new_col_type:
                                select_parts.append(f"COALESCE({cast_expression}, CURRENT_TIMESTAMP)")
                            elif 'TIME' in new_col_type:
                                select_parts.append(f"COALESCE({cast_expression}, CURRENT_TIME)")
                            else:  # TEXT, VARCHAR
                                select_parts.append(f"COALESCE({cast_expression if needs_type_cast else quoted_old}, '')")
                        else:
                            # For PK or regular columns, copy directly (preserves NULL) with casting if needed
                            select_parts.append(cast_expression if needs_type_cast else quoted_old)
                
                    # Execute the copy
                    if select_parts:
                        select_cols = ', '.join(select_parts)
                        insert_cols_str = ', '.join(insert_cols)
                        quoted_old_table = self._quote_identifier(old_table_name)
                    
                        copy_query = f"INSERT INTO {quoted_temp} ({insert_cols_str}) SELECT {select_cols} FROM {quoted_old_table}"
                        self.logger.debug(f"Copy query: {copy_query}")
                        conn.execute(text(copy_query))
            
                # === STEP 5: Replace old table with new ===
                quoted_old = self._quote_identifier(old_table_name)
                quoted_new = self._quote_identifier(new_table_name)

                # Drop inbound FK constraints from OTHER tables that reference old_table_name,
                # then recreate them after the rename so they point at new_table_name.
                inbound_fks = []
                try:
                    fk_result = conn.execute(text("""
                        SELECT
                            tc.table_name        AS src_table,
                            tc.constraint_name   AS constraint_name,
                            kcu.column_name      AS src_col,
                            ccu.column_name      AS ref_col,
                            rc.update_rule,
                            rc.delete_rule
                        FROM information_schema.table_constraints AS tc
                        JOIN information_schema.key_column_usage AS kcu
                            ON tc.constraint_name = kcu.constraint_name
                            AND tc.table_schema = kcu.table_schema
                        JOIN information_schema.constraint_column_usage AS ccu
                            ON ccu.constraint_name = tc.constraint_name
                            AND ccu.table_schema = tc.table_schema
                        JOIN information_schema.referential_constraints AS rc
                            ON tc.constraint_name = rc.constraint_name
                        WHERE tc.constraint_type = 'FOREIGN KEY'
                          AND ccu.table_name = :ref_table
                          AND tc.table_name  != :ref_table
                    """), {'ref_table': old_table_name})
                    inbound_fks = fk_result.fetchall()
                except Exception as fk_err:
                    self.logger.warning(f"Could not query inbound FKs: {fk_err}")

                for fk in inbound_fks:
                    src_table, constraint_name, _, _, _, _ = fk
                    quoted_src = self._quote_identifier(src_table)
                    self.logger.info(f"Dropping inbound FK {constraint_name} on {src_table}")
                    conn.execute(text(f"ALTER TABLE {quoted_src} DROP CONSTRAINT IF EXISTS {constraint_name}"))

                conn.execute(text(f"DROP TABLE {quoted_old}"))

                conn.execute(text(f"ALTER TABLE {quoted_temp} RENAME TO {quoted_new}"))

                # Recreate inbound FKs now pointing at new_table_name
                for fk in inbound_fks:
                    src_table, constraint_name, src_col, ref_col, on_update, on_delete = fk
                    quoted_src = self._quote_identifier(src_table)
                    quoted_src_col = self._quote_identifier(src_col)
                    quoted_ref_col = self._quote_identifier(ref_col)
                    self.logger.info(f"Recreating inbound FK {constraint_name} on {src_table} -> {new_table_name}")
                    conn.execute(text(f"""
                        ALTER TABLE {quoted_src}
                        ADD CONSTRAINT {constraint_name}
                        FOREIGN KEY ({quoted_src_col})
                        REFERENCES {quoted_new}({quoted_ref_col})
                        ON UPDATE {on_update} ON DELETE {on_delete}
                    """))

                conn.commit()
                self.logger.info(f"✓ Table modification completed successfully")
            
        except Exception as e:
            self.logger.error(f"✗ Table modification failed: {str(e)}")
            if self.engine:
                with self.engine.connect() as conn:
                    conn.rollback()
            raise Exception(f"Failed to modify table: {str(e)}")

    def create_default_table(self, table_name):
        """Create default table - quote name"""
        if not self.engine:
            raise Exception("No database selected")
        
        quoted_table = self._quote_identifier(table_name)
        try:
            with self.engine.connect() as conn:
                conn.execute(text(f"CREATE TABLE IF NOT EXISTS {quoted_table} (id SERIAL PRIMARY KEY)"))
                conn.commit()
        except Exception as e:
            self.logger.error(f"Error creating default table: {e}")
            raise
        
    def supports_joins(self):
        return True

    def supports_triggers(self):
        return True

    def supports_plsql(self):
        return True

    def execute_join(self, join_query):
        return self.execute_query(join_query)

    def create_trigger(self, trigger_name: str, table_name: str, trigger_timing: str, trigger_event: str, trigger_body: str):
        """Create trigger with proper function body handling - FULLY FIXED with logging"""
        self.logger.debug(f"CREATE_TRIGGER CALLED: name={trigger_name}, table={table_name}, timing={trigger_timing}, event={trigger_event}")
        self.logger.debug(f"Raw trigger body:\n{trigger_body}")

        q_table = self._quote_identifier(table_name)
        q_trigger = self._quote_identifier(trigger_name)
        import secrets
        func_name = f"trigger_func_{table_name.lower()}_{trigger_name.lower()}_{secrets.token_hex(4)}"

        self.logger.debug(f"Generated function name: {func_name}")
        self.logger.debug(f"Quoted table: {q_table}, Quoted trigger: {q_trigger}")

        # Clean and prepare body
        body = trigger_body.strip().rstrip(';')

        has_return = re.search(r'\bRETURN\b', body, re.IGNORECASE) is not None
        self.logger.debug(f"Body has RETURN statement: {has_return}")

        if body.upper().startswith('BEGIN') and body.upper().endswith('END'):
            trigger_function_body = body
        else:
            inner_body = body + (';' if body and not body.endswith(';') else '')
            return_stmt = "RETURN OLD;" if trigger_event.upper() == 'DELETE' else "RETURN NEW;"
            if not has_return:
                inner_body += f"\n{return_stmt}"
            trigger_function_body = f"BEGIN\n    {inner_body}\nEND;"

        self.logger.debug(f"Final PL/pgSQL function body:\n{trigger_function_body}")

        # Build full SQL using separate safe statements
        sql_parts = [
            f"DROP TRIGGER IF EXISTS {q_trigger} ON {q_table}",
            f"DROP FUNCTION IF EXISTS {func_name}() CASCADE",
            f"""
CREATE OR REPLACE FUNCTION {func_name}()
RETURNS TRIGGER AS $$
{trigger_function_body}
$$ LANGUAGE plpgsql;
            """.strip(),
            f"""
CREATE TRIGGER {q_trigger}
    {trigger_timing} {trigger_event} ON {q_table}
    FOR EACH ROW
    EXECUTE FUNCTION {func_name}();
            """.strip()
        ]

        full_sql = ";\n".join(sql_parts) + ";"
        self.logger.info(f"EXECUTING TRIGGER CREATION SQL:\n{full_sql}")

        try:
            with self.engine.begin() as conn:  # This ensures proper transaction + commit
                for part in sql_parts:
                    self.logger.debug(f"Executing part: {part}")
                    conn.execute(text(part))
                self.logger.info(f"✅ All trigger SQL parts executed successfully")

            self.logger.info(f"🎉 Trigger '{trigger_name}' created successfully on table '{table_name}'")
            return {'success': True, 'message': f"Trigger '{trigger_name}' created and ready to cast its magic!"}

        except Exception as e:
            self.logger.error(f"💀 TRIGGER CREATION FAILED: {str(e)}")
            import traceback
            self.logger.error(f"Full traceback:\n{traceback.format_exc()}")
            raise ValueError(f"Failed to create trigger: {str(e)}")
        
    def create_trigger_in_transaction(self, conn, trigger_name, table_name, timing, event, body):
        """
        Create trigger within an existing transaction (no commit).
        Used during imports/conversions to avoid closing the transaction.
        
        Args:
            conn: Active SQLAlchemy connection object
            trigger_name: Name of trigger
            table_name: Table to attach trigger to
            timing: BEFORE/AFTER/INSTEAD OF
            event: INSERT/UPDATE/DELETE
            body: Trigger body (PL/pgSQL statements)
        """
        logger.debug(f"CREATE_TRIGGER_IN_TRANSACTION CALLED: name={trigger_name}, table={table_name}, timing={timing}, event={event}")
        logger.debug(f"Raw trigger body:\n{body}")
        
        # Generate unique function name
        body_hash = hashlib.md5(body.encode()).hexdigest()[:8]
        func_name = f"trigger_func_{table_name}_{trigger_name}_{body_hash}"
        logger.debug(f"Generated function name: {func_name}")
        
        # Quote identifiers
        quoted_table = self._quote_identifier(table_name)
        quoted_trigger = self._quote_identifier(trigger_name)
        logger.debug(f"Quoted table: {quoted_table}, Quoted trigger: {quoted_trigger}")
        
        # Sanitize: strip MySQL "CREATE TRIGGER ... FOR EACH ROW BEGIN ... END" wrapper
        import re as _re
        create_trig_match = _re.search(
            r'\bCREATE\s+TRIGGER\b.+?\bFOR\s+EACH\s+ROW\b\s*\bBEGIN\b(.+)\bEND\b\s*;?\s*$',
            body,
            _re.DOTALL | _re.IGNORECASE
        )
        if create_trig_match:
            body = create_trig_match.group(1).strip()
        elif _re.match(r'^\s*BEGIN\b', body, _re.IGNORECASE):
            # Strip any leftover BEGIN...END wrapper
            inner = _re.search(r'\bBEGIN\b(.+)\bEND\b', body, _re.DOTALL | _re.IGNORECASE)
            if inner:
                body = inner.group(1).strip()

        # Strip any stray RETURN NEW/OLD (will be added below if missing)
        body = _re.sub(r'\bRETURN\s+(NEW|OLD)\s*;?\s*$', '', body, flags=_re.IGNORECASE).strip()

        # Build PL/pgSQL function body
        has_return = 'RETURN' in body.upper()
        logger.debug(f"Body has RETURN statement: {has_return}")

        if not has_return:
            return_stmt = "RETURN OLD;" if event.upper() == 'DELETE' else "RETURN NEW;"
            plpgsql_body = f"BEGIN\n    {body}\n    {return_stmt}\nEND;"
        else:
            plpgsql_body = f"BEGIN\n    {body}\nEND;"
        
        logger.debug(f"Final PL/pgSQL function body:\n{plpgsql_body}")
        
        sql_parts = [
            f"DROP TRIGGER IF EXISTS {quoted_trigger} ON {quoted_table}",
            f"DROP FUNCTION IF EXISTS {func_name}() CASCADE",
            f"CREATE OR REPLACE FUNCTION {func_name}()\nRETURNS TRIGGER AS $$\n{plpgsql_body}\n$$ LANGUAGE plpgsql",
            f"CREATE TRIGGER {quoted_trigger}\n    {timing.upper()} {event.upper()} ON {quoted_table}\n    FOR EACH ROW\n    EXECUTE FUNCTION {func_name}()",
        ]

        logger.info(f"EXECUTING TRIGGER CREATION SQL (parts):\n" + ";\n".join(sql_parts) + ";")

        # Execute each statement individually within the provided transaction - NO COMMIT
        for part in sql_parts:
            logger.debug(f"Executing part: {part}")
            conn.execute(text(part))

        logger.info(f"✅ All trigger SQL parts executed successfully (within transaction)")
        # DO NOT COMMIT - let the caller handle it

    def list_triggers(self, table_name=None):
        """List triggers - extract function body"""
        if not self.engine:
            return []

        try:
            with self.engine.connect() as conn:
                if table_name:
                    sql = """
                        SELECT trigger_name, event_object_table, action_statement, 
                            action_timing, event_manipulation
                        FROM information_schema.triggers
                        WHERE trigger_schema = 'public' AND event_object_table = :table
                    """
                    params = {'table': table_name}
                else:
                    sql = """
                        SELECT trigger_name, event_object_table, action_statement,
                            action_timing, event_manipulation
                        FROM information_schema.triggers
                        WHERE trigger_schema = 'public'
                    """
                    params = {}
            
                result = conn.execute(text(sql), params)
            
                triggers = []
                for r in result:
                    action_statement = r[2]
                    
                    # ✅ Extract function name from action_statement
                    import re
                    func_match = re.search(r'EXECUTE (?:FUNCTION|PROCEDURE)\s+(\w+)\(\)', 
                                        action_statement, re.IGNORECASE)
                    
                    if func_match:
                        func_name = func_match.group(1)
                        
                        # ✅ Get actual function body
                        func_result = conn.execute(text("""
                            SELECT prosrc FROM pg_proc WHERE proname = :fname
                        """), {'fname': func_name})
                        
                        func_row = func_result.fetchone()
                        trigger_body = func_row[0] if func_row else action_statement
                    else:
                        trigger_body = action_statement
                    
                    # Strip outer BEGIN...END wrapper and RETURN NEW/OLD so the
                    # body is portable to MySQL and SQLite without double-wrapping
                    import re as _re
                    body_match = _re.search(r'\bBEGIN\b(.+?)(?:\bEND\b)', trigger_body, _re.DOTALL | _re.IGNORECASE)
                    if body_match:
                        trigger_body = body_match.group(1).strip()
                    trigger_body = _re.sub(r'\bRETURN\s+(NEW|OLD)\s*;?', '', trigger_body, flags=_re.IGNORECASE).strip()

                    triggers.append({
                        'name': r[0],
                        'table': r[1],
                        'sql': trigger_body,  # clean inner body, portable across DBs
                        'timing': r[3],
                        'event': r[4]
                    })
            
                return triggers
        except Exception as e:
            logger.error(f"Error listing triggers: {e}")
            return []

    def get_trigger_details(self, trigger_name):
        with self.engine.connect() as conn:
            result = conn.execute(text("""
                SELECT trigger_name, event_object_table, action_statement, action_timing, event_manipulation
                FROM information_schema.triggers
                WHERE trigger_schema = 'public' AND trigger_name = :name
            """), {'name': trigger_name})
            row = result.fetchone()
            if row:
                return {'name': row[0], 'table': row[1], 'sql': row[2], 'timing': row[3], 'event': row[4]}
            return None

    def delete_trigger(self, trigger_name: str, table_name: str = None):
        logger.debug(f"delete_trigger start: name={trigger_name}, table={table_name}")
        trigger_name_lower = trigger_name.lower()
        logger.debug(f"Lower name: {trigger_name_lower}")
        q_trigger = self._quote_identifier(trigger_name_lower)
        logger.debug(f"Quoted trigger: {q_trigger}")
        func_name = f"trigger_func_{trigger_name_lower}"
        logger.debug(f"Func name: {func_name}")

        if not table_name:
            logger.debug("No table, auto-detecting")
            with self.engine.connect() as conn:
                sql = """
                    SELECT event_object_table 
                    FROM information_schema.triggers 
                    WHERE trigger_name = :tname AND trigger_schema = 'public'
                """
                params = {'tname': trigger_name_lower}
                logger.debug(f"Auto SQL: {sql}, params={params}")
                result = conn.execute(text(sql), params)
                logger.debug("Auto query executed")
                row = result.fetchone()
                if row:
                    table_name = row[0]
                    logger.debug(f"Detected table: {table_name}")
                else:
                    logger.error("Trigger not found for auto-detect")
                    raise ValueError(f"Trigger '{trigger_name}' not found")

        q_table = self._quote_identifier(table_name)
        logger.debug(f"Quoted table: {q_table}")

        sql = f"""
        DROP TRIGGER IF EXISTS {q_trigger} ON {q_table};
        DROP FUNCTION IF EXISTS public.{func_name}() CASCADE;
        """
        logger.debug(f"Delete SQL: \n{sql}")

        with self.engine.connect() as conn:
            logger.debug("Connected for delete")
            conn.execute(text(sql))
            logger.debug("SQL executed")
            conn.commit()
            logger.debug("Committed")
        logger.debug("delete_trigger success")
        
    def supports_aggregation(self):
        """Return True if database supports aggregation (GROUP BY, SUM, AVG, etc.)"""
        return True  # SQL databases support GROUP BY aggregation
        
    def supports_procedures(self):
        return True

    def list_procedures(self):
        if not self.engine:
            return []
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text("""
                    SELECT 
                        proname AS name,
                        'FUNCTION' AS type,
                        pg_get_functiondef(p.oid) AS code
                    FROM pg_proc p
                    JOIN pg_namespace n ON p.pronamespace = n.oid
                    WHERE n.nspname = 'public' AND p.prokind = 'f'
                    ORDER BY proname
                """))
                return [{'name': r[0], 'type': r[1], 'code': r[2]} for r in result]
        except Exception as e:
            self.logger.error(f"Error listing PostgreSQL functions: {e}")
            return []

    def get_procedure_definition(self, procedure_name, **kwargs):
        """Get full CREATE definition - formatted string version"""
        if not self.engine:
            return None
            
        try:
            with self.engine.connect() as conn:
                # Format the name directly — safe since it's from trusted source
                safe_name = procedure_name.replace("'", "''")  # escape single quotes
                query = text(f"SELECT pg_get_functiondef('{safe_name}'::regproc)")
                result = conn.execute(query)
                row = result.fetchone()
                
                if row and row[0]:
                    return row[0].strip()
                else:
                    return None
        except Exception as e:
            self.logger.error(f"Failed to fetch definition: {e}")
            return None
        
    def get_procedure_call_syntax(self):
        """
        For PostgreSQL functions that return tables/sets, we need SELECT * FROM ...
        to get proper column names instead of composite tuples.
        """
        return "SELECT * FROM {name}()"

    def execute_procedure(self, procedure_code):
        """
        Execute PostgreSQL function code or SELECT statement.
        Handles both CREATE FUNCTION and direct function calls.
        """
        import re
        
        code = procedure_code.strip()
        code_upper = code.upper()
        
        # ✅ NEW: Fix RETURNS TABLE syntax - remove table prefixes from column names
        # Pattern: RETURNS TABLE(table.col TYPE, ...) → RETURNS TABLE(col TYPE, ...)
        code = re.sub(
            r'RETURNS\s+TABLE\s*\((.*?)\)',
            lambda m: 'RETURNS TABLE(' + re.sub(r'\w+\.(\w+)', r'\1', m.group(1)) + ')',
            code,
            flags=re.IGNORECASE | re.DOTALL
        )
        
        
        # Check if it's a SELECT call or CREATE statement
        is_select = code_upper.startswith('SELECT ')
        is_create = 'CREATE' in code_upper and 'FUNCTION' in code_upper
        
        try:
            with self.engine.begin() as conn:
                if is_select:
                    # Execute function call via SELECT
                    result = conn.execute(text(code))
                    
                    # Try to fetch results
                    if result.returns_rows:
                        rows = result.fetchall()
                        if rows:
                            # Get column names from cursor description
                            column_names = None
                            
                            try:
                                # Method 1: From result.keys()
                                if hasattr(result, 'keys') and result.keys():
                                    column_names = list(result.keys())
                            except:
                                pass
                            
                            if not column_names:
                                try:
                                    # Method 2: From cursor description
                                    if hasattr(result, 'cursor') and result.cursor and hasattr(result.cursor, 'description'):
                                        column_names = [desc[0] for desc in result.cursor.description]
                                except:
                                    pass
                            
                            if not column_names:
                                try:
                                    # Method 3: From first row's _mapping
                                    if hasattr(rows[0], '_mapping'):
                                        column_names = list(rows[0]._mapping.keys())
                                except:
                                    pass
                            
                            # Convert rows to dictionaries
                            if column_names:
                                formatted_rows = []
                                for row in rows:
                                    if hasattr(row, '_mapping'):
                                        formatted_rows.append(dict(row._mapping))
                                    elif isinstance(row, tuple):
                                        formatted_rows.append(dict(zip(column_names, row)))
                                    else:
                                        formatted_rows.append(row)
                                return formatted_rows
                            else:
                                # Fallback: generic column names
                                if isinstance(rows[0], tuple):
                                    column_names = [f'column_{i}' for i in range(len(rows[0]))]
                                    return [dict(zip(column_names, row)) for row in rows]
                                else:
                                    return [dict(row._mapping) if hasattr(row, '_mapping') else row for row in rows]
                        else:
                            return {"status": "Function executed successfully"}
                    else:
                        return {"status": "Function executed successfully"}
                        
                elif is_create:
                    # Create/replace function
                    conn.execute(text(code))
                    return {"status": "Function created/replaced successfully!"}
                else:
                    # Try to execute as-is
                    result = conn.execute(text(code))
                    if result.returns_rows:
                        rows = [dict(row._mapping) for row in result.fetchall()]
                        return rows if rows else {"status": "Executed successfully"}
                    else:
                        return {"status": "Executed successfully"}
                        
        except Exception as e:
            raise ValueError(f"Execution failed: {str(e)}")

    def drop_procedure(self, procedure_name, is_function=True):
        """Drop a stored procedure or function - FIXED VERSION with signature detection"""
        try:
            with self._get_connection() as conn:
                # âœ… CRITICAL FIX: Get the full function signature from pg_proc
                # This query gets ALL overloaded versions of the function
                result = conn.execute(text("""
                    SELECT 
                        p.proname,
                        pg_catalog.pg_get_function_identity_arguments(p.oid) as args
                    FROM pg_proc p
                    JOIN pg_namespace n ON p.pronamespace = n.oid
                    WHERE n.nspname = 'public' 
                    AND p.proname = :proc_name
                """), {'proc_name': procedure_name})
                
                rows = result.fetchall()
                
                if not rows:
                    self.logger.error(f"Function {procedure_name} not found in pg_proc")
                    raise ValueError(f"Function {procedure_name} does not exist")
                
                # Drop all overloaded versions
                for row in rows:
                    func_name = row[0]
                    args = row[1] if row[1] else ''  # Empty string if no args
                    
                    # Build the full DROP statement with signature
                    if args:
                        drop_sql = f"DROP FUNCTION IF EXISTS {func_name}({args}) CASCADE"
                    else:
                        drop_sql = f"DROP FUNCTION IF EXISTS {func_name}() CASCADE"
                    
                    self.logger.info(f"Executing: {drop_sql}")
                    conn.execute(text(drop_sql))
                
                conn.commit()
                self.logger.info(f"âœ… Dropped function {procedure_name} successfully")
                return {"success": True}
                
        except Exception as e:
            import logging
            logging.error(f"Error dropping function: {str(e)}")
            raise ValueError(f"Failed to drop function: {str(e)}")
        
    def convert_trigger_syntax(self, trigger_body, trigger_event, table_name):
        """
        Convert MySQL trigger syntax to PostgreSQL PL/pgSQL.
        
        MySQL → PostgreSQL conversions:
        - SET variable = value → variable := value
        - NEW.column → NEW.column (same, but need to ensure proper context)
        - Remove any MySQL-specific syntax
        """
        import re
        
        # Convert MySQL SET to PostgreSQL assignment
        # Pattern: SET NEW.column = value
        converted = re.sub(
            r'\bSET\s+(NEW\.\w+)\s*=\s*',
            r'\1 := ',
            trigger_body,
            flags=re.IGNORECASE
        )
        
        # Convert MySQL functions to PostgreSQL equivalents
        converted = converted.replace('UPPER(', 'UPPER(')  # Same, but validate
        
        return converted.strip()
        
    def convert_procedure_syntax(self, procedure_code, proc_name, proc_type):
        """
        Convert procedure syntax from other databases to PostgreSQL function format.
        Handles MySQL PROCEDURE/FUNCTION → PostgreSQL FUNCTION conversion.
        """
        import re
        
        code_upper = procedure_code.upper()
        
        # ✅ Check if this is MySQL syntax
        if 'DELIMITER' in code_upper or proc_type == 'PROCEDURE':
            return self._convert_mysql_to_postgresql(procedure_code, proc_name, proc_type)
        
        # ✅ Already PostgreSQL format - return as-is
        return procedure_code

    def _convert_mysql_to_postgresql(self, mysql_code, proc_name, proc_type):
        """
        Convert MySQL procedure/function to PostgreSQL function.
        
        MySQL → PostgreSQL conversions:
        - DELIMITER statements → $$ dollar quotes
        - PROCEDURE → FUNCTION with RETURNS type
        - IN/OUT parameters → Function parameters
        - BEGIN...END → BEGIN...END with LANGUAGE plpgsql
        - Variable declarations (DECLARE) → Keep as-is
        - SELECT INTO → Keep as-is (compatible)
        """
        import re
        
        # Remove DELIMITER statements
        cleaned = re.sub(r'DELIMITER\s+\S+\s*[\r\n]*', '', mysql_code, flags=re.IGNORECASE)
        
        # Extract the procedure/function definition
        # Pattern: CREATE (PROCEDURE|FUNCTION) name(params) [RETURNS type] BEGIN ... END
        create_match = re.search(
            r'CREATE\s+(?:PROCEDURE|FUNCTION)\s+`?(\w+)`?\s*\(([^)]*)\)(?:\s+RETURNS\s+(\w+(?:\(\d+(?:,\d+)?\))?))?',
            cleaned,
            re.IGNORECASE | re.DOTALL
        )
        
        if not create_match:
            # Fallback: try simpler pattern
            create_match = re.search(
                r'CREATE\s+(?:PROCEDURE|FUNCTION)\s+(\w+)',
                cleaned,
                re.IGNORECASE
            )
            if not create_match:
                raise ValueError("Could not parse MySQL procedure/function syntax")
        
        func_name = create_match.group(1)
        params = create_match.group(2) if len(create_match.groups()) >= 2 else ''
        returns_type = create_match.group(3) if len(create_match.groups()) >= 3 else None
        
        # Extract body (between BEGIN and END)
        body_match = re.search(
            r'BEGIN\s+(.*?)\s+END',
            cleaned,
            re.DOTALL | re.IGNORECASE
        )
        
        if not body_match:
            raise ValueError("Could not extract procedure body")
        
        body = body_match.group(1).strip()
        
        # ✅ Convert MySQL-specific syntax in body
        
        # Convert variable declarations: DECLARE var TYPE; → var TYPE;
        body = re.sub(
            r'DECLARE\s+(\w+)\s+(\w+(?:\([^)]+\))?)\s*;',
            r'\1 \2;',
            body,
            flags=re.IGNORECASE
        )
        
        # Convert SET to := for assignments (except SET in UPDATE statements)
        # Only convert standalone SET statements, not SET in UPDATE
        body = re.sub(
            r'\bSET\s+(\w+)\s*=',
            r'\1 :=',
            body,
            flags=re.IGNORECASE
        )
        
        # Restore UPDATE ... SET (fix the conversion above)
        body = re.sub(
            r'UPDATE\s+(\w+)\s+(\w+)\s*:=',
            r'UPDATE \1 SET \2 =',
            body,
            flags=re.IGNORECASE
        )
        
        # Convert parameter types
        if params:
            # Remove IN/OUT/INOUT keywords (PostgreSQL uses different mechanism)
            params = re.sub(r'\b(IN|OUT|INOUT)\s+', '', params, flags=re.IGNORECASE)
            
            # Convert INT to INTEGER
            params = re.sub(r'\bINT\b', 'INTEGER', params, flags=re.IGNORECASE)
            
            # Convert VARCHAR without size to TEXT
            params = re.sub(r'\bVARCHAR\b(?!\()', 'TEXT', params, flags=re.IGNORECASE)
            
            # Convert DECIMAL to NUMERIC
            params = re.sub(r'\bDECIMAL\b', 'NUMERIC', params, flags=re.IGNORECASE)
        
        # ✅ Determine return type for PostgreSQL function
        if proc_type == 'PROCEDURE':
            # MySQL PROCEDURE → PostgreSQL FUNCTION returning VOID or TABLE
            # Check if body has SELECT without INTO (returns result set)
            if re.search(r'SELECT\s+(?!.*\bINTO\b)', body, re.IGNORECASE):
                # Procedure returns a result set - use RETURNS TABLE
                # Try to infer columns from the SELECT statement
                select_match = re.search(
                    r'SELECT\s+(.*?)\s+FROM',
                    body,
                    re.IGNORECASE | re.DOTALL
                )
                
                if select_match:
                    select_cols = select_match.group(1).strip()
                    # Simple heuristic: split by comma
                    cols = [c.strip() for c in select_cols.split(',')]
                    
                    # Build RETURNS TABLE clause with TEXT type for all columns
                    table_cols = []
                    for col in cols[:10]:  # Increased limit
                        # Extract column name (handle aliases with AS)
                        col_name = col.split()[-1].strip('`"')
                        # Use TEXT as default type to avoid type mismatch
                        table_cols.append(f"{col_name} TEXT")
                    
                    returns_clause = f"RETURNS TABLE({', '.join(table_cols)})"
                    
                    # ✅ NEW: Add explicit type casts in the SELECT to match RETURNS TABLE
                    # Find the full SELECT statement
                    full_select_match = re.search(r'SELECT\s+(.*?)(?:;|$)', body, re.IGNORECASE | re.DOTALL)
                    if full_select_match:
                        select_statement = full_select_match.group(0).strip()
                        # Add ::TEXT casts to each selected column
                        for col in cols:
                            col_name = col.split()[-1].strip('`"')
                            # Replace "column_name" with "column_name::TEXT"
                            select_statement = re.sub(
                                rf'\b{re.escape(col_name)}\b(?!\s*::)',
                                f'{col_name}::TEXT',
                                select_statement,
                                count=1
                            )
                        # Replace in body
                        body = body.replace(full_select_match.group(0), f"RETURN QUERY {select_statement}")
                    
                    # ✅ FIX: Qualify ALL column references AND add type casts
                    select_match = re.search(r'SELECT\s+(.*?)\s+FROM\s+(\w+)(.*?)(?:;|$)', body, re.IGNORECASE | re.DOTALL)
                    if select_match:
                        columns_part = select_match.group(1).strip()
                        table_ref = select_match.group(2).strip()
                        rest_of_query = select_match.group(3).strip()
                        
                        # Qualify each column in SELECT list AND add ::TEXT cast
                        qualified_cols = []
                        for col in columns_part.split(','):
                            col = col.strip()
                            if '.' not in col and col != '*':
                                qualified_cols.append(f"{table_ref}.{col}::TEXT")
                            elif col != '*':
                                qualified_cols.append(f"{col}::TEXT")
                            else:
                                qualified_cols.append(col)
                        
                        # ✅ CRITICAL: Also qualify columns in WHERE clause
                        if rest_of_query:
                            # Match: WHERE column operator value
                            rest_of_query = re.sub(
                                r'\bWHERE\s+(\w+)\s*([><=!]+)',
                                lambda m: f"WHERE {table_ref}.{m.group(1)} {m.group(2)}" if '.' not in m.group(1) else m.group(0),
                                rest_of_query,
                                flags=re.IGNORECASE
                            )
                            
                            # Also qualify AND/OR clauses
                            rest_of_query = re.sub(
                                r'\b(AND|OR)\s+(\w+)\s*([><=!]+)',
                                lambda m: f"{m.group(1)} {table_ref}.{m.group(2)} {m.group(3)}" if '.' not in m.group(2) else m.group(0),
                                rest_of_query,
                                flags=re.IGNORECASE
                            )
                        
                       # Rebuild SELECT with fully qualified columns
                        qualified_select = f"SELECT {', '.join(qualified_cols)} FROM {table_ref} {rest_of_query}"
                        if not qualified_select.endswith(';'):
                            qualified_select += ';'

                        # Replace the old SELECT with the new qualified one
                        # Remove any existing RETURN QUERY first
                        old_select = select_match.group(0)
                        body = body.replace(old_select, qualified_select)

                        # Now add RETURN QUERY only once at the beginning
                        body = f"RETURN QUERY {body}" if not body.strip().upper().startswith('RETURN') else body
                    else:
                        # Fallback: just add RETURN QUERY
                        body = re.sub(
                            r'(SELECT\s+.*?;)',
                            r'RETURN QUERY \1',
                            body,
                            count=1,
                            flags=re.IGNORECASE | re.DOTALL
                        )
                else:
                    returns_clause = "RETURNS VOID"
            else:
                # No result set - returns VOID
                returns_clause = "RETURNS VOID"
        
        elif proc_type == 'FUNCTION' and returns_type:
            # MySQL FUNCTION with explicit return type
            # Convert type names
            type_mapping = {
                'INT': 'INTEGER',
                'VARCHAR': 'TEXT',
                'DECIMAL': 'NUMERIC',
                'DATETIME': 'TIMESTAMP',
                'TINYINT': 'SMALLINT'
            }
            
            pg_type = returns_type.upper()
            for mysql_type, pg_replacement in type_mapping.items():
                if pg_type.startswith(mysql_type):
                    pg_type = pg_type.replace(mysql_type, pg_replacement, 1)
                    break
            
            returns_clause = f"RETURNS {pg_type}"
        else:
            # Default fallback
            returns_clause = "RETURNS VOID"
        
        # ✅ Build PostgreSQL function
        pg_function = f"""CREATE OR REPLACE FUNCTION {func_name}({params})
    {returns_clause} AS $$
    BEGIN
    {body}
    END;
    $$ LANGUAGE plpgsql;"""
        
        return pg_function

    def get_procedure_placeholder_example(self):
        """Helpful example for creating functions in PostgreSQL"""
        return """-- PostgreSQL Function Examples (PostgreSQL does not support procedures, only functions)

-- Example 1: Simple function returning table
CREATE OR REPLACE FUNCTION get_top_students(min_marks INT DEFAULT 85)
RETURNS TABLE(name TEXT, marks INT) AS $$
BEGIN
    RETURN QUERY
    SELECT students.name::TEXT, students.marks
    FROM students
    WHERE students.marks >= min_marks
    ORDER BY students.marks DESC;
END;
$$ LANGUAGE plpgsql;

-- Call it:
SELECT * FROM get_top_students(90);

-- Example 2: Function with side effects
CREATE OR REPLACE FUNCTION update_marks(student_id INT, new_marks INT)
RETURNS TEXT AS $$
BEGIN
    UPDATE students SET marks = new_marks WHERE id = student_id;
    RETURN 'Updated successfully';
END;
$$ LANGUAGE plpgsql;

-- Call it:
SELECT update_marks(1, 95);"""

    def execute_plsql(self, plsql_code: str):
        code = plsql_code.strip()
        if not code:
            return {"status": "No spell cast.", "notices": [], "refresh": False}

        code_upper = code.upper()

        is_create_function = 'CREATE' in code_upper and ('FUNCTION' in code_upper or 'PROCEDURE' in code_upper)
        is_select_from_function = 'SELECT' in code_upper and 'FROM' in code_upper
        is_call = code_upper.startswith('CALL')

        if is_create_function or is_select_from_function or is_call:
            sql = code
            if not sql.rstrip().endswith(';'):
                sql += ';'
        elif code.upper().startswith('DO') and '$$' in code:
            sql = code
            if not sql.rstrip().endswith(';'):
                sql += ';'
        else:
            body = code
            if not body.upper().startswith('BEGIN'):
                body = f"BEGIN\n    {body}\nEND;"
            sql = f"DO $$\n{body}\n$$;"

        try:
            # raw_connection() gives the actual psycopg2 connection from the pool
            raw_conn = self.engine.raw_connection()
            try:
                # Clear any stale notices from previous executions on this pooled connection
                raw_conn.notices.clear()

                cursor = raw_conn.cursor()
                try:
                    cursor.execute(sql)
                    raw_conn.commit()
                finally:
                    cursor.close()

                # psycopg2 populates raw_conn.notices with RAISE NOTICE messages
                collected_notices = []
                for n in raw_conn.notices:
                    clean = n.replace('NOTICE:  ', '').replace('NOTICE: ', '').strip()
                    if clean:
                        collected_notices.append(clean)

                self.logger.info(f"[PL/SQL] Execution complete. Notices collected: {collected_notices}")
            finally:
                # Return connection to pool instead of closing it
                raw_conn.close()

            return {
                "status": "Success!!",
                "notices": collected_notices,
                "refresh": True
            }
        except Exception as e:
            raise Exception(f"Execution failed: {str(e)}")
        
    def supports_user_management(self):
        """PostgreSQL supports user management"""
        return True
    
    def requires_credentials(self):
        """MongoDB doesn't require credentials for user login in this setup"""
        return True

    def list_users(self):
        """List all PostgreSQL users/roles"""
        if not self.engine:
            return []
    
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text("""
                    SELECT 
                        rolname as username,
                        rolcanlogin as can_login,
                        rolsuper as is_superuser,
                        rolcreatedb as can_create_db,
                        rolcreaterole as can_create_role
                    FROM pg_roles
                    WHERE rolname NOT LIKE 'pg_%'
                    ORDER BY rolname
                """))
            
                users = []
                for row in result.fetchall():
                    username = row[0]
                
                    # Get database privileges
                    privileges = []
                    if row[2]:  # is_superuser
                        privileges = ['ALL']
                    else:
                        # Check specific privileges on current database
                        if self.current_db:
                            priv_result = conn.execute(text("""
                                SELECT 
                                    has_database_privilege(:user, :db, 'CREATE') as can_create,
                                    has_database_privilege(:user, :db, 'CONNECT') as can_connect,
                                    has_database_privilege(:user, :db, 'TEMPORARY') as can_temp
                                """), {'user': username, 'db': self.current_db})
                        
                            priv_row = priv_result.fetchone()
                            if priv_row:
                                if priv_row[0]:
                                    privileges.append('CREATE')
                                if priv_row[1]:
                                    privileges.append('CONNECT')
                    
                        # Check table privileges
                        table_priv_result = conn.execute(text("""
                            SELECT DISTINCT privilege_type
                            FROM information_schema.role_table_grants
                            WHERE grantee = :user
                        """), {'user': username})
                    
                        for priv in table_priv_result.fetchall():
                            priv_type = priv[0]
                            if priv_type not in privileges:
                                privileges.append(priv_type)
                
                    # Check if user has password (can login)
                    has_password = row[1]  # can_login
                
                    users.append({
                        'username': username,
                        'has_password': has_password,
                        'privileges': privileges if privileges else ['USAGE']
                    })
            
                return users
        except Exception as e:
            import logging
            logging.error(f"Error listing PostgreSQL users: {str(e)}")
            return []

    def create_user(self, username, password, privileges):
        """Create a new PostgreSQL user/role"""
        if not self.engine:
            raise Exception("No database connected")
    
        try:
            with self.engine.connect() as conn:
                # Create role with login capability
                if password:
                    conn.execute(text(f"CREATE ROLE {self._quote_identifier(username)} WITH LOGIN PASSWORD '{password}'"))
                else:
                    conn.execute(text(f"CREATE ROLE {self._quote_identifier(username)} WITH LOGIN"))
            
                # Grant privileges
                if 'ALL' in privileges:
                    conn.execute(text(f"ALTER ROLE {self._quote_identifier(username)} WITH SUPERUSER"))
                else:
                    # Grant database-level privileges
                    if self.current_db:
                        if 'CREATE' in privileges:
                            conn.execute(text(f"GRANT CREATE ON DATABASE {self._quote_identifier(self.current_db)} TO {self._quote_identifier(username)}"))
                        if 'CONNECT' in privileges or privileges:  # Default grant CONNECT
                            conn.execute(text(f"GRANT CONNECT ON DATABASE {self._quote_identifier(self.current_db)} TO {self._quote_identifier(username)}"))
                
                    # Grant table privileges on all tables in public schema
                    table_privs = [p for p in privileges if p in ['SELECT', 'INSERT', 'UPDATE', 'DELETE']]
                    if table_privs:
                        priv_str = ', '.join(table_privs)
                        conn.execute(text(f"GRANT {priv_str} ON ALL TABLES IN SCHEMA public TO {self._quote_identifier(username)}"))
                        # Also grant on future tables
                        conn.execute(text(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT {priv_str} ON TABLES TO {self._quote_identifier(username)}"))
            
                conn.commit()
        except Exception as e:
            import logging
            logging.error(f"Error creating PostgreSQL user: {str(e)}")
            raise

    def update_user(self, username, password, privileges):
        """Update PostgreSQL user credentials/privileges"""
        if not self.engine:
            raise Exception("No database connected")
    
        try:
            with self.engine.connect() as conn:
                # Update password if provided
                if password:
                    conn.execute(text(f"ALTER ROLE {self._quote_identifier(username)} WITH PASSWORD '{password}'"))
            
                # Revoke existing privileges
                if self.current_db:
                    conn.execute(text(f"REVOKE ALL ON DATABASE {self._quote_identifier(self.current_db)} FROM {self._quote_identifier(username)}"))
                    conn.execute(text(f"REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {self._quote_identifier(username)}"))
            
                # Remove superuser if not in new privileges
                if 'ALL' not in privileges:
                    conn.execute(text(f"ALTER ROLE {self._quote_identifier(username)} WITH NOSUPERUSER"))
            
                # Grant new privileges
                if 'ALL' in privileges:
                    conn.execute(text(f"ALTER ROLE {self._quote_identifier(username)} WITH SUPERUSER"))
                else:
                    # Grant database-level privileges
                    if self.current_db:
                        if 'CREATE' in privileges:
                            conn.execute(text(f"GRANT CREATE ON DATABASE {self._quote_identifier(self.current_db)} TO {self._quote_identifier(username)}"))
                        if 'CONNECT' in privileges or privileges:
                            conn.execute(text(f"GRANT CONNECT ON DATABASE {self._quote_identifier(self.current_db)} TO {self._quote_identifier(username)}"))
                
                    # Grant table privileges
                    table_privs = [p for p in privileges if p in ['SELECT', 'INSERT', 'UPDATE', 'DELETE']]
                    if table_privs:
                        priv_str = ', '.join(table_privs)
                        conn.execute(text(f"GRANT {priv_str} ON ALL TABLES IN SCHEMA public TO {self._quote_identifier(username)}"))
                        conn.execute(text(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT {priv_str} ON TABLES TO {self._quote_identifier(username)}"))
            
                conn.commit()
        except Exception as e:
            import logging
            logging.error(f"Error updating PostgreSQL user: {str(e)}")
            raise

    def delete_user(self, username):
        """Delete a PostgreSQL user/role"""
        if not self.engine:
            raise Exception("No database connected")
    
        try:
            with self.engine.connect() as conn:
                # Revoke all privileges first
                if self.current_db:
                    conn.execute(text(f"REVOKE ALL ON DATABASE {self._quote_identifier(self.current_db)} FROM {self._quote_identifier(username)}"))
                    conn.execute(text(f"REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {self._quote_identifier(username)}"))
            
                # Drop role
                conn.execute(text(f"DROP ROLE IF EXISTS {self._quote_identifier(username)}"))
                conn.commit()
        except Exception as e:
            import logging
            logging.error(f"Error deleting PostgreSQL user: {str(e)}")
            raise

    def get_user_privileges(self, username):
        """Get privileges for a specific PostgreSQL user"""
        if not self.engine:
            return []
    
        try:
            with self.engine.connect() as conn:
                # Check if superuser
                result = conn.execute(text("""
                    SELECT rolsuper FROM pg_roles WHERE rolname = :user
                """), {'user': username})
            
                row = result.fetchone()
                if row and row[0]:
                    return ['ALL']
            
                privileges = []
            
                # Check database privileges
                if self.current_db:
                    priv_result = conn.execute(text("""
                        SELECT 
                            has_database_privilege(:user, :db, 'CREATE') as can_create,
                            has_database_privilege(:user, :db, 'CONNECT') as can_connect
                    """), {'user': username, 'db': self.current_db})
                
                    priv_row = priv_result.fetchone()
                    if priv_row:
                        if priv_row[0]:
                            privileges.append('CREATE')
                        if priv_row[1]:
                            privileges.append('CONNECT')
            
                # Check table privileges
                table_priv_result = conn.execute(text("""
                    SELECT DISTINCT privilege_type
                    FROM information_schema.role_table_grants
                    WHERE grantee = :user
                """), {'user': username})
            
                for priv in table_priv_result.fetchall():
                    priv_type = priv[0]
                    if priv_type not in privileges:
                        privileges.append(priv_type)
            
                return privileges if privileges else ['USAGE']
        except Exception as e:
            import logging
            logging.error(f"Error getting PostgreSQL user privileges: {str(e)}")
            return []

    def get_user_connection_info(self, username):
        """Return connection info for a specific PostgreSQL user"""
        current_db = self.current_db or 'your_database'
    
        return {
            'connection_string': f'postgresql://{username}:YOUR_PASSWORD@localhost/{current_db}',
            'test_code': f'''from sqlalchemy import create_engine, text

    # Replace YOUR_PASSWORD with the actual password
    username = "{username}"
    password = "YOUR_PASSWORD"
    database = "{current_db}"

    engine = create_engine(f'postgresql://{{username}}:{{password}}@localhost/{{database}}')

    with engine.connect() as conn:
        result = conn.execute(text("SELECT current_database()"))
        print(f"Connected to: {{result.fetchone()[0]}}")
    
        result = conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public'"))
        tables = [row[0] for row in result]
        print(f"Tables: {{tables}}")

    engine.dispose()''',
            'notes': [
                'Replace YOUR_PASSWORD with the actual password for this user',
                'Ensure PostgreSQL server is running on localhost',
                f'User has privileges on database: {current_db}'
            ]
        }
            
    def build_column_definitions(self, schema, quote=True):
        """Build column definition strings for table creation.

        Supports composite primary keys: when more than one column has pk=True,
        inline PRIMARY KEY constraints are omitted from column definitions and a
        table-level PRIMARY KEY (...) clause is appended instead.
        """
        import re
        columns_def = []

        # Detect composite PK up front
        pk_columns = [col for col in schema if col.get('pk')]
        has_composite_pk = len(pk_columns) > 1

        for col in schema:
            col_type = col['type']
            col_name_raw = col['name']

            # CRITICAL FIX: ALWAYS quote column names to handle reserved keywords
            col_name = self._quote_identifier(col_name_raw)

            # Convert autoincrement to SERIAL types
            if col.get('autoincrement'):
                if 'BIGINT' in col_type.upper():
                    col_type = 'BIGSERIAL'
                elif 'SMALLINT' in col_type.upper():
                    col_type = 'SMALLSERIAL'
                else:
                    col_type = 'SERIAL'

            col_def = f"{col_name} {col_type}"

            if col.get('pk'):
                if not has_composite_pk:
                    col_def += " PRIMARY KEY"
                # else: composite PK — skip inline; table-level clause added below
            else:
                if col.get('notnull'):
                    col_def += " NOT NULL"
                if col.get('unique'):
                    col_def += " UNIQUE"

            # ADD CHECK CONSTRAINT with properly quoted identifiers
            if col.get('check_constraint'):
                check_expr = col['check_constraint']
                col_name_unquoted = col['name']
                quoted_check_expr = re.sub(
                    r'\b' + re.escape(col_name_unquoted) + r'\b',
                    f'"{col_name_unquoted}"',
                    check_expr
                )
                col_def += f" CHECK ({quoted_check_expr})"

            columns_def.append(col_def)

        # Append composite PRIMARY KEY table-level constraint
        if has_composite_pk:
            pk_col_names = [self._quote_identifier(col['name']) for col in pk_columns]
            columns_def.append(f"PRIMARY KEY ({', '.join(pk_col_names)})")
            self.logger.debug(f"Added composite PK clause: PRIMARY KEY ({', '.join(pk_col_names)})")

        return columns_def
    
    def build_column_definition_for_create(self, quoted_name, type_with_length, is_pk, is_not_null, is_autoincrement, is_unique, table_name=None, has_composite_pk=False):
        """Build column definition for CREATE TABLE.

        When has_composite_pk=True the caller is responsible for appending a
        table-level PRIMARY KEY (...) clause; this method omits the inline
        PRIMARY KEY keyword for the affected columns.
        """
        base_type = type_with_length.split('(')[0].upper()
        
        # Convert INTEGER to SERIAL for autoincrement (only for single-PK columns)
        if is_autoincrement and not has_composite_pk:
            if base_type in ['INTEGER', 'INT']:
                col_def = f"{quoted_name} SERIAL"
            elif base_type == 'BIGINT':
                col_def = f"{quoted_name} BIGSERIAL"
            elif base_type == 'SMALLINT':
                col_def = f"{quoted_name} SMALLSERIAL"
            else:
                col_def = f"{quoted_name} {type_with_length}"
        else:
            col_def = f"{quoted_name} {type_with_length}"
        
        # Add constraints
        if is_pk and not has_composite_pk:
            col_def += " PRIMARY KEY"
        else:
            if is_not_null:
                col_def += " NOT NULL"
            if is_unique:
                col_def += " UNIQUE"
        
        return col_def
    
    def reset_sequence_after_copy(self, table_name, column_name):
        quoted_table = f'"{table_name}"'
        quoted_column = self._quote_identifier(column_name)

        with self.engine.begin() as conn:
            # 1️⃣ Inline regclass safely (identifiers CANNOT be bound)
            seq_sql = f"""
            SELECT pg_get_expr(ad.adbin, ad.adrelid)
            FROM pg_attribute a
            JOIN pg_attrdef ad
            ON a.attrelid = ad.adrelid
            AND a.attnum = ad.adnum
            WHERE a.attrelid = '{quoted_table}'::regclass
            AND a.attname = :column
            """

            default_expr = conn.execute(
                text(seq_sql),
                {"column": column_name}
            ).scalar()

            if not default_expr or 'nextval' not in default_expr:
                raise RuntimeError(
                    f"No sequence default found for {table_name}.{column_name}"
                )

            # default_expr example:
            # nextval('"Table5_id_seq"'::regclass)
            seq_name = (
                default_expr
                .split("nextval(")[1]
                .split("::")[0]
                .strip("'")
            )

            # 2️⃣ Get MAX(id)
            max_val = conn.execute(text(f"""
                SELECT COALESCE(MAX({quoted_column}), 0)
                FROM {quoted_table}
            """)).scalar()

            # 3️⃣ Reset sequence (value binding is OK)
            conn.execute(
                text("SELECT setval(:seq, :val, true)"),
                {"seq": seq_name, "val": max_val}
            )

            self.logger.info(
                f"🐉 Sequence {seq_name} reset → next id {max_val + 1}"
            )
        
    def get_foreign_keys(self, table_name):
        """Get foreign key constraints for a table"""
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text("""
                    SELECT
                        tc.constraint_name,
                        kcu.column_name,
                        ccu.table_name AS foreign_table_name,
                        ccu.column_name AS foreign_column_name,
                        rc.update_rule,
                        rc.delete_rule
                    FROM information_schema.table_constraints AS tc
                    JOIN information_schema.key_column_usage AS kcu
                        ON tc.constraint_name = kcu.constraint_name
                    JOIN information_schema.constraint_column_usage AS ccu
                        ON ccu.constraint_name = tc.constraint_name
                    JOIN information_schema.referential_constraints AS rc
                        ON tc.constraint_name = rc.constraint_name
                    WHERE tc.constraint_type = 'FOREIGN KEY'
                        AND tc.table_name = :table_name
                """), {'table_name': table_name})
                
                return [{
                    'constraint_name': row[0],
                    'column_name': row[1],
                    'foreign_table': row[2],
                    'foreign_column': row[3],
                    'on_update': row[4],
                    'on_delete': row[5]
                } for row in result.fetchall()]
        except Exception as e:
            self.logger.error(f"Failed to get foreign keys: {e}")
            return []

    def create_foreign_key(self, table_name, constraint_name, column_name, foreign_table, foreign_column, on_update, on_delete):
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
                    SELECT table_name, view_definition
                    FROM information_schema.views
                    WHERE table_schema = 'public'
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
            
    def _get_actual_table_name(self, table_name):
        """Get the actual table name as stored by PostgreSQL (handles case sensitivity)"""
        if not self.engine:
            return table_name.lower()
        
        try:
            with self.engine.connect() as conn:
                # Try exact match first
                result = conn.execute(text("""
                    SELECT tablename FROM pg_tables 
                    WHERE schemaname = 'public' AND tablename = :t
                """), {'t': table_name})
                
                row = result.fetchone()
                if row:
                    return row[0]
                
                # Try lowercase
                result = conn.execute(text("""
                    SELECT tablename FROM pg_tables 
                    WHERE schemaname = 'public' AND tablename = :t
                """), {'t': table_name.lower()})
                
                row = result.fetchone()
                if row:
                    return row[0]
                
                # Fallback to lowercase
                return table_name.lower()
        except Exception:
            return table_name.lower()
            
    def add_check_constraint_to_existing_table(self, table_name, column_name, expression, conn=None):
        """Add CHECK constraint to an existing table via ALTER TABLE - FIXED for case sensitivity"""
        if not self.engine and not conn:
            raise Exception("No database selected")
        
        try:
            # Validate expression syntax
            if not self.validate_check_constraint(expression):
                raise ValueError("Invalid CHECK constraint expression")
            
            # ✅ CRITICAL FIX: Don't force lowercase - use actual table name
            # PostgreSQL preserves case when tables are created with quotes
            actual_table_name = self._get_actual_table_name(table_name)
            quoted_table = self._quote_identifier(actual_table_name)
            
            # Generate unique constraint name
            import secrets
            constraint_name = f"chk_{table_name.lower()}_{column_name}_{secrets.token_hex(4)}"
            
            alter_sql = f"""
                ALTER TABLE {quoted_table}
                ADD CONSTRAINT {constraint_name}
                CHECK ({expression})
            """
            self.logger.debug(f"Adding CHECK constraint: {alter_sql}")
            
            # Use provided connection or create new one
            if conn:
                # Use existing connection (part of transaction)
                conn.execute(text(alter_sql))
            else:
                # Create new connection and commit immediately
                with self.engine.connect() as new_conn:
                    new_conn.execute(text(alter_sql))
                    new_conn.commit()
            
            self.logger.info(f"✅ Added CHECK constraint on {actual_table_name}.{column_name}")
            
        except Exception as e:
            error_str = str(e).lower()
            
            # ✅ Better error handling for common issues
            if 'does not exist' in error_str:
                self.logger.error(f"💥 Table '{table_name}' not found - tried: {actual_table_name}")
                self.logger.error(f"   Available tables: {self.list_tables()}")
            elif 'violates check constraint' in error_str:
                self.logger.error(f"💥 Existing data violates constraint: {expression}")
                self.logger.error(f"   Cannot apply constraint - data must be cleaned first")
            else:
                self.logger.error(f"💥 Failed to add CHECK constraint: {e}")
            
            raise
            
    def copy_table(self, source_table, dest_table):
        """Copy table structure, data, and triggers - CHECK constraints applied AFTER data"""
        schema = self.get_table_schema(source_table)
        data_rows = self.read(source_table)
        
        # ✅ STEP 1: Extract CHECK constraints and build columns WITHOUT them
        check_constraints_to_apply = []
        schema_without_checks = []
        
        for col in schema:
            col_copy = col.copy()
            # Save CHECK constraint if present
            if col_copy.get('check_constraint'):
                check_constraints_to_apply.append({
                    'column': col_copy['name'],
                    'expression': col_copy['check_constraint']
                })
                # Remove CHECK constraint from schema for table creation
                col_copy['check_constraint'] = None
            schema_without_checks.append(col_copy)
        
        self.logger.debug(f"Found {len(check_constraints_to_apply)} CHECK constraints to apply after data copy")
        
        # ✅ STEP 2: Build CREATE TABLE WITHOUT CHECK constraints
        columns_def = self.build_column_definitions(schema_without_checks, quote=False)
        col_def_str = ', '.join(columns_def)
        quoted_dest = self._quote_identifier(dest_table)
        
        with self.engine.connect() as conn:
            create_sql = f"CREATE TABLE {quoted_dest} ({col_def_str})"
            self.logger.debug(f"Creating table: {create_sql}")
            conn.execute(text(create_sql))
            conn.commit()
        
        # ✅ STEP 3: Copy data (skip autoincrement columns)
        for row in data_rows:
            filtered_row = {k: v for k, v in row.items() 
                        if not any(col['name'] == k and col.get('autoincrement') 
                                    for col in schema)}
            if filtered_row:
                self.insert(dest_table, filtered_row)

        # ✅ STEP 4: Apply CHECK constraints AFTER data is copied
        if check_constraints_to_apply:
            self.logger.info(f"Applying {len(check_constraints_to_apply)} CHECK constraints to {dest_table}")
            successful_checks = 0
            failed_checks = 0
            
            for check_info in check_constraints_to_apply:
                try:
                    # PostgreSQL: Add CHECK constraint via ALTER TABLE
                    quoted_table = self._quote_identifier(dest_table)
                    import secrets
                    constraint_name = f"chk_{dest_table}_{check_info['column']}_{secrets.token_hex(2)}"
                    
                    with self.engine.connect() as conn:
                        alter_sql = f"""
                            ALTER TABLE {quoted_table}
                            ADD CONSTRAINT {constraint_name}
                            CHECK ({check_info['expression']})
                        """
                        self.logger.debug(f"Adding CHECK constraint: {alter_sql}")
                        conn.execute(text(alter_sql))
                        conn.commit()
                    
                    self.logger.info(f"✅ Applied CHECK on {check_info['column']}: {check_info['expression']}")
                    successful_checks += 1
                    
                except Exception as check_err:
                    failed_checks += 1
                    self.logger.warning(f"⚠️ Could not apply CHECK on {check_info['column']}: {check_err}")
                    self.logger.warning(f"   Expression: {check_info['expression']}")
                    self.logger.warning(f"   Reason: Existing data may violate the constraint")
            
            if successful_checks > 0:
                self.logger.info(f"✅ Successfully applied {successful_checks} CHECK constraints")
            if failed_checks > 0:
                self.logger.warning(f"⚠️ {failed_checks} CHECK constraints could not be applied due to data violations")

        # ✅ STEP 5: Copy triggers
        self.copy_triggers(source_table, dest_table)

    def copy_triggers(self, source_table, dest_table):
        """Copy triggers from source to destination table - FIXED VERSION with debugging"""
        if not self.engine:
            return
        
        with self.engine.connect() as conn:
            # Get triggers for source table
            result = conn.execute(text("""
                SELECT trigger_name, action_statement, action_timing, event_manipulation
                FROM information_schema.triggers
                WHERE trigger_schema = 'public' AND event_object_table = :table
            """), {'table': source_table})
            
            triggers = result.fetchall()
            
            if not triggers:
                self.logger.debug(f"No triggers found for {source_table}")
                return
            
            for row in triggers:
                trigger_name = row[0]
                action_statement = row[1]
                timing = row[2]
                event = row[3]
                
                try:
                    self.logger.info(f"📋 Processing trigger: {trigger_name}")
                    self.logger.debug(f"   Action statement: {action_statement}")
                    
                    # Extract original function name more robustly
                    func_match = re.search(r'EXECUTE (?:FUNCTION|PROCEDURE)\s+([^\s(]+)', 
                                        action_statement, re.IGNORECASE)
                    
                    if not func_match:
                        self.logger.warning(f"Could not parse function from: {action_statement}")
                        continue
                    
                    old_func_name = func_match.group(1).split('.')[-1]  # Strip schema if present
                    self.logger.info(f"   Original function: {old_func_name}")
                    
                    # Generate new unique names
                    import secrets
                    random_suffix = secrets.token_hex(4)
                    new_func_name = f"trigger_func_{dest_table.lower()}_{trigger_name.lower()}_{random_suffix}"
                    new_trigger_name = f"{dest_table.lower()}_{trigger_name.lower()}_{secrets.token_hex(2)}"
                    
                    self.logger.info(f"   New function name: {new_func_name}")
                    self.logger.info(f"   New trigger name: {new_trigger_name}")
                    
                    # Get full function definition using pg_get_functiondef
                    self.logger.debug(f"   Fetching function definition for: {old_func_name}")
                    func_result = conn.execute(text(f"SELECT pg_get_functiondef('{old_func_name}'::regproc)"))
                    func_row = func_result.fetchone()
                    if not func_row:
                        self.logger.warning(f"Function {old_func_name} not found")
                        continue
                    
                    func_def = func_row[0]
                    self.logger.debug(f"   Original function definition:\n{func_def}")
                    
                    # Replace old function name with new function name in the CREATE FUNCTION statement
                    # Match: CREATE [OR REPLACE] FUNCTION [schema.]old_name(
                    new_func_def = re.sub(
                        rf'CREATE(\s+OR\s+REPLACE)?\s+FUNCTION\s+(?:public\.)?{re.escape(old_func_name)}\s*\(',
                        f'CREATE OR REPLACE FUNCTION {new_func_name}(',
                        func_def,
                        count=1,
                        flags=re.IGNORECASE
                    )
                    
                    self.logger.debug(f"   After function name replacement:\n{new_func_def[:200]}...")
                    
                    # Replace table references ONLY in the function body, not in the function name itself
                    # We need to be careful not to replace the function name we just created
                    lower_source = source_table.lower()
                    lower_dest = dest_table.lower()

                    # Split the function definition into header and body
                    # The function body is between AS $function$ and $function$
                    func_parts = re.split(r'(AS \$function\$)', new_func_def, maxsplit=1)

                    if len(func_parts) == 3:
                        # func_parts[0] = header (CREATE FUNCTION ... RETURNS trigger LANGUAGE plpgsql)
                        # func_parts[1] = AS $function$
                        # func_parts[2] = body + $function$
                        
                        func_header = func_parts[0]
                        func_delimiter = func_parts[1]
                        func_body = func_parts[2]
                        
                        # Only replace table names in the body, not the header (which contains function name)
                        func_body = func_body.replace(f'"{source_table}"', f'"{dest_table}"')
                        func_body = func_body.replace(f'"{lower_source}"', f'"{lower_dest}"')
                        # Be careful with unquoted replacement - only replace word boundaries
                        func_body = re.sub(rf'\b{re.escape(lower_source)}\b', lower_dest, func_body)
                        
                        new_func_def = func_header + func_delimiter + func_body
                    else:
                        # Fallback: do the replacement anyway but log a warning
                        self.logger.warning("   ⚠️ Could not split function definition properly")
                        new_func_def = new_func_def.replace(f'"{source_table}"', f'"{dest_table}"')
                        new_func_def = new_func_def.replace(f'"{lower_source}"', f'"{lower_dest}"')

                    self.logger.info(f"   📝 Creating function: {new_func_name}")
                    self.logger.debug(f"   Full function SQL:\n{new_func_def}")
                    
                    # Create the new function
                    conn.execute(text(new_func_def))
                    conn.commit()
                    
                    self.logger.info(f"   ✅ Function created successfully")
                    
                    # Verify function was created
                    verify_result = conn.execute(text("""
                        SELECT proname FROM pg_proc 
                        WHERE proname = :fname
                    """), {'fname': new_func_name})
                    
                    if verify_result.fetchone():
                        self.logger.info(f"   ✅ Function verified in database")
                    else:
                        self.logger.error(f"   ❌ Function NOT found in database after creation!")
                        continue
                    
                    # Create the new trigger
                    quoted_trigger = self._quote_identifier(new_trigger_name)
                    quoted_table = self._quote_identifier(dest_table)
                    
                    trigger_sql = f"""
                        CREATE TRIGGER {quoted_trigger}
                        {timing} {event} ON {quoted_table}
                        FOR EACH ROW
                        EXECUTE FUNCTION {new_func_name}()
                    """
                    
                    self.logger.info(f"   📝 Creating trigger")
                    self.logger.debug(f"   Trigger SQL:\n{trigger_sql}")
                    
                    conn.execute(text(trigger_sql))
                    conn.commit()
                    
                    self.logger.info(f"✅ Copied trigger {trigger_name} -> {new_trigger_name}")
                    
                except Exception as e:
                    self.logger.error(f"❌ Trigger copy failed for {trigger_name}: {e}")
                    import traceback
                    self.logger.error(traceback.format_exc())
                    continue
                    
    def get_table_connection_info(self, db_name, table_name):
        """Return table-specific connection information"""
        base_conn = self.get_connection_info(db_name)
        
        quoted_table = self._quote_identifier(table_name)
        
        # Build table-specific test code
        test_code = f'''from sqlalchemy import create_engine, text

# ⚠️ REPLACE THESE WITH YOUR ACTUAL CREDENTIALS
username = "YOUR_USERNAME"  # e.g., "postgres"
password = "YOUR_PASSWORD"  # Your PostgreSQL password

engine = create_engine(f'postgresql://{{username}}:{{password}}@localhost/{db_name}')
with engine.connect() as conn:
    result = conn.execute(text('SELECT * FROM {quoted_table} LIMIT 10'))
    rows = [dict(row._mapping) for row in result.fetchall()]
    print(f"Rows: {{len(rows)}}")'''
        
        return {
            'connection_string': base_conn['connection_string'],
            'test_code': test_code,
            'notes': [
                f'This shows how to access the {table_name} table/collection specifically',
                *base_conn.get('notes', [])
            ]
        }
        
    def supports_check_constraints(self):
        """PostgreSQL supports CHECK constraints"""
        return True

    def get_check_constraints(self, table_name):
        """Get CHECK constraints for a table"""
        if not self.engine:
            return []
        
        try:
            with self.engine.connect() as conn:
                # Get all CHECK constraints
                result = conn.execute(text("""
                    SELECT 
                        cc.check_clause as definition,
                        tc.constraint_name
                    FROM information_schema.check_constraints cc
                    JOIN information_schema.table_constraints tc
                        ON cc.constraint_name = tc.constraint_name
                        AND cc.constraint_schema = tc.constraint_schema
                    WHERE tc.table_schema = 'public'
                        AND tc.table_name = :t
                        AND tc.constraint_type = 'CHECK'
                """), {'t': table_name})
                
                checks = []
                for row in result.fetchall():
                    definition = row[0]
                    
                    if definition:
                        # Clean up expression
                        expression = definition.strip()
                        if expression.startswith('(') and expression.endswith(')'):
                            expression = expression[1:-1].strip()
                        
                        # Extract column name from expression
                        import re
                        col_match = re.match(r'^[\(\s]*([a-zA-Z_][a-zA-Z0-9_]*)', expression)
                        column_name = col_match.group(1) if col_match else 'unknown'
                        
                        checks.append({
                            'expression': expression,
                            'column': column_name
                        })
                
                return checks
        except Exception as e:
            self.logger.error(f"Failed to get CHECK constraints: {e}")
            return []

    def validate_check_constraint(self, constraint_expression):
        """Validate a CHECK constraint expression for PostgreSQL"""
        dangerous_keywords = ['DROP', 'DELETE', 'INSERT', 'UPDATE', 'CREATE', 'ALTER']
        upper_expr = constraint_expression.upper()
        
        for keyword in dangerous_keywords:
            if keyword in upper_expr:
                return False
        
        return True
    
    def upgrade_create_table_to_serial(self, create_sql):
        """
        Safely upgrade INTEGER/BIGINT/SMALLINT PRIMARY KEY columns to SERIAL equivalents
        while preserving exact column name casing and removing redundant constraints.
        """
        import re
        
        create_sql = create_sql.strip()
        if not create_sql.upper().startswith('CREATE TABLE'):
            return create_sql
        
        # Extract table name (quoted or unquoted)
        table_match = re.search(r'CREATE TABLE\s+((?:")?.*?(?:"|\s|\())', create_sql, re.IGNORECASE)
        if not table_match:
            return create_sql
        table_part = table_match.group(1).strip().strip('"')
        
        # Extract content inside parentheses
        paren_match = re.search(r'\((.*)\)', create_sql, re.DOTALL)
        if not paren_match:
            return create_sql
        content = paren_match.group(1)
        
        # Split into parts, preserving commas only between top-level items
        parts = []
        depth = 0
        current = ''
        for char in content:
            if char == '(':
                depth += 1
                current += char
            elif char == ')':
                depth -= 1
                current += char
            elif char == ',' and depth == 0:
                parts.append(current.strip())
                current = ''
            else:
                current += char
        if current.strip():
            parts.append(current.strip())
        
        # Detect PK columns (inline or table-level)
        pk_columns = set()
        new_parts = []
        
        for part in parts:
            # Handle table-level PK constraints
            if re.search(r'^\s*(PRIMARY KEY|CONSTRAINT.*PRIMARY KEY)', part, re.IGNORECASE):
                pk_match = re.search(r'\(\s*(["`]?)(.*?)\1\s*\)', part, re.IGNORECASE)
                if pk_match:
                    cols_in_clause = [c.strip().strip('"`') for c in pk_match.group(2).split(',')]
                    if len(cols_in_clause) == 1:
                        # Single-column table-level PK — record it and drop the clause;
                        # the column will be upgraded to SERIAL PRIMARY KEY inline
                        pk_columns.add(cols_in_clause[0])
                        continue  # drop this constraint
                    else:
                        # Composite PK — preserve as-is, do NOT try to convert to SERIAL
                        new_parts.append(part)
                        continue
                continue  # No parentheses found — drop safely
            
            # Look for column definitions with inline PRIMARY KEY
            col_match = re.match(r'\s*(["`]?)([^"\s]+)\1\s+(INTEGER|BIGINT|SMALLINT)', part, re.IGNORECASE)
            if col_match:
                col_name = col_match.group(2)
                base_type = col_match.group(3).upper()
                
                # If this column is a PK (inline), upgrade it
                if re.search(r'PRIMARY KEY', part, re.IGNORECASE):
                    pk_columns.add(col_name)
                    serial_type = {'INTEGER': 'SERIAL', 'BIGINT': 'BIGSERIAL', 'SMALLINT': 'SMALLSERIAL'}[base_type]
                    # Rebuild just this column as SERIAL PRIMARY KEY, keep exact casing
                    # Start with clean SERIAL PRIMARY KEY
                    new_col_def = f'"{col_name}" {serial_type} PRIMARY KEY'
                    
                    # Carry over any extra constraints (e.g., other CHECKs), but remove redundant NOT NULL on the PK
                    rest = re.sub(r'PRIMARY KEY', '', part, count=1, flags=re.IGNORECASE)
                    rest = re.sub(r'NOT NULL', '', rest, flags=re.IGNORECASE)  # SERIAL implies NOT NULL
                    rest = re.sub(r'CHECK\s*\(\s*"?\w+"?\s+IS NOT NULL\s*\)', '', rest, flags=re.IGNORECASE)  # Remove redundant CHECK
                    rest = rest.replace(base_type, serial_type).strip()
                    while '  ' in rest:
                        rest = rest.replace('  ', ' ')
                    
                    # If there are meaningful extras, append them (avoid duplicates)
                    if rest and not rest.startswith(f'"{col_name}" {serial_type}'):
                        # Append after type, before PRIMARY KEY
                        new_col_def = f'"{col_name}" {serial_type}' + ' ' + rest + ' PRIMARY KEY'
                    new_parts.append(new_col_def)
                    continue
            
            new_parts.append(part)
        
        # Reassemble
        new_content = ',\n    '.join(new_parts)
        # Force lowercase quoted table name during import
        # This ensures unquoted mixed-case INSERTs (like INSERT INTO Table2) match the table
        lower_table_name = table_part.lower()
        new_sql = f'CREATE TABLE "{lower_table_name}" (\n    {new_content}\n)'
        
        self.logger.debug(f"Upgraded CREATE TABLE with lowercase quoted name for compatibility: {new_sql[:200]}...")
        return new_sql
    
    def _get_primary_keys_from_create(self, columns_part):
        """Extract PK column names from CREATE TABLE definition (handles composite PKs)"""
        import re
        pk_match = re.search(r'PRIMARY KEY\s*\(\s*(.+?)\s*\)', columns_part, re.IGNORECASE)
        if pk_match:
            # Split by comma and strip quotes/whitespace from each column name
            return {c.strip().strip('"\'`') for c in pk_match.group(1).split(',')}
        # Handle inline PRIMARY KEY on individual columns
        pks = set()
        for col in columns_part.split(','):
            if re.search(r'\bPRIMARY KEY\b', col, re.IGNORECASE):
                name_match = re.match(r'^\s*["`]?(\w+)["`]?', col.strip())
                if name_match:
                    pks.add(name_match.group(1))
        return pks
    
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
                return f"SELECT {row[0]}" if row else None
                
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
            # Detect partition strategy for display
            strategy_result = conn.execute(text("""
                SELECT p.partstrat
                FROM pg_partitioned_table p
                JOIN pg_class c ON c.oid = p.partrelid
                WHERE c.relname = :table_name
                AND c.relnamespace = (SELECT oid FROM pg_namespace WHERE nspname = 'public')
            """), {'table_name': table_name})
            strategy_row = strategy_result.fetchone()
            strategy_map = {'r': 'RANGE', 'l': 'LIST', 'h': 'HASH'}
            partition_type = strategy_map.get(
                strategy_row[0] if strategy_row else '', 'RANGE'
            )

            result = conn.execute(text("""
                SELECT 
                    c.relname as name,
                    pg_get_expr(c.relpartbound, c.oid) as expression
                FROM pg_class c
                JOIN pg_inherits i ON c.oid = i.inhrelid
                JOIN pg_class p ON i.inhparent = p.oid
                WHERE p.relname = :table_name
                AND p.relnamespace = (SELECT oid FROM pg_namespace WHERE nspname = 'public')
                ORDER BY c.relname
            """), {'table_name': table_name})

            return [
                {
                    'name': row[0],
                    'type': partition_type,
                    'expression': row[1]
                }
                for row in result.fetchall()
            ]

    def create_partition(self, table_name, partition_config):
        """
        Create partitions on a table for PostgreSQL.
        PostgreSQL requires the parent table to be declared PARTITION BY at
        creation time, so we: rename the original table, recreate it as a
        partitioned parent, copy the data back, then create child partitions.
        """
        if not self.supports_partitions():
            raise NotImplementedError("Partitions not supported")

        partition_type = partition_config.get('type', 'RANGE').upper()
        column = partition_config.get('column')
        definitions = partition_config.get('definitions', [])

        if not column:
            raise ValueError("Partition column is required")
        if partition_type != 'HASH' and not definitions:
            raise ValueError(
                "Partition definitions are required for RANGE and LIST partitions"
            )

        quoted_table = self._quote_identifier(table_name)
        quoted_column = self._quote_identifier(column)
        temp_name = f"_pgpart_backup_{table_name}"
        quoted_temp = self._quote_identifier(temp_name)

        with self.engine.begin() as conn:
            # --- Step 1: Read existing schema and data ---
            schema = self.get_table_schema(table_name)
            if not schema:
                raise ValueError(f"Table '{table_name}' not found or has no columns")

            rows = self.read(table_name)

            # --- Step 2: Rename original table to backup ---
            conn.execute(text(
                f"ALTER TABLE {quoted_table} RENAME TO {quoted_temp}"
            ))

            # --- Step 3: Build column definitions for new partitioned parent ---
            col_defs = []
            for col in schema:
                col_name = self._quote_identifier(col['name'])
                col_type = col['type']
                # Ensure VARCHAR has length
                if col_type.upper().startswith('VARCHAR') and '(' not in col_type:
                    col_type = 'VARCHAR(255)'
                col_def = f"{col_name} {col_type}"
                if col.get('notnull') and not col.get('pk'):
                    col_def += ' NOT NULL'
                if col.get('unique') and not col.get('pk'):
                    col_def += ' UNIQUE'
                col_defs.append(col_def)

            col_def_str = ', '.join(col_defs)

            # --- Step 4: Create partitioned parent table ---
            conn.execute(text(
                f"CREATE TABLE {quoted_table} ({col_def_str}) "
                f"PARTITION BY {partition_type} ({quoted_column})"
            ))

            # --- Step 5: Create child partition tables ---
            if partition_type == 'RANGE':
                prev_value = 'MINVALUE'
                for part_def in definitions:
                    name = part_def['name']
                    value = part_def['value'].strip()
                    if ',' in value:
                        raise ValueError(
                            f"RANGE partitioning requires a single boundary value "
                            f"per partition, got: '{value}'. Use LIST for multiple values."
                        )
                    quoted_part = self._quote_identifier(f"{table_name}_{name}")
                    if value.upper() == 'MAXVALUE':
                        conn.execute(text(
                            f"CREATE TABLE {quoted_part} "
                            f"PARTITION OF {quoted_table} "
                            f"FOR VALUES FROM ({prev_value}) TO (MAXVALUE)"
                        ))
                    else:
                        conn.execute(text(
                            f"CREATE TABLE {quoted_part} "
                            f"PARTITION OF {quoted_table} "
                            f"FOR VALUES FROM ({prev_value}) TO ({value})"
                        ))
                        prev_value = value

            elif partition_type == 'LIST':
                for part_def in definitions:
                    name = part_def['name']
                    value = part_def['value']
                    values = [v.strip().strip("'\"") for v in value.split(',')]
                    # PostgreSQL LIST supports both strings and integers
                    try:
                        int(values[0])
                        in_values = ', '.join(values)
                    except ValueError:
                        in_values = ', '.join(f"'{v}'" for v in values)
                    quoted_part = self._quote_identifier(f"{table_name}_{name}")
                    conn.execute(text(
                        f"CREATE TABLE {quoted_part} "
                        f"PARTITION OF {quoted_table} "
                        f"FOR VALUES IN ({in_values})"
                    ))

            elif partition_type == 'HASH':
                partition_count = len(definitions) if definitions else 4
                for i in range(partition_count):
                    name = definitions[i]['name'] if definitions and i < len(definitions) else f"p{i}"
                    quoted_part = self._quote_identifier(f"{table_name}_{name}")
                    conn.execute(text(
                        f"CREATE TABLE {quoted_part} "
                        f"PARTITION OF {quoted_table} "
                        f"FOR VALUES WITH (MODULUS {partition_count}, REMAINDER {i})"
                    ))

            else:
                raise ValueError(f"Unsupported partition type: {partition_type}")

            # --- Step 6: Copy data from backup into partitioned table ---
            if rows:
                col_names = [self._quote_identifier(col['name']) for col in schema]
                col_names_str = ', '.join(col_names)
                placeholders = ', '.join([f':{col["name"]}' for col in schema])
                for row in rows:
                    conn.execute(text(
                        f"INSERT INTO {quoted_table} ({col_names_str}) "
                        f"VALUES ({placeholders})"
                    ), row)

            # --- Step 7: Drop the backup table ---
            conn.execute(text(f"DROP TABLE {quoted_temp}"))

        return True

    def get_child_partition_tables(self):
        """
        Return the set of table names that are PostgreSQL child partition tables.
        These must be excluded from list_tables() during export so they are not
        imported as independent plain tables — they are recreated by create_partition.
        """
        try:
            with self._get_connection() as conn:
                result = conn.execute(text("""
                    SELECT c.relname
                    FROM pg_class c
                    JOIN pg_inherits i ON c.oid = i.inhrelid
                    JOIN pg_partitioned_table pt ON i.inhparent = pt.partrelid
                    WHERE c.relnamespace = (
                        SELECT oid FROM pg_namespace WHERE nspname = 'public'
                    )
                """))
                return {row[0] for row in result.fetchall()}
        except Exception as e:
            self.logger.debug(f"get_child_partition_tables failed: {e}")
            return set()

    def drop_partition(self, table_name, partition_name, schema="public"):

        if not table_name or not partition_name:
            raise ValueError("Table name and partition name must be provided.")

        # Normalize name
        if partition_name.startswith(f"{table_name}_"):
            full_partition_name = partition_name
        else:
            full_partition_name = f"{table_name}_{partition_name}"

        qualified_table = f"{schema}.{table_name}"
        qualified_partition = f"{schema}.{full_partition_name}"

        try:
            with self.engine.begin() as conn:

                # Check parent exists
                if not conn.execute(text("SELECT to_regclass(:t)"), {"t": qualified_table}).scalar():
                    raise ValueError(f"Table '{qualified_table}' does not exist.")

                # Check partition exists
                if not conn.execute(text("SELECT to_regclass(:p)"), {"p": qualified_partition}).scalar():
                    raise ValueError(f"Partition '{qualified_partition}' does not exist.")

                # Verify relationship
                if not conn.execute(text("""
                    SELECT 1 FROM pg_inherits
                    WHERE inhrelid = CAST(:p AS regclass)
                    AND inhparent = CAST(:t AS regclass)
                """), {"p": qualified_partition, "t": qualified_table}).scalar():
                    raise ValueError(f"'{qualified_partition}' is not a partition of '{qualified_table}'.")

                # DETACH first
                try:
                    conn.execute(text(f"""
                        ALTER TABLE "{schema}"."{table_name}"
                        DETACH PARTITION "{schema}"."{full_partition_name}"
                    """))
                except Exception:
                    pass  # ignore safely

                # DROP with CASCADE fallback
                try:
                    conn.execute(text(f"""
                        DROP TABLE "{schema}"."{full_partition_name}"
                    """))
                except Exception as drop_err:
                    try:
                        conn.execute(text(f"""
                            DROP TABLE "{schema}"."{full_partition_name}" CASCADE
                        """))
                    except Exception as cascade_err:
                        # 🔥 Show CLEAN but REAL reason
                        msg = str(cascade_err).split("\n")[0]
                        raise ValueError(f"Cannot drop partition: {msg}")

            return f"Partition '{qualified_partition}' dropped successfully."

        except ValueError:
            raise

        except Exception as e:
            msg = str(e).split("\n")[0]
            raise ValueError(f"Unexpected error: {msg}")
    
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
        
    def get_table_indexes(self, table_name):
        """
        Get all non-primary key indexes for a table
        Returns: List of dicts with 'name', 'columns', 'unique'
        """
        indexes = []
        
        with self._get_connection() as conn:
            # Get indexes from pg_indexes
            idx_result = conn.execute(text("""
                SELECT 
                    indexname,
                    indexdef,
                    schemaname
                FROM pg_indexes 
                WHERE tablename = :t AND schemaname = 'public'
            """), {'t': table_name}).fetchall()
            
            for idx_row in idx_result:
                idx_name = idx_row[0]
                idx_def = idx_row[1]
                
                # Skip primary key indexes
                if 'PRIMARY KEY' in idx_def.upper() or '_pkey' in idx_name:
                    continue
                
                # Parse index definition to extract columns and uniqueness
                is_unique = 'UNIQUE' in idx_def.upper()
                
                # Extract column names from index definition
                # Pattern: CREATE [UNIQUE] INDEX ... ON table (col1, col2, ...)
                import re
                col_match = re.search(r'\((.*?)\)', idx_def)
                col_names = []
                if col_match:
                    cols_str = col_match.group(1)
                    # Remove quotes and split by comma
                    col_names = [c.strip().strip('"') for c in cols_str.split(',')]
                
                if col_names:
                    indexes.append({
                        'name': idx_name,
                        'columns': col_names,
                        'unique': is_unique
                    })
        
        return indexes

    def create_index(self, table_name, index_name, columns, unique=False):
        """
        Create an index on a table
        
        Args:
            table_name: Name of the table
            index_name: Name of the index
            columns: List of column names
            unique: Whether the index should be unique
        """
        with self._get_connection() as conn:
            unique_str = "UNIQUE" if unique else ""
            cols_str = ", ".join([self._quote_identifier(c) for c in columns])
            quoted_table = self._quote_identifier(table_name)
            quoted_idx = self._quote_identifier(index_name)
            
            create_idx_sql = f"CREATE {unique_str} INDEX {quoted_idx} ON {quoted_table} ({cols_str})"
            conn.execute(text(create_idx_sql))
            conn.commit()
            
    def check_constraints_inline(self):
        return True
    
    def get_partition_info(self, table_name):
        """
        Return partition metadata for a table so it can be preserved
        during export, import, and database conversion.
        Returns None if the table is not partitioned.
        """
        try:
            with self._get_connection() as conn:
                strategy_result = conn.execute(text("""
                    SELECT p.partstrat,
                           pg_get_partkeydef(c.oid) as partition_key
                    FROM pg_partitioned_table p
                    JOIN pg_class c ON c.oid = p.partrelid
                    WHERE c.relname = :table_name
                    AND c.relnamespace = (
                        SELECT oid FROM pg_namespace WHERE nspname = 'public'
                    )
                """), {'table_name': table_name})
                row = strategy_result.fetchone()
                if not row:
                    return None

                strategy_map = {'r': 'RANGE', 'l': 'LIST', 'h': 'HASH'}
                partition_type = strategy_map.get(row[0], 'RANGE')
                partition_key = row[1]  # e.g. "salary" or "RANGE (salary)"
                # Extract just the column name from the key definition
                col_match = re.search(r'\((.+?)\)', partition_key)
                column = col_match.group(1).strip().strip('"') if col_match else partition_key

                partitions = self.list_partitions(table_name)

                return {
                    'type': partition_type,
                    'column': column,
                    'partitions': partitions
                }
        except Exception as e:
            self.logger.debug(f"get_partition_info failed for {table_name}: {e}")
            return None