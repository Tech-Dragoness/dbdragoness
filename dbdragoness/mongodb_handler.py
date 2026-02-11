# mongodb_handler.py
import json
import re
from pymongo import MongoClient
from bson import ObjectId
import logging
from .db_handler import DBHandler

class MongoDBHandler(DBHandler):
    
    DB_TYPE = 'nosql'
    DB_NAME = 'MongoDB'
    
    def __init__(self):
        self.current_db = None
        self.db = None
        self.client = MongoClient('mongodb://localhost:27017/')
        self.logger = logging.getLogger(__name__)
        
    def get_connection_info(self, db_name):
        """Return MongoDB connection information"""
        return {
            'connection_string': f'mongodb://localhost:27017/{db_name}',
            'test_code': f'''from pymongo import MongoClient
from pymongo.errors import ServerSelectionTimeoutError

try:
    # Connect with a timeout to check if MongoDB is running
    client = MongoClient('mongodb://localhost:27017/', serverSelectionTimeoutMS=2000)

    # Test connection
    client.admin.command('ping')
    print("✅ Connected to MongoDB")

    db = client['{db_name}']
    collections = db.list_collection_names()
    print(f"Collections: {{collections}}")

    if collections:
        # Show first collection's document count
        first_coll = collections[0]
        count = db[first_coll].count_documents({{}})
        print(f"Documents in '{{first_coll}}': {{count}}")
    
except ServerSelectionTimeoutError:
    print("❌ Could not connect to MongoDB.")
    print("Make sure MongoDB is running on localhost:27017")''',
        'notes': [
            'Ensure MongoDB server is running (mongod or MongoDB service)',
            'Default MongoDB port is 27017'
        ]
        }

    def create_db(self, db_name):
        if db_name in self.list_dbs():
            raise ValueError(f"Database '{db_name}' already exists.")
        
        # Switch to the database
        self.db = self.client[db_name]
        self.current_db = db_name
        
        # CRITICAL: Create a persistent marker collection to ensure DB exists
        # This prevents the DB from disappearing when empty
        self.db.create_collection("_dbdragoness_system")
        self.db["_dbdragoness_system"].insert_one({"_marker": True, "_info": "This collection ensures the database persists even when empty"})
        
    def delete_db(self, db_name):
        if self.current_db == db_name:
            self.db = None
            self.current_db = None
        self.client.drop_database(db_name)

    def switch_db(self, db_name):
        # MongoDB creates DB on first write, so don't check if it exists
        self.db = self.client[db_name]
        self.current_db = db_name

    def list_dbs(self):
        return [name for name in self.client.list_database_names() 
                if name not in ['admin', 'local', 'config']]

    def list_tables(self):
        if self.db is None:
            return []
        # Filter out both system collections (starting with _) AND our marker collection
        return [coll for coll in self.db.list_collection_names() 
                if not coll.startswith('_')]
    
    def list_tables_for_db(self, db_name):
        """List collections in a MongoDB database without switching context."""
        temp_db = self.client[db_name]
        collections = temp_db.list_collection_names()
        return [coll for coll in collections if not coll.startswith('_')]

    def get_supported_types(self):
        return []
    
    def supports_non_pk_autoincrement(self):
        """Return True if database supports autoincrement on non-PK columns"""
        return False  

    def get_table_schema(self, table_name):
        return []
    
    def count_documents(self, table_name):
        """Fast count using MongoDB's count_documents"""
        if self.db is None:
            return 0
        try:
            count = self.db[table_name].count_documents({})
            return count
        except Exception as e:
            self.logger.error(f"Count error for {table_name}: {str(e)}")
            return 0

    def read(self, table_name):
        if self.db is None:
            return []

        cursor = self.db[table_name].find()

        docs = []
        batch_count = 0

        for i, doc in enumerate(cursor):
            if i % 50 == 0:
                batch_count += 1
    
            # Convert ObjectId to string
            doc['_id'] = str(doc['_id'])
            
            # CRITICAL FIX: Convert datetime objects to ISO string for frontend
            from datetime import datetime
            for key, value in list(doc.items()):
                if isinstance(value, datetime):
                    # Convert to ISO format string (YYYY-MM-DD)
                    doc[key] = value.strftime('%Y-%m-%d')
            
            docs.append(doc)

        return docs
    
    def close_db(self):
        """Close database connection"""
        pass
    
    def _handle_create_collection(self, command):
        """Handle db.createCollection with options"""
        try:
            import re
            match = re.match(r'db\.createCollection\s*\(\s*["\'](\w+)["\']\s*(?:,\s*(.+))?\s*\)', command, re.DOTALL)
        
            if not match:
                raise ValueError("Invalid createCollection syntax")
        
            coll_name = match.group(1)
            options_str = match.group(2)
        
            if options_str:
                options_str = options_str.strip()
                options_str = self._convert_mongodb_to_python(options_str)
                options = eval(options_str, {"__builtins__": {}, "ObjectId": ObjectId})
                self.db.create_collection(coll_name, **options)
            else:
                self.db.create_collection(coll_name)
        
            return [{"status": f"Collection '{coll_name}' created"}]
        
        except Exception as e:
            raise ValueError(f"Failed to create collection: {str(e)}")

    def execute_query(self, query):
        """
        Execute MongoDB query - accepts ANY format without validation
        """
        if self.db is None and not any(cmd in query.upper() for cmd in ['SHOW DATABASES', 'USE ', 'CREATE DATABASE']):
            raise Exception("No database selected")

        # Dict → pymongo query
        if isinstance(query, dict):
            return self._execute_dict_query(query)

        # String → try everything
        if isinstance(query, str):
            query = query.strip()
            query_upper = query.upper()
        
            # ===== DATABASE-LEVEL COMMANDS =====
        
            # USE database
            if query_upper.startswith('USE '):
                match = re.match(r'USE\s+([a-zA-Z][a-zA-Z0-9_]*)', query, re.I)
                if match:
                    self.switch_db(match.group(1))
                    return [{"status": f"Switched to database '{match.group(1)}'"}]
        
            # SHOW DATABASES
            if query_upper == 'SHOW DATABASES':
                return [{"database": db} for db in self.list_dbs()]
        
            # SHOW COLLECTIONS / SHOW TABLES
            if query_upper in ['SHOW COLLECTIONS', 'SHOW TABLES']:
                return [{"collection": c} for c in self.list_tables()]
        
            # CREATE DATABASE
            if query_upper.startswith('CREATE DATABASE'):
                match = re.match(r'CREATE\s+DATABASE\s+([a-zA-Z][a-zA-Z0-9_]*)', query, re.I)
                if match:
                    db_name = match.group(1)
                    self.create_db(db_name)
                    return [{"status": f"Database '{db_name}' created"}]
        
            # DROP DATABASE
            if query_upper.startswith('DROP DATABASE'):
                match = re.match(r'DROP\s+DATABASE\s+([a-zA-Z][a-zA-Z0-9_]*)', query, re.I)
                if match:
                    db_name = match.group(1)
                    self.delete_db(db_name)
                    return [{"status": f"Database '{db_name}' dropped"}]
        
            # CREATE COLLECTION
            if query_upper.startswith('CREATE COLLECTION') or query_upper.startswith('CREATE TABLE'):
                match = re.match(r'CREATE\s+(?:COLLECTION|TABLE)\s+([a-zA-Z][a-zA-Z0-9_]*)', query, re.I)
                if match:
                    self.create_collection(match.group(1))
                    return [{"status": f"Collection '{match.group(1)}' created"}]
        
            # DROP COLLECTION
            if query_upper.startswith('DROP COLLECTION') or query_upper.startswith('DROP TABLE'):
                match = re.match(r'DROP\s+(?:COLLECTION|TABLE)\s+([a-zA-Z][a-zA-Z0-9_]*)', query, re.I)
                if match:
                    self.delete_table(match.group(1))
                    return [{"status": f"Collection '{match.group(1)}' dropped"}]
        
            # ===== MONGODB SHELL COMMANDS =====
        
            # db.dropDatabase()
            if query.strip() == 'db.dropDatabase()':
                if not self.current_db:
                    raise Exception("No database selected")
                db_name = self.current_db
                self.delete_db(db_name)
                self.current_db = None
                self.db = None
                return [{"status": f"Database '{db_name}' dropped"}]
        
            # db (show current database)
            if query.strip() == 'db':
                if self.current_db:
                    return [{"current_database": self.current_db}]
                else:
                    return [{"status": "No database selected"}]
        
            # show dbs
            if query_upper == 'SHOW DBS':
                return [{"database": db} for db in self.list_dbs()]
        
            # db.collection.renameCollection("newName")
            if '.renameCollection(' in query:
                match = re.match(r'db\.(\w+)\.renameCollection\s*\(\s*["\'](\w+)["\']\s*\)', query)
                if match:
                    old_name = match.group(1)
                    new_name = match.group(2)
                    self.db[old_name].rename(new_name)
                    return [{"status": f"Collection '{old_name}' renamed to '{new_name}'"}]
        
            # db.createCollection with options
            if 'db.createCollection' in query:
                return self._handle_create_collection(query)
        
            # ===== TRY ALL FORMATS =====
        
            # MongoDB shell syntax (db.collection.method())
            if query.startswith('db.'):
                try:
                    return self._execute_mongodb_shell(query)
                except Exception as e:
                    pass  # Continue to next format
        
            # Try JSON
            try:
                query_dict = json.loads(query)
                return self._execute_dict_query(query_dict)
            except json.JSONDecodeError:
                pass
        
            # Try as command string (INSERT INTO, SELECT, etc.)
            try:
                return self._execute_command_string(query)
            except:
                pass
        
            # If all else fails
            raise ValueError(f"Could not parse query: {query[:100]}...")
    
        raise ValueError("Query must be a dict or string")

    def _execute_command_string(self, command):
        """
        Execute MongoDB command strings like:
        - USE database_name
        - SHOW DATABASES / SHOW COLLECTIONS
        - CREATE COLLECTION name
        - DROP COLLECTION name
        - INSERT INTO collection {...}
        - FIND collection WHERE {...}
        - UPDATE collection SET {...} WHERE {...}
        - DELETE FROM collection WHERE {...}
        """
        import re
    
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
    
        # FIND collection WHERE {...}
        if command_upper.startswith('FIND '):
            match = re.match(r'FIND\s+([a-zA-Z][a-zA-Z0-9_]*)\s*(?:WHERE\s+(.+))?', command, re.I | re.DOTALL)
            if match:
                collection_name = match.group(1)
                where_clause = match.group(2)
            
                if where_clause:
                    try:
                        condition = json.loads(where_clause)
                    except json.JSONDecodeError:
                        condition = eval(where_clause, {"__builtins__": {}})
                else:
                    condition = {}
            
                docs = list(self.db[collection_name].find(condition))
                return self._normalize_results(docs)
            raise ValueError("Invalid FIND syntax. Usage: FIND collection [WHERE {condition}]")
    
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
            
                result = self.db[collection_name].insert_one(document)
                return [{"status": "Document inserted", "inserted_id": str(result.inserted_id)}]
            raise ValueError("Invalid INSERT syntax. Usage: INSERT INTO collection VALUES {document}")
    
        # UPDATE collection SET {...} WHERE {...}
        if command_upper.startswith('UPDATE '):
            match = re.match(r'UPDATE\s+([a-zA-Z][a-zA-Z0-9_]*)\s+SET\s+(.+?)\s+WHERE\s+(.+)', command, re.I | re.DOTALL)
            if match:
                collection_name = match.group(1)
                set_str = match.group(2).strip()
                where_str = match.group(3).strip()
            
                try:
                    update_doc = json.loads(set_str)
                    condition = json.loads(where_str)
                except json.JSONDecodeError:
                    update_doc = eval(set_str, {"__builtins__": {}})
                    condition = eval(where_str, {"__builtins__": {}})
            
                result = self.db[collection_name].update_many(condition, {"$set": update_doc})
                return [{"status": f"Updated {result.modified_count} documents"}]
            raise ValueError("Invalid UPDATE syntax. Usage: UPDATE collection SET {updates} WHERE {condition}")
    
        # DELETE FROM collection WHERE {...}
        if command_upper.startswith('DELETE FROM'):
            match = re.match(r'DELETE\s+FROM\s+([a-zA-Z][a-zA-Z0-9_]*)\s+WHERE\s+(.+)', command, re.I | re.DOTALL)
            if match:
                collection_name = match.group(1)
                where_str = match.group(2).strip()
            
                try:
                    condition = json.loads(where_str)
                except json.JSONDecodeError:
                    condition = eval(where_str, {"__builtins__": {}})
            
                result = self.db[collection_name].delete_many(condition)
                return [{"status": f"Deleted {result.deleted_count} documents"}]
            raise ValueError("Invalid DELETE syntax. Usage: DELETE FROM collection WHERE {condition}")
    
        raise ValueError(f"Unknown command: {command[:50]}...")

    def _execute_dict_query(self, query_dict):
        """Execute dict-based MongoDB queries"""
        # Check for special operations
        if 'pipeline' in query_dict:
            # Aggregation pipeline
            collection = query_dict.get('collection')
            if not collection:
                raise ValueError("Aggregation requires 'collection' field")
        
            result = list(self.db[collection].aggregate(query_dict['pipeline']))
            return self._normalize_results(result)
    
        if 'count' in query_dict:
            # Count operation
            collection = query_dict.get('collection')
            condition = query_dict.get('condition', {})
            if not collection:
                raise ValueError("Count requires 'collection' field")
        
            count = self.db[collection].count_documents(condition)
            return [{'count': count}]
    
        if 'distinct' in query_dict:
            # Distinct operation
            collection = query_dict.get('collection')
            field = query_dict['distinct']
            condition = query_dict.get('condition', {})
            if not collection:
                raise ValueError("Distinct requires 'collection' field")
        
            values = self.db[collection].distinct(field, condition)
            return [{'field': field, 'values': values}]
    
        # Legacy format: {"table": "name", "condition": {...}}
        if 'table' in query_dict:
            collection = query_dict['table']
            condition = query_dict.get('condition', {})
            docs = list(self.db[collection].find(condition))
            return self._normalize_results(docs)
    
        # Otherwise, treat as find() condition across all collections
        all_results = []
        collections = self.list_tables()
    
        for coll_name in collections:
            try:
                docs = list(self.db[coll_name].find(query_dict))
                if docs:
                    for doc in docs:
                        doc['_collection'] = coll_name
                    all_results.extend(docs)
            except Exception as e:
                continue
    
        return self._normalize_results(all_results)
    
    def _execute_mongodb_shell(self, command):
        """
        Execute MongoDB shell commands with improved argument parsing
        Handles: db.collection.method(arg1, arg2, ...)
        """
        import re
        import json

        # Pattern: db.collection.method(args)
        match = re.match(r'db\.(\w+)\.(\w+)\((.*)\)', command, re.DOTALL)

        if not match:
            raise ValueError(f"Invalid MongoDB syntax. Use: db.collection.method(...)")

        collection_name = match.group(1)
        method_name = match.group(2)
        args_str = match.group(3).strip()

        # ✅ Special handling for createCollection
        if method_name == 'createCollection':
            try:
                # Parse arguments properly
                args = self._split_mongodb_args(args_str)
            
                if len(args) == 0:
                    raise ValueError("createCollection requires a collection name")
            
                # First arg is collection name
                coll_name = args[0].strip().strip('"\'')
            
                # Second arg (if exists) is options
                options = {}
                if len(args) > 1:
                    options_str = args[1].strip()
                    options = self._convert_mongodb_to_python(options_str)
                    options = eval(options, {"__builtins__": {}})
            
                # Create collection with options
                if options:
                    self.db.create_collection(coll_name, **options)
                else:
                    self.db.create_collection(coll_name)
            
                return [{"status": f"Collection '{coll_name}' created successfully"}]
            
            except Exception as e:
                raise ValueError(f"Failed to create collection: {str(e)}")

        # Map MongoDB shell methods to pymongo methods
        method_mapping = {
            'insertOne': 'insert_one',
            'insertMany': 'insert_many',
            'findOne': 'find_one',
            'find': 'find',
            'updateOne': 'update_one',
            'updateMany': 'update_many',
            'deleteOne': 'delete_one',
            'deleteMany': 'delete_many',
            'countDocuments': 'count_documents',
            'aggregate': 'aggregate',
            'createIndex': 'create_index',
            'distinct': 'distinct',
            'replaceOne': 'replace_one',
        }
        
        # Special handling for aggregate - it needs array parsing
        if method_name == 'aggregate' and args_str:
            try:
                # The argument should be an array (pipeline)
                pipeline_str = args_str.strip()
                
                self.logger.debug(f"Original aggregate pipeline: {pipeline_str[:200]}...")
                
                # Convert MongoDB syntax to Python
                converted = self._convert_mongodb_to_python(pipeline_str)
                
                self.logger.debug(f"Converted pipeline: {converted[:200]}...")
                
                # Parse the pipeline
                safe_env = {
                    '__builtins__': {},
                    'true': True, 'false': False,
                    'True': True, 'False': False,
                    'None': None, 'null': None,
                    'ObjectId': ObjectId
                }
                
                try:
                    pipeline = eval(converted, safe_env)
                except SyntaxError as syntax_err:
                    self.logger.error(f"Syntax error in converted pipeline: {syntax_err}")
                    self.logger.error(f"Converted string was: {converted}")
                    raise ValueError(f"Could not parse pipeline syntax: {str(syntax_err)}")
                
                if not isinstance(pipeline, list):
                    raise ValueError(f"Pipeline must be an array, got {type(pipeline)}")
                
                self.logger.debug(f"Parsed pipeline: {pipeline}")
                
                # Execute aggregate directly
                collection = self.db[collection_name]
                result = list(collection.aggregate(pipeline))
                
                self.logger.debug(f"Aggregate returned {len(result)} documents")
                
                return self._normalize_results(result)
                
            except ValueError as ve:
                raise ve
            except Exception as e:
                self.logger.error(f"Failed to execute aggregate pipeline: {e}")
                import traceback
                self.logger.error(traceback.format_exc())
                raise ValueError(f"Aggregate execution failed: {str(e)}")
    
        # Convert method name to snake_case
        pymongo_method = method_mapping.get(method_name, method_name)
    
        # Get the collection
        collection = self.db[collection_name]
    
        # Parse arguments with IMPROVED handling
        args = []
        if args_str:
            try:
                # Split arguments by top-level commas
                raw_args = self._split_mongodb_args(args_str)
            
                # Convert each argument from MongoDB syntax to Python
                for arg in raw_args:
                    arg = arg.strip()
                    if not arg:
                        continue
                
                    # Convert MongoDB syntax to valid JSON/Python
                    converted_arg = self._convert_mongodb_to_python(arg)
                
                    # Parse the converted argument
                    safe_env = {
                        '__builtins__': {},
                        'true': True, 'false': False,
                        'True': True, 'False': False,
                        'None': None, 'null': None,
                        'ObjectId': ObjectId
                    }
                
                    try:
                        parsed_arg = eval(converted_arg, safe_env)
                        args.append(parsed_arg)
                    except Exception as e:
                        self.logger.error(f"Failed to parse argument '{arg}': {e}")
                        raise ValueError(f"Could not parse argument: {arg}")
                    
            except Exception as e:
                raise ValueError(f"Could not parse arguments: {str(e)}")
    
        # Execute method
        try:
            method = getattr(collection, pymongo_method)
            result = method(*args) if args else method()
            return self._format_mongodb_result(pymongo_method, result)
        except AttributeError:
            raise ValueError(f"Unknown MongoDB method: {method_name} (tried {pymongo_method})")
        except TypeError as e:
            raise ValueError(f"Execution failed - incorrect number/type of arguments: {str(e)}")
        except Exception as e:
            raise ValueError(f"Execution failed: {str(e)}")
        
    def _split_mongodb_args(self, args_str):
        """
        Split MongoDB arguments by commas, respecting nested braces/brackets/quotes
        Example: '{ name: "John" }, { $set: { age: 30 } }' -> ['{ name: "John" }', '{ $set: { age: 30 } }']
        """
        args = []
        current = ""
        depth = 0
        in_string = False
        string_char = None

        i = 0
        while i < len(args_str):
            char = args_str[i]
        
            # Handle string delimiters
            if char in ['"', "'"] and (i == 0 or args_str[i-1] != '\\'):
                if not in_string:
                    in_string = True
                    string_char = char
                elif char == string_char:
                    in_string = False
                    string_char = None
                current += char
                i += 1
                continue
        
            # If inside string, just append
            if in_string:
                current += char
                i += 1
                continue
        
            # Track depth for braces/brackets/parentheses
            if char in '{[(':
                depth += 1
                current += char
            elif char in '}])':
                depth -= 1
                current += char
            elif char == ',' and depth == 0:
                # Top-level comma - split here
                if current.strip():
                    args.append(current.strip())
                current = ""
            else:
                current += char
        
            i += 1

        # Add final argument
        if current.strip():
            args.append(current.strip())

        return args

    def _convert_mongodb_to_python(self, mongo_str):
        """
        Convert MongoDB shell syntax to valid Python/JSON
        Handles: unquoted keys, MongoDB operators ($set, $lt, $lookup, etc.), ObjectId
        """
        import re

        # Handle ObjectId specially
        mongo_str = re.sub(
            r'ObjectId\s*\(\s*["\']([^"\']+)["\']\s*\)', 
            r'ObjectId("\1")', 
            mongo_str
        )

        result = []
        i = 0
        in_string = False
        string_char = None

        while i < len(mongo_str):
            char = mongo_str[i]
        
            # Track string state
            if char in ['"', "'"] and (i == 0 or mongo_str[i-1] != '\\'):
                if not in_string:
                    in_string = True
                    string_char = char
                elif char == string_char:
                    in_string = False
                    string_char = None
                result.append(char)
                i += 1
                continue
        
            # If inside string, just append
            if in_string:
                result.append(char)
                i += 1
                continue
        
            # Outside strings - look for unquoted keys
            if char.isalpha() or char == '$' or char == '_':
                # Found start of potential key/value
                key_start = i
                key = ''
            
                # Collect the full identifier (including $ for operators)
                while i < len(mongo_str) and (mongo_str[i].isalnum() or mongo_str[i] in ['_', '$']):
                    key += mongo_str[i]
                    i += 1
            
                # Skip var(--primaryText)space after key
                while i < len(mongo_str) and mongo_str[i].isspace():
                    i += 1
            
                # Check if followed by colon (it's a key)
                if i < len(mongo_str) and mongo_str[i] == ':':
                    # Quote all keys (including $ operators like $group, $lookup, $avg, etc.)
                    result.append(f'"{key}"')
                else:
                    # Not a key, it's a value
                    if key == 'true':
                        result.append('True')
                    elif key == 'false':
                        result.append('False')
                    elif key == 'null':
                        result.append('None')
                    elif key.startswith('$'):
                        # $ operators as values (like "$department") need quotes
                        result.append(f'"{key}"')
                    else:
                        result.append(key)
            else:
                result.append(char)
                i += 1

        return ''.join(result)

    def _split_top_level_args(self, args_str):
        """Split arguments by comma, respecting nested braces/brackets"""
        args = []
        current = ""
        depth = 0
    
        for char in args_str:
            if char in '{[':
                depth += 1
                current += char
            elif char in '}]':
                depth -= 1
                current += char
            elif char == ',' and depth == 0:
                args.append(current.strip())
                current = ""
            else:
                current += char
    
        if current.strip():
            args.append(current.strip())
    
        return args

    def _format_mongodb_result(self, method_name, result):
        """Format MongoDB operation results"""
        # Insert operations
        if method_name in ['insertOne', 'insert_one']:
            return [{"status": "Document inserted", "inserted_id": str(result.inserted_id)}]

        if method_name in ['insertMany', 'insert_many']:
            return [{"status": f"Inserted {len(result.inserted_ids)} documents", 
                     "inserted_ids": [str(id) for id in result.inserted_ids]}]

        # Update operations
        if method_name in ['updateOne', 'update_one']:
            return [{"status": f"Matched: {result.matched_count}, Modified: {result.modified_count}"}]

        if method_name in ['updateMany', 'update_many']:
            return [{"status": f"Matched: {result.matched_count}, Modified: {result.modified_count}"}]

        # Replace operations
        if method_name in ['replaceOne', 'replace_one']:
            return [{"status": f"Matched: {result.matched_count}, Modified: {result.modified_count}"}]

        # Delete operations
        if method_name in ['deleteOne', 'delete_one']:
            return [{"status": f"Deleted {result.deleted_count} document(s)"}]

        if method_name in ['deleteMany', 'delete_many']:
            return [{"status": f"Deleted {result.deleted_count} document(s)"}]

        # Find operations (cursor)
        if method_name in ['find']:
            docs = list(result)
            return self._normalize_results(docs)

        # Find one
        if method_name in ['findOne', 'find_one']:
            if result:
                result['_id'] = str(result['_id'])
                return [result]
            return [{"status": "No document found"}]

        # Count
        if method_name in ['countDocuments', 'count_documents']:
            return [{"count": result}]

        # Index creation
        if method_name in ['createIndex', 'create_index']:
            return [{"status": f"Index created: {result}"}]

        # Aggregation
        if method_name == 'aggregate':
            docs = list(result)
            return self._normalize_results(docs)

        # Distinct
        if method_name == 'distinct':
            return [{"values": result}]

        # Default - try to return as-is
        if hasattr(result, '__iter__') and not isinstance(result, (str, dict)):
            try:
                docs = list(result)
                return self._normalize_results(docs)
            except:
                pass

        return [{"result": str(result)}]

    def _normalize_results(self, docs):
        """Normalize MongoDB results to use _id consistently"""
        result = []
        for doc in docs:
            normalized = self._convert_objectids_to_strings(dict(doc))
            result.append(normalized)

        return result

    def _convert_objectids_to_strings(self, obj):
        """Recursively convert all ObjectId instances to strings"""
        if isinstance(obj, ObjectId):
            return str(obj)
        elif isinstance(obj, dict):
            return {key: self._convert_objectids_to_strings(value) for key, value in obj.items()}
        elif isinstance(obj, list):
            return [self._convert_objectids_to_strings(item) for item in obj]
        else:
            return obj
    
    def _convert_to_objectid(self, doc_id):
        """Convert string or int to ObjectId"""
        try:
            # If it's already an ObjectId, return it
            if isinstance(doc_id, ObjectId):
                return doc_id
            # Try to convert string to ObjectId
            return ObjectId(doc_id)
        except:
            # If conversion fails, it's probably an integer ID
            # Try to convert to int if it's a string number
            try:
                return int(doc_id)
            except:
                # Return as-is if all else fails
                return doc_id
            
    def _convert_data_types(self, table_name, data):
        """
        Convert string inputs to proper types based on collection's validation schema
        Handles: arrays, objects, dates, booleans that come in as strings
        """
        if self.db is None:
            return data
        
        try:
            # Get collection validation schema
            coll_info = self.db.command("listCollections", filter={"name": table_name})
            
            if not coll_info.get('cursor', {}).get('firstBatch'):
                return data  # No validation, return as-is
            
            coll_data = coll_info['cursor']['firstBatch'][0]
            validator = coll_data.get('options', {}).get('validator', {})
            
            if not validator:
                return data  # No validation, return as-is
            
            # Extract field types from JSON Schema
            json_schema = validator.get('$jsonSchema', {})
            properties = json_schema.get('properties', {})
            required_fields = json_schema.get('required', [])
            
            converted_data = {}
            
            for key, value in data.items():
                if key not in properties:
                    # Field not in schema - keep as-is
                    converted_data[key] = value
                    continue
                
                field_schema = properties[key]
                expected_type = field_schema.get('bsonType')
                
                # Skip if no type specified or value is already None
                if not expected_type or value is None:
                    converted_data[key] = value
                    continue
                
                # ARRAY validation - STRICT
                if expected_type == 'array' or (isinstance(expected_type, list) and 'array' in expected_type):
                    if isinstance(value, list):
                        converted_data[key] = value
                        continue
                    elif isinstance(value, str):
                        stripped = value.strip()
                        # CRITICAL: Must be valid JSON array
                        if not stripped:
                            if key in required_fields:
                                raise ValueError(f"Field '{key}' is required and must be an array")
                            converted_data[key] = []
                            continue
                        
                        if not (stripped.startswith('[') and stripped.endswith(']')):
                            raise ValueError(f"Field '{key}' must be a JSON array like [\"item1\", \"item2\"]. Got: {stripped[:50]}")
                        
                        import json
                        try:
                            parsed = json.loads(stripped)
                            if not isinstance(parsed, list):
                                raise ValueError(f"Field '{key}' must be an array, got {type(parsed).__name__}")
                            converted_data[key] = parsed
                        except json.JSONDecodeError as e:
                            raise ValueError(f"Field '{key}' has invalid JSON syntax: {str(e)}")
                        continue
                    else:
                        raise ValueError(f"Field '{key}' must be an array")
                
                # OBJECT validation - STRICT
                if expected_type == 'object' or (isinstance(expected_type, list) and 'object' in expected_type):
                    if isinstance(value, dict):
                        converted_data[key] = value
                        continue
                    elif isinstance(value, str):
                        stripped = value.strip()
                        # CRITICAL: Must be valid JSON object
                        if not stripped:
                            if key in required_fields:
                                raise ValueError(f"Field '{key}' is required and must be an object")
                            converted_data[key] = {}
                            continue
                        
                        if not (stripped.startswith('{') and stripped.endswith('}')):
                            raise ValueError(f"Field '{key}' must be a JSON object like {{\"key\": \"value\"}}. Got: {stripped[:50]}")
                        
                        import json
                        try:
                            parsed = json.loads(stripped)
                            if not isinstance(parsed, dict):
                                raise ValueError(f"Field '{key}' must be an object, got {type(parsed).__name__}")
                            converted_data[key] = parsed
                        except json.JSONDecodeError as e:
                            raise ValueError(f"Field '{key}' has invalid JSON syntax: {str(e)}")
                        continue
                    else:
                        raise ValueError(f"Field '{key}' must be an object")
                
                # Handle other types (dates, booleans, numbers, strings)
                if isinstance(value, str) and value.strip():
                    try:
                        # DATE type
                        if expected_type == 'date' or (isinstance(expected_type, list) and 'date' in expected_type):
                            from datetime import datetime
                            for fmt in ['%Y-%m-%d', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S']:
                                try:
                                    converted_data[key] = datetime.strptime(value.strip(), fmt)
                                    break
                                except ValueError:
                                    continue
                            else:
                                converted_data[key] = value
                            continue
                        
                        # BOOLEAN type
                        if expected_type == 'bool' or (isinstance(expected_type, list) and 'bool' in expected_type):
                            value_lower = value.strip().lower()
                            if value_lower in ['true', '1', 'yes']:
                                converted_data[key] = True
                            elif value_lower in ['false', '0', 'no']:
                                converted_data[key] = False
                            else:
                                converted_data[key] = value
                            continue
                        
                        # NUMERIC types
                        numeric_types = ['int', 'long', 'double', 'decimal']
                        if expected_type in numeric_types or (isinstance(expected_type, list) and any(t in numeric_types for t in expected_type)):
                            if '.' in value:
                                converted_data[key] = float(value)
                            else:
                                converted_data[key] = int(value)
                            continue
                        
                        # STRING type - keep as-is
                        converted_data[key] = value
                        
                    except (json.JSONDecodeError, ValueError) as e:
                        self.logger.warning(f"Could not convert field '{key}': {e}")
                        converted_data[key] = value
                else:
                    converted_data[key] = value
            
            return converted_data
            
        except ValueError as ve:
            raise ve
        except Exception as e:
            self.logger.error(f"Type conversion failed: {e}")
            raise ValueError(f"Failed to convert data types: {str(e)}")

    def insert(self, table_name, data):
        if '_id' in data:
            del data['_id']
        if 'doc_id' in data:
            del data['doc_id']
        
        # CRITICAL FIX: Parse JSON strings from frontend BEFORE type conversion
        import json
        parsed_data = {}
        for key, value in data.items():
            if isinstance(value, str) and value.strip():
                # Try to parse as JSON if it looks like JSON
                stripped = value.strip()
                if (stripped.startswith('[') and stripped.endswith(']')) or \
                   (stripped.startswith('{') and stripped.endswith('}')):
                    try:
                        parsed_data[key] = json.loads(value)
                        self.logger.debug(f"Parsed {key} from JSON string: {value[:50]}")
                        continue
                    except json.JSONDecodeError:
                        self.logger.debug(f"Failed to parse {key} as JSON: {value[:50]}")
                        pass
            # Keep original value if not parsed
            parsed_data[key] = value
        
        # Convert string inputs to proper types based on validation schema
        converted_data = self._convert_data_types(table_name, parsed_data)
        
        # Validate data against schema BEFORE attempting insert
        try:
            return str(self.db[table_name].insert_one(converted_data).inserted_id)
        except Exception as insert_err:
            error_msg = str(insert_err)
            # Make validation errors more user-friendly
            if 'validation' in error_msg.lower() or 'schema' in error_msg.lower():
                raise ValueError(f"Validation failed: {error_msg}")
            else:
                raise

    def update(self, table_name, doc_id, data):
        doc_id = self._convert_to_objectid(doc_id)

        # CRITICAL FIX: Parse JSON strings from frontend BEFORE type conversion
        import json
        parsed_data = {}
        for key, value in data.items():
            if isinstance(value, str) and value.strip():
                # Try to parse as JSON if it looks like JSON
                stripped = value.strip()
                if (stripped.startswith('[') and stripped.endswith(']')) or \
                   (stripped.startswith('{') and stripped.endswith('}')):
                    try:
                        parsed_data[key] = json.loads(value)
                        self.logger.debug(f"Parsed {key} from JSON string: {value[:50]}")
                        continue
                    except json.JSONDecodeError:
                        self.logger.debug(f"Failed to parse {key} as JSON: {value[:50]}")
                        pass
            # Keep original value if not parsed
            parsed_data[key] = value

        # Convert string inputs to proper types based on validation schema
        converted_data = self._convert_data_types(table_name, parsed_data)

        # Build update document
        update_doc = {}
        unset_doc = {}

        for key, value in converted_data.items():
            if key in ['_id', 'doc_id']:
                continue
            if value is None:
                unset_doc[key] = ""
            else:
                if '$set' not in update_doc:
                    update_doc['$set'] = {}
                update_doc['$set'][key] = value

        if unset_doc:
            update_doc['$unset'] = unset_doc

        if update_doc:
            self.db[table_name].update_one({"_id": doc_id}, update_doc)

    def delete(self, table_name, doc_id):
        doc_id = self._convert_to_objectid(doc_id)
        self.db[table_name].delete_one({"_id": doc_id})

    def delete_table(self, table_name):
        self.db[table_name].drop()

    def can_convert_column(self, table_name, column, new_type):
        return True

    def modify_table(self, old_table_name, new_table_name, new_columns):
        if old_table_name != new_table_name:
            self.db[old_table_name].rename(new_table_name)

    def get_document(self, table_name, doc_id):
        doc_id = self._convert_to_objectid(doc_id)
        doc = self.db[table_name].find_one({"_id": doc_id})
        if doc:
            doc['_id'] = str(doc['_id'])
            doc['doc_id'] = doc['_id']
        return doc

    def create_collection(self, collection_name, validation_rules=None):
        """Create collection with optional validation rules"""
        if validation_rules:
            # Create with validation from the start
            self.db.create_collection(collection_name)
            self.apply_validation_rules(collection_name, validation_rules)
        else:
            self.db.create_collection(collection_name)

    def get_all_keys(self, collection_name):
        """Get all unique keys across all documents in collection"""
        # ✅ FIX: Restore connection if lost
        if self.db is None:
            self.logger.warning("No database selected for get_all_keys, attempting to restore")
            if self.current_db:
                self.switch_db(self.current_db)
            else:
                self.logger.error("Cannot get keys: no current_db set")
                return []
        
        if self.db is None:
            self.logger.error("Still no database after restore attempt")
            return []
        
        try:
            # Method 1: Use aggregation pipeline (efficient)
            pipeline = [
                {"$project": {"arrayofkeyvalue": {"$objectToArray": "$$ROOT"}}},
                {"$unwind": "$arrayofkeyvalue"},
                {"$group": {"_id": None, "allkeys": {"$addToSet": "$arrayofkeyvalue.k"}}}
            ]
            result = list(self.db[collection_name].aggregate(pipeline))
            
            if result and 'allkeys' in result[0]:
                keys = result[0]['allkeys']
                # Filter out MongoDB's internal _id field
                filtered_keys = [k for k in keys if k != '_id']
                return sorted(filtered_keys)
            
            # Method 2: Fallback - manually iterate documents
            all_keys = set()
            for doc in self.db[collection_name].find().limit(100):
                all_keys.update(doc.keys())
            
            # Remove _id from the set
            all_keys.discard('_id')
            
            result_keys = sorted(list(all_keys))
            return result_keys
            
        except Exception as e:
            self.logger.error(f"Error getting keys for {collection_name}: {str(e)}")
            import traceback
            self.logger.error(traceback.format_exc())
            return []
    
    def get_primary_key_name(self):
        """Return the primary key field name for this NoSQL database"""
        return '_id'
    
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
        """Return True if database supports aggregation (GROUP BY, SUM, AVG, etc.)"""
        return True
    
    def supports_aggregation_pipeline(self):
        """Return True if database supports aggregation pipelines"""
        return True  # MongoDB supports aggregation pipelines
    
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
        """MongoDB handler doesn't require credentials"""
        return {
            "needs_credentials": False,
            "handler": self.DB_NAME
        }

    def clear_credentials(self):
        """MongoDB handler doesn't store credentials"""
        pass
    
    def supports_user_management(self):
        """MongoDB supports user management"""
        return True
    
    def requires_credentials(self):
        """MongoDB doesn't require credentials for user login in this setup"""
        return False

    def list_users(self):
        """List all MongoDB users in current database"""
        if self.db is None or self.current_db is None:
            return []
    
        try:
            # Get users from current database
            users_info = self.client[self.current_db].command("usersInfo")
        
            users = []
            for user_doc in users_info.get('users', []):
                username = user_doc['user']
            
                # Extract roles/privileges
                roles = user_doc.get('roles', [])
                privileges = []
            
                for role in roles:
                    role_name = role['role']
                    if role_name == 'root' or role_name == 'dbOwner':
                        privileges = ['ALL']
                        break
                    elif role_name == 'readWrite':
                        privileges.extend(['SELECT', 'INSERT', 'UPDATE', 'DELETE'])
                    elif role_name == 'read':
                        privileges.append('SELECT')
                    elif role_name == 'dbAdmin':
                        privileges.extend(['CREATE', 'DROP'])
            
                # MongoDB users always have passwords
                users.append({
                    'username': username,
                    'has_password': True,
                    'privileges': list(set(privileges)) if privileges else ['USAGE']
                })
        
            return users
        except Exception as e:
            import logging
            logging.error(f"Error listing MongoDB users: {str(e)}")
            return []

    def create_user(self, username, password, privileges):
        """Create a new MongoDB user"""
        if self.db is None or self.current_db is None:
            raise Exception("No database selected")
    
        if not password:
            raise ValueError("MongoDB requires a password for all users")
    
        try:
            # Map privileges to MongoDB roles
            roles = []
        
            if 'ALL' in privileges:
                roles.append('dbOwner')
            else:
                # Determine appropriate role based on privileges
                has_write = any(p in privileges for p in ['INSERT', 'UPDATE', 'DELETE'])
                has_read = 'SELECT' in privileges
                has_admin = any(p in privileges for p in ['CREATE', 'DROP'])
            
                if has_admin:
                    roles.append('dbAdmin')
                if has_write and has_read:
                    roles.append('readWrite')
                elif has_read:
                    roles.append('read')
        
            if not roles:
                roles.append('read')  # Default to read-only
        
            # Create user in current database
            self.db.command("createUser", username, pwd=password, roles=roles)
        
        except Exception as e:
            import logging
            logging.error(f"Error creating MongoDB user: {str(e)}")
            raise

    def update_user(self, username, password, privileges):
        """Update MongoDB user credentials/privileges"""
        if self.db is None or self.current_db is None:
            raise Exception("No database selected")
    
        try:
            # Update password if provided
            if password:
                self.db.command("updateUser", username, pwd=password)
        
            # Map privileges to MongoDB roles
            roles = []
        
            if 'ALL' in privileges:
                roles.append('dbOwner')
            else:
                has_write = any(p in privileges for p in ['INSERT', 'UPDATE', 'DELETE'])
                has_read = 'SELECT' in privileges
                has_admin = any(p in privileges for p in ['CREATE', 'DROP'])
            
                if has_admin:
                    roles.append('dbAdmin')
                if has_write and has_read:
                    roles.append('readWrite')
                elif has_read:
                    roles.append('read')
        
            if not roles:
                roles.append('read')
        
            # Update user roles
            self.db.command("updateUser", username, roles=roles)
        
        except Exception as e:
            import logging
            logging.error(f"Error updating MongoDB user: {str(e)}")
            raise

    def delete_user(self, username):
        """Delete a MongoDB user"""
        if self.db is None or self.current_db is None:
            raise Exception("No database selected")
    
        try:
            self.db.command("dropUser", username)
        except Exception as e:
            import logging
            logging.error(f"Error deleting MongoDB user: {str(e)}")
            raise

    def get_user_privileges(self, username):
        """Get privileges for a specific MongoDB user"""
        if self.db is None or self.current_db is None:
            return []
    
        try:
            users_info = self.db.command("usersInfo", username)
        
            if not users_info.get('users'):
                return []
        
            user_doc = users_info['users'][0]
            roles = user_doc.get('roles', [])
        
            privileges = []
            for role in roles:
                role_name = role['role']
                if role_name == 'root' or role_name == 'dbOwner':
                    return ['ALL']
                elif role_name == 'readWrite':
                    privileges.extend(['SELECT', 'INSERT', 'UPDATE', 'DELETE'])
                elif role_name == 'read':
                    privileges.append('SELECT')
                elif role_name == 'dbAdmin':
                    privileges.extend(['CREATE', 'DROP'])
        
            return list(set(privileges)) if privileges else ['USAGE']
        except Exception as e:
            import logging
            logging.error(f"Error getting MongoDB user privileges: {str(e)}")
            return []

    def get_user_connection_info(self, username):
        """Return connection info for a specific MongoDB user"""
        current_db = self.current_db or 'your_database'
    
        return {
            'connection_string': f'mongodb://{username}:YOUR_PASSWORD@localhost:27017/{current_db}',
            'test_code': f'''from pymongo import MongoClient

    # Replace YOUR_PASSWORD with the actual password
    username = "{username}"
    password = "YOUR_PASSWORD"
    database = "{current_db}"

    # Connect with authentication
    client = MongoClient(
        'mongodb://localhost:27017/',
        username=username,
        password=password,
        authSource=database  # Authenticate against the database where user was created
    )

    db = client[database]

    # Test connection
    collections = db.list_collection_names()
    print(f"Connected to: {{database}}")
    print(f"Collections: {{collections}}")

    if collections:
        # Show document count in first collection
        first_coll = collections[0]
        count = db[first_coll].count_documents({{}})
        print(f"Documents in '{{first_coll}}': {{count}}")

    client.close()''',
            'notes': [
                'Replace YOUR_PASSWORD with the actual password for this user',
                'Ensure MongoDB server is running on localhost:27017',
                f'User was created in database: {current_db}',
                'Use authSource parameter to specify authentication database'
            ]
        }
        
    def build_column_definitions(self, schema, quote=True):
        """NoSQL databases don't use column definitions, but method required for interface compatibility"""
        return []
    
    def reset_sequence_after_copy(self, table_name, column_name):
        """NoSQL databases don't use sequences"""
        pass  # Not applicable for NoSQL
    
    def get_foreign_keys(self, table_name):
        """NoSQL doesn't support foreign keys or method not implemented"""
        return []

    def create_foreign_key(self, table_name, constraint_name, column_name,
                        foreign_table, foreign_column, on_update, on_delete):
        """NoSQL doesn't support foreign keys"""
        pass
    
    def get_views(self):
        """NoSQL databases don't support views"""
        return []

    def create_view(self, view_name, view_definition):
        """NoSQL databases don't support views"""
        pass
    
    def copy_table(self, source_table, dest_table):
        """Copy table structure and data - override in child classes for optimization"""
        # Default implementation - handlers can override for better performance
        raise NotImplementedError(f"{self.DB_NAME} must implement copy_table")

    def copy_triggers(self, source_table, dest_table):
        """NoSQL doesn't have triggers"""
        pass
    
    def get_table_connection_info(self, db_name, table_name):
        """Return collection-specific connection information"""
        base_conn = self.get_connection_info(db_name)
        
        test_code = f'''from pymongo import MongoClient

client = MongoClient('mongodb://localhost:27017/')
db = client['{db_name}']
collection = db['{table_name}']

docs = list(collection.find().limit(10))
print(f"Documents: {{len(docs)}}")
if docs:
    print(f"Sample: {{docs[0]}}")'''
        
        return {
            'connection_string': base_conn['connection_string'],
            'test_code': test_code,
            'notes': base_conn.get('notes', [])
        }
    def supports_check_constraints(self):
        """MongoDB supports validation through JSON Schema"""
        return True

    def get_check_constraints(self, table_name):
        """Get validation rules for a MongoDB collection"""
        if self.db is None:
            return []
        
        try:
            # Get collection info including validator
            coll_info = self.db.command("listCollections", filter={"name": table_name})
            
            if not coll_info.get('cursor', {}).get('firstBatch'):
                return []
            
            coll_data = coll_info['cursor']['firstBatch'][0]
            validator = coll_data.get('options', {}).get('validator', {})
            
            if not validator:
                return []
            
            # Extract field-level validations from $jsonSchema
            json_schema = validator.get('$jsonSchema', {})
            properties = json_schema.get('properties', {})
            required_fields = json_schema.get('required', [])
            
            checks = []
            
            for field_name, field_rules in properties.items():
                # Build human-readable constraint description
                constraints = []
                
                # Type constraint
                if 'bsonType' in field_rules:
                    type_name = field_rules['bsonType']
                    if isinstance(type_name, list):
                        type_name = ', '.join(type_name)
                    constraints.append(f"type: {type_name}")
                
                # Required
                if field_name in required_fields:
                    constraints.append("required")
                
                # Numeric constraints
                if 'minimum' in field_rules:
                    constraints.append(f">= {field_rules['minimum']}")
                if 'maximum' in field_rules:
                    constraints.append(f"<= {field_rules['maximum']}")
                
                # String constraints
                if 'minLength' in field_rules:
                    constraints.append(f"length >= {field_rules['minLength']}")
                if 'maxLength' in field_rules:
                    constraints.append(f"length <= {field_rules['maxLength']}")
                if 'pattern' in field_rules:
                    constraints.append(f"pattern: {field_rules['pattern']}")
                
                # Enum constraint
                if 'enum' in field_rules:
                    enum_values = ', '.join([str(v) for v in field_rules['enum']])
                    constraints.append(f"in [{enum_values}]")
                
                if constraints:
                    checks.append({
                        'column': field_name,
                        'expression': ', '.join(constraints)
                    })
            
            return checks
        
        except Exception as e:
            self.logger.error(f"Failed to get MongoDB validation rules: {e}")
            return []

    def validate_check_constraint(self, constraint_expression):
        """Validate constraint expression - for MongoDB, we accept JSON Schema syntax"""
        # MongoDB uses JSON Schema, so we just check for dangerous operations
        dangerous_keywords = ['$where', 'function', 'eval', 'mapReduce']
        upper_expr = constraint_expression.upper()
        
        for keyword in dangerous_keywords:
            if keyword.upper() in upper_expr:
                return False
        
        return True

    def apply_validation_rules(self, collection_name, validation_rules):
        """
        Apply per-field validation rules to a collection
        validation_rules format: {
            'field_name': {
                'type': 'string' | 'number' | 'boolean' | 'object' | 'array',
                'required': True/False,
                'min': number (for numeric types),
                'max': number (for numeric types),
                'minLength': number (for strings),
                'maxLength': number (for strings),
                'enum': [allowed_values],
                'pattern': 'regex_pattern'
            }
        }
        """
        if self.db is None:
            raise Exception("No database selected")
        
        try:
            # Build JSON Schema from validation rules
            properties = {}
            required_fields = []
            
            # CRITICAL FIX: Map 'number' to numeric array (not individual types)
            type_mapping = {
                'string': 'string',
                'number': ['int', 'long', 'double', 'decimal'],  # Keep as array
                'boolean': 'bool',
                'object': 'object',
                'array': 'array',
                'date': 'date'
            }
            
            for field_name, rules in validation_rules.items():
                if not rules:  # Skip empty rules
                    continue
                
                field_schema = {}
                
                # ✅ CRITICAL FIX: Handle bsonType correctly (can be array or string)
                if 'bsonType' in rules and rules['bsonType']:
                    # bsonType might already be correct (from parser)
                    field_schema['bsonType'] = rules['bsonType']
                elif 'type' in rules and rules['type']:
                    # CRITICAL FIX: Get mapped type (which might be an array for 'number')
                    bson_type = type_mapping.get(rules['type'], 'string')
                    field_schema['bsonType'] = bson_type
                else:
                    # ✅ NEW: If no type specified but has numeric constraints, infer numeric type
                    if 'minimum' in rules or 'maximum' in rules:
                        field_schema['bsonType'] = ['int', 'long', 'double', 'decimal']
                        self.logger.debug(f"Inferred numeric type for {field_name} from min/max constraints")
                    # If has string length constraints, infer string type
                    elif 'minLength' in rules or 'maxLength' in rules or 'pattern' in rules:
                        field_schema['bsonType'] = 'string'
                        self.logger.debug(f"Inferred string type for {field_name} from length/pattern constraints")
                    # If has enum, infer from first value
                    elif 'enum' in rules and rules['enum']:
                        try:
                            int(rules['enum'][0])
                            field_schema['bsonType'] = ['int', 'long']
                        except:
                            field_schema['bsonType'] = 'string'
                        self.logger.debug(f"Inferred type for {field_name} from enum values")
                
                # Required field
                if rules.get('required'):
                    required_fields.append(field_name)
                
                # CRITICAL FIX: Use 'minimum'/'maximum' for MongoDB (not 'min'/'max')
                if 'minimum' in rules and rules['minimum'] is not None:
                    field_schema['minimum'] = rules['minimum']
                elif 'min' in rules and rules['min'] is not None:
                    field_schema['minimum'] = rules['min']
                
                if 'maximum' in rules and rules['maximum'] is not None:
                    field_schema['maximum'] = rules['maximum']
                elif 'max' in rules and rules['max'] is not None:
                    field_schema['maximum'] = rules['max']
                
                # String constraints
                if 'minLength' in rules and rules['minLength'] is not None:
                    field_schema['minLength'] = rules['minLength']
                if 'maxLength' in rules and rules['maxLength'] is not None:
                    field_schema['maxLength'] = rules['maxLength']
                if 'pattern' in rules and rules['pattern']:
                    field_schema['pattern'] = rules['pattern']
                
                # Enum constraint
                if 'enum' in rules and rules['enum']:
                    field_schema['enum'] = rules['enum']
                
                if field_schema:
                    properties[field_name] = field_schema
            
            # Build complete validator
            validator = {
                '$jsonSchema': {
                    'bsonType': 'object',
                    'properties': properties
                }
            }
            
            if required_fields:
                validator['$jsonSchema']['required'] = required_fields
            
            self.logger.info(f"Applying validator to collection {collection_name}")
            self.logger.debug(f"Full validator: {validator}")
            self.db.command('collMod', collection_name, 
                        validator=validator, 
                        validationLevel='strict',
                        validationAction='error')
            self.logger.info(f"✅ Validation rules applied successfully to {collection_name}")

            # Verify the validation was actually applied
            try:
                coll_info = self.db.command("listCollections", filter={"name": collection_name})
                if coll_info.get('cursor', {}).get('firstBatch'):
                    applied_validator = coll_info['cursor']['firstBatch'][0].get('options', {}).get('validator')
                    if applied_validator:
                        self.logger.info(f"✅ VERIFIED: Validator is active on {collection_name}")
                    else:
                        self.logger.error(f"❌ WARNING: No validator found on {collection_name} after applying!")
            except Exception as verify_err:
                self.logger.warning(f"Could not verify validator: {verify_err}")
                        
            return True
        
        except Exception as e:
            self.logger.error(f"Failed to apply validation rules: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            raise Exception(f"Validation failed: {str(e)}")
        
    def copy_database(self, source_db_name, dest_db_name):
        """Copy entire database including all collections and their data"""
        try:
            source_db = self.client[source_db_name]
            dest_db = self.client[dest_db_name]
            
            # Get all collections from source (EXCLUDING system marker - it's already created)
            source_collections = source_db.list_collection_names()
            
            # Filter out system marker collection - it's already created by create_db()
            source_collections = [coll for coll in source_collections if coll != '_dbdragoness_system']
            
            self.logger.info(f"Copying {len(source_collections)} collections from {source_db_name} to {dest_db_name}")
            
            for coll_name in source_collections:
                # Get source collection info including validation
                coll_info = source_db.command("listCollections", filter={"name": coll_name})
                source_validator = None
                
                if coll_info.get('cursor', {}).get('firstBatch'):
                    coll_data = coll_info['cursor']['firstBatch'][0]
                    source_validator = coll_data.get('options', {}).get('validator')
                
                # Get all documents from source collection
                source_docs = list(source_db[coll_name].find())
                
                # Create destination collection WITHOUT validation first
                dest_db.create_collection(coll_name)
                
                # Copy all documents
                if source_docs:
                    # Remove _id to let MongoDB generate new ones
                    docs_to_insert = []
                    for doc in source_docs:
                        doc_copy = doc.copy()
                        if '_id' in doc_copy:
                            del doc_copy['_id']
                        docs_to_insert.append(doc_copy)
                    
                    dest_db[coll_name].insert_many(docs_to_insert)
                    self.logger.info(f"✅ Copied {len(source_docs)} documents to {dest_db_name}.{coll_name}")
                
                # Apply validation rules AFTER data is copied
                if source_validator:
                    try:
                        dest_db.command('collMod', coll_name, validator=source_validator)
                        self.logger.info(f"✅ Applied validation rules to {dest_db_name}.{coll_name}")
                    except Exception as validation_err:
                        self.logger.warning(f"⚠️ Could not apply validation to {coll_name}: {validation_err}")
            
            self.logger.info(f"✅ Successfully copied database {source_db_name} to {dest_db_name}")
            
        except Exception as e:
            self.logger.error(f"Failed to copy database: {e}")
            raise Exception(f"Failed to copy database: {str(e)}")
    
    def copy_table(self, source_table, dest_table):
        """Copy collection and validation rules - data first, then validation"""
        if self.db is None:
            raise Exception("No database selected")
        
        try:
            # Get source collection info including validation
            coll_info = self.db.command("listCollections", filter={"name": source_table})
            source_validator = None
            
            if coll_info.get('cursor', {}).get('firstBatch'):
                coll_data = coll_info['cursor']['firstBatch'][0]
                source_validator = coll_data.get('options', {}).get('validator')
            
            # Get source collection documents
            source_docs = list(self.db[source_table].find())
            
            # Create destination collection WITHOUT validation first
            self.db.create_collection(dest_table)
            
            # Copy all documents
            if source_docs:
                # Remove _id to let MongoDB generate new ones
                for doc in source_docs:
                    if '_id' in doc:
                        del doc['_id']
                
                self.db[dest_table].insert_many(source_docs)
                self.logger.info(f"Copied {len(source_docs)} documents to {dest_table}")
            
            # Try to apply validation rules AFTER data is copied
            if source_validator:
                self.logger.info(f"Attempting to apply validation rules to {dest_table}")
                
                try:
                    self.db.command('collMod', dest_table, validator=source_validator)
                    self.logger.info(f"✅ Successfully applied validation rules to {dest_table}")
                except Exception as validation_err:
                    self.logger.warning(f"⚠️ Could not apply validation rules to {dest_table}: {validation_err}")
                    self.logger.warning(f"   Reason: Existing data may violate the validation constraints")
                    self.logger.warning(f"   The collection was copied successfully, but without validation rules")
                    # Don't raise - allow the copy to succeed without validation
            
            self.logger.info(f"✅ Successfully copied {source_table} to {dest_table}")
            
        except Exception as e:
            self.logger.error(f"Failed to copy collection: {e}")
            # Clean up destination collection if copy failed
            try:
                self.db[dest_table].drop()
            except:
                pass
            raise Exception(f"Failed to copy collection: {str(e)}")