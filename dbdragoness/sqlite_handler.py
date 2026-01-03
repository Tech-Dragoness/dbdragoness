import re
import os
import time
from sqlalchemy import create_engine
from sqlalchemy.sql import text
from .db_handler import DBHandler
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

class SQLiteHandler(DBHandler):
    
    DB_TYPE = 'sql'  
    DB_NAME = 'SQLite'
    
    def __init__(self):
        self.current_db = None
        self.engine = None
        self.logger = logging.getLogger(__name__)
        self.base_path = 'sql_dbs/sqlite'
        os.makedirs(self.base_path, exist_ok=True)

    def _quote_identifier(self, identifier):
        """Quote identifier to preserve case in SQLite"""
        return f'"{identifier}"'
    
    def get_connection_info(self, db_name):
        """Return SQLite connection information"""
        return {
            'connection_string': f'sqlite:///sql_dbs/sqlite/{db_name}.db',
            'test_code': f'''from sqlalchemy import create_engine, text
import os

# Get absolute path to database file
db_path = os.path.abspath('sql_dbs/sqlite/{db_name}.db')
print(f"Connecting to: {{db_path}}")

engine = create_engine(f'sqlite:///{{db_path}}')
with engine.connect() as conn:
    result = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
    tables = [row[0] for row in result]
    print(f"Tables: {{tables}}")''',
        'notes': [
            'Run this code from the same directory as your DBDragoness installation',
            'Make sure the database exists in DBDragoness before testing'
        ]
        }

    def create_db(self, db_name):
        if not os.path.exists(self.base_path):
            os.makedirs(self.base_path)
        db_path = os.path.join(self.base_path, f"{db_name}.db")
        open(db_path, 'a').close()
        self.engine = create_engine(f"sqlite:///{db_path}")
        self.current_db = db_name

    def delete_db(self, db_name):
        db_path = os.path.join(self.base_path, f"{db_name}.db")
        if not os.path.exists(db_path):
            raise FileNotFoundError(f"Database file not found: {db_path}")
    
        # CRITICAL: Close and dispose engine BEFORE deletion
        if self.current_db == db_name:
            if self.engine:
                self.engine.dispose()
                self.engine = None
            self.current_db = None
    
        # Add delay to ensure Windows releases file handle
        time.sleep(0.2)
    
        max_retries = 5
        for attempt in range(max_retries):
            try:
                if os.path.exists(db_path):
                    os.remove(db_path)
                    return
            except OSError as e:
                if attempt == max_retries - 1:
                    raise OSError(f"Failed to delete {db_path} after {max_retries} attempts: {str(e)}")
                time.sleep(0.5 * (attempt + 1))  # Exponential backoff

    def switch_db(self, db_name):
        db_path = os.path.join(self.base_path, f"{db_name}.db")
        if not os.path.exists(db_path):
            raise FileNotFoundError(f"Database file not found: {db_path}")
        if self.engine:
            self.engine.dispose()
        self.engine = create_engine(f"sqlite:///{db_path}")
        self.current_db = db_name

    def list_dbs(self):
        if not os.path.exists(self.base_path):
            return []

        return [
            f.replace('.db', '')
            for f in os.listdir(self.base_path)
            if f.endswith('.db') and '_duckdb' not in f
        ]

    def list_tables(self):
        if not self.engine:
            return []
        with self.engine.connect() as conn:
            result = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'")).fetchall()
            # Filter out sqlite_sequence (SQLite system table)
            tables = [row[0] for row in result if row[0] != 'sqlite_sequence']
            return tables
        
    def list_tables_for_db(self, db_name):
        db_path = os.path.join(self.base_path, f"{db_name}.db")
        if not os.path.exists(db_path):
            return []
        engine = create_engine(f"sqlite:///{db_path}")
        with engine.connect() as conn:
            result = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'")).fetchall()
            return [row[0] for row in result]

    def get_supported_types(self):
        return ['INTEGER', 'TEXT', 'REAL', 'BLOB', 'NUMERIC']
    
    def supports_non_pk_autoincrement(self):
        """Return True if database supports autoincrement on non-PK columns"""
        return False  # SQLite only supports autoincrement on INTEGER PRIMARY KEY

    def get_table_schema(self, table_name, conn=None):
        """Get schema with fallback for unquoted tables - transaction-aware"""
        if not self.engine:
            return []

        # ✅ CRITICAL FIX: Use provided connection if available (same transaction)
        should_close = False
        if conn is None:
            conn = self.engine.connect()
            should_close = True
        
        try:
            # Debug: Check what tables actually exist
            try:
                all_tables = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'")).fetchall()
                self.logger.error(f"🔍 DEBUG: All tables in DB: {[t[0] for t in all_tables]}")
            except:
                pass
            
            self.logger.error(f"🔍 DEBUG: Looking for table '{table_name}'")
            
            # CRITICAL: PRAGMA table_info does NOT accept quoted identifiers
            # Try exact case first
            result = conn.execute(text(f"PRAGMA table_info({table_name})")).fetchall()
            self.logger.error(f"🔍 DEBUG: PRAGMA table_info({table_name}) returned {len(result)} rows")
            
            if not result:
                # Try lowercase
                result = conn.execute(text(f"PRAGMA table_info({table_name.lower()})")).fetchall()
                self.logger.error(f"🔍 DEBUG: PRAGMA table_info({table_name.lower()}) returned {len(result)} rows")
            
            if not result:
                # Try with quotes (sometimes works)
                try:
                    result = conn.execute(text(f'PRAGMA table_info("{table_name}")')).fetchall()
                    self.logger.error(f'🔍 DEBUG: PRAGMA table_info("{table_name}") returned {len(result)} rows')
                except Exception as e:
                    self.logger.error(f"🔍 DEBUG: Quoted PRAGMA failed: {e}")
            
            if not result:
                # Last resort: try all possible case variations
                for table_var in all_tables:
                    table_var_name = table_var[0]
                    if table_var_name.lower() == table_name.lower():
                        result = conn.execute(text(f"PRAGMA table_info({table_var_name})")).fetchall()
                        self.logger.error(f"🔍 DEBUG: Found match! Using '{table_var_name}', got {len(result)} rows")
                        break

            # Get UNIQUE constraints
            unique_cols = set()
            try:
                # PRAGMA doesn't accept quotes
                index_result = conn.execute(text(f"PRAGMA index_list({table_name})")).fetchall()
                if not index_result:
                    index_result = conn.execute(text(f"PRAGMA index_list({table_name.lower()})")).fetchall()
                for idx_row in index_result:
                    if idx_row[2] == 1:  # unique = 1
                        idx_name = idx_row[1]
                        idx_info = conn.execute(text(f"PRAGMA index_info({idx_name})")).fetchall()
                        for info_row in idx_info:
                            unique_cols.add(info_row[2])  # column name
            except:
                pass

            schema = []
            for row in result:
                col_name = row[1]
                col_type_raw = row[2]  # This is the RAW type from SQLite
                
                # ✅ FIX: SQLite type normalization
                # SQLite stores types exactly as defined, but we need to normalize them
                col_type = col_type_raw.upper() if col_type_raw else 'TEXT'
                
                # SQLite has these storage classes: NULL, INTEGER, REAL, TEXT, BLOB
                # Map common types to SQLite storage classes
                if 'INT' in col_type:
                    # INTEGER, INT, TINYINT, SMALLINT, MEDIUMINT, BIGINT -> INTEGER
                    mapped_type = 'INTEGER'
                elif 'CHAR' in col_type or 'CLOB' in col_type or 'TEXT' in col_type:
                    # VARCHAR, CHARACTER, VARYING CHARACTER, NCHAR, TEXT, CLOB -> TEXT
                    mapped_type = 'TEXT'
                elif 'REAL' in col_type or 'FLOA' in col_type or 'DOUB' in col_type:
                    # REAL, DOUBLE, FLOAT -> REAL
                    mapped_type = 'REAL'
                elif 'BLOB' in col_type:
                    # BLOB stays BLOB
                    mapped_type = 'BLOB'
                elif 'NUMERIC' in col_type or 'DECIMAL' in col_type or 'BOOLEAN' in col_type or 'DATE' in col_type or 'TIME' in col_type:
                    # NUMERIC, DECIMAL, BOOLEAN, DATE, DATETIME -> NUMERIC
                    mapped_type = 'NUMERIC'
                else:
                    # Unknown type -> TEXT (SQLite's default)
                    mapped_type = 'TEXT'
                
                schema.append({
                    'name': col_name,
                    'type': mapped_type,  # ✅ Use normalized type
                    'pk': bool(row[5]),
                    'notnull': bool(row[3]),
                    'autoincrement': False,  # Will be set below if AUTOINCREMENT keyword is present
                    'unique': col_name in unique_cols,
                })
                
            # Check for AUTOINCREMENT keyword and CHECK constraints in CREATE TABLE statement
            try:
                create_sql_result = conn.execute(
                    text("SELECT sql FROM sqlite_master WHERE type='table' AND name=:table_name"),
                    {'table_name': table_name}
                ).fetchone()

                if create_sql_result and create_sql_result[0]:
                    create_sql = create_sql_result[0]
                    create_sql_upper = create_sql.upper()
                    logger.debug(f"CREATE TABLE SQL: {create_sql}")

                    # ✅ Extract CHECK constraints per column
                    check_constraints = {}

                    # Pattern to match column-level CHECK constraints
                    # This pattern needs to handle nested parentheses (e.g., IN (...) inside CHECK (...))
                    # Strategy: Find CHECK keyword, then match balanced parentheses

                    # First, let's find all CHECK(...) patterns
                    check_pattern = r'["`]?(\w+)["`]?\s+\w+(?:\([^)]*\))?\s+[^,]*?CHECK\s*\('

                    for match in re.finditer(check_pattern, create_sql, re.IGNORECASE):
                        col_name = match.group(1)
                        check_start = match.end()  # Position right after "CHECK ("
                        
                        # Now find the matching closing parenthesis
                        paren_count = 1
                        pos = check_start
                        check_expr = ""
                        
                        while pos < len(create_sql) and paren_count > 0:
                            char = create_sql[pos]
                            if char == '(':
                                paren_count += 1
                            elif char == ')':
                                paren_count -= 1
                                if paren_count == 0:
                                    break  # Found the matching closing paren
                            check_expr += char
                            pos += 1
                        
                        if check_expr:
                            # Clean up the expression - remove quotes from column names
                            check_expr = check_expr.strip()
                            check_expr = re.sub(r'["`]', '', check_expr)
                            check_constraints[col_name] = check_expr
                            logger.debug(f"Found CHECK constraint on {col_name}: {check_expr}")

                    # Check each column in schema for AUTOINCREMENT and CHECK
                    for col in schema:
                        # Check for AUTOINCREMENT
                        if col['pk']:  # Only PK can have autoincrement in SQLite
                            col_pattern = rf'["\']?{re.escape(col["name"])}["\']?[^,]*?AUTOINCREMENT'
                            if re.search(col_pattern, create_sql_upper, re.IGNORECASE):
                                col['autoincrement'] = True
                                logger.debug(f"Column {col['name']} has AUTOINCREMENT")
                            else:
                                col['autoincrement'] = False
                        else:
                            col['autoincrement'] = False
                        
                        # ✅ Add CHECK constraint to column
                        col['check_constraint'] = check_constraints.get(col['name'])
                        
            except Exception as e:
                logger.error(f"Error getting schema for {table_name}: {e}")
                import traceback
                logger.error(traceback.format_exc())
                raise  # Re-raise the exception instead of silently failing
        
            return schema
        except Exception as e:
            pass
        finally:
            if should_close:
                conn.close()

    def read(self, table_name):
        """Read with quoted table name"""
        if not self.engine:
            return []
        
        with self.engine.connect() as conn:
            # Try quoted first
            try:
                quoted_table = self._quote_identifier(table_name)
                result = conn.execute(text(f"SELECT * FROM {quoted_table}")).fetchall()
                return [dict(row._mapping) for row in result]
            except:
                # Fallback to unquoted
                result = conn.execute(text(f"SELECT * FROM {table_name}")).fetchall()
                return [dict(row._mapping) for row in result]

    def execute_query(self, query):
        if not self.engine:
            raise Exception("No database selected")
    
        statements = [s.strip() for s in query.split(';') if s.strip()]
    
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
            conn.execute(text(f"CREATE TABLE IF NOT EXISTS {quoted_table} (id INTEGER PRIMARY KEY AUTOINCREMENT)"))
            conn.commit()

    def insert(self, table_name, data):
        """Insert with quoted identifiers - handle empty strings as NULL"""
        if not self.engine:
            raise Exception("No database selected")
    
        # Convert empty strings to None (NULL) for numeric/non-text columns
        schema = self.get_table_schema(table_name)
        cleaned_data = {}
    
        for key, value in data.items():
            col_info = next((c for c in schema if c['name'] == key), None)
            if col_info and value == '':
                # For numeric types, convert empty string to None
                if col_info['type'].upper() in ['INTEGER', 'REAL', 'DOUBLE', 'FLOAT', 'BIGINT', 'SMALLINT', 'DECIMAL', 'NUMERIC']:
                    cleaned_data[key] = None
                else:
                    cleaned_data[key] = value
            else:
                cleaned_data[key] = value
    
        quoted_table = self._quote_identifier(table_name)
        quoted_cols = ', '.join([self._quote_identifier(k) for k in cleaned_data.keys()])
        placeholders = ', '.join([f':{key}' for key in cleaned_data.keys()])
        query = f"INSERT INTO {quoted_table} ({quoted_cols}) VALUES ({placeholders})"
    
        with self.engine.connect() as conn:
            conn.execute(text(query), cleaned_data)
            conn.commit()

    def update(self, table_name, data, condition):
        """Update with quoted identifiers"""
        if not self.engine:
            raise Exception("No database selected")
        
        quoted_table = self._quote_identifier(table_name)
        sets = ', '.join([f"{self._quote_identifier(k)}=:{k}" for k in data])
        query = f"UPDATE {quoted_table} SET {sets} WHERE {condition}"
        
        with self.engine.connect() as conn:
            conn.execute(text(query), data)
            conn.commit()

    def delete(self, table_name, condition):
        """Delete with quoted table name"""
        if not self.engine:
            raise Exception("No database selected")
        
        quoted_table = self._quote_identifier(table_name)
        query = f"DELETE FROM {quoted_table} WHERE {condition}"
        
        with self.engine.connect() as conn:
            conn.execute(text(query))
            conn.commit()

    def delete_table(self, table_name):
        """Drop table with quoted name"""
        if not self.engine:
            raise Exception("No database selected")
        
        quoted_table = self._quote_identifier(table_name)
        with self.engine.connect() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS {quoted_table}"))
            conn.commit()

    def can_convert_column(self, table_name, column, new_type):
        return True

    def modify_table(self, old_table_name, new_table_name, new_columns):
        """Modified to handle column renames properly with quoted identifiers"""
        if not self.engine:
            raise Exception("No database selected")
    
        with self.engine.connect() as conn:
            try:
                old_schema = self.get_table_schema(old_table_name)
                old_columns = {col['name']: col for col in old_schema}
            
                import secrets
                temp_table_name = f"temp_{old_table_name}_{secrets.token_hex(4)}"
                
                # Quote all column definitions
                quoted_new_columns = []
                new_column_info = {}

                for col_def in new_columns:
                    parts = col_def.split(maxsplit=1)
                    if len(parts) >= 2:
                        col_name = parts[0]
                        rest = parts[1]
                        quoted_col_def = f'{self._quote_identifier(col_name)} {rest}'
                        quoted_new_columns.append(quoted_col_def)
        
                        new_column_info[col_name] = {
                            'definition': rest,
                            'not_null': 'NOT NULL' in rest.upper(),
                            'pk': 'PRIMARY KEY' in rest.upper(),
                            'unique': 'UNIQUE' in rest.upper(),
                            'autoincrement': 'AUTOINCREMENT' in rest.upper()  
                        }
                    else:
                        quoted_new_columns.append(self._quote_identifier(col_def))
                        new_column_info[col_def] = {
                            'definition': '',
                            'not_null': False,
                            'pk': False
                        }
                
                col_def = ', '.join(quoted_new_columns)
                quoted_temp = self._quote_identifier(temp_table_name)
                conn.execute(text(f"CREATE TABLE {quoted_temp} ({col_def})"))
            
                # Build intelligent column mapping
                new_column_names = list(new_column_info.keys())
                old_column_names = list(old_columns.keys())
            
                column_mapping = {}
                used_old_columns = set()
            
                # First pass: exact name match
                for new_col in new_column_names:
                    if new_col in old_columns:
                        column_mapping[new_col] = new_col
                        used_old_columns.add(new_col)
            
                # Second pass: positional mapping for renames
                unmapped_new = [c for c in new_column_names if c not in column_mapping]
                unmapped_old = [c for c in old_column_names if c not in used_old_columns]
            
                for i, new_col in enumerate(unmapped_new):
                    if i < len(unmapped_old):
                        column_mapping[new_col] = unmapped_old[i]
            
                # Build SELECT and INSERT with proper quoting
                select_parts = []
                insert_cols = []

                for new_col_name, old_col_name in column_mapping.items():
                    insert_cols.append(self._quote_identifier(new_col_name))
    
                    new_col_info = new_column_info[new_col_name]
                    quoted_old = self._quote_identifier(old_col_name)
    
                    # Parse UNIQUE constraint from definition
                    new_col_info['unique'] = 'UNIQUE' in new_col_info['definition'].upper()
                    new_col_info['autoincrement'] = 'AUTOINCREMENT' in new_col_info['definition'].upper()

                    # Handle NOT NULL with COALESCE (only for non-PK and non-autoincrement)
                    if new_col_info['not_null'] and not new_col_info['pk'] and not new_col_info['autoincrement']:
                        old_col_type = old_columns[old_col_name]['type']
                        if old_col_type == 'INTEGER':
                            select_parts.append(f"COALESCE({quoted_old}, 0)")
                        elif old_col_type == 'REAL':
                            select_parts.append(f"COALESCE({quoted_old}, 0.0)")
                        else:
                            select_parts.append(f"COALESCE({quoted_old}, '')")
                    else:
                        select_parts.append(quoted_old)
            
                # Copy data
                if select_parts:
                    select_cols = ', '.join(select_parts)
                    insert_cols_str = ', '.join(insert_cols)
                    quoted_old_table = self._quote_identifier(old_table_name)
                    conn.execute(text(f"INSERT INTO {quoted_temp} ({insert_cols_str}) SELECT {select_cols} FROM {quoted_old_table}"))
            
                # Drop old and rename temp
                quoted_old = self._quote_identifier(old_table_name)
                quoted_new = self._quote_identifier(new_table_name)
                conn.execute(text(f"DROP TABLE {quoted_old}"))
                conn.execute(text(f"ALTER TABLE {quoted_temp} RENAME TO {quoted_new}"))
            
                conn.commit()
            except Exception as e:
                conn.rollback()
                raise Exception(f"Failed to modify table: {str(e)}")
            
    def supports_joins(self):
        return True

    def supports_triggers(self):
        return True
    
    def convert_trigger_syntax(self, trigger_body, trigger_event, table_name):
        """
        Convert trigger syntax from other databases to SQLite.
        
        Conversions:
        - MySQL: SET NEW.column = value → UPDATE OF column SET NEW.column = value
        - PostgreSQL: NEW.column := value → UPDATE OF column SET NEW.column = value
        - Remove BEGIN...END wrappers (SQLite adds them automatically)
        """
        import re
        
        # Remove existing BEGIN...END wrappers
        trigger_body = re.sub(r'^\s*BEGIN\s+', '', trigger_body, flags=re.IGNORECASE)
        trigger_body = re.sub(r'\s*END\s*;?\s*$', '', trigger_body, flags=re.IGNORECASE)
        
        # Convert PostgreSQL assignment (NEW.col := val) to SQLite UPDATE
        trigger_body = re.sub(
            r'(NEW\.\w+)\s*:=\s*',
            r'UPDATE OF ... SET \1 = ',
            trigger_body,
            flags=re.IGNORECASE
        )
        
        # Convert MySQL SET (SET NEW.col = val) to SQLite UPDATE
        trigger_body = re.sub(
            r'\bSET\s+(NEW\.\w+)\s*=\s*',
            r'UPDATE OF ... SET \1 = ',
            trigger_body,
            flags=re.IGNORECASE
        )
        
        # Extract the actual assignment for SQLite
        # Pattern: UPDATE OF ... SET NEW.column = expression
        match = re.search(r'SET\s+(NEW\.\w+)\s*=\s*(.+?)(?:;|$)', trigger_body, re.IGNORECASE)
        if match:
            assignment = f"{match.group(1)} = {match.group(2).strip().rstrip(';')}"
            trigger_body = assignment
        
        return trigger_body.strip()

    def supports_plsql(self):
        return False

    def execute_join(self, join_query):
        return self.execute_query(join_query)
    
    def supports_aggregation(self):
        """Return True if database supports aggregation (GROUP BY, SUM, AVG, etc.)"""
        return True  # SQL databases support GROUP BY aggregation
    
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
        """Create a WORKING SQLite trigger - THE SPRITE-TAMING EDITION"""
        import re
        logger.debug(f"[TRIGGER] Conjuring: {trigger_name} on {table_name} (timing={trigger_timing}, event={trigger_event})")
        logger.debug(f"[TRIGGER] Raw essence: {repr(trigger_body)}")

        quoted_trigger = self._quote_identifier(trigger_name)
        quoted_table = self._quote_identifier(table_name)

        timing = trigger_timing.strip().upper()
        if timing not in ('BEFORE', 'AFTER'):
            timing = 'AFTER'  # Default to AFTER for mods
            logger.debug(f"[TRIGGER] Set timing to: {timing}")

        event = trigger_event.strip().upper()
        if event not in ('INSERT', 'UPDATE', 'DELETE'):
            raise ValueError("Event must be INSERT, UPDATE, or DELETE—keep it simple, sprite!")

        # Detect modification intent (your uppercase alchemy)
        if re.search(r'\bNEW\.\w+', trigger_body, re.IGNORECASE):
            # Force AFTER for INSERT/UPDATE mods—SQLite's golden rule
            if timing == 'BEFORE' and event in ('INSERT', 'UPDATE'):
                timing = 'AFTER'
                logger.warning(f"[TRIGGER] Switched to AFTER for {event} mod—SQLite's whims demand it!")

            # Parse assignments like NEW.name = UPPER(NEW.name)
            assignments = []
            for line in trigger_body.split(';'):
                line = line.strip()
                if line:
                    match = re.match(r'NEW\.(\w+)\s*=\s*(.+)', line, re.IGNORECASE)
                    if match:
                        col = match.group(1)
                        expr = match.group(2).rstrip(';')  # Zap stray ;
                        assignments.append(f"{col} = {expr}")

            if assignments:
                set_clause = ', '.join(assignments)
                body_content = f"UPDATE {quoted_table} SET {set_clause} WHERE rowid = NEW.rowid;"
                logger.debug(f"[TRIGGER] Transformed to UPDATE: {body_content}")
            else:
                # Fallback if no clear assignment
                body_content = trigger_body.strip().rstrip(';') + ';'
                logger.debug(f"[TRIGGER] No assignment found; using raw: {body_content}")

        else:
            # Non-mod triggers (logs, etc.)
            lines = [l.strip().rstrip(';') for l in trigger_body.split(';') if l.strip()]
            body_content = ';\n    '.join(lines) + ';'

        # The grand incantation
        trigger_sql = f"""
    CREATE TRIGGER {quoted_trigger}
        {timing} {event} ON {quoted_table}
    FOR EACH ROW
    BEGIN
        {body_content}
    END;
    """.strip()

        logger.debug(f"[TRIGGER] Final spell:\n{trigger_sql}")

        try:
            with self.engine.connect() as conn:
                conn.execute(text(trigger_sql))
                conn.commit()
            logger.debug(f"[TRIGGER] Victory! {trigger_name} awakens.")
            return {"status": f"Trigger '{trigger_name}' now dances with fire—insert and behold!", "refresh": True}
        except Exception as e:
            logger.error(f"[TRIGGER] Sprite's curse: {e}")
            raise Exception(f"Trigger failed: {str(e)}")
        
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
            body: Trigger body (SQL statements)
        """
        logger.debug(f"[TRIGGER IN TRANSACTION] Conjuring: {trigger_name} on {table_name} (timing={timing}, event={event})")
        logger.debug(f"[TRIGGER IN TRANSACTION] Raw essence: '{body}'")
        
        # Quote identifiers
        quoted_table = self._quote_identifier(table_name)
        quoted_trigger = self._quote_identifier(trigger_name)
        
        # SQLite constraint: BEFORE triggers cannot modify the table
        # Convert BEFORE INSERT/UPDATE to AFTER with UPDATE workaround
        original_timing = timing
        trigger_body = body
        
        if timing.upper() == 'BEFORE' and event.upper() in ['INSERT', 'UPDATE']:
            logger.warning(f"[TRIGGER IN TRANSACTION] Switched to AFTER for {event} mod—SQLite's whims demand it!")
            timing = 'AFTER'
            
            # Transform NEW.column = value to UPDATE statement
            import re
            assignment_match = re.search(r'NEW\.(\w+)\s*[:=]+\s*(.+)', body, re.IGNORECASE)
            if assignment_match:
                column = assignment_match.group(1)
                value_expr = assignment_match.group(2).rstrip(';').strip()
                trigger_body = f"UPDATE {quoted_table} SET {column} = {value_expr} WHERE rowid = NEW.rowid;"
                logger.debug(f"[TRIGGER IN TRANSACTION] Transformed to UPDATE: {trigger_body}")
        
        # Build complete trigger SQL
        trigger_sql = f"""CREATE TRIGGER {quoted_trigger}
            {timing.upper()} {event.upper()} ON {quoted_table}
        FOR EACH ROW
        BEGIN
            {trigger_body}
        END;"""
        
        logger.debug(f"[TRIGGER IN TRANSACTION] Final spell:\n{trigger_sql}")
        
        # Execute within provided transaction - NO COMMIT
        conn.execute(text(trigger_sql))
        
        logger.debug(f"[TRIGGER IN TRANSACTION] Victory! {trigger_name} awakens (within transaction).")
        # DO NOT COMMIT - let the caller handle it

    def list_triggers(self, table_name=None):
        """List triggers - FIXED to return proper results with timing/event parsed"""
        if not self.engine:
            return []

        with self.engine.connect() as conn:
            if table_name:
                # Try quoted first
                try:
                    result = conn.execute(text("""
                        SELECT name, tbl_name, sql 
                        FROM sqlite_master 
                        WHERE type='trigger' AND tbl_name=:table
                    """), {'table': table_name})
                    triggers = []
                    for r in result:
                        trigger_sql = r[2] or ''
                        # Parse timing and event from SQL
                        timing = 'AFTER'  # Default
                        if 'BEFORE' in trigger_sql.upper():
                            timing = 'BEFORE'
                    
                        event = 'UNKNOWN'
                        if 'INSERT' in trigger_sql.upper():
                            event = 'INSERT'
                        elif 'UPDATE' in trigger_sql.upper():
                            event = 'UPDATE'
                        elif 'DELETE' in trigger_sql.upper():
                            event = 'DELETE'
                    
                        triggers.append({
                            'name': r[0], 
                            'table': r[1], 
                            'sql': trigger_sql,
                            'timing': timing,
                            'event': event
                        })
                
                    if triggers:
                        return triggers
                except Exception as e:
                    self.logger.error(f"Error listing triggers for {table_name}: {e}")
        
                # Try lowercase fallback
                try:
                    result = conn.execute(text("""
                        SELECT name, tbl_name, sql 
                        FROM sqlite_master 
                        WHERE type='trigger' AND LOWER(tbl_name)=LOWER(:table)
                    """), {'table': table_name})
                except:
                    return []
            else:
                # List all triggers
                result = conn.execute(text("""
                    SELECT name, tbl_name, sql 
                    FROM sqlite_master 
                    WHERE type='trigger'
                """))
    
            triggers = []
            for r in result:
                trigger_sql = r[2] or ''
                # Parse timing and event from SQL
                timing = 'AFTER'  # Default
                if 'BEFORE' in trigger_sql.upper():
                    timing = 'BEFORE'
            
                event = 'UNKNOWN'
                if 'INSERT' in trigger_sql.upper():
                    event = 'INSERT'
                elif 'UPDATE' in trigger_sql.upper():
                    event = 'UPDATE'
                elif 'DELETE' in trigger_sql.upper():
                    event = 'DELETE'
            
                triggers.append({
                    'name': r[0], 
                    'table': r[1], 
                    'sql': trigger_sql,
                    'timing': timing,
                    'event': event
                })
        
            return triggers

    def delete_trigger(self, trigger_name, table_name=None):
        """Delete trigger - fixed signature to match base class"""
        with self.engine.connect() as conn:
            conn.execute(text(f"DROP TRIGGER IF EXISTS {self._quote_identifier(trigger_name)}"))
            conn.commit()

    def get_trigger_details(self, trigger_name):
        with self.engine.connect() as conn:
            result = conn.execute(text("SELECT name, tbl_name, sql FROM sqlite_master WHERE type='trigger' AND name=:name"), {'name': trigger_name})
            row = result.fetchone()
            if row:
                return {'name': row[0], 'table': row[1], 'sql': row[2]}
            return None

    def execute_plsql(self, plsql_code):
        raise NotImplementedError("SQLite doesn't support PL/SQL")
    
    def get_credential_status(self):
        """SQLite handler doesn't require credentials"""
        return {
            "needs_credentials": False,
            "handler": self.DB_NAME
        }

    def clear_credentials(self):
        """SQLite handler doesn't store credentials"""
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
        
    def _is_system_table(self, table_name):
        """Check if table is a SQLite system table"""
        SYSTEM_TABLES = {
            'sqlite_sequence',
            'sqlite_master',
            'sqlite_temp_master',
            'sqlite_stat1',
            'sqlite_stat2',
            'sqlite_stat3',
            'sqlite_stat4'
        }
        return table_name.lower() in SYSTEM_TABLES

    # And in sqlite_handler.py, replace build_column_definitions method:

    def build_column_definitions(self, schema, quote=True):
        """Build column definition strings for table creation"""
        columns_def = []
        
        # SQLite reserved keywords that should be quoted
        RESERVED_KEYWORDS = {
            'table', 'select', 'from', 'where', 'insert', 'update', 'delete',
            'create', 'drop', 'alter', 'index', 'view', 'trigger', 'order',
            'group', 'having', 'limit', 'offset', 'join', 'on', 'as', 'in',
            'exists', 'case', 'when', 'then', 'else', 'end', 'union', 'all'
        }
        
        for col in schema:
            col_name_raw = col['name']
            col_type = col['type']
            
            # Always quote reserved keywords
            if quote or col_name_raw.lower() in RESERVED_KEYWORDS:
                col_name = self._quote_identifier(col_name_raw)
            else:
                col_name = col_name_raw
            
            # Ensure type is provided
            if not col_type:
                col_type = 'TEXT'
            
            col_def = f"{col_name} {col_type}"
            
            if col.get('pk'):
                col_def += " PRIMARY KEY"
                if col.get('autoincrement'):
                    col_def += " AUTOINCREMENT"
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
    
    def build_column_definition_for_create(self, quoted_name, type_with_length, is_pk, is_not_null, is_autoincrement, is_unique, table_name=None, has_composite_pk=False):
        """Build column definition for CREATE TABLE"""
        col_def = f"{quoted_name} {type_with_length}"
        
        if is_pk:
            if is_autoincrement:
                col_def += " PRIMARY KEY AUTOINCREMENT"
            else:
                col_def += " PRIMARY KEY"
        else:
            if is_not_null:
                col_def += " NOT NULL"
            if is_unique:
                col_def += " UNIQUE"
        
        return col_def
    
    def reset_sequence_after_copy(self, table_name, column_name):
        """SQLite auto-manages AUTOINCREMENT, no action needed"""
        pass  # SQLite automatically handles this
    
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
                    SELECT name, sql
                    FROM sqlite_master
                    WHERE type = 'view'
                """))
                
                # SQLite stores full CREATE VIEW statement
                return [{'name': row[0], 'definition': row[1]} for row in result.fetchall()]
        except Exception as e:
            self.logger.error(f"Failed to get views: {e}")
            return []

    def create_view(self, view_name, view_definition):
        """Create a view"""
        # SQLite view_definition is already the full CREATE VIEW statement
        with self.engine.connect() as conn:
            conn.execute(text(view_definition))
            conn.commit()
            
    def copy_table(self, source_table, dest_table):
        """Copy table structure, data, and triggers"""
        schema = self.get_table_schema(source_table)
        data_rows = self.read(source_table)
        
        # Build CREATE TABLE
        columns_def = self.build_column_definitions(schema, quote=False)
        col_def_str = ', '.join(columns_def)
        quoted_dest = self._quote_identifier(dest_table)
        
        with self.engine.connect() as conn:
            create_sql = f"CREATE TABLE {quoted_dest} ({col_def_str})"
            conn.execute(text(create_sql))
            conn.commit()
        
        # Copy data
        for row in data_rows:
            filtered_row = {k: v for k, v in row.items() 
                        if not any(col['name'] == k and col.get('autoincrement') 
                                    for col in schema)}
            if filtered_row:
                self.insert(dest_table, filtered_row)

        # ✅ STEP: Reapply CHECK constraints AFTER data copy
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
                    # Add CHECK constraint via table rebuild
                    self.create_check_constraint(
                        dest_table,
                        check_info['column'],
                        check_info['expression']
                    )
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

        # Copy triggers
        self.copy_triggers(source_table, dest_table)

    def copy_triggers(self, source_table, dest_table):
        """Copy triggers from source to destination table"""
        if not self.engine:
            return
        
        with self.engine.connect() as conn:
            # Get triggers for source table
            result = conn.execute(text("""
                SELECT name, sql 
                FROM sqlite_master 
                WHERE type='trigger' AND tbl_name=:table
            """), {'table': source_table})
            
            for row in result:
                trigger_name = row[0]
                trigger_sql = row[1]
                
                if not trigger_sql:
                    continue
                
                # Replace table name in trigger SQL
                new_trigger_sql = trigger_sql.replace(
                    f'ON "{source_table}"',
                    f'ON "{dest_table}"'
                ).replace(
                    f'ON {source_table}',
                    f'ON {dest_table}'
                )
                
                # Generate new trigger name
                new_trigger_name = f"{dest_table}_{trigger_name}"
                new_trigger_sql = new_trigger_sql.replace(
                    f'TRIGGER "{trigger_name}"',
                    f'TRIGGER "{new_trigger_name}"'
                ).replace(
                    f'TRIGGER {trigger_name}',
                    f'TRIGGER {new_trigger_name}'
                )
                
                try:
                    conn.execute(text(new_trigger_sql))
                    conn.commit()
                    self.logger.debug(f"Copied trigger {trigger_name} to {new_trigger_name}")
                except Exception as e:
                    self.logger.warning(f"Failed to copy trigger {trigger_name}: {e}")

    def apply_validation_rules(self, table_name, validation_rules):
        """
        Apply validation rules as CHECK constraints.
        Since SQLite requires table recreation for CHECK constraints,
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
        
        # 3. String length constraints (SQLite uses LENGTH not CHAR_LENGTH)
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
                    
    def get_table_connection_info(self, db_name, table_name):
        """Return table-specific connection information"""
        base_conn = self.get_connection_info(db_name)
        quoted_table = self._quote_identifier(table_name)
        
        test_code = f'''from sqlalchemy import create_engine, text
import os

db_path = os.path.abspath('sql_dbs/sqlite/{db_name}.db')
engine = create_engine(f'sqlite:///{{db_path}}')

with engine.connect() as conn:
    result = conn.execute(text('SELECT * FROM {quoted_table} LIMIT 10'))
    rows = [dict(row._mapping) for row in result.fetchall()]
    print(f"Rows: {{len(rows)}}")'''
        
        return {
            'connection_string': base_conn['connection_string'],
            'test_code': test_code,
            'notes': base_conn.get('notes', [])
        }
        
    def supports_check_constraints(self):
        """SQLite supports CHECK constraints"""
        return True

    def get_check_constraints(self, table_name):
        """Get CHECK constraints for a table"""
        if not self.engine:
            return []
        
        try:
            with self.engine.connect() as conn:
                # Get the CREATE TABLE statement
                result = conn.execute(text("""
                    SELECT sql FROM sqlite_master 
                    WHERE type='table' AND name=:table_name
                """), {'table_name': table_name})
                
                row = result.fetchone()
                if not row or not row[0]:
                    return []
                
                create_sql = row[0]
                
                # Parse CHECK constraints from CREATE TABLE
                # Format: CHECK (expression) or CONSTRAINT name CHECK (expression)
                import re
                checks = []
                
                # Match: CHECK (...)
                pattern = r'CHECK\s*\(([^)]+(?:\([^)]*\))*[^)]*)\)'
                matches = re.finditer(pattern, create_sql, re.IGNORECASE)
                
                for match in matches:
                    expression = match.group(1).strip()
                    checks.append({
                        'expression': expression,
                        'column': self._extract_column_from_check(expression)
                    })
                
                return checks
        except Exception as e:
            self.logger.error(f"Failed to get CHECK constraints: {e}")
            return []

    def _extract_column_from_check(self, expression):
        """Try to extract the primary column name from a CHECK expression"""
        import re
        # Simple heuristic: find the first word that looks like a column name
        match = re.search(r'\b([a-zA-Z_][a-zA-Z0-9_]*)\b', expression)
        if match:
            return match.group(1)
        return None

    def validate_check_constraint(self, constraint_expression):
        """Validate a CHECK constraint expression for SQLite"""
        dangerous_keywords = ['DROP', 'DELETE', 'INSERT', 'UPDATE', 'CREATE', 'ALTER']
        upper_expr = constraint_expression.upper()
        
        for keyword in dangerous_keywords:
            if keyword in upper_expr:
                return False
        
        return True
    
    def add_check_constraint_to_existing_table(self, table_name, column_name, expression, conn=None):
        """
        Add CHECK constraint to existing table.
        SQLite requires table recreation, so this delegates to create_check_constraint.
        The conn parameter is used if provided to maintain transaction consistency.
        """
        if not self.engine and not conn:
            raise Exception("No database selected")
        
        try:
            self.logger.info(f"🔥 SQLite: add_check_constraint_to_existing_table called for {table_name}.{column_name}")
            self.logger.info(f"   Expression: {expression}")
            self.logger.info(f"   Connection provided: {conn is not None}")
            
            # Validate expression
            if not self.validate_check_constraint(expression):
                raise ValueError("Invalid CHECK constraint expression")
            
            # Use create_check_constraint which handles table rebuild
            # Pass conn to ensure same transaction
            self.create_check_constraint(table_name, column_name, expression, conn)
            
            self.logger.info(f"✅ SQLite: Successfully added CHECK constraint on {table_name}.{column_name}")
            
        except Exception as e:
            self.logger.error(f"💥 Failed to add CHECK constraint: {e}")
            raise
    
    def create_check_constraint(self, table_name, column_name, expression, conn=None):
        """Create CHECK constraint for a column - requires table rebuild in SQLite"""
        if not self.engine and not conn:
            raise Exception("No database selected")
        
        self.logger.info(f"🔧 SQLite: create_check_constraint called for {table_name}.{column_name}")
        
        # Validate expression
        if not self.validate_check_constraint(expression):
            raise ValueError("Invalid CHECK constraint expression")
        
        # ✅ CRITICAL FIX: Pass connection to get_table_schema to see uncommitted tables
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
        
        # Add CHECK constraint to the specific column
        column_found = False
        for col in schema:
            if col['name'] == column_name:
                col['check_constraint'] = expression
                column_found = True
                break
        
        if not column_found:
            raise ValueError(f"Column {column_name} not found in table {table_name}")
        
        # Get current data
        data_rows = self.read(table_name)
        
        # Create temporary table name
        import secrets
        temp_table_name = f"temp_{table_name}_{secrets.token_hex(4)}"
        
        # Use provided connection or create new one
        should_close = False
        if conn is None:
            conn = self.engine.connect()
            should_close = True
        
        try:
            # Build column definitions WITH CHECK constraint
                columns_def = self.build_column_definitions(schema, quote=True)
                
                if not columns_def:
                    raise ValueError(f"No valid column definitions generated for table {table_name}")
                
                col_def_str = ', '.join(columns_def)
                quoted_temp = self._quote_identifier(temp_table_name)
                
                self.logger.debug(f"Creating temp table with {len(columns_def)} columns including CHECK constraint")
                
                # Create temp table with CHECK constraint
                conn.execute(text(f"CREATE TABLE {quoted_temp} ({col_def_str})"))
                
                # Copy data (this will validate against CHECK constraint)
                for row in data_rows:
                    filtered_row = {k: v for k, v in row.items() 
                                if not any(col['name'] == k and col.get('autoincrement') 
                                            for col in schema)}
                    if filtered_row:
                        quoted_table_temp = self._quote_identifier(temp_table_name)
                        quoted_cols = ', '.join([self._quote_identifier(k) for k in filtered_row.keys()])
                        placeholders = ', '.join([f':{k}' for k in filtered_row.keys()])
                        insert_sql = f"INSERT INTO {quoted_table_temp} ({quoted_cols}) VALUES ({placeholders})"
                        conn.execute(text(insert_sql), filtered_row)
                
                # Drop old table and rename temp table
                quoted_old = self._quote_identifier(table_name)
                conn.execute(text(f"DROP TABLE {quoted_old}"))
                conn.execute(text(f"ALTER TABLE {quoted_temp} RENAME TO {quoted_old}"))
                
                if should_close:
                    conn.commit()
                
        except Exception as e:
            if should_close:
                conn.rollback()
            # Clean up temp table if it exists
            try:
                conn.execute(text(f"DROP TABLE IF EXISTS {quoted_temp}"))
                conn.commit()
            except:
                pass
            raise Exception(f"Failed to create CHECK constraint: {str(e)}")
        finally:
            if should_close and conn:
                conn.close()
            
    def delete_check_constraint(self, table_name, column_name):
        """Delete CHECK constraint from a column - requires table rebuild in SQLite"""
        if not self.engine:
            raise Exception("No database selected")
        
        # Get current schema
        schema = self.get_table_schema(table_name)
        
        # Remove CHECK constraint from the specific column
        constraint_found = False
        for col in schema:
            if col['name'] == column_name and col.get('check_constraint'):
                col['check_constraint'] = None
                constraint_found = True
                break
        
        if not constraint_found:
            raise ValueError(f"No CHECK constraint found on column {column_name}")
        
        # Get current data
        data_rows = self.read(table_name)
        
        # Create temporary table name
        import secrets
        temp_table_name = f"temp_{table_name}_{secrets.token_hex(4)}"
        
        with self.engine.connect() as conn:
            try:
                # Build column definitions WITHOUT CHECK constraint
                columns_def = self.build_column_definitions(schema, quote=True)
                col_def_str = ', '.join(columns_def)
                quoted_temp = self._quote_identifier(temp_table_name)
                
                # Create temp table without CHECK constraint
                conn.execute(text(f"CREATE TABLE {quoted_temp} ({col_def_str})"))
                
                # Copy data
                for row in data_rows:
                    filtered_row = {k: v for k, v in row.items() 
                                if not any(col['name'] == k and col.get('autoincrement') 
                                            for col in schema)}
                    if filtered_row:
                        quoted_table_temp = self._quote_identifier(temp_table_name)
                        quoted_cols = ', '.join([self._quote_identifier(k) for k in filtered_row.keys()])
                        placeholders = ', '.join([f':{k}' for k in filtered_row.keys()])
                        insert_sql = f"INSERT INTO {quoted_table_temp} ({quoted_cols}) VALUES ({placeholders})"
                        conn.execute(text(insert_sql), filtered_row)
                
                # Drop old table and rename temp table
                quoted_old = self._quote_identifier(table_name)
                conn.execute(text(f"DROP TABLE {quoted_old}"))
                conn.execute(text(f"ALTER TABLE {quoted_temp} RENAME TO {quoted_old}"))
                
                conn.commit()
                
            except Exception as e:
                conn.rollback()
                # Clean up temp table if it exists
                try:
                    conn.execute(text(f"DROP TABLE IF EXISTS {quoted_temp}"))
                    conn.commit()
                except:
                    pass
                raise Exception(f"Failed to delete CHECK constraint: {str(e)}")
            
    # === VIEWS SUPPORT ===
    def supports_views(self):
        """Check if database supports views"""
        return True  # All major SQL databases support views

    def list_views(self):
        """List all views in current database"""
        with self.engine.connect() as conn:
            result = conn.execute(text(
                "SELECT name FROM sqlite_master WHERE type='view'"
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