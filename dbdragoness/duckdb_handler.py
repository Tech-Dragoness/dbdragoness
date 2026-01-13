import re
import os
import time
import logging
import platform
from pathlib import Path
from sqlalchemy import create_engine, text, pool
from .db_handler import DBHandler

class DuckDBHandler(DBHandler):
    DB_TYPE = 'sql'
    DB_NAME = 'DuckDB'
    
    def __init__(self):
        self.current_db = None
        self.engine = None
        self.base_path = Path('sql_dbs') / 'duckdb'
        self.logger = logging.getLogger(__name__)
        self.base_path.mkdir(parents=True, exist_ok=True)
        self._internal_id_tables = {}

    def _quote_identifier(self, identifier):
        """Quote identifier to preserve case in DuckDB (like PostgreSQL)"""
        return f'"{identifier}"'
    
    def _get_format_hint(self, data_type):
        """Return format hint for date/time types"""
        data_type_upper = data_type.upper()
        if data_type_upper == 'DATE':
            return 'date'  # YYYY-MM-DD
        elif data_type_upper in ['TIMESTAMP', 'DATETIME']:
            return 'timestamp'  # YYYY-MM-DD HH:MM:SS
        elif data_type_upper == 'TIME':
            return 'time'  # HH:MM:SS
        return None
    
    def _format_datetime_value(self, value, col_type):
        """Format date/time value to standard string format"""
        import datetime
        
        # Handle already-string values
        if isinstance(value, str):
            return value
        
        # Convert to appropriate format
        if 'DATE' in col_type and 'TIME' not in col_type:
            # DATE only - format as YYYY-MM-DD
            if isinstance(value, datetime.date):
                return value.strftime('%Y-%m-%d')
        elif 'TIMESTAMP' in col_type or 'DATETIME' in col_type:
            # TIMESTAMP/DATETIME - format as YYYY-MM-DD HH:MM:SS
            if isinstance(value, datetime.datetime):
                return value.strftime('%Y-%m-%d %H:%M:%S')
        elif 'TIME' in col_type and 'STAMP' not in col_type:
            # TIME only - format as HH:MM:SS
            if isinstance(value, datetime.time):
                return value.strftime('%H:%M:%S')
            elif isinstance(value, datetime.timedelta):
                # Handle timedelta (DuckDB sometimes returns this for TIME)
                total_seconds = int(value.total_seconds())
                hours = total_seconds // 3600
                minutes = (total_seconds % 3600) // 60
                seconds = total_seconds % 60
                return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        
        # Fallback - return as string
        return str(value)
    
    def _parse_datetime_for_insert(self, value, col_type):
        """Parse and validate date/time values for insertion"""
        if value is None or value == '':
            return None
        
        # If already proper type, return as-is
        if not isinstance(value, str):
            return value
        
        col_type_upper = col_type.upper()
        
        try:
            if 'DATE' in col_type_upper and 'TIME' not in col_type_upper:
                # DATE - validate YYYY-MM-DD format
                from datetime import datetime
                dt = datetime.strptime(value, '%Y-%m-%d')
                return value  # Return string, DuckDB will parse
            elif 'TIMESTAMP' in col_type_upper or 'DATETIME' in col_type_upper:
                # TIMESTAMP - validate YYYY-MM-DD HH:MM:SS format
                from datetime import datetime
                dt = datetime.strptime(value, '%Y-%m-%d %H:%M:%S')
                return value
            elif 'TIME' in col_type_upper and 'STAMP' not in col_type_upper:
                # TIME - validate HH:MM:SS format
                from datetime import datetime
                dt = datetime.strptime(value, '%H:%M:%S')
                return value
        except ValueError:
            # If parsing fails, return original value and let database handle error
            pass
        
        return value
    
    def get_connection_info(self, db_name):
        """Return connection information"""
        db_path_rel = Path('sql_dbs') / 'duckdb' / f'{db_name}_duckdb.db'
        return {
            'connection_string': f'duckdb:///{db_path_rel}',
            'test_code': f'''from sqlalchemy import create_engine, text
from pathlib import Path

# Get absolute path to database file
db_path = Path('sql_dbs') / 'duckdb' / '{db_name}_duckdb.db'
db_path_abs = db_path.resolve()

# Check if file exists
if not db_path_abs.exists():
    print(f"✗ Database file not found: {{db_path_abs}}")
    print("Make sure the database exists in DBDragoness first!")
else:
    print(f"✓ Found database: {{db_path_abs}}")
    engine = create_engine(f'duckdb:///{{db_path_abs}}')
    with engine.connect() as conn:
        result = conn.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema='main'"))
        tables = [row[0] for row in result]
        print(f"Tables: {{tables}}")''',
        'notes': [
            'Run this code from the same directory as your DBDragoness installation',
            'Make sure the database exists in DBDragoness before testing'
        ]
        }

    def _get_db_path(self, db_name):
        return str(self.base_path / f"{db_name}_duckdb.db")
    
    def _normalize_db_name_for_comparison(self, name1, name2):
        """Case-insensitive comparison for existing databases on case-insensitive filesystems"""
        return name1.lower() == name2.lower()

    def create_db(self, db_name):
        # Debug logging
        self.logger.info(f"🔍 CREATE_DB called with: '{db_name}' (type: {type(db_name)})")
        
        # Check for existing database (case-insensitive on Windows/macOS)
        existing_dbs = self.list_dbs()
        for existing in existing_dbs:
            if self._normalize_db_name_for_comparison(existing, db_name):
                raise ValueError(f"Database '{existing}' already exists (case-insensitive match).")
        
        path = self._get_db_path(db_name)
        self.logger.info(f"🔍 Creating file at: '{path}'")
        
        if self.engine:
            self.engine.dispose()
        self.engine = create_engine(f"duckdb:///{path}")
        self.current_db = db_name
        
        with self.engine.connect() as conn:
            pass
        
        # Verify what was actually created
        files = list(self.base_path.glob("*_duckdb.db"))
        files_str = [str(f) for f in files]
        self.logger.info(f"🔍 Files after creation: {files_str}")
        self.logger.info(f"🔍 self.current_db set to: '{self.current_db}'")

    def delete_db(self, db_name):
        """Delete database - finds actual case from filesystem"""
        # Find actual database name from filesystem
        actual_db_name = self._find_actual_db_name(db_name)
        if not actual_db_name:
            raise FileNotFoundError(f"Database '{db_name}' not found.")
        
        path = self._get_db_path(actual_db_name)
    
        if self.current_db and self._normalize_db_name_for_comparison(self.current_db, actual_db_name):
            if self.engine:
                try:
                    self.engine.dispose()
                    self.logger.debug(f"Disposed engine before deleting {actual_db_name}")
                except Exception as e:
                    self.logger.warning(f"Error disposing engine: {e}")
                finally:
                    self.engine = None
                    self.current_db = None
    
        # Platform-aware wait time
        system = platform.system()
        if system == 'Windows':
            wait_time = 0.2
        else:
            wait_time = 0.1
        time.sleep(wait_time)
    
        max_retries = 5
        path_obj = Path(path)
        for attempt in range(max_retries):
            try:
                if path_obj.exists():
                    path_obj.unlink()
                    self.logger.debug(f"Successfully deleted {path}")
                return
            except OSError as e:
                if attempt == max_retries - 1:
                    raise OSError(f"Failed to delete {path} after {max_retries} attempts: {str(e)}")
                self.logger.warning(f"Delete attempt {attempt + 1} failed, retrying...")
                # Platform-aware retry delay
                retry_delay = 0.5 * (attempt + 1) if system == 'Windows' else 0.3 * (attempt + 1)
                time.sleep(retry_delay)

    def switch_db(self, db_name):
        """Switch to database - finds exact case-match from filesystem"""
        # Find the actual database name as stored on disk
        actual_db_name = self._find_actual_db_name(db_name)
        if not actual_db_name:
            raise FileNotFoundError(f"Database '{db_name}' not found.")
        
        path = self._get_db_path(actual_db_name)
        if self.engine:
            self.engine.dispose()
        self.engine = create_engine(f"duckdb:///{path}")
        self.current_db = actual_db_name  # Use actual case from disk
    
    def _find_actual_db_name(self, db_name):
        """Find the actual database name as stored on filesystem (case-sensitive)"""
        existing_dbs = self.list_dbs()
        
        # First try exact match
        if db_name in existing_dbs:
            return db_name
        
        # Then try case-insensitive match (for backwards compatibility)
        for existing in existing_dbs:
            if existing.lower() == db_name.lower():
                return existing
        
        return None

    def list_dbs(self):
        """List databases - preserves case from filenames"""
        if not self.base_path.exists():
            return []
        
        dbs = []
        for db_file in self.base_path.glob('*_duckdb.db'):
            # Extract the database name preserving case from filename
            db_name = db_file.stem.replace('_duckdb', '')
            dbs.append(db_name)
        
        return dbs

    def list_tables(self):
        if not self.engine:
            return []
        with self.engine.connect() as conn:
            result = conn.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'")).fetchall()
            tables = [row[0] for row in result if not row[0].startswith('_internal_id_')]
            return tables

    def list_tables_for_db(self, db_name):
        path = self._get_db_path(db_name)
        path_obj = Path(path)
        if not path_obj.exists():
            return []
        engine = create_engine(f"duckdb:///{path}")
        with engine.connect() as conn:
            result = conn.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'")).fetchall()
            tables = [row[0] for row in result if not row[0].startswith('_internal_id_')]
        engine.dispose()
        return tables

    def get_supported_types(self):
        return [
            'INTEGER', 'BIGINT', 'SMALLINT', 'TINYINT',
            'DOUBLE', 'REAL', 'DECIMAL',
            'VARCHAR', 'TEXT',
            'BOOLEAN',
            'DATE', 'TIMESTAMP', 'TIME',
            'BLOB'
        ]

    def _ensure_id_column(self, table_name, columns):
        """Ensure table has an ID column - create internal one if needed"""
        has_id = any('id' in col.lower() for col in columns)
        
        if not has_id:
            internal_table = f"_internal_id_{table_name}"
            self._internal_id_tables[table_name] = internal_table
            
            with self.engine.connect() as conn:
                conn.execute(text(f"""
                    CREATE TABLE IF NOT EXISTS {self._quote_identifier(internal_table)} (
                        _row_id INTEGER PRIMARY KEY,
                        _original_rowid BIGINT
                    )
                """))
                conn.commit()
            
            self.logger.debug(f"Created internal ID table for {table_name}")

    def get_table_schema(self, table_name, conn=None):
        """Return schema with case-preserved column names - detects UNIQUE, AUTOINCREMENT, and CHECK"""
        if not self.engine:
            return []

        # ✅ CRITICAL FIX: Use provided connection if available
        should_close = False
        if conn is None:
            conn = self.engine.connect()
            should_close = True
        try:
            # Debug: Check what tables actually exist
            try:
                debug_tables = conn.execute(text("""
                    SELECT table_name FROM information_schema.tables 
                    WHERE table_schema = 'main'
                """)).fetchall()
                self.logger.error(f"🔍 DEBUG: All tables in DuckDB information_schema: {[t[0] for t in debug_tables]}")
            except Exception as e:
                self.logger.error(f"🔍 DEBUG: Failed to list tables: {e}")

            self.logger.error(f"🔍 DEBUG: Looking for table '{table_name}' in DuckDB")

            # DuckDB stores table names in information_schema - try case-insensitive match
            query = text("""
                SELECT 
                    column_name,
                    data_type,
                    character_maximum_length,
                    numeric_precision,
                    numeric_scale,
                    is_nullable,
                    column_default
                FROM information_schema.columns
                WHERE table_schema = 'main'
                AND LOWER(table_name) = LOWER(:table_name)
                ORDER BY ordinal_position
            """)
            result = conn.execute(query, {'table_name': table_name}).fetchall()
            self.logger.error(f"🔍 DEBUG: Query with LOWER() returned {len(result)} rows")

            if not result:
                # Try without LOWER - exact match
                query_exact = text("""
                    SELECT 
                        column_name,
                        data_type,
                        character_maximum_length,
                        numeric_precision,
                        numeric_scale,
                        is_nullable,
                        column_default
                    FROM information_schema.columns
                    WHERE table_schema = 'main'
                    AND table_name = :table_name
                    ORDER BY ordinal_position
                """)
                result = conn.execute(query_exact, {'table_name': table_name}).fetchall()
                self.logger.error(f"🔍 DEBUG: Query without LOWER() (exact '{table_name}') returned {len(result)} rows")

            if not result:
                # Try lowercase explicitly
                result = conn.execute(query_exact, {'table_name': table_name.lower()}).fetchall()
                self.logger.error(f"🔍 DEBUG: Query with lowercase '{table_name.lower()}' returned {len(result)} rows")

            # Get PRIMARY KEY columns
            pk_query = text("""
                SELECT column_name
                FROM information_schema.key_column_usage
                WHERE LOWER(table_name) = LOWER(:table_name)
                AND (constraint_name LIKE '%pkey%' OR constraint_name LIKE 'PRIMARY%')
            """)
            pk_result = conn.execute(pk_query, {'table_name': table_name}).fetchall()

            pk_columns = {row[0] for row in pk_result}

            # Get UNIQUE constraints
            unique_columns = set()
            try:
                unique_query = text("""
                    SELECT UNNEST(constraint_column_names) as col_name
                    FROM duckdb_constraints()
                    WHERE LOWER(table_name) = LOWER(:table_name)
                    AND constraint_type = 'UNIQUE'
                """)
                unique_result = conn.execute(unique_query, {'table_name': table_name}).fetchall()
                for row in unique_result:
                    unique_columns.add(row[0])
            except Exception as e:
                self.logger.debug(f"Could not fetch unique constraints: {e}")

            # ✅ CRITICAL FIX: Get ALL CHECK constraints for the table at once
            check_constraints_map = {}
            try:
                # Query all CHECK constraints for this table
                check_query = text("""
                    SELECT constraint_text, constraint_column_names
                    FROM duckdb_constraints()
                    WHERE LOWER(table_name) = LOWER(:table_name)
                    AND constraint_type = 'CHECK'
                """)
                check_result = conn.execute(check_query, {'table_name': table_name}).fetchall()
                
                for row in check_result:
                    raw_constraint = row[0].strip()
                    columns_list = row[1]
                    
                    # ✅ FIX: Extract expression and normalize parentheses
                    expression = raw_constraint
                    
                    # Remove outer CHECK(...) wrapper if present
                    if expression.upper().startswith("CHECK"):
                        # Find the matching parentheses for CHECK(...)
                        paren_start = expression.find("(")
                        if paren_start != -1:
                            # Count parentheses to find the matching closing one
                            paren_count = 0
                            for i in range(paren_start, len(expression)):
                                if expression[i] == '(':
                                    paren_count += 1
                                elif expression[i] == ')':
                                    paren_count -= 1
                                    if paren_count == 0:
                                        # Found matching closing paren
                                        expression = expression[paren_start + 1:i].strip()
                                        break
                    
                    # ✅ Remove extra outer parentheses if the entire expression is wrapped
                    while expression.startswith('(') and expression.endswith(')'):
                        # Check if these are the outermost wrapping parens
                        paren_count = 0
                        is_outer_wrap = True
                        for i, char in enumerate(expression):
                            if char == '(':
                                paren_count += 1
                            elif char == ')':
                                paren_count -= 1
                                if paren_count == 0 and i < len(expression) - 1:
                                    # Closing paren before the end - not an outer wrap
                                    is_outer_wrap = False
                                    break
                        
                        if is_outer_wrap:
                            expression = expression[1:-1].strip()
                        else:
                            break
                    
                    # Map constraint to column(s)
                    if columns_list and len(columns_list) > 0:
                        for col_name in columns_list:
                            check_constraints_map[col_name] = expression
                            self.logger.debug(f"Found CHECK constraint on {col_name}: {expression}")
            except Exception as e:
                self.logger.debug(f"Could not fetch CHECK constraints: {e}")

            schema = []
            for row in result:
                col_name = row[0]
                
                self.logger.debug(f"Processing column: {col_name}")
        
                if col_name.startswith('_internal_'):
                    self.logger.debug(f"Skipping internal column: {col_name}")
                    continue
        
                data_type = row[1].upper()
                char_max_length = row[2]
                numeric_precision = row[3]
                numeric_scale = row[4]
                is_nullable = row[5] == 'YES'
                col_default = row[6]
            
                # Build proper type with length
                mapped_type = data_type
                
                if mapped_type == 'VARCHAR' and char_max_length:
                    mapped_type = f'VARCHAR({char_max_length})'
                elif mapped_type == 'CHAR' and char_max_length:
                    mapped_type = f'CHAR({char_max_length})'
                elif mapped_type in ['DECIMAL', 'NUMERIC'] and numeric_precision:
                    if numeric_scale:
                        mapped_type = f'{mapped_type}({numeric_precision},{numeric_scale})'
                    else:
                        mapped_type = f'{mapped_type}({numeric_precision})'
            
                # Detect autoincrement
                is_autoincrement = bool(col_default and 'nextval' in str(col_default).lower())
            
                # Check if column is unique
                is_unique = col_name in unique_columns or col_name in pk_columns
                
                # ✅ Get CHECK constraint from the map we built earlier
                check_constraint = check_constraints_map.get(col_name)
        
                schema.append({
                    'name': col_name,
                    'type': mapped_type,
                    'pk': col_name in pk_columns,
                    'notnull': not is_nullable,
                    'autoincrement': is_autoincrement,
                    'unique': is_unique,
                    'check_constraint': check_constraint,
                    'format_hint': self._get_format_hint(data_type)  # Add format hint for frontend
                })

            return schema
        except Exception as e:
            self.logger.error(f"Error getting schema for {table_name}: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            raise  # Re-raise the exception instead of returning []
        
        finally:
            if should_close:
                conn.close()

    def read(self, table_name):
        """Read with quoted table name and format date/time values"""
        if not self.engine:
            return []
        
        # Get schema to identify date/time columns
        schema = self.get_table_schema(table_name)
        date_time_columns = {}
        for col in schema:
            col_type = col['type'].upper()
            if 'DATE' in col_type or 'TIME' in col_type:
                date_time_columns[col['name']] = col_type
        
        with self.engine.connect() as conn:
            try:
                # Try quoted first
                quoted_table = self._quote_identifier(table_name)
                query = f"SELECT * FROM {quoted_table}"
                result = conn.execute(text(query)).fetchall()
                
                # Format date/time values
                formatted_rows = []
                for row in result:
                    row_dict = dict(row._mapping)
                    formatted_row = {}
                    
                    for key, value in row_dict.items():
                        if key in date_time_columns and value is not None:
                            formatted_row[key] = self._format_datetime_value(value, date_time_columns[key])
                        else:
                            formatted_row[key] = value
                    
                    formatted_rows.append(formatted_row)
                
                return formatted_rows
            except:
                # Fallback to unquoted
                query = f"SELECT * FROM {table_name}"
                result = conn.execute(text(query)).fetchall()
                
                # Format date/time values for fallback too
                formatted_rows = []
                for row in result:
                    row_dict = dict(row._mapping)
                    formatted_row = {}
                    
                    for key, value in row_dict.items():
                        if key in date_time_columns and value is not None:
                            formatted_row[key] = self._format_datetime_value(value, date_time_columns[key])
                        else:
                            formatted_row[key] = value
                    
                    formatted_rows.append(formatted_row)
                
                return formatted_rows
    
    def _smart_split(self, query):
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
        return statements

    def execute_query(self, query):
        """Execute query - DuckDB handles quoting in raw SQL"""
        if self.current_db is None:
            raise ValueError("No database selected.")

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
        
    def create_default_table(self, table_name):
        """Create default table with quoted name"""
        quoted_table = self._quote_identifier(table_name)
        with self.engine.connect() as conn:
            conn.execute(text(f"CREATE TABLE IF NOT EXISTS {quoted_table} (id INTEGER PRIMARY KEY)"))
            conn.commit()

    def insert(self, table_name, data):
        """Insert with quoted identifiers - handle empty strings as NULL and skip autoincrement"""
        if not self.engine:
            raise Exception("No database selected")

        schema = self.get_table_schema(table_name)
        cleaned_data = {}

        for key, value in data.items():
            col_info = next((c for c in schema if c['name'] == key), None)
            if col_info:
                # ✅ Skip autoincrement columns entirely - don't insert them
                if col_info.get('autoincrement', False):
                    continue
        
                # Convert empty strings to None (NULL) for numeric types
                if value == '':
                    if col_info['type'].upper() in ['INTEGER', 'INT', 'BIGINT', 'SMALLINT', 'TINYINT', 'DOUBLE', 'REAL', 'FLOAT', 'DECIMAL', 'NUMERIC']:
                        cleaned_data[key] = None
                    else:
                        cleaned_data[key] = value
                else:
                    # Parse date/time values
                    cleaned_data[key] = self._parse_datetime_for_insert(value, col_info['type'])

        quoted_table = self._quote_identifier(table_name)
        quoted_cols = ', '.join([self._quote_identifier(k) for k in cleaned_data.keys()])
        placeholders = ', '.join([f':{k}' for k in cleaned_data.keys()])
        query = f"INSERT INTO {quoted_table} ({quoted_cols}) VALUES ({placeholders})"

        with self.engine.connect() as conn:
            conn.execute(text(query), cleaned_data)
            conn.commit()

    def update(self, table_name, data, condition):
        """Update with quoted identifiers"""
        if 'id' in data and data['id'] is not None:
            try:
                data['id'] = int(data['id'])
            except (ValueError, TypeError):
                raise ValueError("DuckDB requires 'id' column to be INTEGER type")
        
        quoted_table = self._quote_identifier(table_name)
        sets = ', '.join([f'{self._quote_identifier(k)}=:{k}' for k in data.keys()])
        query = f"UPDATE {quoted_table} SET {sets} WHERE {condition}"
        
        with self.engine.connect() as conn:
            conn.execute(text(query), data)
            conn.commit()

    def delete(self, table_name, condition):
        """Delete with quoted table name"""
        quoted_table = self._quote_identifier(table_name)
        query = f"DELETE FROM {quoted_table} WHERE {condition}"
        
        with self.engine.connect() as conn:
            conn.execute(text(query))
            conn.commit()

    def delete_table(self, table_name):
        """Drop table with quoted name"""
        quoted_table = self._quote_identifier(table_name)
        
        with self.engine.connect() as conn:
            if table_name in self._internal_id_tables:
                internal_table = self._internal_id_tables[table_name]
                quoted_internal = self._quote_identifier(internal_table)
                conn.execute(text(f"DROP TABLE IF EXISTS {quoted_internal}"))
                del self._internal_id_tables[table_name]
            
            conn.execute(text(f"DROP TABLE IF EXISTS {quoted_table}"))
            conn.commit()

    def can_convert_column(self, table_name, column, new_type):
        return True
    
    def supports_non_pk_autoincrement(self):
        """DuckDB supports sequences on any integer column"""
        return True
    

    def modify_table(self, old_table_name, new_table_name, new_columns):
        """Modify table with quoted identifiers - supports UNIQUE and AUTOINCREMENT"""
        if not self.engine:
            raise Exception("No database selected")

        with self.engine.connect() as conn:
            try:
                # 🔒 FORCE schema context (ABSOLUTELY REQUIRED on Linux)
                if old_table_name.count('.') == 1:
                    forced_schema = old_table_name.split('.')[0]
                    conn.execute(text(f"SET schema '{forced_schema}'"))
                    self.logger.debug(f"🔒 Forced schema context: {forced_schema}")

                # ✅ CRITICAL FIX: Get fully qualified table name FIRST
                old_table_qualified = self._get_fully_qualified_table_name(old_table_name, conn)
                self.logger.debug(f"Resolved old table reference: {old_table_qualified}")
                
                # ✅ CRITICAL FIX: Use the QUALIFIED name to get schema
                # Extract just the table name from qualified name for schema lookup
                table_name_only = old_table_name.split('.')[-1] if '.' in old_table_name else old_table_name
                old_schema = self.get_table_schema(table_name_only, conn=conn)
                
                old_table_qualified = self._get_fully_qualified_table_name(old_table_name, conn)
                self.logger.debug(f"Resolved old table reference: {old_table_qualified}")
                
                old_columns = {col['name']: col for col in old_schema}
            
                # Parse new column definitions - DON'T extract CHECK yet
                new_column_info = {}
                quoted_new_columns = []

                # STEP 1: Drop OLD sequences that are being replaced (CASCADE to remove dependencies)
                try:
                    old_autoincrement_cols = [col['name'] for col in old_schema if col.get('autoincrement')]
                    if old_autoincrement_cols:
                        self.logger.debug(f"Found {len(old_autoincrement_cols)} old autoincrement columns to clean up")
                        
                        for old_col_name in old_autoincrement_cols:
                            old_seq_name = f"{old_table_name}_{old_col_name}_seq"
                            quoted_old_seq = self._quote_identifier(old_seq_name)
                            try:
                                conn.execute(text(f"DROP SEQUENCE IF EXISTS {quoted_old_seq} CASCADE"))
                                self.logger.debug(f"Dropped old sequence {old_seq_name} CASCADE")
                            except Exception as drop_err:
                                self.logger.warning(f"Could not drop old sequence {old_seq_name}: {drop_err}")

                except Exception as cleanup_err:
                    self.logger.warning(f"Sequence cleanup failed: {cleanup_err}")

                # STEP 2: Create NEW sequences for new autoincrement columns
                for col_def in new_columns:
                    parts = col_def.split(maxsplit=1)
                    if len(parts) >= 2:
                        col_name = parts[0]
                        rest = parts[1]
                        rest_upper = rest.upper()
                        
                        has_autoincrement = 'AUTOINCREMENT' in rest_upper
                        
                        if has_autoincrement:
                            seq_name = f"{new_table_name}_{col_name}_seq"
                            quoted_seq = self._quote_identifier(seq_name)
                            
                            # Create sequence in separate connection
                            try:
                                conn.execute(text(f"CREATE SEQUENCE IF NOT EXISTS {quoted_seq} START 1"))
                                self.logger.debug(f"Created sequence {seq_name}")
                            except Exception as e:
                                self.logger.error(f"Failed to create sequence {seq_name}: {e}")
                                raise
            
                # ✅ STEP 2: Build column definitions - preserve CHECK constraints
                for col_def in new_columns:
                    parts = col_def.split(maxsplit=1)
                    if len(parts) >= 2:
                        col_name = parts[0]
                        rest = parts[1]
                        rest_upper = rest.upper()
                        
                        # Detect constraints
                        has_pk = 'PRIMARY KEY' in rest_upper
                        has_not_null = 'NOT NULL' in rest_upper
                        has_unique = 'UNIQUE' in rest_upper
                        has_autoincrement = 'AUTOINCREMENT' in rest_upper
                        
                        # ✅ CRITICAL FIX: Extract CHECK constraint INCLUDING parentheses - IMPROVED
                        check_constraint = None
                        rest_without_check = rest
                        
                        if 'CHECK' in rest_upper:
                            import re
                            # Match CHECK (expression) - handle nested parentheses properly
                            check_match = re.search(r'CHECK\s*\(', rest, re.IGNORECASE)
                            if check_match:
                                start_pos = check_match.end() - 1  # Position of opening '('
                                paren_count = 0
                                end_pos = -1
                                
                                # Find matching closing parenthesis
                                for i in range(start_pos, len(rest)):
                                    if rest[i] == '(':
                                        paren_count += 1
                                    elif rest[i] == ')':
                                        paren_count -= 1
                                        if paren_count == 0:
                                            end_pos = i
                                            break
                                
                                if end_pos != -1:
                                    # Extract just the expression (without CHECK and outer parens)
                                    check_constraint = rest[start_pos + 1:end_pos].strip()
                                    # Remove entire CHECK clause from rest
                                    rest_without_check = rest[:check_match.start()].strip() + ' ' + rest[end_pos + 1:].strip()
                                    rest_without_check = rest_without_check.strip()
                        
                        # Build column definition WITHOUT check first
                        if has_autoincrement:
                            seq_name = f"{new_table_name}_{col_name}_seq"
                            # Remove AUTOINCREMENT keyword from rest
                            rest_clean = rest_without_check.upper().replace('AUTOINCREMENT', '').strip()
                            quoted_col_def = f'{self._quote_identifier(col_name)} {rest_clean} DEFAULT nextval(\'{seq_name}\')'
                        else:
                            quoted_col_def = f'{self._quote_identifier(col_name)} {rest_without_check}'
                        
                        # ✅ Add CHECK constraint at the end if present
                        if check_constraint:
                            quoted_col_def += f' CHECK ({check_constraint})'
                        
                        quoted_new_columns.append(quoted_col_def)
                        
                        new_column_info[col_name] = {
                            'definition': rest,
                            'not_null': has_not_null,
                            'type': rest_without_check.split()[0] if rest_without_check else 'TEXT',
                            'pk': has_pk,
                            'unique': has_unique,
                            'autoincrement': has_autoincrement,
                            'check_constraint': check_constraint
                        }
                    else:
                        quoted_new_columns.append(self._quote_identifier(col_def))
                        new_column_info[col_def] = {
                            'definition': '',
                            'not_null': False,
                            'type': 'TEXT',
                            'pk': False,
                            'unique': False,
                            'autoincrement': False,
                            'check_constraint': None
                        }
            
                # Create temp table with cross-platform unique name
                import secrets
                temp_table_name = f"temp_{old_table_name}_{secrets.token_hex(4)}"
                col_def = ', '.join(quoted_new_columns)
                quoted_temp = self._quote_identifier(temp_table_name)

                self.logger.debug(f"Creating temp table with SQL: CREATE TABLE {quoted_temp} ({col_def})")
                conn.execute(text(f"CREATE TABLE {quoted_temp} ({col_def})"))
            
                # Build column mapping
                column_mapping = {}
                used_old_columns = set()
                new_column_names = list(new_column_info.keys())
            
                # First pass: exact name match
                for new_col_name in new_column_names:
                    if new_col_name in old_columns:
                        column_mapping[new_col_name] = new_col_name
                        used_old_columns.add(new_col_name)
            
                # Second pass: positional mapping
                unmapped_new = [col for col in new_column_names if col not in column_mapping]
                unmapped_old = [col for col in old_columns.keys() if col not in used_old_columns]
            
                for i, new_col in enumerate(unmapped_new):
                    if i < len(unmapped_old):
                        column_mapping[new_col] = unmapped_old[i]
                        self.logger.debug(f"Mapped renamed column: {unmapped_old[i]} -> {new_col}")
            
                # Build SELECT and INSERT
                select_parts = []
                insert_cols = []
            
                for new_col_name, old_col_name in column_mapping.items():
                    new_col_info = new_column_info[new_col_name]
                
                    # Skip autoincrement columns - they're auto-generated
                    if new_col_info['autoincrement']:
                        continue
                
                    insert_cols.append(self._quote_identifier(new_col_name))
                    quoted_old = self._quote_identifier(old_col_name)
                
                    # Handle NOT NULL with COALESCE and format date/time types
                    new_col_type_upper = new_col_info['type'].upper()
                    
                    # Format date/time columns during copy
                    if 'DATE' in new_col_type_upper or 'TIME' in new_col_type_upper:
                        if 'DATE' in new_col_type_upper and 'TIME' not in new_col_type_upper:
                            # DATE - cast to ensure proper format
                            select_parts.append(f"CAST({quoted_old} AS DATE) AS {self._quote_identifier(new_col_name)}")
                        elif 'TIMESTAMP' in new_col_type_upper or 'DATETIME' in new_col_type_upper:
                            # TIMESTAMP - cast to ensure proper format
                            select_parts.append(f"CAST({quoted_old} AS TIMESTAMP) AS {self._quote_identifier(new_col_name)}")
                        elif 'TIME' in new_col_type_upper and 'STAMP' not in new_col_type_upper:
                            # TIME - cast to ensure proper format
                            select_parts.append(f"CAST({quoted_old} AS TIME) AS {self._quote_identifier(new_col_name)}")
                        else:
                            select_parts.append(f"{quoted_old} AS {self._quote_identifier(new_col_name)}")
                    elif new_col_info['not_null'] and not new_col_info['pk'] and not new_col_info['autoincrement']:
                        # Handle NOT NULL with COALESCE for non-date types
                        if 'INT' in new_col_type_upper:
                            select_parts.append(f"COALESCE({quoted_old}, 0) AS {self._quote_identifier(new_col_name)}")
                        elif 'REAL' in new_col_type_upper or 'DOUBLE' in new_col_type_upper or 'FLOAT' in new_col_type_upper:
                            select_parts.append(f"COALESCE({quoted_old}, 0.0) AS {self._quote_identifier(new_col_name)}")
                        else:
                            select_parts.append(f"COALESCE({quoted_old}, '') AS {self._quote_identifier(new_col_name)}")
                    else:
                        select_parts.append(f"{quoted_old} AS {self._quote_identifier(new_col_name)}")
            
                # Copy data - ✅ USE FULLY QUALIFIED NAME WITH PROPER QUOTING
                if select_parts:
                    select_cols = ', '.join(select_parts)
                    insert_cols_str = ', '.join(insert_cols)
                    
                    # ✅ CRITICAL FIX: Quote the fully qualified source table name
                    # Split the qualified name and quote each part separately
                    if '.' in old_table_qualified:
                        schema_part, table_part = old_table_qualified.rsplit('.', 1)
                        # Remove any existing quotes before re-quoting
                        schema_part = schema_part.strip('"')
                        table_part = table_part.strip('"')
                        source_table_ref = f'{self._quote_identifier(schema_part)}.{self._quote_identifier(table_part)}'
                    else:
                        source_table_ref = self._quote_identifier(old_table_qualified)
                    
                    self.logger.debug(f"Copying data from {source_table_ref} to {quoted_temp}")
                    
                    conn.execute(
                        text(f"INSERT INTO {quoted_temp} ({insert_cols_str}) SELECT {select_cols} FROM {source_table_ref}")
                    )
            
                # Drop old and rename - ✅ USE SIMPLE NAME FOR DROP (we're in same database)
                quoted_new = self._quote_identifier(new_table_name)
                quoted_old = self._quote_identifier(table_name_only)  # ✅ Use simple name
                
                # ✅ CRITICAL FIX: Check if table exists before dropping
                try:
                    conn.execute(text(f"DROP TABLE IF EXISTS {quoted_old}"))
                except Exception as drop_err:
                    self.logger.error(f"Failed to drop old table {quoted_old}: {drop_err}")
                    # If drop fails, try with qualified name
                    try:
                        conn.execute(text(f"DROP TABLE IF EXISTS {old_table_qualified}"))
                    except Exception as qualified_drop_err:
                        self.logger.error(f"Failed to drop with qualified name: {qualified_drop_err}")
                        raise Exception(f"Could not drop old table. Manual cleanup may be needed.")
                
                conn.execute(text(f"ALTER TABLE {quoted_temp} RENAME TO {quoted_new}"))
            
                conn.commit()
                self.logger.debug(f"Successfully modified table {old_table_name} to {new_table_name}")
                # ✅ NO CLEANUP NEEDED ON SUCCESS - temp table was renamed!
                
            except Exception as e:
                conn.rollback()  # ✅ Add explicit rollback
                # ✅ CRITICAL: Clean up temporary table ONLY if it still exists (creation succeeded but later step failed)
                try:
                    if 'temp_table_name' in locals():
                        quoted_temp = self._quote_identifier(temp_table_name)
                        conn.execute(text(f"DROP TABLE IF EXISTS {quoted_temp}"))
                        conn.commit()  # ✅ Commit the cleanup
                        self.logger.debug(f"Cleaned up temporary table {temp_table_name}")
                except Exception as cleanup_err:  # ✅ Rename variable to avoid shadowing
                    self.logger.warning(f"Could not clean up temporary table: {cleanup_err}")
                
                self.logger.error(f"Modify table error: {e}")
                import traceback
                self.logger.error(traceback.format_exc())
                raise Exception(f"Failed to modify table: {str(e)}")
            
    def supports_joins(self):
        return True

    def supports_triggers(self):
        return False

    def supports_plsql(self):
        return False

    def execute_join(self, join_query):
        return self.execute_query(join_query)
    
    def supports_procedures(self):
        """Override in child classes - return True if DB supports stored procedures"""
        return False
    
    def execute_procedure(self, procedure_code):
        """Execute stored procedure/function code - override in child classes"""
        return None
    
    def list_procedures(self):
        """List all stored procedures/functions - override in child classes"""
        return None
    
    def get_procedure_definition(self, procedure_name):
        """Get the source code of a procedure - override in child classes"""
        return None
    
    def drop_procedure(self, procedure_name, is_function=False):
        """Drop a stored procedure/function - override in child classes"""
        return None
    
    def get_procedure_placeholder_example(self):
        """Return database-specific example code for procedures tab"""
        return "This database does not support stored procedures."

    def create_trigger(self, trigger_name, table_name, trigger_timing, trigger_event, trigger_body):
        raise NotImplementedError("DuckDB doesn't support triggers yet")

    def list_triggers(self, table_name=None):
        return []

    def get_trigger_details(self, trigger_name):
        return None

    def delete_trigger(self, trigger_name):
        raise NotImplementedError("DuckDB doesn't support triggers yet")

    def execute_plsql(self, plsql_code):
        raise NotImplementedError("DuckDB doesn't support PL/SQL")
    
    def get_credential_status(self):
        """DuckDB handler doesn't require credentials"""
        return {
            "needs_credentials": False,
            "handler": self.DB_NAME
        }

    def clear_credentials(self):
        """DuckDB handler doesn't store credentials"""
        pass
    
    def supports_user_management(self):
        """Return True if database supports user management"""
        return False

    def list_users(self):
        """List all database users - override in child classes"""
        return []

    def create_user(self, username, password, privileges):
        """Create a new user - override in child classes"""
        raise NotImplementedError(f"{self.DB_NAME} does not support user management")

    def update_user(self, username, password, privileges):
        """Update user credentials/privileges - override in child classes"""
        raise NotImplementedError(f"{self.DB_NAME} does not support user management")

    def delete_user(self, username):
        """Delete a user - override in child classes"""
        raise NotImplementedError(f"{self.DB_NAME} does not support user management")

    def get_user_privileges(self, username):
        """Get privileges for a specific user - override in child classes"""
        return []

    def get_user_connection_info(self, username):
        """Return connection info for a specific user"""
        return {
            'connection_string': 'User management not supported',
            'test_code': 'User management not supported',
        'notes': []
        }
        
    def build_column_definitions(self, schema, quote=True):
        """Build column definition strings for table creation"""
        columns_def = []
        
        # Add this RESERVED_KEYWORDS definition at the start of the method
        RESERVED_KEYWORDS = {
            'table', 'select', 'from', 'where', 'insert', 'update', 'delete',
            'create', 'drop', 'alter', 'index', 'view', 'trigger', 'order',
            'group', 'having', 'limit', 'offset', 'join', 'on', 'as', 'in',
            'exists', 'case', 'when', 'then', 'else', 'end', 'union', 'all'
        }
        
        for col in schema:
            col_type = col['type']
            col_name_raw = col['name']
            
            if quote or col_name_raw.lower() in RESERVED_KEYWORDS:
                col_name = self._quote_identifier(col_name_raw)
            else:
                col_name = col_name_raw
            
            # ✅ CRITICAL FIX: DuckDB doesn't support SERIAL - keep original type
            # Autoincrement is handled via sequences and DEFAULT nextval()
            # Don't convert to SERIAL types
            
            col_def = f"{col_name} {col_type}"
            
            if col.get('pk'):
                col_def += " PRIMARY KEY"
            else:
                if col.get('notnull'):
                    col_def += " NOT NULL"
                if col.get('unique'):
                    col_def += " UNIQUE"
            
            # ✅ ADD CHECK CONSTRAINT
            if col.get('check_constraint'):
                col_def += f" CHECK ({col['check_constraint']})"
            
            columns_def.append(col_def)
        
        return columns_def
    
    def build_column_definition_for_create(self, quoted_name, type_with_length, is_pk, is_not_null, is_autoincrement, is_unique, table_name=None, check_constraint=None):
        """Build column definition for CREATE TABLE - FIXED to preserve length"""
        
        # ✅ CRITICAL FIX: Use type_with_length AS-IS, don't strip anything
        # This preserves VARCHAR(100), DECIMAL(10,2), etc.
        
        if is_autoincrement and table_name:
            # Use sequence for autoincrement
            col_name = quoted_name.strip('"')
            seq_name = f"{table_name}_{col_name}_seq"
            col_def = f"{quoted_name} {type_with_length} DEFAULT nextval('{seq_name}')"
        else:
            # ✅ KEY CHANGE: Use full type_with_length instead of extracting base type
            col_def = f"{quoted_name} {type_with_length}"
        
        # Add constraints
        if is_pk:
            col_def += " PRIMARY KEY"
        else:
            if is_not_null:
                col_def += " NOT NULL"
            if is_unique:
                col_def += " UNIQUE"
        
        # ✅ NEW: Add CHECK constraint if provided (but this should NOT be used during copy operations)
        if check_constraint:
            col_def += f" CHECK ({check_constraint})"
        
        return col_def
    
    def reset_sequence_after_copy(self, table_name, column_name):
        """Reset sequence to max value + 1 after copying data"""
        try:
            quoted_table = self._quote_identifier(table_name)
            quoted_col = self._quote_identifier(column_name)
            
            with self.engine.connect() as conn:
                # Get max value
                max_val_query = f"SELECT MAX({quoted_col}) FROM {quoted_table}"
                result = conn.execute(text(max_val_query)).fetchone()
                max_val = result[0] if result and result[0] else 0
                
                # Reset sequence
                seq_name = f"{table_name}_{column_name}_seq"
                quoted_seq = self._quote_identifier(seq_name)
                conn.execute(text(f"ALTER SEQUENCE {quoted_seq} RESTART WITH {max_val + 1}"))
                conn.commit()
                
                self.logger.debug(f"Reset sequence {seq_name} to {max_val + 1}")
        except Exception as e:
            self.logger.warning(f"Failed to reset sequence: {e}")
            raise
        
    def get_foreign_keys(self, table_name):
        """This database doesn't support foreign keys or method not implemented"""
        return []

    def create_foreign_key(self, table_name, constraint_name, column_name,
                        foreign_table, foreign_column, on_update, on_delete):
        """This database doesn't support foreign keys"""
        pass
    
    def get_views(self):
        """Get all views in current database"""
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text("""
                    SELECT view_name, sql
                    FROM duckdb_views()
                """))
                
                return [{'name': row[0], 'definition': row[1]} for row in result.fetchall()]
        except Exception as e:
            self.logger.error(f"Failed to get views: {e}")
            return []

    def create_view(self, view_name, view_definition):
        """Create a view"""
        # DuckDB stores full CREATE VIEW statement
        with self.engine.connect() as conn:
            conn.execute(text(view_definition))
            conn.commit()
            
    def copy_table(self, source_table, dest_table):
        """Copy table - FIXED to preserve autoincrement values"""
        schema = self.get_table_schema(source_table)
        data_rows = self.read(source_table)
        
        # Build CREATE TABLE WITHOUT autoincrement defaults
        temp_columns_def = []
        autoincrement_columns = []
        
        for col in schema:
            col_name = self._quote_identifier(col['name'])
            col_type = col['type']
            col_def = f"{col_name} {col_type}"
            
            if col.get('pk'):
                col_def += " PRIMARY KEY"
            else:
                if col.get('notnull'):
                    col_def += " NOT NULL"
                if col.get('unique'):
                    col_def += " UNIQUE"
            
            temp_columns_def.append(col_def)
            
            if col.get('autoincrement'):
                autoincrement_columns.append(col['name'])
        
        col_def_str = ', '.join(temp_columns_def)
        quoted_dest = self._quote_identifier(dest_table)
        
        # Create table
        with self.engine.connect() as conn:
            conn.execute(text(f"CREATE TABLE {quoted_dest} ({col_def_str})"))
            conn.commit()
        
        # Copy ALL data including autoincrement values
        for row in data_rows:
            filtered_row = {col['name']: row[col['name']] for col in schema if col['name'] in row}
            
            if filtered_row:
                quoted_cols = ', '.join([self._quote_identifier(k) for k in filtered_row.keys()])
                placeholders = ', '.join([f':{k}' for k in filtered_row.keys()])
                insert_sql = f"INSERT INTO {quoted_dest} ({quoted_cols}) VALUES ({placeholders})"
                
                with self.engine.connect() as conn:
                    conn.execute(text(insert_sql), filtered_row)
                    conn.commit()
        
        # Add sequences and defaults for autoincrement columns
        for col_name in autoincrement_columns:
            seq_name = f"{dest_table}_{col_name}_seq"
            quoted_seq = self._quote_identifier(seq_name)
            quoted_col = self._quote_identifier(col_name)
            
            try:
                with self.engine.connect() as conn:
                    # Get max value from copied data
                    max_val_query = f"SELECT MAX({quoted_col}) FROM {quoted_dest}"
                    result = conn.execute(text(max_val_query)).fetchone()
                    max_val = result[0] if result and result[0] else 0
                    
                    # ✅ CRITICAL FIX: DuckDB doesn't support ALTER SEQUENCE RESTART
                    # Instead: DROP and CREATE with correct START value
                    
                    # Drop sequence if exists
                    try:
                        conn.execute(text(f"DROP SEQUENCE IF EXISTS {quoted_seq}"))
                    except:
                        pass
                    
                    # Create sequence starting at max_val + 1
                    conn.execute(text(f"CREATE SEQUENCE {quoted_seq} START {max_val + 1}"))
                    
                    # ✅ Add DEFAULT to column to use the sequence
                    conn.execute(text(f"ALTER TABLE {quoted_dest} ALTER COLUMN {quoted_col} SET DEFAULT nextval('{seq_name}')"))
                    
                    conn.commit()
                    self.logger.info(f"✅ Set autoincrement for {col_name}: sequence starts at {max_val + 1}")
                    
            
                    
            except Exception as e:
                self.logger.error(f"❌ Failed to set autoincrement for {col_name}: {e}")
                import traceback
                self.logger.error(traceback.format_exc())
                
                # ✅ Reapply CHECK constraints AFTER data copy — safely, with autoincrement rescue
        check_constraints_to_reapply = [col for col in schema if col.get('check_constraint')]
        
        if check_constraints_to_reapply:
            self.logger.info(
                f"🔮 Found {len(check_constraints_to_reapply)} CHECK constraint(s) to reapply on {dest_table}. "
                "This requires table recreation in DuckDB — autoincrement will be preserved afterward."
            )
            
            for col in check_constraints_to_reapply:
                try:
                    self.create_check_constraint(
                        table_name=dest_table,
                        column_name=col['name'],
                        expression=col['check_constraint']
                    )
                    self.logger.info(
                        f"✅ Successfully reapplied CHECK constraint on {dest_table}.{col['name']}"
                    )
                except Exception as e:
                    self.logger.error(
                        f"❌ Failed to reapply CHECK constraint on {dest_table}.{col['name']}: {e}"
                    )
                    # Continue anyway — better to have data than fail completely
        
        # 🔧 CRITICAL RESCUE: After any CHECK reapplication (which recreates the table),
        # re-fix all autoincrement sequences so new inserts get correct IDs
        if autoincrement_columns:
            self.logger.info(
                f"🔧 Re-fixing {len(autoincrement_columns)} autoincrement sequence(s) "
                f"after possible table recreation from CHECK constraints"
            )
            for col_name in autoincrement_columns:
                try:
                    self.reset_sequence_after_copy(dest_table, col_name)
                    self.logger.info(
                        f"✅ Re-fixed autoincrement for {dest_table}.{col_name}"
                    )
                except Exception as e:
                    self.logger.warning(
                        f"⚠️ Could not fully re-fix sequence for {col_name}: {e}"
                    )
        # End of copy_table fixes
        

    def apply_validation_rules(self, table_name, validation_rules):
        """
        Apply validation rules as CHECK constraints.
        Since DuckDB requires table recreation for CHECK constraints,
        this will use create_check_constraint for each rule.
        """
        if not validation_rules:
            self.logger.info("No validation rules to apply")
            return
        
        self.logger.info(f"Applying {len(validation_rules)} validation rules to {table_name}")
        
        successful = 0
        failed = 0
        
        for column_name, rules in validation_rules.items():
            try:
                # Convert validation rules to CHECK expression
                check_expr = self._validation_to_check(rules, column_name)
                
                if not check_expr:
                    self.logger.debug(f"No enforceable CHECK expression for '{column_name}'")
                    continue
                
                self.logger.info(f"Applying CHECK constraint on '{column_name}': {check_expr}")
                
                # Use existing create_check_constraint which handles table rebuild
                self.create_check_constraint(table_name, column_name, check_expr)
                
                successful += 1
                self.logger.info(f"✅ Successfully applied CHECK constraint on '{column_name}'")
                
            except Exception as e:
                failed += 1
                self.logger.error(f"💥 Failed to apply CHECK on '{column_name}': {e}")
        
        self.logger.info(f"Validation rules complete: {successful} succeeded, {failed} failed")
        
        if failed > 0:
            self.logger.warning(f"⚠️ {failed} validation rules could not be applied")

    def _validation_to_check(self, validation_rules, column_name):
        """
        Convert validation rules dict to SQL CHECK constraint expression.
        Handles: required, minimum, maximum, minLength, maxLength, enum, pattern
        """
        constraints = []
        
        bson_type = validation_rules.get('bsonType')
        is_numeric = (isinstance(bson_type, list) and 
                    any(t in ['int', 'long', 'double', 'decimal'] for t in bson_type) or 
                    bson_type in ['int', 'long', 'double', 'decimal'])
        is_string = bson_type == 'string'
        
        self.logger.debug(f"Converting validation for '{column_name}': {validation_rules}")
        
        # 1. Required (NOT NULL)
        if validation_rules.get('required'):
            constraints.append(f'{column_name} IS NOT NULL')
        
        # 2. Numeric constraints
        if 'minimum' in validation_rules and is_numeric:
            constraints.append(f'{column_name} >= {validation_rules["minimum"]}')
        
        if 'maximum' in validation_rules and is_numeric:
            constraints.append(f'{column_name} <= {validation_rules["maximum"]}')
        
        # 3. String length constraints
        if 'minLength' in validation_rules:
            constraints.append(f'LENGTH({column_name}) >= {validation_rules["minLength"]}')
        
        if 'maxLength' in validation_rules:
            constraints.append(f'LENGTH({column_name}) <= {validation_rules["maxLength"]}')
        
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
        
        # 5. Pattern (convert regex to LIKE if possible)
        if 'pattern' in validation_rules:
            pattern = validation_rules['pattern']
            like_pattern = pattern.strip('^$').replace('.*', '%').replace('.', '_')
            constraints.append(f"{column_name} LIKE '{like_pattern}'")
        
        result = ' AND '.join(constraints) if constraints else None
        self.logger.debug(f"Generated CHECK expression: {result}")
        return result

                    
    def copy_triggers(self, source_table, dest_table):
        """DuckDB does not support triggers"""
        raise NotImplementedError("DuckDB doesn't support triggers yet")
                    
    def get_table_connection_info(self, db_name, table_name):
        """Return table-specific connection information"""
        base_conn = self.get_connection_info(db_name)
        quoted_table = self._quote_identifier(table_name)
        
        test_code = f'''from sqlalchemy import create_engine, text
from pathlib import Path

db_path = Path('sql_dbs') / 'duckdb' / '{db_name}_duckdb.db'
db_path_abs = db_path.resolve()
engine = create_engine(f'duckdb:///{{db_path_abs}}')

with engine.connect() as conn:
    result = conn.execute(text('SELECT * FROM {quoted_table} LIMIT 10'))
    rows = [dict(row._mapping) for row in result.fetchall()]
    print(f"Rows: {{len(rows)}}")
    
    result = conn.execute(text('DESCRIBE {quoted_table}'))
    print("Columns:", [row[0] for row in result.fetchall()])'''
        
        return {
            'connection_string': base_conn['connection_string'],
            'test_code': test_code,
            'notes': base_conn.get('notes', [])
        }
        
    def supports_check_constraints(self):
        """DuckDB supports CHECK constraints"""
        return True

    def get_check_constraints(self, table_name):
        """Get CHECK constraints for a table"""
        if not self.engine:
            return []
        
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text("""
                    SELECT constraint_text, constraint_column_names
                    FROM duckdb_constraints()
                    WHERE table_name = :t AND constraint_type = 'CHECK'
                """), {'t': table_name})
                
                checks = []
                for row in result.fetchall():
                    raw = row[0].strip()
                    
                    # Extract expression from CHECK(...)
                    if raw.upper().startswith("CHECK"):
                        expression = raw[raw.find("(") + 1 : raw.rfind(")")]
                    else:
                        expression = raw
                    
                    columns = row[1]
                    column = columns[0] if columns and len(columns) > 0 else None
                    
                    checks.append({
                        'expression': expression,
                        'column': column
                    })
                
                return checks
        except Exception as e:
            self.logger.error(f"Failed to get CHECK constraints: {e}")
            return []

    def validate_check_constraint(self, constraint_expression):
        """Validate a CHECK constraint expression"""
        dangerous_keywords = ['DROP', 'DELETE', 'INSERT', 'UPDATE', 'CREATE', 'ALTER']
        upper_expr = constraint_expression.upper()
        
        for keyword in dangerous_keywords:
            if keyword in upper_expr:
                return False
        
        return True

    def add_check_constraint_to_existing_table(self, table_name, column_name, expression, conn=None):
        """
        Add CHECK constraint to existing table.
        DuckDB requires table recreation, so this delegates to create_check_constraint.
        The conn parameter is used if provided to maintain transaction consistency.
        """
        if not self.engine and not conn:
            raise Exception("No database selected")
        
        self.logger.info(f"🔥 DuckDB: add_check_constraint_to_existing_table called for {table_name}.{column_name}")
        self.logger.info(f"   Expression: {expression}")
        self.logger.info(f"   Connection provided: {conn is not None}")
        
        try:
            # Validate expression
            if not self.validate_check_constraint(expression):
                raise ValueError("Invalid CHECK constraint expression")
            
            # Use create_check_constraint which handles table rebuild
            # Pass conn to ensure same transaction
            self.create_check_constraint(table_name, column_name, expression, conn)
            
            self.logger.info(f"✅ DuckDB: Successfully added CHECK constraint on {table_name}.{column_name}")
            
        except Exception as e:
            self.logger.error(f"💥 Failed to add CHECK constraint: {e}")
            raise
        
    def _get_fully_qualified_table_name(self, table_name, conn):
        """
        Get the fully qualified table name (database.schema.table) in DuckDB.
        Returns the proper reference to use in SQL queries.
        """
        try:
            # Query DuckDB's catalog to find where the table actually exists
            catalog_query = text("""
                SELECT database_name, schema_name, table_name
                FROM duckdb_tables()
                WHERE LOWER(table_name) = LOWER(:t)
                LIMIT 1
            """)
            catalog_result = conn.execute(catalog_query, {'t': table_name}).fetchone()
            
            if catalog_result:
                db_name = catalog_result[0]
                schema_name = catalog_result[1]
                actual_table = catalog_result[2]
                
                # Build fully qualified name based on context
                if db_name and db_name not in ['system', 'temp', 'memory']:
                    if schema_name and schema_name != 'main':
                        # Full path: database.schema.table
                        return f"{db_name}.{schema_name}.{self._quote_identifier(actual_table)}"
                    else:
                        # Just database.table (main schema is default)
                        return f"{db_name}.{self._quote_identifier(actual_table)}"
                else:
                    # Just quoted table name for system/temp/memory
                    return self._quote_identifier(actual_table)
            else:
                # Fallback: use quoted table name directly
                self.logger.warning(f"Could not find table '{table_name}' in duckdb_tables(), using quoted name")
                return self._quote_identifier(table_name)
                
        except Exception as e:
            self.logger.warning(f"Error resolving table reference: {e}, using quoted name")
            return self._quote_identifier(table_name)

    def create_check_constraint(self, table_name, column_name, expression, conn=None):
        """Create CHECK constraint - requires table recreation in DuckDB"""
        if not self.engine and not conn:
            raise Exception("No database selected")
        
        self.logger.info(f"🔧 DuckDB: create_check_constraint called for {table_name}.{column_name}")
        self.logger.info(f"   Connection provided: {conn is not None}")
        
        try:
            if not self.validate_check_constraint(expression):
                raise ValueError("Invalid CHECK constraint expression")
            
            # ✅ CRITICAL FIX: Use provided connection or create one
            should_close = False
            if conn is None:
                conn = self.engine.connect()
                should_close = True
            
            try:
                # ✅ NEW: Detect the actual schema location of the table FIRST
                actual_table_reference = self._get_fully_qualified_table_name(table_name, conn)
                self.logger.info(f"📍 Resolved table reference: {actual_table_reference}")
                
                # Get schema using the resolved reference
                schema = self.get_table_schema(table_name, conn=conn)
                
                # DIAGNOSTIC - REMOVE AFTER DEBUGGING
                self.logger.error(f"DEBUG: Schema retrieved = {schema}")
                self.logger.error(f"DEBUG: Schema length = {len(schema) if schema else 'None'}")
                self.logger.error(f"DEBUG: Schema type = {type(schema)}")
                if schema:
                    self.logger.error(f"DEBUG: First column = {schema[0] if len(schema) > 0 else 'empty'}")
                # END DIAGNOSTIC
                            
                self.logger.debug(f"Retrieved schema for {table_name}: {schema}")
                
                if not schema or len(schema) == 0:
                    raise ValueError(f"Could not retrieve schema for table {table_name} - schema is empty")
                
                # Add check constraint to the column
                column_found = False
                for col in schema:
                    if col['name'] == column_name:
                        col['check_constraint'] = expression
                        column_found = True
                        break
                
                if not column_found:
                    raise ValueError(f"Column {column_name} not found in table {table_name}")
                
                # Rebuild column definitions with CHECK - CRITICAL: Must include autoincrement handling
                column_defs = []
                for col in schema:
                    col_name_quoted = self._quote_identifier(col['name'])
                    col_type = col['type']
                    
                    # Handle autoincrement columns specially
                    if col.get('autoincrement'):
                        seq_name = f"{table_name}_{col['name']}_seq"
                        col_def = f"{col_name_quoted} {col_type} DEFAULT nextval('{seq_name}')"
                    else:
                        col_def = f"{col_name_quoted} {col_type}"
                    
                    # Add constraints
                    if col.get('pk'):
                        col_def += " PRIMARY KEY"
                    else:
                        if col.get('notnull'):
                            col_def += " NOT NULL"
                        if col.get('unique'):
                            col_def += " UNIQUE"
                    
                    # Add CHECK constraint
                    if col.get('check_constraint'):
                        col_def += f" CHECK ({col['check_constraint']})"
                    
                    column_defs.append(col_def)
                
                if not column_defs:
                    raise ValueError(f"No valid column definitions generated for table {table_name}")
                
                self.logger.debug(f"Rebuilding table with {len(column_defs)} columns including CHECK constraint")
                
                # ✅ CRITICAL FIX: Fetch data using the resolved table reference
                try:
                    data_rows = conn.execute(text(f"SELECT * FROM {actual_table_reference}")).fetchall()
                    self.logger.info(f"✅ Fetched {len(data_rows)} rows from {actual_table_reference}")
                except Exception as e:
                    self.logger.error(f"Failed to fetch table data: {e}")
                    raise
                    
                # Create temp table name
                import os
                import secrets
                temp_table_name = f"temp_{table_name}_{secrets.token_hex(4)}"
                quoted_temp = self._quote_identifier(temp_table_name)

                # Use the provided connection to rebuild table
                col_def_str = ', '.join(column_defs)

                # Create temp table with CHECK constraint
                conn.execute(text(f"CREATE TABLE {quoted_temp} ({col_def_str})"))

                # Copy data
                if data_rows:
                    # Get column names (excluding autoincrement columns for INSERT)
                    insert_cols = [col['name'] for col in schema if not col.get('autoincrement')]
                    
                    for row in data_rows:
                        row_dict = dict(row._mapping)
                        filtered_row = {k: row_dict[k] for k in insert_cols if k in row_dict}
                        
                        if filtered_row:
                            quoted_cols = ', '.join([self._quote_identifier(k) for k in filtered_row.keys()])
                            placeholders = ', '.join([f':{k}' for k in filtered_row.keys()])
                            insert_sql = f"INSERT INTO {quoted_temp} ({quoted_cols}) VALUES ({placeholders})"
                            conn.execute(text(insert_sql), filtered_row)

                # Drop old table using resolved reference
                conn.execute(text(f"DROP TABLE {actual_table_reference}"))
                # Rename temp to simple name (without schema prefix)
                quoted_new = self._quote_identifier(table_name)
                conn.execute(text(f"ALTER TABLE {quoted_temp} RENAME TO {quoted_new}"))

                self.logger.info(f"✅ Successfully rebuilt table {table_name} with CHECK constraint")
                
            finally:
                if should_close:
                    conn.close()
            
        except Exception as e:
            self.logger.error(f"Failed to create CHECK constraint: {e}")
            raise

    def delete_check_constraint(self, table_name, column_name):
        """Delete CHECK constraint - requires table recreation"""
        if not self.engine:
            raise Exception("No database selected")
        
        try:
            schema = self.get_table_schema(table_name)
            
            # Remove check constraint from column
            for col in schema:
                if col['name'] == column_name:
                    col['check_constraint'] = None
                    break
            
            # Rebuild without CHECK
            column_defs = []
            for col in schema:
                col_def = f"{col['name']} {col['type']}"
                
                if col.get('pk'):
                    col_def += " PRIMARY KEY"
                else:
                    if col.get('notnull'):
                        col_def += " NOT NULL"
                    if col.get('unique'):
                        col_def += " UNIQUE"
                
                # Skip CHECK for the column we're removing it from
                if col.get('check_constraint') and col['name'] != column_name:
                    col_def += f" CHECK ({col['check_constraint']})"
                
                column_defs.append(col_def)
            
            self.modify_table(table_name, table_name, column_defs)
            
        except Exception as e:
            self.logger.error(f"Failed to delete CHECK constraint: {e}")
            raise
    
    def supports_aggregation(self):
        """Return True if database supports aggregation (GROUP BY, SUM, AVG, etc.)"""
        return True  # SQL databases support GROUP BY aggregation
    
    # === VIEWS SUPPORT ===
    def supports_views(self):
        """Check if database supports views"""
        return True  # All major SQL databases support views

    def list_views(self):
        """List all views in current database"""
        with self.engine.connect() as conn:
            result = conn.execute(text(
                "SELECT view_name as name FROM duckdb_views()"
            ))
    
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
        
        with self.engine.connect() as conn:
            conn.execute(text(create_sql))
            conn.commit()
        
        return True

    def drop_view(self, view_name):
        """Drop a view"""
        quoted_name = self._quote_identifier(view_name)
        
        with self.engine.connect() as conn:
            conn.execute(text(f"DROP VIEW IF EXISTS {quoted_name}"))
            conn.commit()
        
        return True

    def get_view_definition(self, view_name):
        """Get the SQL definition of a view"""
        with self.engine.connect() as conn:
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
        
    # === PARTITIONS SUPPORT (NOT SUPPORTED) ===
    def supports_partitions(self):
        """Check if database supports table partitions"""
        return False
    
    def supports_partition_listing(self):
        return False

    def supports_partition_creation(self):
        return False

    def supports_partition_deletion(self):
        return False

    def list_partitions(self, table_name):
        """List all partitions for a table"""
        return []

    def create_partition(self, table_name, partition_config):
        """Create a partition on a table"""
        raise NotImplementedError(f"{self.DB_NAME} does not support partitions")

    def drop_partition(self, table_name, partition_name):
        """Drop a partition from a table"""
        raise NotImplementedError(f"{self.DB_NAME} does not support partitions")
    
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