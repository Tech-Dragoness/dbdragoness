# tinydb_handler.py
import re
import time
from .db_handler import DBHandler
from tinydb import TinyDB, Query
import os
import logging
import json
import traceback
import gc
from pathlib import Path

class TinyDBHandler(DBHandler):
    
    DB_TYPE = 'nosql'
    DB_NAME = 'TinyDB'
    
    def __init__(self):
        self.current_db = None
        self.db = None
        self.base_path = 'nosql_dbs/tinydb'  # ← CHANGED: Added tinydb subdirectory
        self.logger = logging.getLogger(__name__)
        
        if not os.path.exists(self.base_path):
            self.logger.debug(f"Creating directory {self.base_path}")
            os.makedirs(self.base_path)
            
    def get_connection_info(self, db_name):
        """Return TinyDB connection information"""
        return {
            'connection_string': f'nosql_dbs/tinydb/{db_name}.json',
            'test_code': f'''from tinydb import TinyDB
import os

# Get absolute path to database file
db_path = os.path.abspath('nosql_dbs/tinydb/{db_name}.json')

# Check if file exists
if not os.path.exists(db_path):
    print(f"❌ Database file not found: {{db_path}}")
    print("Make sure the database exists in DBDragoness first!")
else:
    print(f"✅ Found database: {{db_path}}")
    db = TinyDB(db_path)
    tables = db.tables()
    print(f"Tables: {{tables}}")

    if tables:
        # Show first table's documents
        first_table = tables[0]
        docs = db.table(first_table).all()
        print(f"Documents in '{{first_table}}': {{len(docs)}}")
        if docs:
            print(f"Sample: {{docs[0]}}")''',
        'notes': [
            'Run this code from the same directory as your DBDragoness installation',
            'Make sure the database exists in DBDragoness before testing'
        ]
        }
            
    def release_current_db(self):
        """Call this when leaving a DB (e.g., going home or switching)"""
        if self.db is not None:
            try:
                self.db.close()
                self.logger.debug(f"Released TinyDB: {self.current_db}")
            except Exception as e:
                self.logger.warning(f"Release error: {e}")
            finally:
                self.db = None
                self.current_db = None
        gc.collect()
        time.sleep(0.05)  # Let Windows breathe

    def create_db(self, db_name):
        db_path = os.path.join(self.base_path, f"{db_name}.json")
        self.logger.debug(f"Creating database at {db_path}")
        with open(db_path, 'w') as f:
            json.dump({"_default": {}}, f)
        self.switch_db(db_name)
        self.logger.debug(f"Database {db_name} created successfully")

    def count_documents(self, table_name):
        """Fast count without loading all documents"""
        if not self.db:
            self.logger.error("No database selected for count operation")
            if self.current_db:
                self.switch_db(self.current_db)
            else:
                return 0
        try:
            count = len(self.db.table(table_name))
            self.logger.debug(f"Counted {count} documents in {table_name}")
            return count
        except Exception as e:
            self.logger.error(f"Count error for {table_name}: {str(e)}")
            return 0

    def close_db(self):
        """Public method to close database"""
        if self.db is not None:
            try:
                self.db.close()
                self.logger.debug(f"Closed TinyDB: {self.current_db}")
            except Exception as e:
                self.logger.warning(f"Close error: {e}")
            finally:
                self.db = None

    def delete_db(self, db_name):
        db_path = os.path.join(self.base_path, f"{db_name}.json")
        self.logger.debug(f"ETERNAL WATCHER: Deleting {db_name}")

        # 1. Close if open
        if self.current_db == db_name:
            self.release_current_db()

        if not os.path.exists(db_path):
            return

        # 2. Try instant delete
        try:
            os.remove(db_path)
            self.logger.debug("Instant delete success")
            return
        except PermissionError:
            self.logger.debug("Locked — entering background purge")

        # 3. Rename to mark for death
        import uuid
        trash_name = f"__DELETING_{db_name}_{uuid.uuid4().hex[:8]}.json"
        trash_path = os.path.join(self.base_path, trash_name)
        try:
            os.rename(db_path, trash_path)
            self.logger.debug(f"Marked for death: {trash_name}")
        except Exception as e:
            raise Exception(f"Cannot even rename {db_name}: {e}")

        # 4. SPAWN ETERNAL WATCHER
        import threading
        def _background_purge():
            max_attempts = 60  # Try for ~2 minutes
            for i in range(max_attempts):
                try:
                    if os.path.exists(trash_path):
                        os.remove(trash_path)
                        self.logger.debug(f"Background purge success: {trash_name}")
                        return
                except:
                    pass
                time.sleep(2)
            self.logger.warning(f"Gave up on {trash_name} after {max_attempts} tries")

        threading.Thread(target=_background_purge, daemon=True).start()

        # 5. UI sees success — file is "gone"
        return  # No exception → success

    def switch_db(self, db_name):
        db_path = os.path.join(self.base_path, f"{db_name}.json")
        if not os.path.exists(db_path):
            raise FileNotFoundError(f"Database file not found: {db_path}")
    
        # Close old ONLY if it's a different database
        if self.current_db and self.current_db != db_name and self.db:
            try:
                self.db.close()
                self.logger.debug(f"Closed previous TinyDB: {self.current_db}")
            except:
                pass
    
        self.db = TinyDB(db_path)
        self.current_db = db_name
        self.logger.debug(f"Switched to TinyDB: {db_name}")

    def list_dbs(self):
        if not os.path.exists(self.base_path):
            return []
        all_files = os.listdir(self.base_path)
        dbs = []
        for f in all_files:
            if f.endswith('.json') and not f.startswith('__DELETING_'):
                dbs.append(f.replace('.json', ''))
        self.logger.debug(f"Listed databases (hiding doomed): {dbs}")
        return dbs

    def list_tables(self):
        if not self.db:
            self.logger.debug("No database selected, attempting to restore from current_db")
            if self.current_db:
                self.switch_db(self.current_db)
            else:
                self.logger.debug("No database or current_db, returning empty tables list")
                return []
        tables = self.db.tables()
        filtered_tables = [t for t in tables if t != '_default']
        self.logger.debug(f"Listed tables: {filtered_tables}")
        return filtered_tables

    def list_tables_for_db(self, db_name):
        db_path = os.path.join(self.base_path, f"{db_name}.json")
        self.logger.debug(f"Listing tables for database {db_name} at {db_path}")
        if not os.path.exists(db_path):
            self.logger.debug(f"Database {db_name} not found, returning empty tables list")
            return []
        temp_db = TinyDB(db_path)
        tables = temp_db.tables()
        filtered = [t for t in tables if t != '_default' or len(temp_db.table(t)) > 0]
        temp_db.close()
        self.logger.debug(f"Tables for {db_name}: {filtered}")
        return filtered

    def get_supported_types(self):
        return []
    
    def supports_non_pk_autoincrement(self):
        """Return True if database supports autoincrement on non-PK columns"""
        return False  

    def get_table_schema(self, table_name):
        return []

    def read(self, table_name):
        if not self.db:
            self.logger.error("No database selected for read operation")
            if self.current_db:
                self.switch_db(self.current_db)
            else:
                return []
        data = self.db.table(table_name).all()
    
        # Normalize documents to use doc_id consistently
        result = []
        for doc in data:
            normalized = dict(doc)
            if 'doc_id' not in normalized:
                normalized['doc_id'] = doc.doc_id
            # Remove _id if it exists to avoid duplication
            normalized.pop('_id', None)
            result.append(normalized)
    
        self.logger.debug(f"Read {len(result)} documents from {table_name}")
        return result

    def execute_query(self, query):
        """
        Execute TinyDB query - accepts ANY format without validation
        """
        # Allow database-level commands without requiring a database
        query_upper = query.strip().upper() if isinstance(query, str) else ""
        db_level_commands = ['USE ', 'SHOW DATABASES', 'CREATE DATABASE', 'DROP DATABASE']

        if not self.db and not any(query_upper.startswith(cmd) for cmd in db_level_commands):
            self.logger.error("No database selected for query")
            if self.current_db:
                self.switch_db(self.current_db)
            else:
                raise Exception("No database selected")

        # Handle dict queries (from aggregation API)
        if isinstance(query, dict):
            return self._execute_dict_query(query)

        if not isinstance(query, str):
            raise ValueError("Query must be a string or dict")

        query = query.strip()
        query_upper = query.upper()

        self.logger.debug(f"🔍 TinyDB Query: {query[:100]}...")

        # ===== DATABASE-LEVEL COMMANDS =====

        # USE database
        if query_upper.startswith('USE '):
            match = re.match(r'USE\s+([a-zA-Z][a-zA-Z0-9_]*)', query, re.I)
            if match:
                db_name = match.group(1)
                self.switch_db(db_name)
                return [{"status": f"✅ Switched to database '{db_name}'"}]
            raise ValueError("Invalid USE syntax. Usage: USE database_name")

        # SHOW DATABASES
        if query_upper == 'SHOW DATABASES':
            dbs = self.list_dbs()
            return [{"database": db} for db in dbs]

        # SHOW COLLECTIONS / SHOW TABLES
        if query_upper in ['SHOW COLLECTIONS', 'SHOW TABLES']:
            collections = self.list_tables()
            return [{"collection": coll} for coll in collections]
    
        # CREATE DATABASE
        if query_upper.startswith('CREATE DATABASE'):
            match = re.match(r'CREATE\s+DATABASE\s+([a-zA-Z][a-zA-Z0-9_]*)', query, re.I)
            if match:
                db_name = match.group(1)
                self.create_db(db_name)
                return [{"status": f"✅ Database '{db_name}' created"}]
    
        # DROP DATABASE
        if query_upper.startswith('DROP DATABASE'):
            match = re.match(r'DROP\s+DATABASE\s+([a-zA-Z][a-zA-Z0-9_]*)', query, re.I)
            if match:
                db_name = match.group(1)
                if db_name == self.current_db:
                    # Close current database before dropping
                    self.current_db = None
                    self.db = None
                self.delete_db(db_name)
                return [{"status": f"✅ Database '{db_name}' dropped"}]

        # ===== COLLECTION-LEVEL COMMANDS =====

        # CREATE COLLECTION/TABLE
        if query_upper.startswith('CREATE COLLECTION') or query_upper.startswith('CREATE TABLE'):
            match = re.match(r'CREATE\s+(?:COLLECTION|TABLE)\s+([a-zA-Z][a-zA-Z0-9_]*)', query, re.I)
            if match:
                coll_name = match.group(1)
                self.create_collection(coll_name)
                return [{"status": f"✅ Collection '{coll_name}' created"}]

        # DROP COLLECTION/TABLE
        if query_upper.startswith('DROP COLLECTION') or query_upper.startswith('DROP TABLE'):
            match = re.match(r'DROP\s+(?:COLLECTION|TABLE)\s+([a-zA-Z][a-zA-Z0-9_]*)', query, re.I)
            if match:
                coll_name = match.group(1)
                self.delete_table(coll_name)
                return [{"status": f"✅ Collection '{coll_name}' dropped"}]
    
        # ALTER TABLE ... RENAME TO ...
        if query_upper.startswith('ALTER TABLE') and ' RENAME TO ' in query_upper:
            match = re.match(r'ALTER\s+TABLE\s+([a-zA-Z][a-zA-Z0-9_]*)\s+RENAME\s+TO\s+([a-zA-Z][a-zA-Z0-9_]*)', query, re.I)
            if match:
                old_name = match.group(1)
                new_name = match.group(2)
                self.modify_table(old_name, new_name, [])
                return [{"status": f"✅ Table '{old_name}' renamed to '{new_name}'"}]

        # ===== EVERYTHING ELSE: TRY TO EXECUTE DIRECTLY =====

        try:
            # Try as native TinyDB Python code first
            if 'db.' in query or 'Query()' in query:
                return self._execute_native_tinydb(query)
    
            # Try as JSON
            try:
                query_obj = json.loads(query)
                return self._execute_dict_query(query_obj)
            except json.JSONDecodeError:
                pass
    
            # Try as SQL-like command (INSERT, SELECT, UPDATE, DELETE, etc.)
            return self._execute_sql_like_command(query)
    
        except Exception as e:
            # If everything fails, return the error
            raise ValueError(f"Query execution failed: {str(e)}")
        
    def _execute_dict_query(self, query_dict):
        """Execute dictionary-based query"""
        if 'table' in query_dict:
            # Check if it's an aggregation query
            if 'pipeline' in query_dict:
                return self._execute_aggregation_query(query_dict)
            
            table_name = query_dict['table']
            condition = query_dict.get('condition', {})
            projection = query_dict.get('projection', {})
        
            table = self.db.table(table_name)
        
            if condition:
                # Build TinyDB query from condition
                q = Query()
                docs = self._search_with_condition(table, condition)
            else:
                docs = table.all()
            
            # Apply projection if specified
            if projection:
                projected_docs = []
                for doc in docs:
                    projected_doc = {}
                    for field_name, include in projection.items():
                        if include and field_name in doc:
                            projected_doc[field_name] = doc[field_name]
                    # Always include doc_id
                    if 'doc_id' in doc:
                        projected_doc['doc_id'] = doc['doc_id']
                    projected_docs.append(projected_doc)
                docs = projected_docs
        
            return self._normalize_results(docs)

        # Otherwise treat as find condition
        raise ValueError("Query dict must have 'table' field")
    
    def _execute_aggregation_query(self, query_dict):
        """Execute aggregation-style query for TinyDB (simulate aggregation pipeline)"""
        table_name = query_dict.get('table')
        pipeline = query_dict.get('pipeline', [])
        
        if not table_name:
            raise ValueError("Aggregation query must have 'table' field")
        
        table = self.db.table(table_name)
        
        # Get all documents
        docs = table.all()
        
        # Process pipeline stages
        for stage in pipeline:
            if '$group' in stage:
                # Group aggregation
                group_spec = stage['$group']
                group_by_field = group_spec.get('_id', '').replace('$', '')
                
                # Group documents
                grouped = {}
                for doc in docs:
                    group_key = doc.get(group_by_field, 'null')
                    if group_key not in grouped:
                        grouped[group_key] = []
                    grouped[group_key].append(doc)
                
                # Build result with aggregations
                result_docs = []
                for group_key, group_docs in grouped.items():
                    result_doc = {group_by_field: group_key}
                    
                    # Apply aggregation functions
                    for field_name, agg_spec in group_spec.items():
                        if field_name == '_id' or field_name == group_by_field:
                            continue
                        
                        if isinstance(agg_spec, dict):
                            if '$sum' in agg_spec:
                                if agg_spec['$sum'] == 1:
                                    # Count
                                    result_doc[field_name] = len(group_docs)
                                else:
                                    # Sum of field
                                    sum_field = agg_spec['$sum'].replace('$', '')
                                    result_doc[field_name] = sum(doc.get(sum_field, 0) for doc in group_docs)
                            
                            elif '$avg' in agg_spec:
                                avg_field = agg_spec['$avg'].replace('$', '')
                                values = [doc.get(avg_field, 0) for doc in group_docs if avg_field in doc]
                                result_doc[field_name] = sum(values) / len(values) if values else 0
                            
                            elif '$max' in agg_spec:
                                max_field = agg_spec['$max'].replace('$', '')
                                values = [doc.get(max_field, 0) for doc in group_docs if max_field in doc]
                                result_doc[field_name] = max(values) if values else None
                            
                            elif '$min' in agg_spec:
                                min_field = agg_spec['$min'].replace('$', '')
                                values = [doc.get(min_field, 0) for doc in group_docs if min_field in doc]
                                result_doc[field_name] = min(values) if values else None
                            
                            elif '$first' in agg_spec:
                                first_field = agg_spec['$first'].replace('$', '')
                                result_doc[field_name] = group_docs[0].get(first_field) if group_docs else None
                    
                    result_docs.append(result_doc)
                
                docs = result_docs
            
            elif '$sort' in stage:
                # Sort stage
                sort_spec = stage['$sort']
                for field_name, direction in sort_spec.items():
                    docs = sorted(docs, key=lambda x: x.get(field_name, ''), reverse=(direction == -1))
            
            elif '$project' in stage:
                # Project stage (select fields)
                project_spec = stage['$project']
                projected_docs = []
                for doc in docs:
                    projected_doc = {}
                    for field_name, include in project_spec.items():
                        if include and field_name in doc:
                            projected_doc[field_name] = doc[field_name]
                    projected_docs.append(projected_doc)
                docs = projected_docs
        
        return docs

    def _search_with_condition(self, table, condition):
        """Search table with JSON condition"""
        from tinydb import Query
        q = Query()
    
        # Simple equality
        if not any(isinstance(v, dict) for v in condition.values()):
            # All simple key-value pairs
            query_obj = None
            for key, value in condition.items():
                field_query = (q[key] == value)
                if query_obj is None:
                    query_obj = field_query
                else:
                    query_obj = query_obj & field_query
            return table.search(query_obj) if query_obj else table.all()
    
        # Complex operators like $gt, $lt, etc.
        query_obj = None
        for key, value in condition.items():
            if isinstance(value, dict):
                # Handle operators
                for op, val in value.items():
                    if op == '$gt':
                        field_query = (q[key] > val)
                    elif op == '$gte':
                        field_query = (q[key] >= val)
                    elif op == '$lt':
                        field_query = (q[key] < val)
                    elif op == '$lte':
                        field_query = (q[key] <= val)
                    elif op == '$eq':
                        field_query = (q[key] == val)
                    elif op == '$ne':
                        field_query = (q[key] != val)
                    else:
                        continue
                
                    if query_obj is None:
                        query_obj = field_query
                    else:
                        query_obj = query_obj & field_query
            else:
                # Simple equality
                field_query = (q[key] == value)
                if query_obj is None:
                    query_obj = field_query
                else:
                    query_obj = query_obj & field_query
    
        return table.search(query_obj) if query_obj else table.all()

    def _execute_sql_like_command(self, command):
        """
        Execute SQL-like commands with minimal validation
        Just extract table name and try to execute
        """
        command_upper = command.upper()

        # CREATE COLLECTION/TABLE
        if command_upper.startswith('CREATE COLLECTION') or command_upper.startswith('CREATE TABLE'):
            match = re.match(r'CREATE\s+(?:COLLECTION|TABLE)\s+([a-zA-Z][a-zA-Z0-9_]*)', command, re.I)
            if match:
                coll_name = match.group(1)
                self.create_collection(coll_name)
                return [{"status": f"✅ Collection '{coll_name}' created"}]

        # DROP COLLECTION/TABLE
        if command_upper.startswith('DROP COLLECTION') or command_upper.startswith('DROP TABLE'):
            match = re.match(r'DROP\s+(?:COLLECTION|TABLE)\s+([a-zA-Z][a-zA-Z0-9_]*)', command, re.I)
            if match:
                coll_name = match.group(1)
                self.delete_table(coll_name)
                return [{"status": f"✅ Collection '{coll_name}' dropped"}]

        # INSERT INTO collection VALUES (val1, val2, ...)
        # ✅ NEW: Handle SQL-style VALUES syntax
        if command_upper.startswith('INSERT INTO') and ' VALUES ' in command_upper:
            match = re.match(r'INSERT\s+INTO\s+([a-zA-Z][a-zA-Z0-9_]*)\s+VALUES\s*\((.+)\)', command, re.I | re.DOTALL)
            if match:
                table_name = match.group(1)
                values_str = match.group(2).strip()
            
                try:
                    # Parse comma-separated values
                    # Handle strings in quotes and numbers
                    values = []
                    current = ""
                    in_string = False
                    string_char = None
                
                    for char in values_str:
                        if char in ['"', "'"] and (not current or current[-1] != '\\'):
                            if not in_string:
                                in_string = True
                                string_char = char
                            elif char == string_char:
                                in_string = False
                                string_char = None
                                values.append(current)
                                current = ""
                                continue
                            else:
                                current += char
                        elif char == ',' and not in_string:
                            if current.strip():
                                # Try to parse as number
                                val = current.strip()
                                try:
                                    if '.' in val:
                                        values.append(float(val))
                                    else:
                                        values.append(int(val))
                                except:
                                    values.append(val)
                            current = ""
                        elif in_string:
                            current += char
                        elif char not in [' ', '\n', '\t'] or current:
                            current += char
                
                    # Don't forget last value
                    if current.strip():
                        val = current.strip()
                        try:
                            if '.' in val:
                                values.append(float(val))
                            else:
                                values.append(int(val))
                        except:
                            values.append(val)
                
                    # Get table schema to create document
                    table = self.db.table(table_name)
                
                    # Check if table has any documents to infer field names
                    existing_docs = table.all()
                    if existing_docs:
                        # Use field names from first document (excluding doc_id)
                        field_names = [k for k in existing_docs[0].keys() if k not in ['doc_id', '_id']]
                    else:
                        # No existing documents - create generic field names
                        field_names = [f"field_{i+1}" for i in range(len(values))]
                
                    # Create document
                    if len(values) != len(field_names):
                        # If counts don't match, use generic names
                        field_names = [f"field_{i+1}" for i in range(len(values))]

                    document = dict(zip(field_names, values))
                    doc_id = table.insert(document)
                
                    return [{"status": f"✅ Inserted 1 document with doc_id {doc_id}"}]
                
                except Exception as e:
                    raise ValueError(f"Failed to parse VALUES: {str(e)}")

        # INSERT INTO collection {json} or INSERT INTO collection JSON_OBJECT
        if command_upper.startswith('INSERT INTO'):
            match = re.match(r'INSERT\s+INTO\s+([a-zA-Z][a-zA-Z0-9_]*)\s+(.+)', command, re.I | re.DOTALL)
            if match:
                table_name = match.group(1)
                data_str = match.group(2).strip()
        
                try:
                    document = json.loads(data_str)
                    doc_id = self.db.table(table_name).insert(document)
                    return [{"status": f"✅ Inserted 1 document with doc_id {doc_id}"}]
                except json.JSONDecodeError as e:
                    raise ValueError(f"Invalid JSON: {e}")

        # INSERT MULTIPLE INTO collection [...]
        if command_upper.startswith('INSERT MULTIPLE'):
            match = re.match(r'INSERT\s+MULTIPLE\s+INTO\s+([a-zA-Z][a-zA-Z0-9_]*)\s+(.+)', command, re.I | re.DOTALL)
            if match:
                table_name = match.group(1)
                data_str = match.group(2).strip()
        
                try:
                    documents = json.loads(data_str)
                    doc_ids = self.db.table(table_name).insert_multiple(documents)
                    return [{"status": f"✅ Inserted {len(doc_ids)} documents"}]
                except json.JSONDecodeError as e:
                    raise ValueError(f"Invalid JSON: {e}")

        # SELECT * FROM table [WHERE ...]
        if command_upper.startswith('SELECT'):
            # Extract table name
            match = re.match(r'SELECT\s+.+?\s+FROM\s+([a-zA-Z][a-zA-Z0-9_]*)', command, re.I)
            if match:
                table_name = match.group(1)
                table = self.db.table(table_name)
        
                # Check for WHERE clause
                where_match = re.search(r'WHERE\s+(.+)', command, re.I | re.DOTALL)
                if where_match:
                    condition_str = where_match.group(1).strip()
                    result = self._parse_and_execute_where(table, condition_str)
                else:
                    result = table.all()
        
                return self._normalize_results(result)

        # UPDATE table SET ... WHERE ...
        if command_upper.startswith('UPDATE'):
            match = re.match(r'UPDATE\s+([a-zA-Z][a-zA-Z0-9_]*)\s+SET\s+(.+?)\s+WHERE\s+(.+)', command, re.I | re.DOTALL)
            if match:
                table_name = match.group(1)
                set_clause = match.group(2).strip()
                where_clause = match.group(3).strip()
        
                table = self.db.table(table_name)
        
                # Parse SET: field = value
                set_match = re.match(r'(\w+)\s*=\s*(.+)', set_clause)
                if set_match:
                    field = set_match.group(1)
                    value_str = set_match.group(2).strip()
                    value = json.loads(value_str) if value_str.startswith(('"', '[', '{')) else eval(value_str)
            
                    # Find matching docs
                    docs = self._parse_and_execute_where(table, where_clause)
                    count = len(docs)
            
                    # Update each
                    for doc in docs:
                        table.update({field: value}, doc_ids=[doc.doc_id])

                    return [{"status": f"✅ Updated {count} document(s)"}]

        # DELETE FROM table WHERE ...
        if command_upper.startswith('DELETE'):
            match = re.match(r'DELETE\s+FROM\s+([a-zA-Z][a-zA-Z0-9_]*)\s+WHERE\s+(.+)', command, re.I | re.DOTALL)
            if match:
                table_name = match.group(1)
                where_clause = match.group(2).strip()
        
                table = self.db.table(table_name)
                docs = self._parse_and_execute_where(table, where_clause)
                count = len(docs)
                doc_ids = [doc.doc_id for doc in docs]
                table.remove(doc_ids=doc_ids)
                return [{"status": f"✅ Deleted {count} document(s)"}]

        # TRUNCATE table
        if command_upper.startswith('TRUNCATE'):
            match = re.match(r'TRUNCATE\s+(?:TABLE\s+)?([a-zA-Z][a-zA-Z0-9_]*)', command, re.I)
            if match:
                table_name = match.group(1)
                self.db.table(table_name).truncate()
                return [{"status": f"✅ Truncated table '{table_name}'"}]

        raise ValueError(f"Unable to parse query: {command[:50]}...")

    def _parse_and_execute_where(self, table, condition_str):
        """Parse WHERE conditions like: age > 19 AND marks >= 90"""
        q = Query()
    
        # Split by AND
        conditions = re.split(r'\s+AND\s+', condition_str, flags=re.I)
    
        query_obj = None
        for cond in conditions:
            cond = cond.strip()
        
            # Check for CONTAINS operator
            if ' CONTAINS ' in cond.upper():
                match = re.match(r'(\w+(?:\.\w+)*)\s+CONTAINS\s+(.+)', cond, re.I)
                if match:
                    field = match.group(1)
                    value_str = match.group(2).strip().strip('"\'')
                    field_query = self._build_field_query(q, field).any([value_str])
            # Regular comparison operators
            else:
                # FIX: Use negative lookahead to prevent > and < matching when followed by =
                # Pattern explanation:
                # >=|<= matches these first
                # (?<!>)= matches = but NOT when preceded by >
                # (?<!<)= matches = but NOT when preceded by 
                # >(?!=) matches > but NOT when followed by =
                # <(?!=) matches < but NOT when followed by =
                match = re.match(r'(\w+(?:\.\w+)*)\s*(>=|<=|==|!=|>(?!=)|<(?!=)|=)\s*(.+)', cond)
                if match:
                    field = match.group(1)
                    op = match.group(2)
                    value_str = match.group(3).strip()
                
                    self.logger.debug(f"Parsed condition: field={field}, op={op}, value_str={value_str}")
                
                    # Parse value with proper type conversion
                    try:
                        value = json.loads(value_str)
                    except:
                        try:
                            if '.' not in value_str:
                                value = int(value_str)
                            else:
                                value = float(value_str)
                        except:
                            value = value_str.strip('"\'')
                
                    self.logger.debug(f"Converted value: {value} (type: {type(value).__name__})")
                
                    # Build query
                    field_query = self._build_field_query(q, field)
                
                    if op in ['==', '=']:
                        field_query = (field_query == value)
                    elif op == '!=':
                        field_query = (field_query != value)
                    elif op == '>=':
                        field_query = (field_query >= value)
                    elif op == '<=':
                        field_query = (field_query <= value)
                    elif op == '>':
                        field_query = (field_query > value)
                    elif op == '<':
                        field_query = (field_query < value)
                else:
                    raise ValueError(f"Invalid condition: {cond}")
        
            # Combine with AND
            if query_obj is None:
                query_obj = field_query
            else:
                query_obj = query_obj & field_query
    
        return table.search(query_obj)

    def _build_field_query(self, q, field):
        """Build nested field query for dotted notation like contact.email"""
        parts = field.split('.')
        query = q
        for part in parts:
            query = query[part]
        return query

    def _execute_native_tinydb(self, query):
        """
        Execute native TinyDB Python syntax directly
        Examples:
        - db.table('users').search(Query().age > 25)
        - db.table('users').all()
        - db.table('users').insert({'name': 'John', 'age': 30})
        """
        from tinydb import Query as Q
    
        # Create safe execution environment
        safe_env = {
            'db': self.db,
            'Query': Q,
            'Q': Q,
            '__builtins__': {},
        }
    
        try:
            # Execute the query directly
            result = eval(query, safe_env)
        
            # Handle different result types
            if isinstance(result, list):
                # search() or all() returns list
                return self._normalize_results(result)
            elif isinstance(result, int):
                # insert() returns doc_id
                return [{"status": "Document inserted", "doc_id": result}]
            elif isinstance(result, dict):
                # get() returns single document
                return [result]
            elif result is None:
                return [{"status": "Operation completed successfully"}]
            else:
                return [{"result": str(result)}]
            
        except Exception as e:
            self.logger.error(f"Native TinyDB query execution error: {str(e)}")
            raise Exception(f"Query execution failed: {str(e)}")

    def _normalize_results(self, docs):
        """Normalize TinyDB results to use doc_id consistently"""
        result = []
        for doc in docs:
            normalized = dict(doc)
            if 'doc_id' not in normalized and hasattr(doc, 'doc_id'):
                normalized['doc_id'] = doc.doc_id
            # Remove _id if it exists to avoid duplication
            normalized.pop('_id', None)
            result.append(normalized)
    
        return result

    def _execute_command_string(self, command):
        """
        Execute TinyDB command strings like:
        - USE database_name
        - SHOW DATABASES / SHOW COLLECTIONS
        - CREATE COLLECTION name
        - DROP COLLECTION name
        - FIND collection WHERE {...}
        - INSERT INTO collection VALUES {...}
        - UPDATE collection SET {...} WHERE {...}
        - DELETE FROM collection WHERE {...}
        - SELECT * FROM collection WHERE {...}
        """
        import re
        from tinydb import Query
    
        command = command.strip()
        command_upper = command.upper()
    
        # USE database
        if command_upper.startswith('USE '):
            match = re.match(r'USE\s+([a-zA-Z][a-zA-Z0-9_]*)', command, re.I)
            if match:
                db_name = match.group(1)
                self.switch_db(db_name)
                return [{"status": f"Switched to database '{db_name}'"}]
            raise ValueError("Invalid USE syntax. Usage: USE database_name")
    
        # SHOW DATABASES
        if command_upper == 'SHOW DATABASES':
            dbs = self.list_dbs()
            return [{"database": db} for db in dbs]
    
        # SHOW COLLECTIONS / SHOW TABLES
        if command_upper in ['SHOW COLLECTIONS', 'SHOW TABLES']:
            collections = self.list_tables()
            return [{"collection": coll} for coll in collections]
    
        # CREATE COLLECTION
        if command_upper.startswith('CREATE COLLECTION') or command_upper.startswith('CREATE TABLE'):
            match = re.match(r'CREATE\s+(?:COLLECTION|TABLE)\s+([a-zA-Z][a-zA-Z0-9_]*)', command, re.I)
            if match:
                coll_name = match.group(1)
                self.create_collection(coll_name)
                return [{"status": f"Collection '{coll_name}' created"}]
            raise ValueError("Invalid CREATE COLLECTION syntax")
    
        # DROP COLLECTION
        if command_upper.startswith('DROP COLLECTION') or command_upper.startswith('DROP TABLE'):
            match = re.match(r'DROP\s+(?:COLLECTION|TABLE)\s+([a-zA-Z][a-zA-Z0-9_]*)', command, re.I)
            if match:
                coll_name = match.group(1)
                self.delete_table(coll_name)
                return [{"status": f"Collection '{coll_name}' dropped"}]
            raise ValueError("Invalid DROP COLLECTION syntax")
    
        # FIND collection WHERE {...} or SELECT * FROM collection WHERE {...}
        if command_upper.startswith('FIND ') or command_upper.startswith('SELECT'):
            # Handle both formats
            if command_upper.startswith('FIND '):
                match = re.match(r'FIND\s+([a-zA-Z][a-zA-Z0-9_]*)\s*(?:WHERE\s+(.+))?', command, re.I | re.DOTALL)
            else:
                match = re.match(r'SELECT\s+\*\s+FROM\s+([a-zA-Z][a-zA-Z0-9_]*)\s*(?:WHERE\s+(.+))?', command, re.I | re.DOTALL)
        
            if match:
                collection_name = match.group(1)
                where_clause = match.group(2)
            
                table = self.db.table(collection_name)
            
                if where_clause:
                    try:
                        condition = json.loads(where_clause)
                        docs = self._search_with_condition(table, condition)
                    except json.JSONDecodeError:
                        # Try as Python expression
                        q = Query()
                        query_obj = eval(where_clause, {"Query": Query, "q": q, "__builtins__": {}})
                        docs = table.search(query_obj)
                else:
                    docs = table.all()
            
                return self._normalize_results(docs)
            raise ValueError("Invalid FIND/SELECT syntax")
    
        # INSERT INTO collection VALUES {...}
        if command_upper.startswith('INSERT INTO'):
            match = re.match(r'INSERT\s+INTO\s+([a-zA-Z][a-zA-Z0-9_]*)\s+VALUES\s+(.+)', command, re.I | re.DOTALL)
            if match:
                collection_name = match.group(1)
                values_str = match.group(2).strip()
            
                try:
                    document = json.loads(values_str)
                except json.JSONDecodeError:
                    document = eval(values_str, {"__builtins__": {}})
            
                doc_id = self.db.table(collection_name).insert(document)
                return [{"status": "Document inserted", "doc_id": doc_id}]
            raise ValueError("Invalid INSERT syntax")
    
        # UPDATE collection SET {...} WHERE {...}
        if command_upper.startswith('UPDATE '):
            match = re.match(r'UPDATE\s+([a-zA-Z][a-zA-Z0-9_]*)\s+SET\s+(.+?)\s+WHERE\s+(.+)', command, re.I | re.DOTALL)
            if match:
                collection_name = match.group(1)
                set_str = match.group(2).strip()
                where_str = match.group(3).strip()
            
                table = self.db.table(collection_name)
            
                try:
                    update_doc = json.loads(set_str)
                    condition = json.loads(where_str)
                except json.JSONDecodeError:
                    update_doc = eval(set_str, {"__builtins__": {}})
                    condition = eval(where_str, {"__builtins__": {}})
            
                # Build TinyDB query
                docs = self._search_with_condition(table, condition)
                count = len(docs)
            
                # Update each document
                for doc in docs:
                    table.update(update_doc, doc_ids=[doc.doc_id])
            
                return [{"status": f"Updated {count} documents"}]
            raise ValueError("Invalid UPDATE syntax")
    
        # DELETE FROM collection WHERE {...}
        if command_upper.startswith('DELETE FROM'):
            match = re.match(r'DELETE\s+FROM\s+([a-zA-Z][a-zA-Z0-9_]*)\s+WHERE\s+(.+)', command, re.I | re.DOTALL)
            if match:
                collection_name = match.group(1)
                where_str = match.group(2).strip()
            
                table = self.db.table(collection_name)
            
                try:
                    condition = json.loads(where_str)
                except json.JSONDecodeError:
                    condition = eval(where_str, {"__builtins__": {}})
            
                docs = self._search_with_condition(table, condition)
                count = len(docs)
            
                # Delete documents
                doc_ids = [doc.doc_id for doc in docs]
                table.remove(doc_ids=doc_ids)
            
                return [{"status": f"Deleted {count} documents"}]
            raise ValueError("Invalid DELETE syntax")
    
        raise ValueError(f"Unknown command: {command[:50]}...")

    def insert(self, table_name, data):
        if not self.db:
            self.logger.error("No database selected for insert operation")
            if self.current_db:
                self.switch_db(self.current_db)
            else:
                raise Exception("No database selected")
        doc_id = self.db.table(table_name).insert(data)
        self.logger.debug(f"Inserted document into {table_name}: {data}, doc_id: {doc_id}")
        return doc_id

    def update(self, table_name, doc_id, data):
        if not self.db:
            self.logger.error("No database selected for update operation")
            if self.current_db:
                self.switch_db(self.current_db)
            else:
                raise Exception("No database selected")

        table = self.db.table(table_name)
        doc = table.get(doc_id=doc_id)
        if not doc:
            self.logger.error(f"Document {doc_id} not found in {table_name} during update")
            raise ValueError(f"Document {doc_id} not found")

        new_doc = {}
        for key, value in doc.items():
            if key == 'doc_id':
                continue
            if key in data and data[key] is None:
                self.logger.debug(f"Marked key '{key}' for deletion from document {doc_id}")
                continue
            elif key in data:
                new_doc[key] = data[key]
                self.logger.debug(f"Updated key '{key}' in document {doc_id}")
            else:
                new_doc[key] = value

        for key, value in data.items():
            if value is not None and key not in doc:
                new_doc[key] = value
                self.logger.debug(f"Added new key '{key}' to document {doc_id}")

        try:
            db_path = self.db._storage._handle.name
            self.db.close()
            with open(db_path, 'r') as f:
                storage_data = json.load(f)
            if table_name not in storage_data:
                storage_data[table_name] = {}
            storage_data[table_name][str(doc_id)] = new_doc
            with open(db_path, 'w') as f:
                json.dump(storage_data, f, indent=4)
            self.db = TinyDB(db_path)
            self.logger.debug(f"Updated document {doc_id} in {table_name} with field deletion support")
        except Exception as e:
            self.logger.error(f"Storage update failed: {e}")
            self.logger.error(traceback.format_exc())
            raise

    def delete(self, table_name, doc_id):
        if not self.db:
            self.logger.error("No database selected for delete operation")
            if self.current_db:
                self.switch_db(self.current_db)
            else:
                raise Exception("No database selected")
        self.db.table(table_name).remove(doc_ids=[doc_id])
        self.logger.debug(f"Deleted document {doc_id} from {table_name}")

    def delete_table(self, table_name):
        if not self.db:
            self.logger.error("No database selected for delete_table operation")
            if self.current_db:
                self.switch_db(self.current_db)
            else:
                raise Exception("No database selected")
        self.db.drop_table(table_name)
        self.logger.debug(f"Dropped table {table_name}")

    def can_convert_column(self, table_name, column, new_type):
        return True

    def modify_table(self, old_table_name, new_table_name, new_columns):
        if not self.db:
            self.logger.error("No database selected for modify_table operation")
            if self.current_db:
                self.switch_db(self.current_db)
            else:
                raise Exception("No database selected")
        if old_table_name != new_table_name:
            data = self.db.table(old_table_name).all()
            self.db.drop_table(old_table_name)
            if data:
                self.db.table(new_table_name).insert_multiple(data)
            self.logger.debug(f"Renamed table {old_table_name} to {new_table_name}")

    def get_document(self, table_name, doc_id):
        if not self.db:
            self.logger.error("No database selected for get_document operation")
            if self.current_db:
                self.switch_db(self.current_db)
            else:
                return None
        doc = self.db.table(table_name).get(doc_id=int(doc_id))
        if doc and '_id' not in doc:
            doc['_id'] = doc.get('doc_id', doc_id)
        self.logger.debug(f"Retrieved document {doc_id} from {table_name}: {doc}")
        return doc

    def create_collection(self, collection_name):
        if not self.db:
            self.logger.error("No database selected for create_collection operation")
            if self.current_db:
                self.switch_db(self.current_db)
            else:
                raise Exception("No database selected")
    
        table = self.db.table(collection_name)
        marker_id = table.insert({'_dbdragoness_marker': True})
        table.remove(doc_ids=[marker_id])
        self.logger.debug(f"Created and persisted collection {collection_name}")

    def get_all_keys(self, collection_name):
        if not self.db:
            self.logger.error("No database selected for get_all_keys operation")
            if self.current_db:
                self.switch_db(self.current_db)
            else:
                return []
        documents = self.db.table(collection_name).all()
        keys = set()
        for doc in documents:
            keys.update([k for k in doc.keys() if k not in ['doc_id', '_id']])
        self.logger.debug(f"Retrieved keys from {collection_name}: {keys}")
        return sorted(list(keys))
    
    def get_primary_key_name(self):
        """Return the primary key field name for this NoSQL database"""
        return 'doc_id'
    
    def supports_joins(self):
        return False

    def supports_triggers(self):
        return False

    def supports_plsql(self):
        return False

    def execute_join(self, join_query):
        raise NotImplementedError("Joins not supported in this NoSQL database")

    def create_trigger(self, trigger_name, table_name, trigger_timing, trigger_event, trigger_body):
        raise NotImplementedError("Triggers not supported in NoSQL")

    def list_triggers(self, table_name=None):
        return []

    def get_trigger_details(self, trigger_name):
        return None

    def delete_trigger(self, trigger_name):
        raise NotImplementedError("Triggers not supported in NoSQL")
    
    def supports_aggregation(self):
        """Return True if database supports aggregation"""
        return False  # TinyDB doesn't support complex aggregation
    
    def supports_aggregation_pipeline(self):
        """Return True if database supports aggregation pipelines"""
        return False  # TinyDB doesn't support true pipelines
    
    def supports_procedures(self):
        """Override in child classes - return True if DB supports stored procedures"""
        return False
    
    def execute_procedure(self, procedure_code):
        """Execute stored procedure/function code - override in child classes"""
        raise NotImplementedError(f"{self.DB_NAME} does not support stored procedures")
    
    def list_procedures(self):
        """List all stored procedures/functions - override in child classes"""
        return []
    
    def get_procedure_definition(self, procedure_name):
        """Get the source code of a procedure - override in child classes"""
        return None
    
    def drop_procedure(self, procedure_name, is_function=False):
        """Drop a stored procedure/function - override in child classes"""
        raise NotImplementedError(f"{self.DB_NAME} does not support stored procedures")
    
    def get_procedure_placeholder_example(self):
        """Return database-specific example code for procedures tab"""
        return "This database does not support stored procedures."

    def execute_plsql(self, plsql_code):
        raise NotImplementedError("PL/SQL not supported in NoSQL")
    
    def get_credential_status(self):
        """TinyDB handler doesn't require credentials"""
        return {
            "needs_credentials": False,
            "handler": self.DB_NAME
        }

    def clear_credentials(self):
        """TinyDB handler doesn't store credentials"""
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
        """NoSQL databases don't use column definitions, but method required for interface compatibility"""
        return []
    
    def reset_sequence_after_copy(self, table_name, column_name):
        """NoSQL databases don't use sequences"""
        pass  # Not applicable for NoSQL
    
    def get_foreign_keys(self, table_name):
        """This database doesn't support foreign keys or method not implemented"""
        return []

    def create_foreign_key(self, table_name, constraint_name, column_name,
                        foreign_table, foreign_column, on_update, on_delete):
        """This database doesn't support foreign keys"""
        pass
    
    def get_views(self):
        """NoSQL databases don't support views"""
        return []

    def create_view(self, view_name, view_definition):
        """NoSQL databases don't support views"""
        pass

    def copy_triggers(self, source_table, dest_table):
        """NoSQL doesn't have triggers"""
        pass
    
    def copy_table(self, source_table, dest_table):
        """Copy table/collection including data and validation rules"""
        # Restore connection if closed
        if not self.db:
            if self.current_db:
                self.switch_db(self.current_db)
            else:
                raise Exception("No database selected")
        
        try:
            # Get source collection info including validation rules
            source_checks = []
            if hasattr(self, 'get_check_constraints'):
                try:
                    source_checks = self.get_check_constraints(source_table)
                except Exception as e:
                    self.logger.warning(f"Could not get validation rules: {e}")
            
            # Read all documents from source
            source_docs = self.read(source_table)
            
            # Create destination collection WITHOUT validation first
            self.create_collection(dest_table)
            
            # Get primary key name
            primary_key = self.get_primary_key_name()
            
            # Copy all documents
            if source_docs:
                for doc in source_docs:
                    # Remove primary key - it will be auto-generated
                    clean_doc = {k: v for k, v in doc.items() if k != primary_key}
                    self.insert(dest_table, clean_doc)
                
                self.logger.info(f"Copied {len(source_docs)} documents to {dest_table}")
            
            # Apply validation rules AFTER data is copied
            if source_checks and hasattr(self, 'apply_validation_rules'):
                try:
                    validation_rules = {}
                    for check in source_checks:
                        col_name = check.get('column')
                        if col_name:
                            validation_rules[col_name] = {'expression': check.get('expression')}
                    
                    if validation_rules:
                        try:
                            self.apply_validation_rules(dest_table, validation_rules)
                            self.logger.info(f"✅ Applied validation rules to {dest_table}")
                        except Exception as validation_err:
                            self.logger.warning(f"⚠️ Could not apply validation rules to {dest_table}: {validation_err}")
                except Exception as e:
                    self.logger.warning(f"Failed to copy validation rules: {e}")
            
            self.logger.info(f"✅ Successfully copied {source_table} to {dest_table}")
            
        except Exception as e:
            self.logger.error(f"Failed to copy table: {e}")
            # Clean up destination table if copy failed
            try:
                self.delete_table(dest_table)
            except:
                pass
            raise Exception(f"Failed to copy table: {str(e)}")
        
    def copy_database(self, source_db_name, dest_db_name):
        """Copy entire database including all collections and their data"""
        try:
            # Ensure we have source database connection
            self.switch_db(source_db_name)
            
            # Get all tables from source database
            source_tables = self.list_tables_for_db(source_db_name)
            
            # Filter out system tables/markers if any
            source_tables = [t for t in source_tables if not t.startswith('_')]
            
            self.logger.info(f"Copying {len(source_tables)} tables from {source_db_name} to {dest_db_name}")
            
            for table_name in source_tables:
                self.logger.info(f"Copying table: {table_name}")
                
                # Switch to source database and get validation rules
                self.switch_db(source_db_name)
                source_checks = []
                if hasattr(self, 'get_check_constraints'):
                    try:
                        source_checks = self.get_check_constraints(table_name)
                    except Exception as e:
                        self.logger.warning(f"Could not get validation rules: {e}")
                
                # Read all documents
                documents = self.read(table_name)
                
                # Switch to destination database
                self.switch_db(dest_db_name)
                
                # Create collection WITHOUT validation first
                self.create_collection(table_name)
                
                # Get primary key name
                primary_key = self.get_primary_key_name()
                
                # Copy all documents
                if documents:
                    for doc in documents:
                        clean_doc = {k: v for k, v in doc.items() if k != primary_key}
                        self.insert(table_name, clean_doc)
                    
                    self.logger.info(f"✅ Copied {len(documents)} documents to {dest_db_name}.{table_name}")
                
                # Apply validation rules AFTER data is copied
                if source_checks and hasattr(self, 'apply_validation_rules'):
                    try:
                        validation_rules = {}
                        for check in source_checks:
                            col_name = check.get('column')
                            if col_name:
                                validation_rules[col_name] = {'expression': check.get('expression')}
                        
                        if validation_rules:
                            try:
                                self.apply_validation_rules(table_name, validation_rules)
                                self.logger.info(f"✅ Applied validation rules to {dest_db_name}.{table_name}")
                            except Exception as validation_err:
                                self.logger.warning(f"⚠️ Could not apply validation rules to {table_name}: {validation_err}")
                    except Exception as e:
                        self.logger.warning(f"Failed to copy validation rules for {table_name}: {e}")
            
            self.logger.info(f"✅ Successfully copied database {source_db_name} to {dest_db_name}")
            
        except Exception as e:
            self.logger.error(f"Failed to copy database: {e}")
            raise Exception(f"Failed to copy database: {str(e)}")
    
    def get_table_connection_info(self, db_name, table_name):
        """Return table-specific connection information"""
        base_conn = self.get_connection_info(db_name)
        
        test_code = f'''from tinydb import TinyDB
import os

db_path = os.path.abspath('nosql_dbs/tinydb/{db_name}.json')
db = TinyDB(db_path)

table = db.table('{table_name}')
docs = table.all()
print(f"Documents in '{table_name}': {{len(docs)}}")
if docs:
    print(f"Sample: {{docs[0]}}")'''
        
        return {
            'connection_string': base_conn['connection_string'],
            'test_code': test_code,
            'notes': base_conn.get('notes', [])
        }
        
    def supports_check_constraints(self):
        """Return True if database supports CHECK constraints"""
        return False

    def get_check_constraints(self, table_name):
        """Get CHECK constraints for a table"""
        return []

    def validate_check_constraint(self, constraint_expression):
        """Validate a CHECK constraint expression"""
        return True