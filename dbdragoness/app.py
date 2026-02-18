import time
from flask import Flask, Response, current_app, jsonify, render_template, request, redirect, url_for
from .sql_handler import SQLHandler
from .nosql_handler import NoSQLHandler
from sqlalchemy.sql import text
from sqlalchemy.exc import IntegrityError
import os
import re
import logging
import json
from collections import OrderedDict
import hashlib
from .query_history_manager import QueryHistoryManager
from .db_registry import DBRegistry
import platform
from pathlib import Path

def create_app(initial_db_type, handler_name=None):
    app = Flask(__name__)
    
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'enchanted_key')
    app.config['DB_TYPE'] = initial_db_type
    
    # Setup logging
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(levelname)s: %(message)s')
    logger = logging.getLogger(__name__)
    logging.getLogger().setLevel(logging.DEBUG)  # Force root logger
    logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)  # Optional: reduce noise
    logging.getLogger('sqlalchemy.dialects.postgresql').setLevel(logging.DEBUG)  # For notices
    
    def ensure_directory_exists(base_path, *subdirs):
        """Cross-platform directory creation helper"""
        dir_path = Path(base_path)
        for subdir in subdirs:
            dir_path = dir_path / subdir
        dir_path.mkdir(parents=True, exist_ok=True)
        
        # Set proper permissions on Linux/Unix
        if platform.system() != 'Windows':
            try:
                os.chmod(dir_path, 0o755)
            except Exception as e:
                logger.debug(f"Could not set directory permissions: {e}")
        
        return dir_path
    
    def format_procedure_result(result):
        """Helper to format procedure results consistently"""
        if isinstance(result, dict):
            # Check if it has a 'result' key (nested result)
            if 'result' in result:
                nested = result['result']
                if isinstance(nested, list) and len(nested) > 0:
                    return {
                        'data': nested,
                        'type': 'table',
                        'rows_affected': result.get('rows_affected', len(nested))
                    }
                else:
                    return {
                        'data': result,
                        'type': 'status',
                        'rows_affected': result.get('rows_affected', 0)
                    }
            # Check if it's rows_affected format
            elif 'rows_affected' in result:
                # If there's actual data, return it as table
                if any(key not in ['rows_affected', 'status'] for key in result.keys()):
                    # Has data fields beyond just status
                    return {
                        'data': [result],
                        'type': 'table',
                        'rows_affected': result['rows_affected']
                    }
                else:
                    return {
                        'data': result,
                        'type': 'status',
                        'rows_affected': result.get('rows_affected', 0)
                    }
            else:
                # It's a data dict, wrap in list for table display
                return {
                    'data': [result],
                    'type': 'table',
                    'rows_affected': 1
                }
        elif isinstance(result, list):
            if len(result) > 0:
                return {
                    'data': result,
                    'type': 'table',
                    'rows_affected': len(result)
                }
            else:
                return {
                    'data': {'status': 'No results returned'},
                    'type': 'status',
                    'rows_affected': 0
                }
        else:
            return {
                'data': {'status': str(result)},
                'type': 'status',
                'rows_affected': 0
            }
            
    def send_sse_message(data_dict):
        """Helper to send SSE messages properly (cross-platform)"""
        return f"data: {json.dumps(data_dict)}\r\n\r\n"
    
    def normalize_db_name(name):
        """Normalize database names for case-sensitive filesystems"""
        if platform.system() != 'Windows':
            return name.lower()
        return name
            
    def format_nosql_result(result, handler):
        """Format NoSQL results - remove duplicate IDs"""
        if not result:
            return []
    
        primary_key = 'doc_id'
        if hasattr(handler, 'get_primary_key_name'):
            primary_key = handler.get_primary_key_name()
    
        if isinstance(result, list) and len(result) > 0:
            formatted = []
            for doc in result:
                if isinstance(doc, dict):
                    # Keep status messages as-is
                    if 'status' in doc and len(doc) == 1:
                        formatted.append(doc)
                        continue
                
                    clean = {}
                    # Primary key first
                    if primary_key in doc:
                        clean[primary_key] = doc[primary_key]
                
                    # Other fields (skip alt IDs)
                    for k, v in doc.items():
                        if k == primary_key:
                            continue
                        if k in ['_id', 'doc_id'] and k != primary_key:
                            continue
                        clean[k] = v
                
                    formatted.append(clean)
                else:
                    formatted.append(doc)
            return formatted
    
        return result
    
    # Discover all available handlers
    DBRegistry.discover_handlers()
    
    # Determine handler name
    if handler_name:
        app.config['CURRENT_HANDLER_NAME'] = handler_name
    else:
        # Use first available handler
        if initial_db_type == 'sql':
            default_sql = list(DBRegistry.get_sql_handlers().keys())[0] if DBRegistry.get_sql_handlers() else None
            app.config['CURRENT_HANDLER_NAME'] = default_sql
        else:
            default_nosql = list(DBRegistry.get_nosql_handlers().keys())[0] if DBRegistry.get_nosql_handlers() else None
            app.config['CURRENT_HANDLER_NAME'] = default_nosql
    
    # Initialize with handler
    if initial_db_type == 'sql':
        app.config['HANDLER'] = SQLHandler(app.config['CURRENT_HANDLER_NAME'])
    else:
        app.config['HANDLER'] = NoSQLHandler(app.config['CURRENT_HANDLER_NAME'])
        
    query_history_manager = QueryHistoryManager(
        history_file=str(Path(app.root_path) / 'data' / 'query_history.json')
    )

    # Ensure data directory exists (cross-platform)
    ensure_directory_exists(app.root_path, 'data')

    def is_use_query(query):
        """Check if query is a USE database command"""
        query_stripped = query.strip().upper()
        return query_stripped.startswith('USE ') and not query_stripped.startswith('USER')
        
    @app.after_request
    def auto_close_nosql(response):
        """Close TinyDB file handle after EVERY request to prevent delete lock"""
        if (app.config['DB_TYPE'] == 'nosql' and 
            hasattr(app.config['HANDLER'], 'handler') and 
            hasattr(app.config['HANDLER'].handler, 'close_db')):
            try:
                app.config['HANDLER'].handler.close_db()
                logger.debug("Auto-closed TinyDB after request")
            except Exception as e:
                logger.warning(f"Auto-close error: {e}")
        return response
            
    def sanitize_mermaid_type(sql_type: str) -> str:
        if not sql_type:
            return "TEXT"

        # Remove anything after '('
        base = sql_type.upper().split('(')[0]

        # Keep Mermaid-friendly words only
        return base.replace(' ', '_')
    
    def generate_er_diagram_data(db_name):
        """Generate ER (Entity-Relationship) diagram data for SQL databases"""
        tables = []
        relationships = []
    
        try:
            all_tables = app.config['HANDLER'].list_tables()
        
            for table in all_tables:
                columns = app.config['HANDLER'].get_table_schema(table)
                table_data = {
                    'name': table,
                    'fields': []
                }
            
                for col in columns:
                    field = {
                        'name': col['name'],
                        'type': sanitize_mermaid_type(col.get('type', 'TEXT')),
                        'pk': col.get('pk', False),
                        'notnull': col.get('notnull', False),
                        'fk': False
                    }
                    table_data['fields'].append(field)
            
                tables.append(table_data)
        
            # Detect relationships via foreign key naming patterns and actual FK constraints
            handler = app.config['HANDLER']
        
            # Try to get actual FK constraints from database
            for table in all_tables:
                try:
                    # For SQLite/DuckDB - query PRAGMA or information schema
                    with handler._get_connection() as conn:
                        # Try different methods depending on DB type
                        if hasattr(handler, 'handler') and hasattr(handler.handler, 'DB_NAME'):
                            db_type = handler.handler.DB_NAME
                        
                            if db_type == 'SQLite' or db_type == 'DuckDB':
                                # Use PRAGMA for SQLite/DuckDB
                                result = conn.execute(text(f"PRAGMA foreign_key_list({table})"))
                                for row in result:
                                    row_dict = dict(row._mapping)
                                    referenced_table = row_dict.get('table')
                                    from_column = row_dict.get('from')
                                
                                    if referenced_table:
                                        relationships.append({
                                            'from': table,
                                            'to': referenced_table,
                                            'type': 'foreign_key',
                                            'column': from_column
                                        })
                                    
                                        # Mark field as FK
                                        for t in tables:
                                            if t['name'] == table:
                                                for field in t['fields']:
                                                    if field['name'] == from_column:
                                                        field['fk'] = True
                        
                            elif db_type == 'PostgreSQL':
                                # PostgreSQL information schema query
                                query = text("""
                                    SELECT
                                        kcu.column_name,
                                        ccu.table_name AS foreign_table_name
                                    FROM information_schema.table_constraints AS tc
                                    JOIN information_schema.key_column_usage AS kcu
                                        ON tc.constraint_name = kcu.constraint_name
                                    JOIN information_schema.constraint_column_usage AS ccu
                                        ON ccu.constraint_name = tc.constraint_name
                                    WHERE tc.constraint_type = 'FOREIGN KEY'
                                        AND tc.table_name = :table_name
                                """)
                                result = conn.execute(query, {'table_name': table})
                                for row in result:
                                    row_dict = dict(row._mapping)
                                    relationships.append({
                                        'from': table,
                                        'to': row_dict['foreign_table_name'],
                                        'type': 'foreign_key',
                                        'column': row_dict['column_name']
                                    })
                                
                                    # Mark field as FK
                                    for t in tables:
                                        if t['name'] == table:
                                            for field in t['fields']:
                                                if field['name'] == row_dict['column_name']:
                                                    field['fk'] = True
                except Exception as e:
                    logger.debug(f"Could not detect FKs for {table}: {e}")
        
            # Fallback: naming convention detection if no FKs found
            if not relationships:
                for table_data in tables:
                    table_name = table_data['name']
                    for field in table_data['fields']:
                        field_name = field['name'].lower()
                    
                        # Common FK patterns: user_id, customer_id, etc.
                        if field_name.endswith('_id') and not field['pk']:
                            # Extract potential table name
                            potential_table = field_name[:-3]  # Remove '_id'
                        
                            # Check if a table with similar name exists
                            for other_table in all_tables:
                                if (other_table.lower() == potential_table or 
                                    other_table.lower() == potential_table + 's' or
                                    other_table.lower() + 's' == potential_table):
                                
                                    relationships.append({
                                        'from': table_name,
                                        'to': other_table,
                                        'type': 'inferred',
                                        'column': field['name']
                                    })
                                    field['fk'] = True
                                    break
        
            return {
                'tables': tables,
                'relationships': relationships
            }
        except Exception as e:
            logger.error(f"ER diagram generation error: {str(e)}")
            return {'tables': [], 'relationships': [], 'error': str(e)}

    def generate_schema_diagram_data(db_name):
        """Generate Schema/Table structure diagram data"""
        tables = []
    
        try:
            all_tables = app.config['HANDLER'].list_tables()
        
            for table in all_tables:
                columns = app.config['HANDLER'].get_table_schema(table)
            
                # ✅ FIX: Ensure we have valid column data
                if not columns:
                    logger.warning(f"No columns found for table {table}")
                    tables.append({
                        'name': table,
                        'total_columns': 0,
                        'type_distribution': {'UNKNOWN': 0},
                        'pk_count': 0,
                        'notnull_count': 0,
                        'fields': []  # ✅ Add this
                    })
                    continue
            
                # Count columns by type
                type_counts = {}
                for col in columns:
                    col_type = col.get('type', 'TEXT')
                    type_counts[col_type] = type_counts.get(col_type, 0) + 1
            
                # Count constraints
                pk_count = sum(1 for col in columns if col.get('pk', False))
                notnull_count = sum(1 for col in columns if col.get('notnull', False))
            
                table_data = {
                    'name': table,
                    'total_columns': len(columns),  # ✅ Direct count
                    'type_distribution': type_counts if type_counts else {'UNKNOWN': len(columns)},
                    'pk_count': pk_count,
                    'notnull_count': notnull_count,
                    'fields': columns  # ✅ Add full column info
                }
                tables.append(table_data)
        
            return {
                'tables': tables,
                'total_tables': len(tables)
            }
        except Exception as e:
            logger.error(f"Schema diagram generation error: {str(e)}")
            return {'tables': [], 'total_tables': 0, 'error': str(e)}

    def generate_collections_diagram_data(db_name):
        """Generate collections overview diagram for NoSQL"""
        collections = []
    
        try:
            all_collections = app.config['HANDLER'].list_tables()
            total_docs = 0
        
            for collection in all_collections:
                try:
                    count = app.config['HANDLER'].count_documents(collection)
                    total_docs += count
                
                    # Get sample keys
                    keys = app.config['HANDLER'].get_all_keys(collection)
                
                    collections.append({
                        'name': collection,
                        'document_count': count,
                        'key_count': len(keys),
                        'sample_keys': keys[:10]  # First 10 keys
                    })
                except Exception as e:
                    logger.error(f"Error processing collection {collection}: {str(e)}")
                    collections.append({
                        'name': collection,
                        'document_count': 0,
                        'key_count': 0,
                        'error': str(e)
                    })
        
            return {
                'collections': collections,
                'total_collections': len(collections),
                'total_documents': total_docs
            }
        except Exception as e:
            logger.error(f"Collections diagram generation error: {str(e)}")
            return {'collections': [], 'error': str(e)}

    def generate_hierarchy_diagram_data(db_name):
        """Generate data hierarchy/structure diagram for NoSQL"""
        collections = []
    
        try:
            all_collections = app.config['HANDLER'].list_tables()
        
            for collection in all_collections:
                try:
                    count = app.config['HANDLER'].count_documents(collection)
                    keys = app.config['HANDLER'].get_all_keys(collection)
                
                    # Get sample document
                    docs = app.config['HANDLER'].read(collection)
                    sample_doc = docs[0] if docs else {}
                
                    # Analyze field types
                    field_info = {}
                    for key in keys:
                        sample_values = []
                        for doc in docs[:5]:  # Sample first 5 docs
                            if key in doc:
                                sample_values.append(doc[key])
                    
                        # Determine type
                        field_type = 'mixed'
                        if sample_values:
                            first_val = sample_values[0]
                            if isinstance(first_val, int):
                                field_type = 'integer'
                            elif isinstance(first_val, float):
                                field_type = 'float'
                            elif isinstance(first_val, bool):
                                field_type = 'boolean'
                            elif isinstance(first_val, str):
                                field_type = 'string'
                            elif isinstance(first_val, list):
                                field_type = 'array'
                            elif isinstance(first_val, dict):
                                field_type = 'object'
                    
                        field_info[key] = {
                            'type': field_type,
                            'sample_values': sample_values[:3]
                        }
                
                    collections.append({
                        'name': collection,
                        'document_count': count,
                        'fields': field_info
                    })
                except Exception as e:
                    logger.error(f"Error analyzing collection {collection}: {str(e)}")
        
            return {
                'collections': collections,
                'total_collections': len(collections)
            }
        except Exception as e:
            logger.error(f"Hierarchy diagram generation error: {str(e)}")
            return {'collections': [], 'error': str(e)}
        
    # ===== REACT FRONTEND SERVING =====
    @app.route('/react/')
    @app.route('/react/<path:path>')
    def serve_react(path='index.html'):
        """Serve React frontend"""
        react_dir = Path(app.root_path) / 'static' / 'react'
        
        if not react_dir.exists():
            return "React frontend not built. Run: cd frontend && npm run build", 404
        
        # Serve index.html for all routes (SPA routing)
        file_path = react_dir / path
        if path != 'index.html' and not file_path.exists():
            path = 'index.html'
        
        return app.send_static_file(f'react/{path}')
    
    # ===== JSON API ROUTES (for React) =====
    @app.route('/api/databases', methods=['GET', 'POST'])
    def api_databases():
        """JSON API: List/Create/Delete databases"""
        try:
            if request.method == 'GET':
                print("✓ API call: GET /api/databases")
                dbs = app.config['HANDLER'].list_dbs()
                
                # Get available handlers
                if app.config['DB_TYPE'] == 'sql':
                    available_handlers = list(DBRegistry.get_sql_handlers().keys())
                else:
                    available_handlers = list(DBRegistry.get_nosql_handlers().keys())
                
                return jsonify({
                    'success': True,
                    'databases': dbs,
                    'db_type': app.config['DB_TYPE'],
                    'handler': app.config['CURRENT_HANDLER_NAME'],
                    'available_handlers': available_handlers
                })
            
            elif request.method == 'POST':
                data = request.get_json()
                action = data.get('action')
                db_name = data.get('db_name')
                
                print(f"✓ API call: POST /api/databases - action={action}, db_name={db_name}")
                
                if action == 'create':
                    if not re.match(r'^[a-zA-Z][a-zA-Z0-9_]*$', db_name):
                        return jsonify({'success': False, 'error': 'Invalid database name'}), 400
                    
                    if db_name in app.config['HANDLER'].list_dbs():
                        return jsonify({'success': False, 'error': 'Database already exists'}), 400
                    
                    try:
                        app.config['HANDLER'].create_db(db_name)
                        logger.debug(f"API: Created database {db_name}")
                        return jsonify({'success': True, 'message': f'Database {db_name} created successfully'}), 201
                    except Exception as create_error:
                        error_msg = str(create_error)
                        logger.error(f"Database creation error: {error_msg}")
                        return jsonify({'success': False, 'error': error_msg}), 400
                
                elif action == 'delete':
                    app.config['HANDLER'].delete_db(db_name)
                    logger.debug(f"API: Deleted database {db_name}")
                    return jsonify({'success': True, 'message': f'Database {db_name} deleted'})
                
                else:
                    return jsonify({'success': False, 'error': 'Invalid action'}), 400
                    
        except Exception as e:
            print(f"❌ API call failed: /api/databases - {e}")
            logger.error(f"API error: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500
        
    @app.route('/api/databases/rename', methods=['POST'])
    def api_rename_database():
        """JSON API: Rename database by copying to new name and optionally deleting old"""
        try:
            data = request.get_json()
            old_name = data.get('old_name')
            new_name = data.get('new_name')
            keep_old = data.get('keep_old', False)
        
            logger.debug(f"✅ API call: POST /api/databases/rename - old={old_name}, new={new_name}, keep_old={keep_old}")
        
            # Validate inputs
            if not old_name or not new_name:
                return jsonify({'success': False, 'error': 'Both old and new names are required'}), 400
        
            if not re.match(r'^[a-zA-Z][a-zA-Z0-9_]*$', new_name):
                return jsonify({
                    'success': False, 
                    'error': 'New name must start with a letter, contain only letters, numbers, underscores.'
                }), 400
        
            # Check if old database exists
            existing_dbs = app.config['HANDLER'].list_dbs()
            if old_name not in existing_dbs:
                return jsonify({'success': False, 'error': f'Database {old_name} not found'}), 404
        
            # Check if new name already exists
            if new_name in existing_dbs:
                return jsonify({'success': False, 'error': f'Database {new_name} already exists'}), 400
        
            # Close current connection if it's the database being renamed
            if app.config['HANDLER'].current_db == old_name:
                if hasattr(app.config['HANDLER'], 'handler') and hasattr(app.config['HANDLER'].handler, 'close_db'):
                    app.config['HANDLER'].handler.close_db()
                app.config['HANDLER'].current_db = None
        
            # Step 1: Create new database
            app.config['HANDLER'].create_db(new_name)
            logger.debug(f"Created new database: {new_name}")
        
            # Step 2: Copy all tables/collections and their complete structures
            try:
                old_tables = app.config['HANDLER'].list_tables_for_db(old_name)
                logger.debug(f"Found {len(old_tables)} tables/collections to copy")
                
                # Filter out system tables (SQL only - NoSQL needs ALL collections for proper copy)
                if app.config['DB_TYPE'] == 'sql':
                    handler = app.config['HANDLER']
                    actual_handler = handler.handler if hasattr(handler, 'handler') else handler
                    
                    if hasattr(actual_handler, '_is_system_table'):
                        old_tables = [t for t in old_tables if not actual_handler._is_system_table(t)]
                        logger.debug(f"After filtering system tables: {len(old_tables)} tables to copy")
                
                for table in old_tables:
                    logger.debug(f"Copying table/collection: {table}")

                    # Switch to old database and read data
                    app.config['HANDLER'].switch_db(old_name)

                    # ✅ NoSQL: Special handling for database-level copy
                    if app.config['DB_TYPE'] == 'nosql':
                        handler = app.config['HANDLER']
                        
                        # For NoSQL, we need to copy at the handler level to preserve everything
                        if hasattr(handler, 'handler'):
                            actual_handler = handler.handler
                            
                            # Use handler-specific database copy if available
                            if hasattr(actual_handler, 'copy_database'):
                                try:
                                    actual_handler.copy_database(old_name, new_name)
                                    logger.info(f"✅ Successfully copied database {old_name} to {new_name} using handler's copy_database")
                                    break  # Exit the table loop - we copied everything at once
                                except Exception as copy_err:
                                    logger.warning(f"Handler copy_database failed: {copy_err}")
                                    # Fall through to table-by-table copy
                        
                        # Table-by-table copy for NoSQL
                        # Switch to old database
                        handler.switch_db(old_name)
                        
                        # Read all documents
                        documents = handler.read(table)
                        
                        # Switch to new database
                        handler.switch_db(new_name)
                        
                        # Create collection
                        handler.create_collection(table)
                        
                        # Get primary key name
                        primary_key = handler.get_primary_key_name()
                        
                        # Insert documents
                        for doc in documents:
                            clean_doc = {k: v for k, v in doc.items() if k != primary_key}
                            handler.insert(table, clean_doc)
                        
                        # Try to copy validation rules AFTER data
                        if hasattr(handler, 'get_check_constraints') and hasattr(handler, 'apply_validation_rules'):
                            try:
                                handler.switch_db(old_name)
                                old_checks = handler.get_check_constraints(table)
                                
                                if old_checks:
                                    handler.switch_db(new_name)
                                    
                                    validation_rules = {}
                                    for check in old_checks:
                                        col_name = check.get('column')
                                        if col_name:
                                            validation_rules[col_name] = {'expression': check.get('expression')}
                                    
                                    if validation_rules:
                                        try:
                                            handler.apply_validation_rules(table, validation_rules)
                                            logger.info(f"✅ Applied validation rules to {table}")
                                        except Exception as validation_err:
                                            logger.warning(f"⚠️ Could not apply validation rules to {table}: {validation_err}")
                            except Exception as e:
                                logger.warning(f"Failed to copy validation rules for {table}: {e}")
                        
                        continue  # Skip to next table
                    
                    if app.config['DB_TYPE'] == 'sql':
                        # Get table schema
                        schema = app.config['HANDLER'].get_table_schema(table)
                        # Read all data
                        data = app.config['HANDLER'].read(table)
                    
                        # Switch to new database
                        app.config['HANDLER'].switch_db(new_name)
                    
                        # Get handler info
                        actual_handler = app.config['HANDLER'].handler if hasattr(app.config['HANDLER'], 'handler') else app.config['HANDLER']
                        db_name_type = actual_handler.DB_NAME if hasattr(actual_handler, 'DB_NAME') else 'SQLite'
                        
                        # Build column definitions WITHOUT CHECK constraints for copying
                        creation_schema = []
                        check_constraints_to_apply = []

                        for col in schema:
                            col_copy = col.copy()
                            
                            # ✅ Store CHECK constraint for later - PARSE validation_rules if present
                            if col_copy.get('check_constraint'):
                                check_constraints_to_apply.append({
                                    'column': col_copy['name'],
                                    'expression': col_copy['check_constraint']
                                })
                                # Remove it from the schema used for table creation
                                col_copy['check_constraint'] = None
                            # ✅ NEW: Also handle validation_rules from NoSQL exports
                            elif col_copy.get('validation_rules'):
                                # Convert validation_rules to CHECK expression
                                check_expr = _validation_to_check(col_copy['validation_rules'], col_copy['name'])
                                if check_expr:
                                    check_constraints_to_apply.append({
                                        'column': col_copy['name'],
                                        'expression': check_expr
                                    })
                            
                            # Handle database-specific column name validation (SQLite)
                            if db_name_type == 'SQLite':
                                col_name = col_copy['name']
                                if col_name.isdigit() or (col_name and col_name[0].isdigit()):
                                    col_copy['name'] = f"col_{col_name}"
                                    logger.warning(f"Renamed column {col_name} to {col_copy['name']}")
                            
                            creation_schema.append(col_copy)
                        
                        # ✅ STEP 3: Build SQL column definitions (WITHOUT CHECK constraints)
                        columns_def = actual_handler.build_column_definitions(creation_schema, quote=False)
                        col_def_str = ', '.join(columns_def)
                        
                        # Quote table name for CREATE
                        if hasattr(actual_handler, '_quote_identifier'):
                            quoted_table = actual_handler._quote_identifier(table)
                        else:
                            quoted_table = f'"{table}"'
                        
                        # Execute CREATE TABLE
                        with app.config['HANDLER']._get_connection() as conn:
                            create_sql = f"CREATE TABLE {quoted_table} ({col_def_str})"
                            logger.debug(f"Creating table with SQL: {create_sql}")
                            conn.execute(text(create_sql))
                            conn.commit()
                    
                        # Insert data - copy ALL values INCLUDING autoincrement
                        for row in data:
                            filtered_row = {}
                            
                            for col in creation_schema:
                                original_col_name = col['name']
                                
                                # Find the original column name in case it was renamed
                                source_col_name = original_col_name
                                for orig_col in schema:
                                    if orig_col['name'].isdigit() and f"col_{orig_col['name']}" == original_col_name:
                                        source_col_name = orig_col['name']
                                        break
                                    elif orig_col['name'] and orig_col['name'][0].isdigit() and f"col_{orig_col['name']}" == original_col_name:
                                        source_col_name = orig_col['name']
                                        break
                                
                                # ✅ CRITICAL FIX: Copy ALL values including autoincrement
                                if source_col_name in row:
                                    filtered_row[original_col_name] = row[source_col_name]
                            
                            # ✅ Use raw SQL INSERT to preserve autoincrement values
                            if filtered_row:
                                try:
                                    quoted_table = actual_handler._quote_identifier(table) if hasattr(actual_handler, '_quote_identifier') else f'"{table}"'
                                    quoted_cols = ', '.join([actual_handler._quote_identifier(k) if hasattr(actual_handler, '_quote_identifier') else f'"{k}"' for k in filtered_row.keys()])
                                    placeholders = ', '.join([f':{k}' for k in filtered_row.keys()])
                                    insert_sql = f"INSERT INTO {quoted_table} ({quoted_cols}) VALUES ({placeholders})"
                                    
                                    with app.config['HANDLER']._get_connection() as conn:
                                        conn.execute(text(insert_sql), filtered_row)
                                        conn.commit()
                                except Exception as e:
                                    logger.error(f"Failed to insert row: {filtered_row}")
                                    logger.error(f"Error: {e}")
                                    raise
                                
                        # ✅ STEP 4: Apply CHECK constraints AFTER data is copied
                        if check_constraints_to_apply:
                            logger.info(f"Applying {len(check_constraints_to_apply)} CHECK constraints to {new_name}")
                            successful_checks = 0
                            failed_checks = 0
                            
                            app.config['HANDLER'].switch_db(new_name)
                            
                            for check_info in check_constraints_to_apply:
                                logger.info(f"🔥 PROCESSING CONSTRAINT FOR COLUMN '{check_info['column']}'")
                                logger.info(f"Expression: {check_info['expression']}")
                                logger.info(f"Handler type: {actual_handler.DB_NAME if hasattr(actual_handler, 'DB_NAME') else 'Unknown'}")
                                
                                try:
                                    # ✅ Use the appropriate method based on what the handler supports
                                    logger.info("Checking if handler has add_check_constraint_to_existing_table...")
                                    if hasattr(actual_handler, 'add_check_constraint_to_existing_table'):
                                        logger.info("YES – method found! Calling it now...")
                                        # Handler supports adding CHECK to existing table (e.g., via ALTER TABLE)
                                        actual_handler.add_check_constraint_to_existing_table(
                                            table,
                                            check_info['column'],
                                            check_info['expression']
                                        )
                                        logger.info(f"✅ Applied CHECK on {check_info['column']}: {check_info['expression']}")
                                        successful_checks += 1
                                    elif hasattr(actual_handler, 'create_check_constraint'):
                                        logger.info("Trying create_check_constraint as fallback...")
                                        # Handler requires table recreation to add CHECK constraint
                                        actual_handler.create_check_constraint(
                                            table,
                                            check_info['column'],
                                            check_info['expression'],
                                            conn  # Pass connection for transaction consistency
                                        )
                                        logger.info(f"✅ Applied CHECK on {check_info['column']}: {check_info['expression']}")
                                        successful_checks += 1
                                    else:
                                        # Handler doesn't support CHECK constraints
                                        logger.warning(f"Handler does not support CHECK constraints, skipping")
                                        continue
                                    
                                    logger.info(f"✅ Applied CHECK on {check_info['column']}: {check_info['expression']}")
                                    successful_checks += 1
                                except Exception as check_err:
                                    failed_checks += 1
                                    logger.warning(f"⚠️ Could not apply CHECK on {check_info['column']}: {check_err}")
                                    logger.warning(f"   Expression: {check_info['expression']}")
                                    logger.error(f"💥 EXCEPTION CAUGHT for {check_info['column']}: {type(check_err).__name__}: {check_err}")
                                    import traceback
                                    logger.error("Full traceback:")
                                    logger.error(traceback.format_exc())
                            
                            if successful_checks > 0:
                                logger.info(f"✅ Successfully applied {successful_checks} CHECK constraints")
                            if failed_checks > 0:
                                logger.warning(f"⚠️ {failed_checks} CHECK constraints could not be applied")
                                logger.warning("   Existing data may violate these constraints")

                        # ✅ CRITICAL: Reset sequences after copying (if handler supports it)
                        if hasattr(actual_handler, 'reset_sequence_after_copy'):
                            for col in creation_schema:
                                if col.get('autoincrement'):
                                    try:
                                        actual_handler.reset_sequence_after_copy(table, col['name'])
                                        logger.debug(f"Reset sequence for {col['name']}")
                                    except Exception as e:
                                        logger.warning(f"Failed to reset sequence for {col['name']}: {e}")
                                        
                        
                        # ✅ COPY TRIGGERS for this table
                        if hasattr(app.config['HANDLER'], 'supports_triggers'):
                            try:
                                if app.config['HANDLER'].supports_triggers():
                                    app.config['HANDLER'].switch_db(old_name)
                                    old_triggers = app.config['HANDLER'].list_triggers(table)
                                    
                                    if old_triggers:
                                        app.config['HANDLER'].switch_db(new_name)
                                        for trigger in old_triggers:
                                            try:
                                                # Extract trigger body from SQL definition
                                                trigger_sql = trigger.get('sql', '')
                                                trigger_body = trigger_sql
                                                
                                                # Try to extract just the body if possible
                                                if 'BEGIN' in trigger_sql.upper() and 'END' in trigger_sql.upper():
                                                    # Extract between BEGIN and END
                                                    match = re.search(r'BEGIN(.+?)END', trigger_sql, re.DOTALL | re.IGNORECASE)
                                                    if match:
                                                        trigger_body = match.group(1).strip()
                                                
                                                # Recreate trigger with new table name
                                                app.config['HANDLER'].create_trigger(
                                                    trigger['name'],
                                                    table,  # New table name
                                                    trigger.get('timing', 'AFTER'),
                                                    trigger.get('event', 'INSERT'),
                                                    trigger_body
                                                )
                                                logger.debug(f"Copied trigger: {trigger['name']}")
                                            except Exception as trig_err:
                                                logger.warning(f"Failed to copy trigger {trigger['name']}: {trig_err}")
                            except Exception as trigger_error:
                                logger.warning(f"Failed to copy triggers for {table}: {trigger_error}")
                        
                        # ✅ COPY INDEXES (non-primary key indexes)
                        try:
                            app.config['HANDLER'].switch_db(old_name)
                            
                            # Use handler method to get indexes (database-agnostic)
                            if hasattr(actual_handler, 'get_table_indexes'):
                                try:
                                    indexes = actual_handler.get_table_indexes(table)
                                    
                                    if indexes:
                                        # Recreate indexes in new database
                                        app.config['HANDLER'].switch_db(new_name)
                                        
                                        for index_info in indexes:
                                            try:
                                                idx_name = index_info['name']
                                                idx_columns = index_info['columns']
                                                is_unique = index_info.get('unique', False)
                                                
                                                # Use handler method to create index (database-agnostic)
                                                if hasattr(actual_handler, 'create_index'):
                                                    actual_handler.create_index(
                                                        table_name=table,
                                                        index_name=idx_name,
                                                        columns=idx_columns,
                                                        unique=is_unique
                                                    )
                                                    logger.debug(f"Copied index: {idx_name}")
                                                else:
                                                    # Fallback: Build CREATE INDEX SQL using handler's quoting
                                                    unique_str = "UNIQUE" if is_unique else ""
                                                    cols_str = ", ".join([actual_handler._quote_identifier(c) for c in idx_columns])
                                                    quoted_table_idx = actual_handler._quote_identifier(table)
                                                    quoted_idx = actual_handler._quote_identifier(idx_name)
                                                    
                                                    create_idx_sql = f"CREATE {unique_str} INDEX {quoted_idx} ON {quoted_table_idx} ({cols_str})"
                                                    with app.config['HANDLER']._get_connection() as conn:
                                                        conn.execute(text(create_idx_sql))
                                                        conn.commit()
                                                    logger.debug(f"Copied index: {idx_name}")
                                                    
                                            except Exception as idx_create_error:
                                                logger.warning(f"Failed to create index {idx_name}: {idx_create_error}")
                                        
                                        app.config['HANDLER'].switch_db(old_name)
                                    else:
                                        logger.debug(f"No indexes found for table {table}")
                                        
                                except Exception as get_idx_error:
                                    logger.debug(f"Failed to get indexes for {table}: {get_idx_error}")
                            else:
                                logger.debug(f"Handler does not support get_table_indexes method")

                        except Exception as idx_error:
                            logger.warning(f"Failed to copy indexes for {table}: {idx_error}")
                            
                        # ✅ COPY FOREIGN KEY CONSTRAINTS (if handler supports it)
                        if hasattr(actual_handler, 'copy_foreign_keys'):
                            try:
                                app.config['HANDLER'].switch_db(old_name)
                                
                                # Get foreign keys from old table
                                old_fks = actual_handler.get_foreign_keys(table)
                                
                                if old_fks:
                                    app.config['HANDLER'].switch_db(new_name)
                                    
                                    for fk in old_fks:
                                        try:
                                            actual_handler.create_foreign_key(
                                                table,
                                                fk['constraint_name'],
                                                fk['column_name'],
                                                fk['foreign_table'],
                                                fk['foreign_column'],
                                                fk.get('on_update', 'NO ACTION'),
                                                fk.get('on_delete', 'NO ACTION')
                                            )
                                            logger.debug(f"Copied FK: {fk['constraint_name']}")
                                        except Exception as fk_err:
                                            logger.warning(f"Failed to copy FK {fk['constraint_name']}: {fk_err}")
                                    
                                    app.config['HANDLER'].switch_db(old_name)
                            except Exception as fk_error:
                                logger.warning(f"Failed to copy foreign keys for {table}: {fk_error}")
                
                    else:
                        # NoSQL: Copy collection
                        data = app.config['HANDLER'].read(table)
                    
                        # Switch to new database
                        app.config['HANDLER'].switch_db(new_name)
                    
                        # Create collection
                        app.config['HANDLER'].create_collection(table)
                    
                        # Get primary key name from handler
                        primary_key = app.config['HANDLER'].get_primary_key_name()
                    
                        # Insert documents
                        for doc in data:
                            # Remove primary key field (it will be auto-generated)
                            clean_doc = {k: v for k, v in doc.items() if k != primary_key}
                            app.config['HANDLER'].insert(table, clean_doc)
                
                    logger.debug(f"Successfully copied: {table}")
                
                # ✅ COPY DATABASE-LEVEL OBJECTS (procedures, functions, views)
                if app.config['DB_TYPE'] == 'sql':
                    try:
                        logger.info("=" * 80)
                        logger.info("COPYING DATABASE-LEVEL OBJECTS (PROCEDURES/FUNCTIONS)")
                        logger.info("=" * 80)
                        
                        handler = app.config['HANDLER']
                        
                        # Check if handler supports procedures (generic check)
                        if hasattr(handler, 'supports_procedures') and handler.supports_procedures():
                            logger.info(f"✅ Handler supports procedures, checking for procedures in {old_name}")
                            
                            # Switch to OLD database to read procedures
                            handler.switch_db(old_name)
                            procedures = handler.list_procedures()
                            
                            logger.info(f"Found {len(procedures)} procedures/functions in {old_name}")
                            
                            if procedures:
                                # Switch to NEW database to create procedures
                                handler.switch_db(new_name)
                                
                                for proc in procedures:
                                    try:
                                        proc_name = proc['name']
                                        proc_type = proc.get('type', 'PROCEDURE').upper()
                                        
                                        logger.info(f"Copying {proc_type}: {proc_name}")
                                        
                                        # Get procedure definition from OLD database
                                        handler.switch_db(old_name)
                                        
                                        if hasattr(handler, 'get_procedure_definition'):
                                            proc_def = handler.get_procedure_definition(proc_name)
                                            
                                            if proc_def:
                                                logger.info(f"Got definition for {proc_name} ({len(proc_def)} chars)")
                                                logger.debug(f"Definition preview: {proc_def[:200]}...")
                                                
                                                # Switch to NEW database to create
                                                handler.switch_db(new_name)
                                                
                                                # Execute the procedure definition
                                                handler.execute_procedure(proc_def)
                                                logger.info(f"✅ Successfully copied {proc_type} '{proc_name}'")
                                            else:
                                                logger.warning(f"⚠️ Could not get definition for {proc_name}")
                                        else:
                                            logger.warning(f"⚠️ Handler does not support get_procedure_definition")
                                            
                                    except Exception as proc_err:
                                        logger.error(f"❌ Failed to copy procedure {proc_name}: {proc_err}")
                                        import traceback
                                        logger.error(traceback.format_exc())
                                        # Continue with other procedures
                                        continue
                                
                                # Switch back to new database
                                handler.switch_db(new_name)
                                logger.info(f"✅ Finished copying procedures")
                            else:
                                logger.info(f"No procedures found in {old_name}")
                        else:
                            logger.info(f"Handler does not support procedures, skipping")
                            
                        # ✅ COPY VIEWS (if handler supports it)
                        if hasattr(actual_handler, 'get_views') and hasattr(actual_handler, 'create_view'):
                            try:
                                logger.info("=" * 80)
                                logger.info("COPYING DATABASE VIEWS")
                                logger.info("=" * 80)
                                
                                handler.switch_db(old_name)
                                views = actual_handler.get_views()
                                
                                logger.info(f"Found {len(views)} views in {old_name}")
                                
                                if views:
                                    handler.switch_db(new_name)
                                    
                                    for view in views:
                                        try:
                                            logger.info(f"Copying view: {view['name']}")
                                            actual_handler.create_view(view['name'], view['definition'])
                                            logger.info(f"✅ Successfully copied view '{view['name']}'")
                                        except Exception as view_err:
                                            logger.error(f"❌ Failed to copy view {view['name']}: {view_err}")
                                            continue
                                    
                                    logger.info(f"✅ Finished copying views")
                                else:
                                    logger.info(f"No views found in {old_name}")
                                    
                            except Exception as view_error:
                                logger.error(f"❌ Failed to copy views: {view_error}")
                    
                    except Exception as db_obj_error:
                        logger.error(f"❌ Failed to copy database-level objects: {db_obj_error}")
                        import traceback
                        logger.error(traceback.format_exc())
                
                # Step 3: Optionally delete old database
                if not keep_old:
                    # Close all connections before delete
                    app.config['HANDLER'].switch_db(new_name)
                    
                    # For certain databases, ensure engine is fully disposed
                    handler = app.config['HANDLER']
                    actual_handler = handler.handler if hasattr(handler, 'handler') else handler
                    db_name_type = actual_handler.DB_NAME if hasattr(actual_handler, 'DB_NAME') else 'SQLite'
                    
                    # ✅ Close and dispose engine completely (SQL databases only)
                    if hasattr(handler, 'engine') and handler.engine:
                        handler.engine.dispose()
                        handler.engine = None
                    
                    # Force garbage collection to release file handles
                    import gc
                    gc.collect()
                    
                    # Platform-aware wait time for file handle release
                    system = platform.system()
                    if system == 'Windows':
                        wait_time = 0.5  # Windows needs more time
                    elif system == 'Darwin':  # macOS
                        wait_time = 0.2
                    else:  # Linux and others
                        wait_time = 0.1
                    
                    time.sleep(wait_time)
                    
                    try:
                        app.config['HANDLER'].delete_db(old_name)
                        logger.debug(f"Deleted old database: {old_name}")
                        
                        # SUCCESS - database renamed without backup
                        return jsonify({
                            'success': True,
                            'message': f'Database renamed from {old_name} to {new_name}',
                            'kept_old': False
                        })
                    except Exception as delete_error:
                        logger.error(f"Failed to delete old database: {delete_error}")
                        # Don't fail the entire operation if delete fails
                        # The rename was successful, just couldn't clean up
                        return jsonify({
                            'success': True,
                            'message': f'Database renamed from {old_name} to {new_name}',
                            'kept_old': True,
                            'warning': f'Note: Could not delete original database ({str(delete_error)}). You may need to manually delete it.'
                        })
                
                # If we kept the old database (keep_old=True)
                return jsonify({
                    'success': True,
                    'message': f'Database renamed from {old_name} to {new_name} (backup kept)',
                    'kept_old': True
                })
                    
            except Exception as e:
                # Rollback: delete the new database if copy failed
                logger.error(f"Copy failed, rolling back: {e}")
                try:
                    app.config['HANDLER'].delete_db(new_name)
                except:
                    pass
                raise Exception(f"Failed to copy data: {str(e)}")
        
        except Exception as e:
            logger.error(f"❌ API call failed: /api/databases/rename - {e}")
            return jsonify({'success': False, 'error': str(e)}), 500
        
    @app.route('/api/databases/convert', methods=['POST'])
    def api_convert_database():
        """JSON API: Convert database to different type/handler - streams progress"""
        # ✅ CRITICAL: Get request data BEFORE generator function
        try:
            request_data = request.get_json()
            source_db = request_data.get('source_db')
            target_db_name = request_data.get('target_db_name')
            target_type = request_data.get('target_type')
            target_handler = request_data.get('target_handler')
        except Exception as e:
            logger.error(f"❌ Failed to parse request: {e}")
            return jsonify({'success': False, 'error': 'Invalid request data'}), 400
        
        def generate():
            try:
                logger.debug(f"✅ API call: POST /api/databases/convert")
                logger.debug(f"   Source: {source_db}, Target: {target_db_name}, Type: {target_type}, Handler: {target_handler}")
                
                # Validate inputs
                if not all([source_db, target_db_name, target_type, target_handler]):
                    yield send_sse_message({'error': 'Missing required parameters'})
                    return
                
                if not re.match(r'^[a-zA-Z][a-zA-Z0-9_]*$', target_db_name):
                    yield send_sse_message({'error': 'Target database name must start with a letter, contain only letters, numbers, underscores.'})
                    return
                
                # Check if target name already exists in BOTH SQL and NoSQL
                current_handler = app.config['HANDLER']
                current_type = app.config['DB_TYPE']
                
                # Check in current type
                if target_db_name in current_handler.list_dbs():
                    yield send_sse_message({'error': f'Database {target_db_name} already exists in current handler'})
                    return
                
                # Check in target type if different
                if target_type != current_type:
                    # Temporarily switch to target handler to check
                    if target_type == 'sql':
                        temp_handler = SQLHandler(target_handler)
                    else:
                        temp_handler = NoSQLHandler(target_handler)
                    
                    if target_db_name in temp_handler.list_dbs():
                        yield send_sse_message({'error': f'Database {target_db_name} already exists in target handler'})
                        return
                
                # Step 1: Export from source database (JSON format)
                logger.info(f"Step 1: Exporting {source_db} as JSON")
                yield send_sse_message({'progress': 5, 'stage': 'export', 'message': 'Starting export...'})
                
                try:
                    current_handler.switch_db(source_db)
                    
                    export_data = {
                        'metadata': {
                            'database_name': source_db,
                            'export_date': time.strftime('%Y-%m-%d %H:%M:%S'),
                            'db_type': current_type,
                            'handler': app.config['CURRENT_HANDLER_NAME'],
                            'version': '1.0'
                        },
                        'tables': []
                    }
                    
                    tables = current_handler.list_tables()
                    total_tables = len(tables)
                    
                    if total_tables == 0:
                        yield send_sse_message({'error': 'Source database is empty'})
                        return
                    
                    for idx, table in enumerate(tables):
                        # Yield progress
                        progress = 5 + int((idx / total_tables) * 45)  # 5-50% for export
                        yield send_sse_message({'progress': progress, 'stage': 'export', 'current': table, 'message': f'Exporting {table}...'})
                        
                        table_data = {
                            'name': table,
                            'schema': [],
                            'data': [],
                            'constraints': {},
                            'triggers': []
                        }
                        
                        # Get schema (SQL only)
                        if current_type == 'sql':
                            schema = current_handler.get_table_schema(table)
                            for col in schema:
                                col_export = {
                                    'name': col['name'],
                                    'type': col['type'],
                                    'nullable': not col.get('notnull', False),
                                    'primary_key': col.get('pk', False),
                                    'autoincrement': col.get('autoincrement', False),
                                    'unique': col.get('unique', False),
                                    'check_constraint': None
                                }
                                
                                if col.get('check_constraint'):
                                    check_expr = col['check_constraint']
                                    col_export['check_constraint'] = check_expr
                                    
                                    parsed_rules = _parse_check_to_validation(check_expr, col['name'])
                                    if parsed_rules:
                                        col_export['validation_rules'] = parsed_rules
                                
                                table_data['schema'].append(col_export)
                        
                        # Get data
                        rows = current_handler.read(table)
                        table_data['data'] = rows
                        
                        # Get constraints
                        if hasattr(current_handler, 'supports_check_constraints') and current_handler.supports_check_constraints():
                            if hasattr(current_handler, 'get_check_constraints'):
                                checks = current_handler.get_check_constraints(table)
                                if checks:
                                    normalized_checks = []
                                    for check in checks:
                                        normalized = {
                                            'column': check.get('column'),
                                            'expression': check.get('expression')
                                        }
                                        
                                        if check.get('expression'):
                                            parsed = _parse_validation_expression(check['expression'])
                                            if parsed:
                                                normalized['validation_rules'] = parsed
                                        
                                        normalized_checks.append(normalized)
                                    
                                    table_data['constraints']['check'] = normalized_checks
                        
                        # Get triggers
                        if hasattr(current_handler, 'supports_triggers') and current_handler.supports_triggers():
                            triggers = current_handler.list_triggers(table)
                            for trigger in triggers:
                                table_data['triggers'].append({
                                    'name': trigger['name'],
                                    'timing': trigger.get('timing'),
                                    'event': trigger.get('event'),
                                    'body': trigger.get('sql')
                                })
                        
                        export_data['tables'].append(table_data)
                    
                    # Add procedures (database-level)
                    if hasattr(current_handler, 'supports_procedures') and current_handler.supports_procedures():
                        procedures = current_handler.list_procedures()
                        export_data['procedures'] = []
                        for proc in procedures:
                            proc_data = {
                                'name': proc['name'],
                                'type': proc.get('type'),
                                'definition': None
                            }
                            if hasattr(current_handler, 'get_procedure_definition'):
                                proc_data['definition'] = current_handler.get_procedure_definition(proc['name'])
                            export_data['procedures'].append(proc_data)
                    
                    logger.info(f"Export complete: {len(export_data['tables'])} tables")
                    yield send_sse_message({'progress': 50, 'stage': 'export', 'message': 'Export complete'})
                    
                except Exception as export_error:
                    logger.error(f"Export failed: {export_error}")
                    yield send_sse_message({'error': f'Export failed: {str(export_error)}'})
                    return
                
                # Step 2: Switch to target handler
                logger.info(f"Step 2: Switching to target handler ({target_type}/{target_handler})")
                yield send_sse_message({'progress': 55, 'stage': 'switch', 'message': 'Switching database handler...'})
                
                try:
                    # Switch handler
                    app.config['DB_TYPE'] = target_type
                    app.config['CURRENT_HANDLER_NAME'] = target_handler
                    
                    if target_type == 'sql':
                        app.config['HANDLER'] = SQLHandler(target_handler)
                    else:
                        app.config['HANDLER'] = NoSQLHandler(target_handler)
                    
                    target_handler_obj = app.config['HANDLER']
                    
                    # Create target database
                    target_handler_obj.create_db(target_db_name)
                    target_handler_obj.switch_db(target_db_name)
                    
                    logger.info(f"Created target database: {target_db_name}")
                    yield send_sse_message({'progress': 60, 'stage': 'switch', 'message': f'Created database {target_db_name}'})
                    
                except Exception as switch_error:
                    logger.error(f"Handler switch failed: {switch_error}")
                    yield send_sse_message({'error': f'Failed to switch handler: {str(switch_error)}'})
                    return
                
                # Step 3: Import into target database (reuse existing import logic)
                logger.info(f"Step 3: Importing into {target_db_name}")
                yield send_sse_message({'progress': 65, 'stage': 'import', 'message': 'Starting import...'})
                
                try:
                    total_tables = len(export_data['tables'])
                    
                    if target_type == 'sql':
                        actual_handler = target_handler_obj.handler if hasattr(target_handler_obj, 'handler') else target_handler_obj
                        db_handler_name = actual_handler.DB_NAME if hasattr(actual_handler, 'DB_NAME') else 'SQLite'
                        
                        if db_handler_name in ['DuckDB', 'PostgreSQL']:
                            with target_handler_obj.engine.begin() as conn:
                                for idx, table_data in enumerate(export_data['tables']):
                                    progress = 65 + int((idx / total_tables) * 30)  # 65-95%
                                    yield send_sse_message({'progress': progress, 'stage': 'import', 'current': table_data['name'], 'message': f'Importing {table_data["name"]}...'})
                                    
                                    table_name = table_data['name']
                                    
                                    if db_handler_name == 'PostgreSQL':
                                        table_name = table_name.lower()
                                        table_data['name'] = table_name
                                    
                                    # Create table
                                    if table_data.get('schema') and len(table_data.get('schema', [])) > 0:
                                        normalized_schema = []
                                        for col in table_data['schema']:
                                            col_copy = col.copy()
                                            original_type = col['type']
                                            normalized_type = _normalize_datatype(original_type, target_handler_obj)
                                            col_copy['type'] = normalized_type
                                            if original_type != normalized_type:
                                                logger.info(f"Normalized type for {col['name']}: {original_type} -> {normalized_type}")
                                            normalized_schema.append(col_copy)
                                        _create_table_from_schema(target_handler_obj, table_name, normalized_schema, conn)
                                    else:
                                        if table_data.get('data') and len(table_data['data']) > 0:
                                            inferred_schema = _infer_schema_from_data(table_data['data'], table_name)
                                            _create_table_from_schema(target_handler_obj, table_name, inferred_schema, conn)
                                    
                                    # Insert data
                                    if hasattr(actual_handler, '_quote_identifier'):
                                        quoted_table = actual_handler._quote_identifier(table_name)
                                    else:
                                        quoted_table = f'"{table_name}"'
                                    
                                    for row in table_data.get('data', []):
                                        clean_row = {k: v for k, v in row.items() if k not in ['_id', 'doc_id']}
                                        if not clean_row:
                                            continue
                                        
                                        serialized_row = {}
                                        for k, v in clean_row.items():
                                            if v is None:
                                                serialized_row[k] = None
                                            elif isinstance(v, (dict, list)):
                                                serialized_row[k] = json.dumps(v)
                                            else:
                                                serialized_row[k] = v
                                        
                                        columns = list(serialized_row.keys())
                                        if hasattr(actual_handler, '_quote_identifier'):
                                            quoted_cols = ', '.join([actual_handler._quote_identifier(k) for k in columns])
                                        else:
                                            quoted_cols = ', '.join([f'"{k}"' for k in columns])
                                        
                                        placeholders = ', '.join([f':{k}' for k in columns])
                                        insert_stmt = f"INSERT INTO {quoted_table} ({quoted_cols}) VALUES ({placeholders})"
                                        conn.execute(text(insert_stmt), serialized_row)
                                    
                                    # Import triggers
                                    if hasattr(target_handler_obj, 'supports_triggers') and target_handler_obj.supports_triggers():
                                        for trigger in table_data.get('triggers', []):
                                            try:
                                                trigger_name = trigger['name']
                                                trigger_timing = trigger.get('timing', 'AFTER')
                                                trigger_event = trigger.get('event', 'INSERT')
                                                trigger_body = trigger.get('body', '')
                                                
                                                if trigger_body.strip().upper().startswith('BEGIN'):
                                                    match = re.search(r'BEGIN\s+(.*?)\s+END', trigger_body, re.DOTALL | re.IGNORECASE)
                                                    if match:
                                                        trigger_body = match.group(1).strip()
                                                
                                                actual_handler = target_handler_obj.handler if hasattr(target_handler_obj, 'handler') else target_handler_obj
                                                if hasattr(actual_handler, 'convert_trigger_syntax'):
                                                    trigger_body = actual_handler.convert_trigger_syntax(
                                                        trigger_body, trigger_event, table_name
                                                    )
                                                
                                                if hasattr(actual_handler, 'create_trigger_in_transaction'):
                                                    actual_handler.create_trigger_in_transaction(
                                                        conn, trigger_name, table_name, trigger_timing, trigger_event, trigger_body
                                                    )
                                                else:
                                                    logger.warning(f"Handler lacks create_trigger_in_transaction, using regular create_trigger")
                                                    target_handler_obj.create_trigger(
                                                        trigger_name, table_name, trigger_timing, trigger_event, trigger_body
                                                    )
                                                
                                                logger.info(f"✅ Imported trigger: {trigger_name}")
                                            except Exception as trig_err:
                                                logger.warning(f"⚠️ Failed to import trigger {trigger.get('name')}: {trig_err}")
                                    
                                    # Apply CHECK constraints
                                    check_constraints_to_apply = []
                                    
                                    if table_data.get('constraints', {}).get('check'):
                                        for check in table_data['constraints']['check']:
                                            col_name = check.get('column')
                                            
                                            validation_rules = check.get('validation_rules')
                                            if validation_rules:
                                                check_expr = _validation_to_check(validation_rules, col_name)
                                                if check_expr:
                                                    # ✅ MySQL: Clean CHECK expression
                                                    if db_handler_name == 'MySQL':
                                                        # Remove PostgreSQL type casts
                                                        check_expr = re.sub(r'::\s*[a-zA-Z_][a-zA-Z0-9_]*(?:\s*\[\s*\])?', '', check_expr)
                                                        check_expr = re.sub(r'::[^\s\),\]]+', '', check_expr)
                                                        
                                                        # Convert ARRAY to IN
                                                        if 'ARRAY[' in check_expr or '= ANY' in check_expr.upper():
                                                            array_match = re.search(r'ARRAY\s*\[\s*(.*?)\s*\]', check_expr, re.DOTALL | re.IGNORECASE)
                                                            if array_match:
                                                                values = re.findall(r"'([^']*)'", array_match.group(1))
                                                                if values:
                                                                    mysql_in = "IN (" + ", ".join([f"'{v}'" for v in values]) + ")"
                                                                    check_expr = re.sub(
                                                                        r'=\s*ANY\s*\(\s*\(?\s*ARRAY\s*\[.*?\]\s*\)?\s*\)',
                                                                        mysql_in,
                                                                        check_expr,
                                                                        flags=re.DOTALL | re.IGNORECASE
                                                                    )
                                                        
                                                        # Remove quotes from column name
                                                        check_expr = check_expr.replace(f'"{col_name}"', col_name).replace(f'`{col_name}`', col_name)
                                                    
                                                    check_constraints_to_apply.append({
                                                        'column': col_name,
                                                        'expression': check_expr
                                                    })
                                            elif check.get('expression'):
                                                parsed = _parse_validation_expression(check['expression'])
                                                if parsed:
                                                    check_expr = _validation_to_check(parsed, col_name)
                                                    if check_expr:
                                                        # ✅ MySQL: Clean CHECK expression
                                                        if db_handler_name == 'MySQL':
                                                            # Remove PostgreSQL type casts
                                                            check_expr = re.sub(r'::\s*[a-zA-Z_][a-zA-Z0-9_]*(?:\s*\[\s*\])?', '', check_expr)
                                                            check_expr = re.sub(r'::[^\s\),\]]+', '', check_expr)
                                                            
                                                            # Convert ARRAY to IN
                                                            if 'ARRAY[' in check_expr or '= ANY' in check_expr.upper():
                                                                array_match = re.search(r'ARRAY\s*\[\s*(.*?)\s*\]', check_expr, re.DOTALL | re.IGNORECASE)
                                                                if array_match:
                                                                    values = re.findall(r"'([^']*)'", array_match.group(1))
                                                                    if values:
                                                                        mysql_in = "IN (" + ", ".join([f"'{v}'" for v in values]) + ")"
                                                                        check_expr = re.sub(
                                                                            r'=\s*ANY\s*\(\s*\(?\s*ARRAY\s*\[.*?\]\s*\)?\s*\)',
                                                                            mysql_in,
                                                                            check_expr,
                                                                            flags=re.DOTALL | re.IGNORECASE
                                                                        )
                                                            
                                                            # Remove quotes from column name
                                                            check_expr = check_expr.replace(f'"{col_name}"', col_name).replace(f'`{col_name}`', col_name)
                                                        
                                                        check_constraints_to_apply.append({
                                                            'column': col_name,
                                                            'expression': check_expr
                                                        })
                                    
                                    # Apply CHECK constraints AFTER data copy
                                    if check_constraints_to_apply and not getattr(actual_handler, 'check_constraints_inline', lambda: False)():
                                        logger.info(f"Found {len(check_constraints_to_apply)} CHECK constraints to apply to {table_name}")
                                        for check_info in check_constraints_to_apply:
                                            logger.info(f"  - Column '{check_info['column']}': {check_info['expression']}")
                                        
                                        if hasattr(target_handler_obj, 'supports_check_constraints') and target_handler_obj.supports_check_constraints():
                                            successful_checks = 0
                                            failed_checks = 0
                                            
                                            for check_info in check_constraints_to_apply:
                                                try:
                                                    logger.info(f"Applying CHECK constraint to {table_name}.{check_info['column']}")
                                                    
                                                    if hasattr(actual_handler, 'add_check_constraint_to_existing_table'):
                                                        actual_handler.add_check_constraint_to_existing_table(
                                                            table_name,
                                                            check_info['column'],
                                                            check_info['expression'],
                                                            conn
                                                        )
                                                        successful_checks += 1
                                                        logger.info(f"✅ Successfully applied CHECK on {check_info['column']}")
                                                except Exception as check_err:
                                                    failed_checks += 1
                                                    logger.error(f"❌ Failed to apply CHECK on {check_info['column']}: {check_err}")
                                                    import traceback
                                                    logger.error(f"Traceback: {traceback.format_exc()}")
                                            
                                            logger.info(f"CHECK constraint summary: {successful_checks} succeeded, {failed_checks} failed")
                        
                        else:
                            # Other SQL databases - same logic as above
                            with target_handler_obj._get_connection() as conn:
                                # ✅ Don't use explicit BEGIN for handlers that manage transactions
                                if db_handler_name not in ['DuckDB']:
                                    conn.execute(text("BEGIN"))
                                
                                try:
                                    for idx, table_data in enumerate(export_data['tables']):
                                        progress = 65 + int((idx / total_tables) * 30)
                                        yield send_sse_message({'progress': progress, 'stage': 'import', 'current': table_data['name'], 'message': f'Importing {table_data["name"]}...'})
                                        
                                        table_name = table_data['name']
                                        
                                        if table_data.get('schema') and len(table_data.get('schema', [])) > 0:
                                            normalized_schema = []
                                            for col in table_data['schema']:
                                                col_copy = col.copy()
                                                original_type = col['type']
                                                normalized_type = _normalize_datatype(original_type, target_handler_obj)
                                                col_copy['type'] = normalized_type
                                                normalized_schema.append(col_copy)
                                            _create_table_from_schema(target_handler_obj, table_name, normalized_schema, conn)
                                        else:
                                            if table_data.get('data') and len(table_data['data']) > 0:
                                                inferred_schema = _infer_schema_from_data(table_data['data'], table_name)
                                                _create_table_from_schema(target_handler_obj, table_name, inferred_schema, conn)
                                        
                                        # Insert data - same as above
                                        actual_handler = target_handler_obj.handler if hasattr(target_handler_obj, 'handler') else target_handler_obj
                                        if hasattr(actual_handler, '_quote_identifier'):
                                            quoted_table = actual_handler._quote_identifier(table_name)
                                        else:
                                            quoted_table = f'"{table_name}"'
                                        
                                        for row in table_data.get('data', []):
                                            clean_row = {k: v for k, v in row.items() if k not in ['_id', 'doc_id']}
                                            if not clean_row:
                                                continue
                                            
                                            serialized_row = {}
                                            for k, v in clean_row.items():
                                                if v is None:
                                                    serialized_row[k] = None
                                                elif isinstance(v, (dict, list)):
                                                    serialized_row[k] = json.dumps(v)
                                                else:
                                                    serialized_row[k] = v
                                            
                                            columns = list(serialized_row.keys())
                                            if hasattr(actual_handler, '_quote_identifier'):
                                                quoted_cols = ', '.join([actual_handler._quote_identifier(k) for k in columns])
                                            else:
                                                quoted_cols = ', '.join([f'"{k}"' for k in columns])
                                            
                                            placeholders = ', '.join([f':{k}' for k in columns])
                                            insert_stmt = f"INSERT INTO {quoted_table} ({quoted_cols}) VALUES ({placeholders})"
                                            conn.execute(text(insert_stmt), serialized_row)
                                        
                                        # ✅ CRITICAL: Apply CHECK constraints AFTER data copy (MySQL/SQLite)
                                        check_constraints_to_apply = []

                                        if table_data.get('constraints', {}).get('check'):
                                            for check in table_data['constraints']['check']:
                                                col_name = check.get('column')
                                                
                                                validation_rules = check.get('validation_rules')
                                                if validation_rules:
                                                    check_expr = _validation_to_check(validation_rules, col_name)
                                                    if check_expr:
                                                        # ✅ MySQL: Clean CHECK expression
                                                        if db_handler_name == 'MySQL':
                                                            # Remove PostgreSQL type casts
                                                            check_expr = re.sub(r'::\s*[a-zA-Z_][a-zA-Z0-9_]*(?:\s*\[\s*\])?', '', check_expr)
                                                            check_expr = re.sub(r'::[^\s\),\]]+', '', check_expr)
                                                            
                                                            # Convert ARRAY to IN
                                                            if 'ARRAY[' in check_expr or '= ANY' in check_expr.upper():
                                                                array_match = re.search(r'ARRAY\s*\[\s*(.*?)\s*\]', check_expr, re.DOTALL | re.IGNORECASE)
                                                                if array_match:
                                                                    values = re.findall(r"'([^']*)'", array_match.group(1))
                                                                    if values:
                                                                        mysql_in = "IN (" + ", ".join([f"'{v}'" for v in values]) + ")"
                                                                        check_expr = re.sub(
                                                                            r'=\s*ANY\s*\(\s*\(?\s*ARRAY\s*\[.*?\]\s*\)?\s*\)',
                                                                            mysql_in,
                                                                            check_expr,
                                                                            flags=re.DOTALL | re.IGNORECASE
                                                                        )
                                                            
                                                            # Remove quotes from column name
                                                            check_expr = check_expr.replace(f'"{col_name}"', col_name).replace(f'`{col_name}`', col_name)
                                                        
                                                        check_constraints_to_apply.append({
                                                            'column': col_name,
                                                            'expression': check_expr
                                                        })
                                                elif check.get('expression'):
                                                    parsed = _parse_validation_expression(check['expression'])
                                                    if parsed:
                                                        check_expr = _validation_to_check(parsed, col_name)
                                                        if check_expr:
                                                            # ✅ MySQL: Clean CHECK expression
                                                            if db_handler_name == 'MySQL':
                                                                check_expr = re.sub(r'::\s*[a-zA-Z_][a-zA-Z0-9_]*(?:\s*\[\s*\])?', '', check_expr)
                                                                check_expr = re.sub(r'::[^\s\),\]]+', '', check_expr)
                                                                
                                                                if 'ARRAY[' in check_expr or '= ANY' in check_expr.upper():
                                                                    array_match = re.search(r'ARRAY\s*\[\s*(.*?)\s*\]', check_expr, re.DOTALL | re.IGNORECASE)
                                                                    if array_match:
                                                                        values = re.findall(r"'([^']*)'", array_match.group(1))
                                                                        if values:
                                                                            mysql_in = "IN (" + ", ".join([f"'{v}'" for v in values]) + ")"
                                                                            check_expr = re.sub(
                                                                                r'=\s*ANY\s*\(\s*\(?\s*ARRAY\s*\[.*?\]\s*\)?\s*\)',
                                                                                mysql_in,
                                                                                check_expr,
                                                                                flags=re.DOTALL | re.IGNORECASE
                                                                            )
                                                                
                                                                check_expr = check_expr.replace(f'"{col_name}"', col_name).replace(f'`{col_name}`', col_name)
                                                            
                                                            check_constraints_to_apply.append({
                                                                'column': col_name,
                                                                'expression': check_expr
                                                            })
                                        
                                        # Apply all collected CHECK constraints
                                        if check_constraints_to_apply:
                                            logger.info(f"Attempting to apply {len(check_constraints_to_apply)} CHECK constraints to {table_name}")
                                            
                                            # ✅ CRITICAL FIX: For MySQL and SQLite, commit transaction FIRST
                                            if db_handler_name in ['MySQL', 'SQLite']:
                                                conn.commit()
                                                logger.debug(f"Committed transaction before applying CHECK constraints for {db_handler_name}")
                                            
                                            if hasattr(target_handler_obj, 'supports_check_constraints') and target_handler_obj.supports_check_constraints():
                                                successful = 0
                                                failed = 0
                                                
                                                for check_info in check_constraints_to_apply:
                                                    try:
                                                        if hasattr(target_handler_obj, 'add_check_constraint_to_existing_table'):
                                                            actual_handler = target_handler_obj.handler if hasattr(target_handler_obj, 'handler') else target_handler_obj
                                                            
                                                            # For MySQL and SQLite, DON'T pass conn
                                                            if db_handler_name in ['MySQL', 'SQLite']:
                                                                actual_handler.add_check_constraint_to_existing_table(
                                                                    table_name,
                                                                    check_info['column'],
                                                                    check_info['expression']
                                                                )
                                                            else:
                                                                actual_handler.add_check_constraint_to_existing_table(
                                                                    table_name,
                                                                    check_info['column'],
                                                                    check_info['expression'],
                                                                    conn
                                                                )
                                                            successful += 1
                                                        elif hasattr(target_handler_obj, 'create_check_constraint'):
                                                            target_handler_obj.create_check_constraint(
                                                                table_name,
                                                                check_info['column'],
                                                                check_info['expression']
                                                            )
                                                            successful += 1
                                                    except Exception as check_err:
                                                        failed += 1
                                                        logger.warning(f"⚠️ Could not apply CHECK on {check_info['column']}: {check_err}")
                                                
                                                if successful > 0:
                                                    logger.info(f"✅ Successfully applied {successful}/{len(check_constraints_to_apply)} CHECK constraints")
                                                if failed > 0:
                                                    logger.warning(f"⚠️ Failed to apply {failed}/{len(check_constraints_to_apply)} CHECK constraints")
                                            else:
                                                logger.warning(f"⚠️ Handler does not support CHECK constraints")
                                    
                                    # ✅ CRITICAL FIX: Final commit for all databases
                                    if db_handler_name == 'DuckDB':
                                        # DuckDB auto-commits
                                        pass
                                    else:
                                        # Final commit (safe even if already committed earlier)
                                        try:
                                            conn.commit()
                                            logger.debug(f"Final commit for {db_handler_name}")
                                        except Exception as e:
                                            logger.debug(f"Final commit unnecessary (already committed): {e}")
                            
                                except Exception as e:
                                    if db_handler_name != 'DuckDB':
                                        conn.execute(text("ROLLBACK"))
                                    raise e
                    
                    else:
                        # NoSQL import
                        for idx, table_data in enumerate(export_data['tables']):
                            progress = 65 + int((idx / total_tables) * 30)
                            yield send_sse_message({'progress': progress, 'stage': 'import', 'current': table_data['name'], 'message': f'Importing {table_data["name"]}...'})
                            
                            collection_name = table_data['name']
                            
                            try:
                                target_handler_obj.create_collection(collection_name)
                            except Exception as create_err:
                                logger.debug(f"Collection {collection_name} might already exist: {create_err}")
                            
                            primary_key = target_handler_obj.get_primary_key_name() if hasattr(target_handler_obj, 'get_primary_key_name') else None
                            
                            for doc in table_data.get('data', []):
                                clean_doc = doc.copy()
                                
                                if primary_key and primary_key in clean_doc:
                                    del clean_doc[primary_key]
                                if '_id' in clean_doc and clean_doc['_id'] is None:
                                    del clean_doc['_id']
                                
                                if not clean_doc:
                                    continue
                                
                                target_handler_obj.insert(collection_name, clean_doc)
                            
                            # ✅ CRITICAL FIX: Actually apply validation rules from CHECK constraints
                            check_constraints = table_data.get('constraints', {}).get('check', [])
                            if check_constraints and hasattr(target_handler_obj, 'apply_validation_rules'):
                                logger.info(f"Found {len(check_constraints)} CHECK constraints to convert for {collection_name}")
                                validation_rules = {}
                                
                                for constraint in check_constraints:
                                    col_name = constraint.get('column')
                                    
                                    # Try validation_rules field first (already parsed)
                                    if constraint.get('validation_rules'):
                                        validation_rules[col_name] = constraint['validation_rules']
                                        logger.debug(f"Using pre-parsed rules for {col_name}: {constraint['validation_rules']}")
                                    # Otherwise parse expression
                                    elif constraint.get('expression'):
                                        parsed = _parse_validation_expression(constraint['expression'])
                                        if parsed:
                                            validation_rules[col_name] = parsed
                                            logger.debug(f"Parsed rules for {col_name}: {parsed}")
                                
                                if validation_rules:
                                    try:
                                        logger.info(f"Applying {len(validation_rules)} validation rules to {collection_name}")
                                        for field, rules in validation_rules.items():
                                            logger.info(f"  {field}: {rules}")
                                        
                                        target_handler_obj.apply_validation_rules(collection_name, validation_rules)
                                        logger.info(f"✅ Successfully applied validation rules to {collection_name}")
                                    except Exception as val_err:
                                        logger.error(f"❌ Failed to apply validation rules to {collection_name}: {val_err}")
                                        import traceback
                                        logger.error(traceback.format_exc())
                                        # Don't fail the entire import - continue with warning
                    
                    # Import procedures
                    yield send_sse_message({'progress': 95, 'stage': 'import', 'message': 'Importing procedures...'})
                    if hasattr(target_handler_obj, 'supports_procedures') and target_handler_obj.supports_procedures():
                        for proc in export_data.get('procedures', []):
                            try:
                                proc_def = proc.get('definition', '').strip()
                                if not proc_def:
                                    continue
                                
                                proc_name = proc.get('name')
                                proc_type = proc.get('type', 'PROCEDURE')
                                
                                proc_def = re.sub(r'::[A-Z]+(::[A-Z]+)?', '', proc_def)
                                proc_def = re.sub(r'::+', '', proc_def)
                                proc_def = proc_def.replace(':=', '=')
                                
                                actual_handler = target_handler_obj.handler if hasattr(target_handler_obj, 'handler') else target_handler_obj
                                if hasattr(actual_handler, 'convert_procedure_syntax'):
                                    converted_def = actual_handler.convert_procedure_syntax(
                                        proc_def, proc_name, proc_type
                                    )
                                else:
                                    converted_def = proc_def
                                
                                target_handler_obj.execute_procedure(converted_def)
                                logger.info(f"✅ Imported {proc_type}: {proc_name}")
                            except Exception as proc_err:
                                logger.warning(f"⚠️ Failed to import procedure {proc.get('name')}: {proc_err}")
                    
                    yield send_sse_message({'progress': 100, 'stage': 'complete', 'target_db': target_db_name, 'message': 'Conversion complete!'})
                    logger.info(f"✅ Conversion complete: {source_db} -> {target_db_name}")
                    
                except Exception as import_error:
                    logger.error(f"Import failed: {import_error}")
                    import traceback
                    logger.error(traceback.format_exc())
                    yield send_sse_message({'error': f'Import failed: {str(import_error)}'})
                    return
            
            except Exception as e:
                logger.error(f"❌ Conversion failed: {e}")
                import traceback
                logger.error(traceback.format_exc())
                yield send_sse_message({'error': str(e)})
        
        return Response(generate(), mimetype='text/event-stream')
    
    @app.route('/api/databases/convert/stream', methods=['POST'])
    def api_convert_database_stream():
        """Streaming version of database conversion"""
        return Response(api_convert_database(), mimetype='text/event-stream')
    
    @app.route('/api/available_handlers', methods=['GET'])
    def api_available_handlers():
        """JSON API: Get all available SQL and NoSQL handlers"""
        try:
            logger.debug(f"✅ API call: GET /api/available_handlers")
            
            sql_handlers = list(DBRegistry.get_sql_handlers().keys())
            nosql_handlers = list(DBRegistry.get_nosql_handlers().keys())
            
            return jsonify({
                'success': True,
                'sql': sql_handlers,
                'nosql': nosql_handlers
            })
        except Exception as e:
            logger.error(f"❌ Failed to get handlers: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500
        
    @app.route('/api/db/<db_name>/table/<table_name>/rename', methods=['POST'])
    def api_rename_table(db_name, table_name):
        """JSON API: Rename/copy table by copying to new name"""
        try:
            data = request.get_json()
            new_name = data.get('new_name')
            keep_old = data.get('keep_old', False)
            
            logger.debug(f"✅ API call: POST /api/db/{db_name}/table/{table_name}/rename - new={new_name}, keep_old={keep_old}")
            
            # Validate inputs
            if not new_name:
                return jsonify({'success': False, 'error': 'New name is required'}), 400
            
            if not re.match(r'^[a-zA-Z][a-zA-Z0-9_]*$', new_name):
                return jsonify({
                    'success': False, 
                    'error': 'New name must start with a letter, contain only letters, numbers, underscores.'
                }), 400
            
            app.config['HANDLER'].switch_db(db_name)
            
            # Check if new name already exists
            existing_tables = app.config['HANDLER'].list_tables()
            if new_name in existing_tables:
                return jsonify({'success': False, 'error': f'Table {new_name} already exists'}), 400
            
            # Get handler
            handler = app.config['HANDLER']
            
            if app.config['DB_TYPE'] == 'sql':
                # SQL: Use handler's copy_table method if available
                if hasattr(handler, 'copy_table'):
                    handler.copy_table(table_name, new_name)
                else:
                    # Fallback: manual copy
                    schema = handler.get_table_schema(table_name)
                    data_rows = handler.read(table_name)
                    
                    # Build CREATE TABLE WITHOUT CHECK constraints first
                    actual_handler = handler.handler if hasattr(handler, 'handler') else handler

                    # Remove CHECK constraints temporarily
                    schema_no_checks = []
                    table_check_constraints = []

                    for col in schema:
                        col_copy = col.copy()
                        if col_copy.get('check_constraint'):
                            table_check_constraints.append({
                                'column': col_copy['name'],
                                'expression': col_copy['check_constraint']
                            })
                            col_copy['check_constraint'] = None  # Critical: Remove for table creation
                        schema_no_checks.append(col_copy)

                    # ✅ Build columns WITHOUT checks
                    columns_def = actual_handler.build_column_definitions(schema_no_checks, quote=False)
                    
                    if not isinstance(columns_def, (list, tuple)):
                        raise TypeError(
                            f"build_column_definitions() must return a list, got {type(columns_def)} → {columns_def}"
                        )

                    col_def_str = ', '.join(columns_def)
                    
                    # Quote table names
                    if hasattr(actual_handler, '_quote_identifier'):
                        quoted_new = actual_handler._quote_identifier(new_name)
                    else:
                        quoted_new = f'"{new_name}"'
                    
                    # Create new table
                    with handler._get_connection() as conn:
                        create_sql = f"CREATE TABLE {quoted_new} ({col_def_str})"
                        conn.execute(text(create_sql))
                        conn.commit()
                    
                    # Copy data (skip autoincrement columns)
                    for row in data_rows:
                        filtered_row = {}
                        for col in schema:
                            if col.get('autoincrement', False):
                                continue
                            if col['name'] in row:
                                filtered_row[col['name']] = row[col['name']]
                        
                        if filtered_row:
                            handler.insert(new_name, filtered_row)
                    
                    # Reset sequences if needed
                    if hasattr(actual_handler, 'reset_sequence_after_copy'):
                        for col in schema:
                            if col.get('autoincrement'):
                                try:
                                    actual_handler.reset_sequence_after_copy(new_name, col['name'])
                                except Exception as e:
                                    logger.warning(f"Failed to reset sequence: {e}")
                                    
                    # ✅ Apply CHECK constraints AFTER data copy
                    if table_check_constraints and hasattr(actual_handler, 'supports_check_constraints'):
                        try:
                            if actual_handler.supports_check_constraints():
                                successful_checks = 0
                                failed_checks = 0
                                
                                for check_info in table_check_constraints:
                                    try:
                                        if hasattr(actual_handler, 'create_check_constraint'):
                                            actual_handler.create_check_constraint(
                                                new_name, 
                                                check_info['column'], 
                                                check_info['expression']
                                            )
                                            logger.debug(f"✅ Applied CHECK: {check_info['column']} -> {check_info['expression']}")
                                            successful_checks += 1
                                    except Exception as check_err:
                                        failed_checks += 1
                                        logger.warning(f"⚠️ CHECK constraint failed for {check_info['column']}: {check_err}")
                                        logger.warning(f"   Expression: {check_info['expression']}")
                                
                                if failed_checks > 0:
                                    logger.warning(f"⚠️ {failed_checks} CHECK constraints could not be applied to {new_name}")
                                    logger.warning("   Existing data may violate these constraints")
                        except Exception as e:
                            logger.warning(f"Failed to apply CHECK constraints to {new_name}: {e}")
                    
                    # Copy triggers if supported
                    if hasattr(handler, 'copy_triggers'):
                        try:
                            handler.copy_triggers(table_name, new_name)
                        except Exception as e:
                            logger.warning(f"Failed to copy triggers: {e}")
            else:
                # NoSQL: Use handler's copy_table method if available (preserves validation)
                if hasattr(handler, 'copy_table'):
                    try:
                        handler.copy_table(table_name, new_name)
                        logger.info(f"✅ Successfully copied {table_name} to {new_name} using handler's copy_table")
                    except Exception as copy_err:
                        logger.error(f"Handler's copy_table failed: {copy_err}")
                        raise
                else:
                    # Fallback: Manual copy
                    documents = handler.read(table_name)
                    
                    # Create new collection WITHOUT validation first
                    handler.create_collection(new_name)
                    
                    # Get primary key name
                    primary_key = handler.get_primary_key_name()
                    
                    # Copy documents
                    for doc in documents:
                        clean_doc = {k: v for k, v in doc.items() if k != primary_key}
                        handler.insert(new_name, clean_doc)
                    
                    # Try to copy validation rules AFTER data
                    if hasattr(handler, 'get_check_constraints') and hasattr(handler, 'apply_validation_rules'):
                        try:
                            old_checks = handler.get_check_constraints(table_name)
                            
                            if old_checks:
                                logger.info(f"Found {len(old_checks)} validation rules to copy")
                                
                                # Build validation rules dict
                                validation_rules = {}
                                for check in old_checks:
                                    col_name = check.get('column')
                                    if col_name:
                                        validation_rules[col_name] = {'expression': check.get('expression')}
                                
                                if validation_rules:
                                    try:
                                        handler.apply_validation_rules(new_name, validation_rules)
                                        logger.info(f"✅ Successfully applied {len(validation_rules)} validation rules to {new_name}")
                                    except Exception as validation_err:
                                        logger.warning(f"⚠️ Could not apply validation rules to {new_name}: {validation_err}")
                                        logger.warning(f"   Reason: Existing data may violate the validation constraints")
                        except Exception as e:
                            logger.warning(f"Failed to copy validation rules: {e}")
            
            # Delete old table if requested
            if not keep_old:
                try:
                    handler.delete_table(table_name)
                    message = f'Table renamed from {table_name} to {new_name}'
                except Exception as e:
                    logger.warning(f"Failed to delete old table: {e}")
                    message = f'Table copied to {new_name} (could not delete original: {str(e)})'
            else:
                message = f'Table copied from {table_name} to {new_name}'
            
            return jsonify({
                'success': True,
                'message': message,
                'kept_old': keep_old or True,
                'new_name': new_name
            })
            
        except Exception as e:
            logger.error(f"❌ API call failed: /api/db/{db_name}/table/{table_name}/rename - {e}")
            return jsonify({'success': False, 'error': str(e)}), 500


    @app.route('/api/db/<db_name>/table/<table_name>/connection_info', methods=['GET'])
    def api_get_table_connection_info(db_name, table_name):
        """JSON API: Get connection info for specific table"""
        try:
            logger.debug(f"✅ API call: GET /api/db/{db_name}/table/{table_name}/connection_info")
            
            # ✅ Add try-catch around switch_db
            try:
                app.config['HANDLER'].switch_db(db_name)
            except Exception as switch_err:
                logger.error(f"Failed to switch to database {db_name}: {switch_err}")
                return jsonify({'success': False, 'error': f'Database not found: {db_name}'}), 404
            
            handler = app.config['HANDLER']
            
            # ✅ Check if method exists with detailed logging
            if hasattr(handler, 'get_table_connection_info'):
                logger.debug(f"Handler has get_table_connection_info method")
                try:
                    conn_info = handler.get_table_connection_info(db_name, table_name)
                except Exception as method_err:
                    logger.error(f"get_table_connection_info failed: {method_err}")
                    import traceback
                    logger.error(traceback.format_exc())
                    return jsonify({'success': False, 'error': str(method_err)}), 500
            else:
                # Fallback
                logger.warning(f"Handler {handler.__class__.__name__} missing get_table_connection_info")
                base_conn_info = handler.get_connection_info(db_name)
                conn_info = {
                    'connection_string': base_conn_info['connection_string'],
                    'test_code': f"# Connect to database, then query {table_name}",
                    'notes': base_conn_info.get('notes', [])
                }
            
            return jsonify({
                'success': True,
                'connection_string': conn_info['connection_string'],
                'test_code': conn_info['test_code'],
                'notes': conn_info.get('notes', [])
            })
            
        except Exception as e:
            logger.error(f"❌ API call failed: /api/db/{db_name}/table/{table_name}/connection_info")
            logger.error(f"Error: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return jsonify({'success': False, 'error': str(e)}), 500
        
    def format_datetime_columns(rows, columns):
        """Format date/time/timestamp columns to standard formats"""
        if not rows or not columns:
            return rows
        
        # Build map of column names to types
        column_types = {}
        for col in columns:
            col_type = col.get('type', '').upper()
            column_types[col['name']] = col_type
        
        formatted_rows = []
        for row in rows:
            formatted_row = {}
            for key, value in row.items():
                if value is None:
                    formatted_row[key] = value
                    continue
                
                col_type = column_types.get(key, '').upper()
                
                # Format based on column type
                if 'DATE' in col_type and 'TIME' not in col_type:
                    # DATE type - format as YYYY-MM-DD
                    try:
                        if isinstance(value, str):
                            # Try to parse and reformat
                            from datetime import datetime
                            # Handle various input formats
                            for fmt in ['%Y-%m-%d', '%Y-%m-%d %H:%M:%S', '%a, %d %b %Y %H:%M:%S %Z']:
                                try:
                                    dt = datetime.strptime(value, fmt)
                                    formatted_row[key] = dt.strftime('%Y-%m-%d')
                                    break
                                except:
                                    continue
                            else:
                                # If no format matched, keep original
                                formatted_row[key] = value
                        else:
                            # Already in correct format
                            formatted_row[key] = value
                    except:
                        formatted_row[key] = value
                        
                elif 'TIMESTAMP' in col_type or 'DATETIME' in col_type:
                    # TIMESTAMP/DATETIME - format as YYYY-MM-DD HH:MM:SS
                    try:
                        if isinstance(value, str):
                            from datetime import datetime
                            for fmt in ['%Y-%m-%d %H:%M:%S', '%a, %d %b %Y %H:%M:%S %Z', '%Y-%m-%d']:
                                try:
                                    dt = datetime.strptime(value, fmt)
                                    formatted_row[key] = dt.strftime('%Y-%m-%d %H:%M:%S')
                                    break
                                except:
                                    continue
                            else:
                                formatted_row[key] = value
                        else:
                            formatted_row[key] = value
                    except:
                        formatted_row[key] = value
                        
                elif 'TIME' in col_type and 'STAMP' not in col_type:
                    # TIME type - format as HH:MM:SS
                    try:
                        if isinstance(value, str):
                            from datetime import datetime
                            for fmt in ['%H:%M:%S', '%Y-%m-%d %H:%M:%S']:
                                try:
                                    dt = datetime.strptime(value, fmt)
                                    formatted_row[key] = dt.strftime('%H:%M:%S')
                                    break
                                except:
                                    continue
                            else:
                                formatted_row[key] = value
                        else:
                            formatted_row[key] = value
                    except:
                        formatted_row[key] = value
                else:
                    # Not a date/time column
                    formatted_row[key] = value
            
            formatted_rows.append(formatted_row)
        
        return formatted_rows
        
    @app.route('/api/table/<db_name>/<table_name>', methods=['GET'])
    def api_table_details(db_name, table_name):
        """JSON API: Get table details with data"""
        try:
            print(f"✓ API call: GET /api/table/{db_name}/{table_name}")
            
            app.config['HANDLER'].switch_db(db_name)
            
            # Get pagination params
            page = request.args.get('page', 1, type=int)
            per_page = request.args.get('per_page', 20, type=int)
            sort_column = request.args.get('sort_column', '')
            sort_order = request.args.get('sort_order', 'asc')
            
            # Get schema
            columns = app.config['HANDLER'].get_table_schema(table_name)
            
            # Get all data
            all_rows = app.config['HANDLER'].read(table_name)
            
            # ✅ NEW: Format date/time columns for display
            all_rows = format_datetime_columns(all_rows, columns)
            
            # Apply sorting
            if sort_column and columns:
                col_names = [col['name'] for col in columns]
                if sort_column in col_names:
                    try:
                        all_rows = sorted(
                            all_rows,
                            key=lambda x: (x.get(sort_column) is None, x.get(sort_column) if x.get(sort_column) is not None else ''),
                            reverse=(sort_order == 'desc')
                        )
                    except Exception as e:
                        logger.error(f"Sorting error: {e}")
            
            record_count = len(all_rows)
            total_pages = (record_count + per_page - 1) // per_page
            
            # Paginate
            start = (page - 1) * per_page
            end = start + per_page
            rows = all_rows[start:end]
            
            return jsonify({
                'success': True,
                'columns': columns,
                'rows': rows,
                'record_count': record_count,
                'page': page,
                'per_page': per_page,
                'total_pages': total_pages,
                'db_type': app.config['DB_TYPE'],
                'handler': app.config['CURRENT_HANDLER_NAME']
            })
            
        except Exception as e:
            print(f"❌ API call failed: /api/table/{db_name}/{table_name} - {e}")
            logger.error(f"API error: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500
        
    @app.route('/api/db/<db_name>/tables', methods=['GET'])
    def api_database_tables(db_name):
        """JSON API: Get tables/collections in a database"""
        try:
            logger.debug(f"✅ API call: GET /api/db/{db_name}/tables")
        
            # ✅ CRITICAL FIX: Ensure connection is open before operations
            app.config['HANDLER'].switch_db(db_name)
            
            # ✅ For TinyDB specifically, reopen if closed
            if app.config['DB_TYPE'] == 'nosql' and hasattr(app.config['HANDLER'], 'handler'):
                handler = app.config['HANDLER'].handler
                if hasattr(handler, 'DB_NAME') and handler.DB_NAME == 'TinyDB':
                    if hasattr(handler, 'db') and handler.db is None:
                        logger.debug(f"Reopening TinyDB connection for {db_name}")
                        handler.switch_db(db_name)
        
            # Get pagination params
            page = request.args.get('page', 1, type=int)
            per_page = request.args.get('per_page', 10, type=int)
        
            # Get all tables
            all_tables = app.config['HANDLER'].list_tables()
        
            if app.config['DB_TYPE'] == 'sql':
                all_tables = sorted(all_tables)
                total_items = len(all_tables)
                total_pages = (total_items + per_page - 1) // per_page
            
                # Paginate
                start = (page - 1) * per_page
                end = start + per_page
                tables = all_tables[start:end]
            
                return jsonify({
                    'success': True,
                    'tables': tables,
                    'total_tables': total_items,
                    'page': page,
                    'per_page': per_page,
                    'total_pages': total_pages,
                    'db_type': app.config['DB_TYPE'],
                    'handler': app.config['CURRENT_HANDLER_NAME']
                })
            else:
                # NoSQL - get collection stats
                all_tables = sorted(all_tables)
                collection_stats = []
            
                for coll in all_tables:
                    try:
                        count = app.config['HANDLER'].count_documents(coll)
                    except Exception as e:
                        logger.error(f"Error counting documents in {coll}: {str(e)}")
                        count = 0
                    collection_stats.append({'name': coll, 'count': count})
            
                total_items = len(collection_stats)
                total_pages = (total_items + per_page - 1) // per_page
            
                # Paginate
                start = (page - 1) * per_page
                end = start + per_page
                collections = collection_stats[start:end]
            
                return jsonify({
                    'success': True,
                    'collections': collections,
                    'total_collections': total_items,
                    'page': page,
                    'per_page': per_page,
                    'total_pages': total_pages,
                    'db_type': app.config['DB_TYPE'],
                    'handler': app.config['CURRENT_HANDLER_NAME']
                })
        
        except Exception as e:
            logger.error(f"❌ API call failed: /api/db/{db_name}/tables - {e}")
            return jsonify({'success': False, 'error': str(e)}), 500
        
    # ===== JSON API ROUTES (for React) =====

    @app.route('/api/switch_handler', methods=['POST'])
    def api_switch_handler():
        """JSON API: Switch database type/handler"""
        try:
            data = request.get_json()
            new_type = data.get('type')
            new_handler = data.get('handler')
    
            print(f"✓ API call: POST /api/switch_handler - type={new_type}, handler={new_handler}")
    
            # Validate inputs
            if new_type not in ['sql', 'nosql']:
                return jsonify({'success': False, 'error': 'Invalid type'}), 400
    
            # Get available handlers
            if new_type == 'sql':
                available_handlers = list(DBRegistry.get_sql_handlers().keys())
            else:
                available_handlers = list(DBRegistry.get_nosql_handlers().keys())
    
            if new_handler not in available_handlers:
                new_handler = available_handlers[0] if available_handlers else None
                if not new_handler:
                    return jsonify({'success': False, 'error': f'No handlers available for {new_type}'}), 400
    
            # Switch handler
            app.config['DB_TYPE'] = new_type
            app.config['CURRENT_HANDLER_NAME'] = new_handler
    
            if new_type == 'sql':
                app.config['HANDLER'] = SQLHandler(new_handler)
            else:
                app.config['HANDLER'] = NoSQLHandler(new_handler)
    
            # Reset current_db
            app.config['HANDLER'].current_db = None
    
            logger.debug(f"API: Switched to {new_type}/{new_handler}")
    
            # ✅ CRITICAL FIX: Check if credentials are needed AFTER switching
            handler = app.config['HANDLER']
            needs_credentials = False
        
            # Check wrapped handler first
            if hasattr(handler, 'handler') and hasattr(handler.handler, 'get_credential_status'):
                cred_status = handler.handler.get_credential_status()
                needs_credentials = cred_status.get('needs_credentials', False)
            elif hasattr(handler, 'get_credential_status'):
                cred_status = handler.get_credential_status()
                needs_credentials = cred_status.get('needs_credentials', False)
        
            return jsonify({
                'success': True,
                'db_type': new_type,
                'handler': new_handler,
                'needs_credentials': needs_credentials,  # ✅ ADD THIS
                'message': f'Switched to {new_handler}'
            })
    
        except Exception as e:
            print(f"✗ API call failed: /api/switch_handler - {e}")
            logger.error(f"API error: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500
        
    @app.route('/api/db/<db_name>/capabilities', methods=['GET'])
    def api_db_capabilities(db_name):
        """JSON API: Get database capabilities"""
        try:
            app.config['HANDLER'].switch_db(db_name)
            handler = app.config['HANDLER']
        
            # Get the actual handler (unwrap if needed)
            actual_handler = handler.handler if hasattr(handler, 'handler') else handler
        
            capabilities = {
                'supports_non_pk_autoincrement': False,
                'supports_triggers': False,
                'supports_procedures': False,
                'supports_check_constraints': False,  
                'supports_aggregation': False,
                'supports_aggregation_pipeline': False,
                'supports_views': False,  # âœ… ADD THIS
            }
        
            if hasattr(actual_handler, 'supports_non_pk_autoincrement'):
                capabilities['supports_non_pk_autoincrement'] = actual_handler.supports_non_pk_autoincrement()
        
            if hasattr(handler, 'supports_triggers'):
                capabilities['supports_triggers'] = handler.supports_triggers()
            
            if hasattr(handler, 'supports_procedures'):
                capabilities['supports_procedures'] = handler.supports_procedures()
            
            # Add check constraints capability
            if hasattr(handler, 'supports_check_constraints'):
                capabilities['supports_check_constraints'] = handler.supports_check_constraints()
                
            # Add aggregation pipeline capability - check actual handler first
            if hasattr(actual_handler, 'supports_aggregation_pipeline'):
                capabilities['supports_aggregation_pipeline'] = actual_handler.supports_aggregation_pipeline()
            elif hasattr(handler, 'supports_aggregation_pipeline'):
                capabilities['supports_aggregation_pipeline'] = handler.supports_aggregation_pipeline()

            # âœ… Check if handler supports aggregation at all
            if hasattr(actual_handler, 'supports_aggregation'):
                capabilities['supports_aggregation'] = actual_handler.supports_aggregation()
            elif hasattr(handler, 'supports_aggregation'):
                capabilities['supports_aggregation'] = handler.supports_aggregation()
            
            # âœ… ADD THIS: Check if handler supports views
            if hasattr(actual_handler, 'supports_views'):
                capabilities['supports_views'] = actual_handler.supports_views()
            elif hasattr(handler, 'supports_views'):
                capabilities['supports_views'] = handler.supports_views()

            return jsonify({
                'success': True,
                'capabilities': capabilities
            })
        except Exception as e:
            logger.error(f"Failed to get capabilities: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500
        
    def parse_datetime_value(value, col_type):
        """Parse datetime string to appropriate format for database"""
        if not value or value == '':
            return None
        
        col_type = col_type.upper()
        
        try:
            from datetime import datetime
            
            if 'DATE' in col_type and 'TIME' not in col_type:
                # DATE - accept YYYY-MM-DD
                # Try to parse and ensure correct format
                for fmt in ['%Y-%m-%d', '%Y-%m-%d %H:%M:%S', '%a, %d %b %Y %H:%M:%S %Z']:
                    try:
                        dt = datetime.strptime(value, fmt)
                        return dt.strftime('%Y-%m-%d')
                    except:
                        continue
                # If no format worked, return original
                return value
                
            elif 'TIMESTAMP' in col_type or 'DATETIME' in col_type:
                # TIMESTAMP/DATETIME - accept YYYY-MM-DD HH:MM:SS
                for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%a, %d %b %Y %H:%M:%S %Z']:
                    try:
                        dt = datetime.strptime(value, fmt)
                        return dt.strftime('%Y-%m-%d %H:%M:%S')
                    except:
                        continue
                return value
                
            elif 'TIME' in col_type and 'STAMP' not in col_type:
                # TIME - accept HH:MM:SS
                for fmt in ['%H:%M:%S', '%Y-%m-%d %H:%M:%S']:
                    try:
                        dt = datetime.strptime(value, fmt)
                        return dt.strftime('%H:%M:%S')
                    except:
                        continue
                return value
            else:
                return value
        except:
            return value

    @app.route('/api/table/<db_name>/<table_name>/data', methods=['POST'])
    def api_table_data_operation(db_name, table_name):
        """JSON API: Insert/Update/Delete table data"""
        try:
            print(f"✓ API call: POST /api/table/{db_name}/{table_name}/data")
        
            app.config['HANDLER'].switch_db(db_name)
        
            data = request.get_json()
            action = data.get('action')
        
            if action == 'insert':
                row_data = data.get('data', {})
                
                # ✅ NEW: Parse date/time values
                schema = app.config['HANDLER'].get_table_schema(table_name)
                for col in schema:
                    col_name = col['name']
                    if col_name in row_data:
                        row_data[col_name] = parse_datetime_value(row_data[col_name], col['type'])
                
                app.config['HANDLER'].insert(table_name, row_data)
                logger.debug(f"API: Inserted into {table_name}: {row_data}")
                return jsonify({'success': True, 'message': 'Row inserted successfully'})
        
            elif action == 'update':
                row_data = data.get('data', {})
                condition = data.get('condition', '')
                original_data = data.get('original_data', {})  # ✅ NEW: Get original row data
                
                # ✅ Parse date/time values
                schema = app.config['HANDLER'].get_table_schema(table_name)
                for col in schema:
                    col_name = col['name']
                    if col_name in row_data:
                        row_data[col_name] = parse_datetime_value(row_data[col_name], col['type'])
                
                # ✅ CRITICAL FIX: Build condition from ORIGINAL row data if not provided
                if not condition.strip():
                    # No condition provided - build from original_data (for tables without primary key)
                    if not original_data:
                        return jsonify({'success': False, 'error': 'Cannot update without condition or original_data'}), 400
                    
                    # Build WHERE clause using ALL columns from ORIGINAL row as unique identifier
                    conditions = []
                    for col_name, col_value in original_data.items():
                        if col_value is None:
                            conditions.append(f"{col_name} IS NULL")
                        else:
                            # ✅ Escape single quotes in values
                            escaped_value = str(col_value).replace("'", "''")
                            conditions.append(f"{col_name} = '{escaped_value}'")
                    condition = ' AND '.join(conditions)
                    
                    logger.debug(f"Built condition from original_data: {condition}")
                
                app.config['HANDLER'].update(table_name, row_data, condition)
                logger.debug(f"API: Updated {table_name} WHERE {condition}")
                return jsonify({'success': True, 'message': 'Row updated successfully'})

            elif action == 'delete':
                condition = data.get('condition', '')
                
                # ✅ CRITICAL FIX: Accept row data to build condition
                row_data = data.get('data', {})
                
                if not condition.strip() and not row_data:
                    return jsonify({'success': False, 'error': 'Delete condition or row data is required'}), 400
                
                # ✅ Build condition from row data if not provided
                if not condition.strip() and row_data:
                    conditions = []
                    for col_name, col_value in row_data.items():
                        if col_value is None:
                            conditions.append(f"{col_name} IS NULL")
                        else:
                            conditions.append(f"{col_name} = '{col_value}'")
                    condition = ' AND '.join(conditions)
                    
                    logger.debug(f"Built delete condition from row data: {condition}")
                
                app.config['HANDLER'].delete(table_name, condition)
                logger.debug(f"API: Deleted from {table_name} WHERE {condition}")
                return jsonify({'success': True, 'message': 'Row deleted successfully'})
            
        except Exception as e:
            print(f"✗ API call failed: /api/table/{db_name}/{table_name}/data - {e}")
            logger.error(f"API error: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/table/<db_name>/<table_name>/query', methods=['POST'])
    def api_execute_query(db_name, table_name):
        """JSON API: Execute custom query"""
        try:
            print(f"✅ API call: POST /api/table/{db_name}/{table_name}/query")
    
            app.config['HANDLER'].switch_db(db_name)
    
            data = request.get_json()
            query = data.get('query', '')
    
            if not query:
                return jsonify({'success': False, 'error': 'Query is required'}), 400
        
            # ✅ CRITICAL: Check if it's a procedure call FIRST
            query_stripped = query.strip().upper()
            is_procedure = (
                query_stripped.startswith('CALL ') or 
                query_stripped.startswith('EXEC ') or 
                query_stripped.startswith('EXECUTE ')
            )
        
            logger.debug(f"Query: {query[:50]}... Is procedure: {is_procedure}")
        
            try:
                if is_procedure:
                    # Execute as procedure
                    logger.debug("Executing as procedure")
                    result = app.config['HANDLER'].execute_procedure(query)
                    logger.debug(f"Raw procedure result: {result}")
                
                    # Format the result
                    formatted = format_procedure_result(result)
                    logger.debug(f"Formatted result: {formatted}")
                
                    return jsonify({
                        'success': True,
                        'result': formatted['data'],
                        'result_type': formatted['type'],
                        'rows_affected': formatted.get('rows_affected', 0)
                    })
                else:
                    # Regular query
                    result = app.config['HANDLER'].execute_query(query)
            
                    logger.debug(f"Query executed successfully on {table_name}")
            
                    # ✅ Unwrap [results, metadata] structure
                    if isinstance(result, list) and len(result) == 2:
                        if isinstance(result[0], list) and isinstance(result[1], dict):
                            result = result[0]
                            logger.debug(f"Unwrapped result: {len(result)} rows")
            
                    # ✅ Format result for display
                    if isinstance(result, list):
                        if len(result) > 0:
                            pass  # Results ready to display
                        else:
                            result = None
                    elif isinstance(result, dict):
                        if 'rows_affected' in result:
                            pass  # Keep as is
            
                    return jsonify({
                        'success': True,
                        'result': result
                    })
        
            except Exception as e:
                error_msg = f"Query execution failed: {str(e)}"
                logger.error(error_msg)
                return jsonify({'success': False, 'error': error_msg}), 500
    
        except Exception as e:
            print(f"❌ API call failed: /api/table/{db_name}/{table_name}/query - {e}")
            logger.error(f"API error: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/current_state', methods=['GET'])
    def api_current_state():
        """JSON API: Get current database type and handler"""
        try:
            print("✓ API call: GET /api/current_state")
        
            # Get available handlers
            if app.config['DB_TYPE'] == 'sql':
                available_handlers = list(DBRegistry.get_sql_handlers().keys())
            else:
                available_handlers = list(DBRegistry.get_nosql_handlers().keys())
        
            return jsonify({
                'success': True,
                'db_type': app.config['DB_TYPE'],
                'handler': app.config['CURRENT_HANDLER_NAME'],
                'available_handlers': available_handlers,
                'current_db': app.config['HANDLER'].current_db
            })
        
        except Exception as e:
            print(f"✗ API call failed: /api/current_state - {e}")
            logger.error(f"API error: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/table/<db_name>/<table_name>/triggers', methods=['GET', 'POST', 'DELETE'])
    def api_table_triggers(db_name, table_name):
        """JSON API: Manage triggers"""
        try:
            app.config['HANDLER'].switch_db(db_name)
        
            if request.method == 'GET':
                supports_triggers = app.config['HANDLER'].supports_triggers()
                triggers = []
            
                if supports_triggers:
                    try:
                        triggers = app.config['HANDLER'].list_triggers(table_name)
                    except Exception as e:
                        logger.error(f"Error fetching triggers: {e}")
            
                return jsonify({
                    'success': True,
                    'triggers': triggers,
                    'supports_triggers': supports_triggers
                })
        
            elif request.method == 'POST':
                data = request.get_json()
                trigger_name = data.get('trigger_name')
                trigger_timing = data.get('trigger_timing')
                trigger_event = data.get('trigger_event')
                trigger_body = data.get('trigger_body')
            
                if not all([trigger_name, trigger_timing, trigger_event, trigger_body]):
                    return jsonify({
                        'success': False,
                        'error': 'All trigger fields are required'
                    }), 400
            
                try:
                    result = app.config['HANDLER'].create_trigger(
                        trigger_name, table_name, trigger_timing, trigger_event, trigger_body
                    )
                
                    return jsonify({
                        'success': True,
                        'message': 'Trigger created successfully'
                    })
                except Exception as e:
                    return jsonify({
                        'success': False,
                        'error': str(e)
                    }), 500
        
            elif request.method == 'DELETE':
                data = request.get_json()
                trigger_name = data.get('trigger_name')
            
                if not trigger_name:
                    return jsonify({
                        'success': False,
                        'error': 'Trigger name is required'
                    }), 400
            
                try:
                    app.config['HANDLER'].delete_trigger(trigger_name, table_name)
                    return jsonify({
                        'success': True,
                        'message': f'Trigger {trigger_name} deleted successfully'
                    })
                except Exception as e:
                    return jsonify({
                        'success': False,
                        'error': str(e)
                    }), 500
                
        except Exception as e:
            logger.error(f"API triggers error: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/table/<db_name>/<table_name>/procedures', methods=['GET', 'POST', 'DELETE'])
    def api_table_procedures(db_name, table_name):
        """JSON API: Manage procedures"""
        try:
            app.config['HANDLER'].switch_db(db_name)
        
            if request.method == 'GET':
                supports_procedures = app.config['HANDLER'].supports_procedures()
                procedures = []
            
                if supports_procedures:
                    try:
                        procedures = app.config['HANDLER'].list_procedures()
                    except Exception as e:
                        logger.error(f"Error fetching procedures: {e}")
            
                return jsonify({
                    'success': True,
                    'procedures': procedures,
                    'supports_procedures': supports_procedures
                })
        
            elif request.method == 'POST':
                data = request.get_json()
                procedure_code = data.get('procedure_code')

                if not procedure_code:
                    return jsonify({
                        'success': False,
                        'error': 'Procedure code is required'
                    }), 400

                try:
                    result = app.config['HANDLER'].execute_procedure(procedure_code)
        
                    # ✅ REPLACE the existing formatting logic with this:
                    formatted = format_procedure_result(result)
        
                    return jsonify({
                        'success': True,
                        'message': 'Procedure executed successfully',
                        'result': formatted['data'],
                        'result_type': formatted['type'],
                        'rows_affected': formatted.get('rows_affected', 0)
                    })
                except Exception as e:
                    return jsonify({
                        'success': False,
                        'error': str(e)
                    }), 500
        
            elif request.method == 'DELETE':
                data = request.get_json()
                procedure_name = data.get('procedure_name')
                is_function = data.get('is_function', False)
            
                if not procedure_name:
                    return jsonify({
                        'success': False,
                        'error': 'Procedure name is required'
                    }), 400
            
                try:
                    app.config['HANDLER'].drop_procedure(procedure_name, is_function)
                    return jsonify({
                        'success': True,
                        'message': f'Procedure {procedure_name} dropped successfully'
                    })
                except Exception as e:
                    return jsonify({
                        'success': False,
                        'error': str(e)
                    }), 500
                
        except Exception as e:
            logger.error(f"API procedures error: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500
        
    @app.route('/api/db/<db_name>/procedures/execute', methods=['POST'])
    def api_execute_procedure_db_level(db_name):
        """JSON API: Execute procedure at database level"""
        try:
            logger.debug(f"✅ API call: POST /api/db/{db_name}/procedures/execute")
            
            app.config['HANDLER'].switch_db(db_name)
            
            data = request.get_json()
            procedure_code = data.get('procedure_code', '').strip()
            
            if not procedure_code:
                return jsonify({
                    'success': False,
                    'error': 'Procedure code is required'
                }), 400
            
            try:
                handler = app.config['HANDLER']
                
                # Execute the procedure code directly
                result = handler.execute_procedure(procedure_code)
                
                formatted = format_procedure_result(result)
                
                return jsonify({
                    'success': True,
                    'result': formatted['data'],
                    'result_type': formatted['type'],
                    'rows_affected': formatted.get('rows_affected', 0),
                    'message': 'Procedure executed successfully'
                })
                    
            except NotImplementedError as e:
                return jsonify({
                    'success': False,
                    'error': f'This database does not support stored procedures: {str(e)}'
                }), 400
            except Exception as e:
                return jsonify({
                    'success': False,
                    'error': f'Procedure execution failed: {str(e)}'
                }), 500
                
        except Exception as e:
            logger.error(f"❌ API call failed: /api/db/{db_name}/procedures/execute - {e}")
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/db/<db_name>/procedure/<procedure_name>/execute', methods=['POST'])
    def api_execute_specific_procedure(db_name, procedure_name):
        """JSON API: Execute a specific procedure by name"""
        try:
            logger.debug(f"✅ API call: POST /api/db/{db_name}/procedure/{procedure_name}/execute")
            
            app.config['HANDLER'].switch_db(db_name)
            handler = app.config['HANDLER']
            
            # Build appropriate call statement based on handler
            if hasattr(handler, 'get_procedure_call_syntax'):
                call_template = handler.get_procedure_call_syntax()
                call_statement = call_template.format(name=procedure_name)
            else:
                # Fallback to CALL (MySQL style)
                call_statement = f"CALL {procedure_name}()"
            
            try:
                result = handler.execute_procedure(call_statement)
                
                # Format using helper
                formatted = format_procedure_result(result)
                
                return jsonify({
                    'success': True,
                    'result': formatted['data'],
                    'result_type': formatted['type'],
                    'rows_affected': formatted.get('rows_affected', 0),
                    'message': f'Procedure {procedure_name} executed successfully'
                })
                
            except Exception as e:
                return jsonify({
                    'success': False,
                    'error': f'Execution failed: {str(e)}'
                }), 500
            
        except Exception as e:
            logger.error(f"❌ API call failed: /api/db/{db_name}/procedure/{procedure_name}/execute - {e}")
            return jsonify({'success': False, 'error': str(e)}), 500
        
    @app.route('/api/table/<db_name>/<table_name>/procedures/execute', methods=['POST'])
    def api_execute_procedure_better(db_name, table_name):
        """JSON API: Execute procedure with better result formatting"""
        try:
            logger.debug(f"✅ API call: POST /api/table/{db_name}/{table_name}/procedures/execute")
        
            app.config['HANDLER'].switch_db(db_name)
        
            data = request.get_json()
            procedure_code = data.get('procedure_code', '').strip()
        
            if not procedure_code:
                return jsonify({
                    'success': False,
                    'error': 'Procedure code is required'
                }), 400
        
            try:
                result = app.config['HANDLER'].execute_procedure(procedure_code)
    
                # ✅ REPLACE with formatted result
                formatted = format_procedure_result(result)
    
                return jsonify({
                    'success': True,
                    'result': formatted['data'],
                    'result_type': formatted['type'],
                    'rows_affected': formatted.get('rows_affected', 0),
                    'message': 'Procedure executed successfully'
                })

            except NotImplementedError as e:
                return jsonify({
                    'success': False,
                    'error': f'This database does not support stored procedures: {str(e)}'
                }), 400
            except Exception as e:
                return jsonify({
                    'success': False,
                    'error': f'Procedure execution failed: {str(e)}'
                }), 500
        
        except Exception as e:
            logger.error(f"❌ API call failed: /api/table/{db_name}/{table_name}/procedures/execute - {e}")
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/table/<db_name>/<table_name>/procedure/<procedure_name>/code')
    def api_get_procedure_code(db_name, table_name, procedure_name):
        """JSON API: Get procedure definition from table view — ignores table_name"""
        try:
            app.config['HANDLER'].switch_db(db_name)
        
            if hasattr(app.config['HANDLER'], 'get_procedure_definition'):
                code = app.config['HANDLER'].get_procedure_definition(procedure_name)  # only pass procedure_name
                if code:
                    return jsonify({
                        'success': True,
                        'code': code
                    })
                else:
                    return jsonify({
                        'success': False,
                        'error': 'Procedure not found'
                    }), 404
        
            return jsonify({
                'success': False,
                'error': 'Not supported'
            }), 400
        
        except Exception as e:
            logger.error(f"API get procedure code error: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/table/<db_name>/<table_name>/plsql', methods=['POST'])
    def api_execute_plsql(db_name, table_name):
        """JSON API: Execute PL/SQL code"""
        try:
            app.config['HANDLER'].switch_db(db_name)
        
            data = request.get_json()
            plsql_code = data.get('plsql_code', '').strip()
        
            if not plsql_code:
                return jsonify({
                    'success': False,
                    'error': 'PL/SQL code is required'
                }), 400
        
            try:
                result = app.config['HANDLER'].execute_plsql(plsql_code)
            
                if isinstance(result, dict) and result.get("refresh"):
                    return jsonify({
                        'success': True,
                        'refresh': True,
                        'status': result.get("status", "Executed."),
                        'notices': result.get("notices", [])
                    })
            
                return jsonify({
                    'success': True,
                    'message': result.get("status", "PL/SQL executed successfully"),
                    'result': result
                })
            except Exception as e:
                return jsonify({
                    'success': False,
                    'error': f'Execution Failed: {str(e)}'
                }), 500
            
        except Exception as e:
            logger.error(f"API PL/SQL error: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500
        
    @app.route('/api/db/<db_name>/query', methods=['POST'])
    def api_db_query(db_name):
        """JSON API: Execute query in database context (supports JOINs, GROUP BY, etc.)"""
        try:
            logger.debug(f"✅ API call: POST /api/db/{db_name}/query")
    
            app.config['HANDLER'].switch_db(db_name)
    
            data = request.get_json()
            query = data.get('query', '')
    
            if not query:
                return jsonify({'success': False, 'error': 'Query is required'}), 400
    
            try:
                if app.config['DB_TYPE'] == 'nosql':
                    # Parse JSON query for NoSQL
                    import json as json_lib
                    query_obj = json_lib.loads(query)
                    result = app.config['HANDLER'].execute_query(query_obj)
                else:
                    # ✅ SQL: Check if it's a procedure call
                    query_stripped = query.strip().upper()
                    is_procedure = (
                        query_stripped.startswith('CALL ') or 
                        query_stripped.startswith('EXEC ') or 
                        query_stripped.startswith('EXECUTE ')
                    )
                
                    logger.debug(f"DB Query - Is procedure: {is_procedure}")
                
                    if is_procedure:
                        # Execute as procedure
                        logger.debug("Executing as procedure")
                        result = app.config['HANDLER'].execute_procedure(query)
                        logger.debug(f"Raw procedure result: {result}")
                    
                        # Format using helper
                        formatted = format_procedure_result(result)
                        logger.debug(f"Formatted procedure result: {formatted}")
                    
                        return jsonify({
                            'success': True,
                            'result': formatted['data'],
                            'result_type': formatted['type'],
                            'rows_affected': formatted.get('rows_affected', 0)
                        })
                    else:
                        # Execute SQL query directly
                        result = app.config['HANDLER'].execute_query(query)
        
                logger.debug(f"API: Executed query in {db_name}")
        
                # ✅ FIX: Unwrap nested results
                if isinstance(result, list) and len(result) == 2:
                    if isinstance(result[0], list) and isinstance(result[1], dict):
                        result = result[0]
        
                # Format result for display
                if isinstance(result, list):
                    if len(result) > 0:
                        # Results ready to display
                        pass
                    else:
                        # Empty result
                        result = []
                elif isinstance(result, dict):
                    # DML result (rows_affected) - keep as dict
                    if 'rows_affected' not in result:
                        # Wrap single dict result
                        result = [result]
        
                return jsonify({
                    'success': True,
                    'result': result
                })
    
            except Exception as e:
                error_msg = f"Query execution failed: {str(e)}"
                logger.error(error_msg)
                return jsonify({'success': False, 'error': error_msg}), 500
        
        except Exception as e:
            logger.error(f"❌ API call failed: /api/db/{db_name}/query - {e}")
            return jsonify({'success': False, 'error': str(e)}), 500
    @app.route('/api/db/<db_name>/aggregation', methods=['POST'])
    def api_db_aggregation(db_name):
        """JSON API: Execute aggregation query (SQL: GROUP BY, NoSQL: aggregation pipeline)"""
        try:
            logger.debug(f"✅ API call: POST /api/db/{db_name}/aggregation")
            
            app.config['HANDLER'].switch_db(db_name)
            handler = app.config['HANDLER']
            
            data = request.get_json()
            
            # Option 1: Direct query execution (same as query tab)
            if 'query' in data:
                query = data.get('query', '').strip()
                
                if not query:
                    return jsonify({'success': False, 'error': 'Query is required'}), 400
                
                try:
                    # Check if it's a procedure call
                    query_stripped = query.strip().upper()
                    is_procedure = (
                        query_stripped.startswith('CALL ') or 
                        query_stripped.startswith('EXEC ') or 
                        query_stripped.startswith('EXECUTE ')
                    )
                    
                    if is_procedure:
                        result = handler.execute_procedure(query)
                        formatted = format_procedure_result(result)
                        
                        return jsonify({
                            'success': True,
                            'result': formatted['data'],
                            'result_type': formatted['type'],
                            'rows_affected': formatted.get('rows_affected', 0)
                        })
                    
                    # Regular query execution
                    if app.config['DB_TYPE'] == 'nosql':
                        import json as json_lib
                        query_obj = json_lib.loads(query)
                        result = handler.execute_query(query_obj)
                    else:
                        result = handler.execute_query(query)
                    
                    # Unwrap nested results
                    if isinstance(result, list) and len(result) == 2:
                        if isinstance(result[0], list) and isinstance(result[1], dict):
                            result = result[0]
                    
                    # Format result
                    if isinstance(result, list):
                        if len(result) > 0:
                            pass
                        else:
                            result = []
                    elif isinstance(result, dict):
                        if 'rows_affected' not in result:
                            result = [result]
                    
                    return jsonify({
                        'success': True,
                        'result': result
                    })
                    
                except Exception as e:
                    error_msg = f"Query execution failed: {str(e)}"
                    logger.error(error_msg)
                    return jsonify({'success': False, 'error': error_msg}), 500
            
            # Option 2: Visual aggregation builder
            table = data.get('table')
            select_fields = data.get('select_fields', [])  # List of fields/expressions
            group_by = data.get('group_by')  # Field to group by
            order_by = data.get('order_by')  # Field to order by
            order_direction = data.get('order_direction', 'ASC')  # ASC or DESC
            join_config = data.get('join_config')  # Only for SQL
            
            if not table:
                return jsonify({'success': False, 'error': 'Table/collection is required'}), 400
            
            if not select_fields or len(select_fields) == 0:
                return jsonify({'success': False, 'error': 'At least one field is required'}), 400
            
            try:
                if app.config['DB_TYPE'] == 'sql':
                    # Build SQL aggregation query
                    query_parts = ['SELECT']
                    
                    # Add select fields (can include aggregations like COUNT(*), AVG(price))
                    query_parts.append(', '.join(select_fields))
                    
                    query_parts.append('FROM')
                    
                    # Add main table with alias
                    table_alias = data.get('table_alias')
                    if table_alias:
                        query_parts.append(f"{table} AS {table_alias}")
                    else:
                        query_parts.append(table)
                    
                    # Add JOIN if specified
                    if join_config:
                        join_table = join_config.get('table')
                        join_table_alias = join_config.get('table_alias')
                        join_on = join_config.get('on')  # e.g., "table1.id = table2.id"
                        join_type = join_config.get('type', 'INNER')  # INNER, LEFT, RIGHT
                        
                        if join_table and join_on:
                            if join_table_alias:
                                query_parts.append(f"{join_type} JOIN {join_table} AS {join_table_alias} ON {join_on}")
                            else:
                                query_parts.append(f"{join_type} JOIN {join_table} ON {join_on}")
                    
                    # Add GROUP BY
                    if group_by:
                        query_parts.append(f"GROUP BY {group_by}")
                    
                    # Add ORDER BY
                    if order_by:
                        query_parts.append(f"ORDER BY {order_by} {order_direction}")
                    
                    query = ' '.join(query_parts)
                    logger.debug(f"Generated SQL aggregation: {query}")
                    
                    result = handler.execute_query(query)
                    
                    # Unwrap nested results
                    if isinstance(result, list) and len(result) == 2:
                        if isinstance(result[0], list) and isinstance(result[1], dict):
                            result = result[0]
                    
                    return jsonify({
                        'success': True,
                        'result': result,
                        'generated_query': query
                    })
                    
                else:
                    # NoSQL aggregation
                    # Build aggregation pipeline
                    pipeline = []
                    
                    # Project stage - select specific fields if not using *
                    if select_fields and select_fields != ['*']:
                        project_stage = {}
                        has_aggregation = False
                        
                        for field in select_fields:
                            field_upper = field.upper()
                            if any(agg in field_upper for agg in ['COUNT', 'SUM', 'AVG', 'MAX', 'MIN']):
                                has_aggregation = True
                            else:
                                # Regular field - include in projection
                                project_stage[field] = 1
                        
                        if project_stage and not has_aggregation:
                            pipeline.append({"$project": project_stage})
                    
                    # Group stage
                    if group_by:
                        group_stage = {
                            "_id": f"${group_by}",
                            group_by: {"$first": f"${group_by}"}
                        }
                        
                        # Add aggregation functions
                        for field in select_fields:
                            if field != group_by:
                                field_upper = field.upper()
                                # Parse aggregation expressions like "COUNT(*)", "AVG(price)"
                                if 'COUNT' in field_upper:
                                    group_stage['count'] = {"$sum": 1}
                                elif 'SUM(' in field_upper:
                                    field_name = field.split('(')[1].split(')')[0].strip()
                                    group_stage[f'sum_{field_name}'] = {"$sum": f"${field_name}"}
                                elif 'AVG(' in field_upper:
                                    field_name = field.split('(')[1].split(')')[0].strip()
                                    group_stage[f'avg_{field_name}'] = {"$avg": f"${field_name}"}
                                elif 'MAX(' in field_upper:
                                    field_name = field.split('(')[1].split(')')[0].strip()
                                    group_stage[f'max_{field_name}'] = {"$max": f"${field_name}"}
                                elif 'MIN(' in field_upper:
                                    field_name = field.split('(')[1].split(')')[0].strip()
                                    group_stage[f'min_{field_name}'] = {"$min": f"${field_name}"}
                        
                        pipeline.append({"$group": group_stage})
                    
                    # Sort stage
                    if order_by:
                        sort_direction = 1 if order_direction.upper() == 'ASC' else -1
                        pipeline.append({"$sort": {order_by: sort_direction}})
                    
                    # Execute aggregation
                    if pipeline:
                        # Use aggregation pipeline
                        query_dict = {
                            "collection": table,
                            "pipeline": pipeline
                        }
                        
                        logger.debug(f"Generated NoSQL aggregation: {query_dict}")
                        
                        result = handler.execute_query(query_dict)
                    else:
                        # Simple find with projection
                        query_dict = {"table": table}
                        if select_fields and select_fields != ['*']:
                            projection = {field: 1 for field in select_fields if not any(agg in field.upper() for agg in ['COUNT', 'SUM', 'AVG', 'MAX', 'MIN'])}
                            if projection:
                                query_dict["projection"] = projection
                        
                        result = handler.execute_query(query_dict)
                    
                    formatted_result = format_nosql_result(result, handler)
                    
                    return jsonify({
                        'success': True,
                        'result': formatted_result,
                        'generated_query': json.dumps(query_dict) if pipeline else 'Simple query'
                    })
                    
            except Exception as e:
                error_msg = f"Aggregation execution failed: {str(e)}"
                logger.error(error_msg)
                return jsonify({'success': False, 'error': error_msg}), 500
            
        except Exception as e:
            logger.error(f"❌ API call failed: /api/db/{db_name}/aggregation - {e}")
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/db/<db_name>/table/<table_name>/delete', methods=['POST'])
    def api_delete_table(db_name, table_name):
        """JSON API: Delete a table"""
        try:
            logger.debug(f"✓ API call: POST /api/db/{db_name}/table/{table_name}/delete")
        
            app.config['HANDLER'].switch_db(db_name)
            app.config['HANDLER'].delete_table(table_name)
        
            logger.debug(f"API: Deleted table {table_name} from {db_name}")
        
            return jsonify({
                'success': True,
                'message': f'Table {table_name} deleted successfully'
            })
        
        except Exception as e:
            logger.error(f"✗ API call failed: /api/db/{db_name}/table/{table_name}/delete - {e}")
            return jsonify({'success': False, 'error': str(e)}), 500
        
    @app.route('/api/table/<db_name>/<table_name>/structure', methods=['GET', 'POST'])
    def api_table_structure(db_name, table_name):
        """JSON API: Get/modify table structure"""
        try:
            app.config['HANDLER'].switch_db(db_name)

            if request.method == 'GET':
                columns = app.config['HANDLER'].get_table_schema(table_name)
                types = app.config['HANDLER'].get_supported_types() if app.config['DB_TYPE'] == 'sql' else []
    
                return jsonify({
                    'success': True,
                    'columns': columns,
                    'types': types,
                    'table_name': table_name
                })

            elif request.method == 'POST':
                # Modify structure
                data = request.get_json()
                new_table_name = data.get('new_table_name', table_name)
                submitted_columns = data.get('columns', [])

                if not new_table_name or not re.match(r'^[a-zA-Z][a-zA-Z0-9_]*$', new_table_name):
                    return jsonify({
                        'success': False,
                        'error': 'Table name must start with a letter, contain only letters, numbers, underscores.'
                    }), 400

                if new_table_name != table_name and new_table_name in app.config['HANDLER'].list_tables():
                    return jsonify({
                        'success': False,
                        'error': 'New table name already exists.'
                    }), 400

                # Build column definitions
                new_columns = []
                has_pk = False
            
                # Get handler type
                handler = app.config['HANDLER']
                actual_handler = handler.handler if hasattr(handler, 'handler') else handler
                db_name_type = actual_handler.DB_NAME if hasattr(actual_handler, 'DB_NAME') else 'SQLite'

                for col_data in submitted_columns:
                    name = col_data.get('name', '').strip()
                    type_ = col_data.get('type', 'TEXT')
                    is_pk = col_data.get('is_pk', False)
                    is_not_null = col_data.get('is_not_null', False)
                    is_autoincrement = col_data.get('is_autoincrement', False)
                    is_unique = col_data.get('is_unique', False)

                    if not name or (app.config['DB_TYPE'] == 'sql' and not type_):
                        return jsonify({
                            'success': False,
                            'error': f'Column name and type are required'
                        }), 400

                    if is_pk:
                        if has_pk:
                            return jsonify({
                                'success': False,
                                'error': 'Only one primary key allowed.'
                            }), 400
                        has_pk = True

                    # ✅ POSTGRESQL FIX: Convert INTEGER + autoincrement to SERIAL
                    if db_name_type == 'PostgreSQL' and is_autoincrement:
                        type_upper = type_.upper()
                        if type_upper == 'INTEGER' or type_upper == 'INT':
                            type_ = 'SERIAL'
                        elif type_upper == 'BIGINT':
                            type_ = 'BIGSERIAL'
                        elif type_upper == 'SMALLINT':
                            type_ = 'SMALLSERIAL'
                    
                        logger.info(f"PostgreSQL: Converted {type_upper} + autoincrement to {type_}")

                    # Build column definition
                    col_def = f"{name} {type_}"

                    # Get CHECK constraint from submitted data
                    check_expr = col_data.get('check_constraint', '').strip()

                    # Build constraints based on DB type
                    if db_name_type == 'PostgreSQL':
                        if is_pk:
                            col_def += " PRIMARY KEY"
                        else:
                            if is_not_null:
                                col_def += " NOT NULL"
                            if is_unique:
                                col_def += " UNIQUE"
                    elif db_name_type == 'MySQL':
                        if is_pk:
                            if is_autoincrement:
                                col_def += " AUTO_INCREMENT PRIMARY KEY"
                            else:
                                col_def += " PRIMARY KEY"
                        else:
                            if is_autoincrement:
                                col_def += " AUTO_INCREMENT UNIQUE NOT NULL"
                            elif is_not_null:
                                col_def += " NOT NULL"
                            if is_unique and not is_autoincrement:
                                col_def += " UNIQUE"
                        
                        # ✅ CRITICAL: For MySQL, add CHECK constraint AFTER all other constraints
                        if check_expr and db_name_type == 'MySQL':
                            # Convert PostgreSQL ARRAY syntax to MySQL IN syntax
                            mysql_check = check_expr
                            
                            # CRITICAL: Remove ALL type casts more thoroughly
                            # Pattern 1: ::identifier
                            mysql_check = re.sub(r'::\s*[a-zA-Z_][a-zA-Z0-9_]*', '', mysql_check)
                            # Pattern 2: ::identifier[]
                            mysql_check = re.sub(r'::\s*[a-zA-Z_][a-zA-Z0-9_]*\s*\[\s*\]', '', mysql_check)
                            # Pattern 3: Any remaining ::
                            mysql_check = re.sub(r'::[^\s\),\]]+', '', mysql_check)
                            
                            # ENHANCED: Handle PostgreSQL ARRAY syntax (already cleaned of type casts)
                            # Pattern: = ANY ((ARRAY['val1', 'val2']))
                            # Convert to: IN ('val1', 'val2')
                            
                            if 'ARRAY[' in mysql_check or '= ANY' in mysql_check.upper():
                                
                                # Extract array content - handle nested parentheses (type casts already removed above)
                                array_match = re.search(r'ARRAY\s*\[\s*(.*?)\s*\]', mysql_check, re.DOTALL | re.IGNORECASE)
                                if array_match:
                                    array_content = array_match.group(1)
                                    
                                    # Extract just the quoted values (no type casts to remove - already done above)
                                    values = re.findall(r"'([^']*)'", array_content)
                                    
                                    if values:
                                        # Build MySQL IN clause
                                        mysql_in = "IN (" + ", ".join([f"'{v}'" for v in values]) + ")"
                                        
                                        # Replace the entire ARRAY construct (type casts already removed)
                                        # Handle: = ANY ((ARRAY[...])) or = ANY (ARRAY[...])
                                        mysql_check = re.sub(
                                            r'=\s*ANY\s*\(\s*\(?\s*ARRAY\s*\[.*?\]\s*\)?\s*\)',
                                            mysql_in,
                                            mysql_check,
                                            flags=re.DOTALL | re.IGNORECASE
                                        )
                                        
                                        logger.debug(f"✅ Converted PostgreSQL ARRAY to MySQL IN: {mysql_check}")
                            
                            # Ensure column name uses backticks
                            mysql_check = re.sub(
                                r'\b' + re.escape(name) + r'\b',
                                f'`{name}`',
                                mysql_check
                            )
                            
                            col_def += f' CHECK ({mysql_check})'
                            logger.debug(f"✅ Added CHECK constraint to {name}: {mysql_check}")
                    else:  # SQLite, DuckDB
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
                            if is_autoincrement:
                                col_def += " AUTOINCREMENT"

                    # ✅ ADD CHECK CONSTRAINT (works for all databases)
                    if check_expr:
                        col_def += f" CHECK ({check_expr})"
                        logger.debug(f"✅ Added CHECK constraint to {name}: {check_expr}")

                    logger.debug(f"Column {name}: type={type_}, is_pk={is_pk}, is_autoincrement={is_autoincrement}, col_def={col_def}")
                    new_columns.append(col_def)

                if not new_columns:
                    return jsonify({
                        'success': False,
                        'error': 'At least one column is required.'
                    }), 400

                try:
                    app.config['HANDLER'].modify_table(table_name, new_table_name, new_columns)
                    logger.debug(f"API: Modified table {table_name} to {new_table_name}")

                    return jsonify({
                        'success': True,
                        'message': f'Modified table {table_name} to {new_table_name}',
                        'new_table_name': new_table_name
                    })
                except Exception as e:
                    logger.error(f"Modify table error: {str(e)}")
                    return jsonify({
                        'success': False,
                        'error': str(e)
                    }), 500
        
        except Exception as e:
            logger.error(f"API structure error: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500
        
    @app.route('/api/db/<db_name>/check_support', methods=['GET'])
    def api_check_support(db_name):
        """JSON API: Check if handler supports CHECK constraints"""
        try:
            logger.debug(f"✅ API call: GET /api/db/{db_name}/check_support")
            
            app.config['HANDLER'].switch_db(db_name)
            handler = app.config['HANDLER']
            
            supports_checks = False
            if hasattr(handler, 'supports_check_constraints'):
                supports_checks = handler.supports_check_constraints()
            
            return jsonify({
                'success': True,
                'supports_check_constraints': supports_checks,
                'handler': app.config['CURRENT_HANDLER_NAME']
            })
        except Exception as e:
            logger.error(f"❌ API call failed: /api/db/{db_name}/check_support - {e}")
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/table/<db_name>/<table_name>/check_constraints', methods=['GET'])
    def api_get_check_constraints(db_name, table_name):
        """JSON API: Get CHECK constraints for a table"""
        try:
            logger.debug(f"✅ API call: GET /api/table/{db_name}/{table_name}/check_constraints")
            
            app.config['HANDLER'].switch_db(db_name)
            handler = app.config['HANDLER']
            
            checks = []
            if hasattr(handler, 'get_check_constraints'):
                checks = handler.get_check_constraints(table_name)
            
            return jsonify({
                'success': True,
                'checks': checks
            })
        except Exception as e:
            logger.error(f"❌ API call failed: /api/table/{db_name}/{table_name}/check_constraints - {e}")
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/validate_check_constraint', methods=['POST'])
    def api_validate_check_constraint():
        """JSON API: Validate a CHECK constraint expression"""
        try:
            data = request.get_json()
            expression = data.get('expression', '').strip()
            
            if not expression:
                return jsonify({'success': False, 'error': 'Expression is required'}), 400
            
            handler = app.config['HANDLER']
            
            is_valid = True
            if hasattr(handler, 'validate_check_constraint'):
                is_valid = handler.validate_check_constraint(expression)
            
            return jsonify({
                'success': True,
                'is_valid': is_valid,
                'message': 'Valid constraint' if is_valid else 'Invalid constraint - may contain dangerous keywords'
            })
        except Exception as e:
            logger.error(f"❌ Validate check constraint error: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500
        
    @app.route('/api/table/<db_name>/<table_name>/check_constraints/create', methods=['POST'])
    def api_create_check_constraint(db_name, table_name):
        """JSON API: Create CHECK constraint for a column"""
        try:
            logger.debug(f"✅ API call: POST /api/table/{db_name}/{table_name}/check_constraints/create")
            
            app.config['HANDLER'].switch_db(db_name)
            handler = app.config['HANDLER']
            
            if not hasattr(handler, 'create_check_constraint'):
                return jsonify({'success': False, 'error': 'Handler does not support CHECK constraints'}), 400
            
            data = request.get_json()
            column_name = data.get('column_name')
            expression = data.get('expression', '').strip()
            
            if not column_name or not expression:
                return jsonify({'success': False, 'error': 'Column name and expression are required'}), 400
            
            # Validate expression
            if hasattr(handler, 'validate_check_constraint'):
                if not handler.validate_check_constraint(expression):
                    return jsonify({'success': False, 'error': 'Invalid CHECK constraint expression'}), 400
            
            # Create CHECK constraint
            handler.create_check_constraint(table_name, column_name, expression)
            
            return jsonify({
                'success': True,
                'message': f'CHECK constraint created for {column_name}'
            })
            
        except Exception as e:
            logger.error(f"❌ API call failed: /api/table/{db_name}/{table_name}/check_constraints/create - {e}")
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/table/<db_name>/<table_name>/check_constraints/delete', methods=['POST'])
    def api_delete_check_constraint(db_name, table_name):
        """JSON API: Delete CHECK constraint from a column"""
        try:
            logger.debug(f"✅ API call: POST /api/table/{db_name}/{table_name}/check_constraints/delete")
            
            app.config['HANDLER'].switch_db(db_name)
            handler = app.config['HANDLER']
            
            if not hasattr(handler, 'delete_check_constraint'):
                return jsonify({'success': False, 'error': 'Handler does not support CHECK constraints'}), 400
            
            data = request.get_json()
            column_name = data.get('column_name')
            
            if not column_name:
                return jsonify({'success': False, 'error': 'Column name is required'}), 400
            
            # Delete CHECK constraint
            handler.delete_check_constraint(table_name, column_name)
            
            return jsonify({
                'success': True,
                'message': f'CHECK constraint removed from {column_name}'
            })
            
        except Exception as e:
            logger.error(f"❌ API call failed: /api/table/{db_name}/{table_name}/check_constraints/delete - {e}")
            return jsonify({'success': False, 'error': str(e)}), 500
        
    @app.route('/api/collection/<db_name>/<collection_name>/validation_rules', methods=['GET'])
    def api_get_validation_rules(db_name, collection_name):
        """JSON API: Get validation rules for a MongoDB collection"""
        try:
            logger.debug(f"✅ API call: GET /api/collection/{db_name}/{collection_name}/validation_rules")
            
            # Ensure we're in NoSQL mode
            if app.config['DB_TYPE'] != 'nosql':
                return jsonify({
                    'success': False,
                    'error': 'This endpoint is for NoSQL collections only'
                }), 400
            
            app.config['HANDLER'].switch_db(db_name)
            handler = app.config['HANDLER']
            
            # Get validation rules
            rules = []
            if hasattr(handler, 'get_check_constraints'):
                rules = handler.get_check_constraints(collection_name)
            
            return jsonify({
                'success': True,
                'rules': rules
            })
            
        except Exception as e:
            logger.error(f"❌ API call failed: /api/collection/{db_name}/{collection_name}/validation_rules - {e}")
            return jsonify({'success': False, 'error': str(e)}), 500
        
    @app.route('/api/collection/<db_name>/<collection_name>/validation', methods=['POST'])
    def api_apply_collection_validation(db_name, collection_name):
        """JSON API: Apply per-field validation rules to a NoSQL collection"""
        try:
            logger.debug(f"✅ API call: POST /api/collection/{db_name}/{collection_name}/validation")
            
            raw_body = request.get_data(as_text=True)
            logger.debug(f"Raw request body: {raw_body}")
            
            data = request.get_json() or {}
            logger.debug(f"Parsed JSON data: {data}")
            
            validation_rules = data.get('validation_rules', {})
            logger.debug(f"Extracted validation_rules: {validation_rules}")
            
            app.config['HANDLER'].switch_db(db_name)
            handler = app.config['HANDLER']
            
            # Temporary: Log what methods the handler has
            logger.debug(f"Handler methods: {dir(handler)}")
            logger.debug(f"Has apply_validation_rules: {hasattr(handler, 'apply_validation_rules')}")
            
            # Temporarily bypass the guard to test
            # if not hasattr(handler, 'apply_validation_rules'):
            #     return jsonify({'success': False, 'error': 'Validation rules are not supported for this database type'}), 400
            
            result = handler.apply_validation_rules(collection_name, validation_rules)
            logger.debug(f"Validation apply result: {result}")
            
            return jsonify({
                'success': True,
                'message': 'Validation rules applied successfully'
            })
            
        except Exception as e:
            logger.error(f"❌ Validation apply error: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/table/<db_name>/<table_name>/query', methods=['POST'])
    def api_table_query(db_name, table_name):
        """JSON API: Execute query for specific table (supports JOINs, GROUP BY, etc.)"""
        try:
            logger.debug(f"✅ API call: POST /api/table/{db_name}/{table_name}/query")

            app.config['HANDLER'].switch_db(db_name)

            data = request.get_json()
            query = data.get('query', '')

            if not query:
                return jsonify({'success': False, 'error': 'Query is required'}), 400

            # ✅ CRITICAL: Detect procedure calls
            query_stripped = query.strip().upper()
            is_procedure = (
                query_stripped.startswith('CALL ') or 
                query_stripped.startswith('EXEC ') or 
                query_stripped.startswith('EXECUTE ')
            )
        
            logger.debug(f"Query type check - Is procedure: {is_procedure}")

            try:
                if is_procedure:
                    # Execute as procedure
                    logger.debug("Executing as procedure")
                    result = app.config['HANDLER'].execute_procedure(query)
                    logger.debug(f"Raw procedure result: {result}")
                
                    # ✅ Format using helper
                    formatted = format_procedure_result(result)
                    logger.debug(f"Formatted procedure result: {formatted}")
                
                    return jsonify({
                        'success': True,
                        'result': formatted['data'],
                        'result_type': formatted['type'],
                        'rows_affected': formatted.get('rows_affected', 0)
                    })
            
                # Not a procedure - handle as regular query
                if app.config['DB_TYPE'] == 'nosql':
                    import json as json_lib
                    query_obj = json_lib.loads(query)
                    result = app.config['HANDLER'].execute_query(query_obj)
                else:
                    result = app.config['HANDLER'].execute_query(query)
            
                logger.debug(f"API: Executed query on {table_name}")
            
                # Unwrap nested results
                if isinstance(result, list) and len(result) == 2:
                    if isinstance(result[0], list) and isinstance(result[1], dict):
                        result = result[0]
                        logger.debug(f"Unwrapped result: {len(result)} rows")
            
                # Format based on type
                formatted_result = None
                result_type = 'data'
            
                if isinstance(result, list):
                    if len(result) > 0:
                        formatted_result = result
                        result_type = 'table'
                    else:
                        formatted_result = []
                        result_type = 'empty'
                elif isinstance(result, dict):
                    if 'rows_affected' in result:
                        formatted_result = result
                        result_type = 'status'
                    else:
                        formatted_result = [result]
                        result_type = 'table'
                else:
                    formatted_result = {'status': str(result)}
                    result_type = 'status'

                return jsonify({
                    'success': True,
                    'result': formatted_result,
                    'result_type': result_type
                })

            except Exception as e:
                error_msg = f"Query execution failed: {str(e)}"
                logger.error(error_msg)
                return jsonify({'success': False, 'error': error_msg}), 500
    
        except Exception as e:
            logger.error(f"❌ API call failed: /api/table/{db_name}/{table_name}/query - {e}")
            return jsonify({'success': False, 'error': str(e)}), 500
        
    @app.route('/api/table/<db_name>/<table_name>/plsql/support', methods=['GET'])
    def api_plsql_support(db_name, table_name):
        """JSON API: Check if PL/SQL is supported"""
        try:
            app.config['HANDLER'].switch_db(db_name)
        
            supports_plsql = False
            if hasattr(app.config['HANDLER'], 'supports_plsql'):
                supports_plsql = app.config['HANDLER'].supports_plsql()
            elif hasattr(app.config['HANDLER'], 'handler') and hasattr(app.config['HANDLER'].handler, 'supports_plsql'):
                supports_plsql = app.config['HANDLER'].handler.supports_plsql()
        
            return jsonify({
                'success': True,
                'supports_plsql': supports_plsql
            })
        except Exception as e:
            logger.error(f"API PL/SQL support check error: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500
        
    @app.route('/api/db/<db_name>/create_table', methods=['POST'])
    def api_create_table(db_name):
        """JSON API: Create new table"""
        try:
            logger.debug(f"✅ API call: POST /api/db/{db_name}/create_table")

            app.config['HANDLER'].switch_db(db_name)

            data = request.get_json()
            table_name = data.get('table_name', '')
            columns = data.get('columns', [])

            # Validate table name
            if not table_name or not re.match(r'^[a-zA-Z][a-zA-Z0-9_]*$', table_name):
                return jsonify({
                    'success': False,
                    'error': 'Table name must start with a letter, contain only letters, numbers, underscores.'
                }), 400

            if table_name in app.config['HANDLER'].list_tables():
                return jsonify({
                    'success': False,
                    'error': 'Table name already exists.'
                }), 400

            if not columns or len(columns) < 1 or len(columns) > 20:
                return jsonify({
                    'success': False,
                    'error': 'Number of columns must be between 1 and 20.'
                }), 400

            # Validate columns
            has_pk = False

            # ✅ Validate CHECK constraints
            handler = app.config['HANDLER']
            actual_handler = handler.handler if hasattr(handler, 'handler') else handler

            for col in columns:
                check_expr = col.get('check_constraint')
                if check_expr:
                    if hasattr(actual_handler, 'validate_check_constraint'):
                        if not actual_handler.validate_check_constraint(check_expr):
                            return jsonify({
                                'success': False,
                                'error': f'Invalid CHECK constraint for column {col.get("name")}: {check_expr}'
                            }), 400

            col_defs = []

            # Get handler type for database-specific syntax
            handler = app.config['HANDLER']
            actual_handler = handler.handler if hasattr(handler, 'handler') else handler
            db_handler_name = actual_handler.DB_NAME if hasattr(actual_handler, 'DB_NAME') else 'SQLite'

            # ✅ For DuckDB, create sequences OUTSIDE the main transaction first
            if db_handler_name == 'DuckDB':
                with app.config['HANDLER']._get_connection() as conn:
                    for col in columns:
                        if col.get('is_autoincrement', False):
                            col_name = col.get('name', '').strip()
                            seq_name = f"{table_name}_{col_name}_seq"
                            quoted_seq = actual_handler._quote_identifier(seq_name)
                        
                            try:
                                conn.execute(text(f"CREATE OR REPLACE SEQUENCE {quoted_seq} START 1"))
                                conn.commit()
                                logger.debug(f"Created sequence {seq_name} for DuckDB autoincrement")
                            except Exception as e:
                                logger.error(f"Failed to create sequence {seq_name}: {e}")
                                try:
                                    conn.execute(text(f"DROP SEQUENCE IF EXISTS {quoted_seq}"))
                                    conn.commit()
                                    conn.execute(text(f"CREATE SEQUENCE {quoted_seq} START 1"))
                                    conn.commit()
                                except Exception as e2:
                                    logger.error(f"Failed to create sequence (attempt 2): {e2}")

            for col in columns:
                name = col.get('name', '').strip()
                type_ = col.get('type', 'TEXT')
                is_pk = col.get('is_pk', False)
                is_not_null = col.get('is_not_null', False)
                is_autoincrement = col.get('is_autoincrement', False)
                is_unique = col.get('is_unique', False)
                check_expr = col.get('check_constraint', '').strip()  # ✅ GET CHECK

                if not name or (app.config['DB_TYPE'] == 'sql' and not type_):
                    return jsonify({
                        'success': False,
                        'error': f'Column name and type are required'
                    }), 400

                if is_pk:
                    if has_pk:
                        return jsonify({
                            'success': False,
                            'error': 'Only one primary key allowed.'
                        }), 400
                    has_pk = True

                # ✅ Use type_ AS-IS (already includes length from frontend)
                quoted_name = name
                if hasattr(app.config['HANDLER'], 'handler'):
                    actual_handler = app.config['HANDLER'].handler
                    if hasattr(actual_handler, '_quote_identifier'):
                        quoted_name = actual_handler._quote_identifier(name)

                base_type_with_length = type_  # Already "VARCHAR(100)", not just "VARCHAR"

                # Use handler method to build column definition
                col_def = None

                if hasattr(actual_handler, 'build_column_definition_for_create'):
                    col_def = actual_handler.build_column_definition_for_create(
                        quoted_name, 
                        base_type_with_length,
                        is_pk, 
                        is_not_null, 
                        is_autoincrement, 
                        is_unique,
                        table_name
                    )
                else:
                    # Fallback: build generic definition
                    col_def = f"{quoted_name} {base_type_with_length}"
                    
                    if is_pk:
                        col_def += " PRIMARY KEY"
                        if is_autoincrement:
                            col_def += " AUTOINCREMENT"
                    else:
                        if is_not_null:
                            col_def += " NOT NULL"
                        if is_unique:
                            col_def += " UNIQUE"
                
                # ✅ ADD CHECK CONSTRAINT (works for all databases)
                if check_expr:
                    col_def += f" CHECK ({check_expr})"
                    logger.debug(f"✅ Added CHECK constraint to {name}: {check_expr}")

                logger.debug(f"Create table - Column {name}: type={type_}, is_pk={is_pk}, is_autoincrement={is_autoincrement}, check={check_expr}, col_def={col_def}")

                col_defs.append(col_def)

            if not col_defs:
                return jsonify({
                    'success': False,
                    'error': 'At least one column is required.'
                }), 400

            # Create table (sequences already created for DuckDB)
            try:
                col_def_str = ', '.join(col_defs)

                quoted_table = table_name
                if hasattr(app.config['HANDLER'], 'handler'):
                    actual_handler = app.config['HANDLER'].handler
                    if hasattr(actual_handler, '_quote_identifier'):
                        quoted_table = actual_handler._quote_identifier(table_name)
                    elif hasattr(actual_handler, 'DB_NAME') and actual_handler.DB_NAME == 'PostgreSQL':
                        quoted_table = f'"{table_name}"'

                # ✅ Now create the table in a separate transaction
                with app.config['HANDLER']._get_connection() as conn:
                    create_sql = f'CREATE TABLE IF NOT EXISTS {quoted_table} ({col_def_str})'
                    logger.debug(f"CREATE TABLE SQL: {create_sql}")  # ✅ ADD DEBUG LOG
                    app.config['HANDLER']._execute(create_sql)
                    conn.commit()

                logger.debug(f"API: Created table {table_name} in {db_name}")

                return jsonify({
                    'success': True,
                    'message': f'Table {table_name} created successfully',
                    'table_name': table_name
                })

            except Exception as e:
                logger.error(f"Create table error: {str(e)}")
                return jsonify({
                    'success': False,
                    'error': str(e)  # Remove the 'Failed to create table:' prefix
                }), 400  # Changed from 500 to 400 since this is a validation/user error

        except Exception as e:
            logger.error(f"❌ API call failed: /api/db/{db_name}/create_table - {e}")
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/db/<db_name>/supported_types', methods=['GET'])
    def api_supported_types(db_name):
        """JSON API: Get supported column types"""
        try:
            app.config['HANDLER'].switch_db(db_name)
            types = app.config['HANDLER'].get_supported_types() if app.config['DB_TYPE'] == 'sql' else []
        
            return jsonify({
                'success': True,
                'types': types
            })
        except Exception as e:
            logger.error(f"Failed to get supported types: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500
        
    @app.route('/api/db/<db_name>/diagram_data', methods=['GET'])
    def api_diagram_data(db_name):
        """JSON API: Get diagram data"""
        try:
            logger.debug(f"✓ API call: GET /api/db/{db_name}/diagram_data")
        
            app.config['HANDLER'].switch_db(db_name)
        
            diagram_type = request.args.get('type', 'er')
        
            if app.config['DB_TYPE'] == 'sql':
                if diagram_type == 'er':
                    diagram_data = generate_er_diagram_data(db_name)
                elif diagram_type == 'schema':
                    diagram_data = generate_schema_diagram_data(db_name)
                else:
                    return jsonify({
                        'success': False,
                    'error': 'Unknown diagram type'
                    }), 400
            else:
                # NoSQL diagrams
                if diagram_type == 'collections':
                    diagram_data = generate_collections_diagram_data(db_name)
                elif diagram_type == 'hierarchy':
                    diagram_data = generate_hierarchy_diagram_data(db_name)
                else:
                    return jsonify({
                        'success': False,
                        'error': 'Unknown diagram type'
                    }), 400
        
            return jsonify({
                'success': True,
                'data': diagram_data,
                'db_type': app.config['DB_TYPE']
            })
    
        except Exception as e:
            logger.error(f"Diagram data fetch error: {str(e)}")
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500

    @app.route('/api/table/<db_name>/<table_name>/chart_data', methods=['GET'])
    def api_chart_data(db_name, table_name):
        """JSON API: Get chart data"""
        try:
            logger.debug(f"✓ API call: GET /api/table/{db_name}/{table_name}/chart_data")
        
            app.config['HANDLER'].switch_db(db_name)
        
            # Fetch ALL rows/documents (no pagination)
            all_data = app.config['HANDLER'].read(table_name)
        
            # Get schema/keys
            if app.config['DB_TYPE'] == 'sql':
                columns = app.config['HANDLER'].get_table_schema(table_name)
                keys = [col['name'] for col in columns]
            else:
                keys = app.config['HANDLER'].get_all_keys(table_name)
                primary_key = app.config['HANDLER'].get_primary_key_name()
                if primary_key not in keys:
                    keys.insert(0, primary_key)
        
            return jsonify({
                'success': True,
                'data': all_data,
                'keys': keys,
                'total': len(all_data)
            })
        except Exception as e:
            logger.error(f"Chart data fetch error: {str(e)}")
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500
            
    @app.route('/api/db/<db_name>/triggers', methods=['GET'])
    def api_list_all_triggers(db_name):
        """JSON API: Get all triggers in database"""
        try:
            logger.debug(f"✓ API call: GET /api/db/{db_name}/triggers")
        
            app.config['HANDLER'].switch_db(db_name)
        
            supports_triggers = app.config['HANDLER'].supports_triggers()
            triggers = []
        
            if supports_triggers:
                try:
                    triggers = app.config['HANDLER'].list_triggers()
                except Exception as e:
                    logger.error(f"Error listing all triggers: {e}")
        
            return jsonify({
                'success': True,
                'triggers': triggers,
                'supports_triggers': supports_triggers,
                'db_type': app.config['DB_TYPE'],
                'handler': app.config['CURRENT_HANDLER_NAME']
            })
        
        except Exception as e:
            logger.error(f"✗ API call failed: /api/db/{db_name}/triggers - {e}")
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/db/<db_name>/triggers/delete', methods=['POST'])
    def api_delete_trigger_from_list(db_name):
        """JSON API: Delete trigger from database-level list"""
        try:
            app.config['HANDLER'].switch_db(db_name)
        
            data = request.get_json()
            trigger_name = data.get('trigger_name')
        
            if not trigger_name:
                return jsonify({
                    'success': False,
                    'error': 'Trigger name is required'
                }), 400
        
            # Find which table the trigger belongs to
            triggers = app.config['HANDLER'].list_triggers()
            trigger_table = None
        
            for t in triggers:
                if t['name'] == trigger_name:
                    trigger_table = t.get('table')
                    break
        
            if not trigger_table:
                return jsonify({
                    'success': False,
                    'error': f'Could not find table for trigger {trigger_name}'
                }), 404
        
            app.config['HANDLER'].delete_trigger(trigger_name, trigger_table)
            logger.debug(f"API: Deleted trigger {trigger_name} from table {trigger_table}")
        
            return jsonify({
                'success': True,
                'message': f'Trigger {trigger_name} deleted successfully'
            })
        
        except Exception as e:
            logger.error(f"API delete trigger error: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/db/<db_name>/procedures', methods=['GET'])
    def api_list_all_procedures(db_name):
        """JSON API: Get all procedures in database"""
        try:
            logger.debug(f"✓ API call: GET /api/db/{db_name}/procedures")
        
            app.config['HANDLER'].switch_db(db_name)
        
            supports_procedures = app.config['HANDLER'].supports_procedures()
            procedures = []
        
            if supports_procedures:
                try:
                    procedures = app.config['HANDLER'].list_procedures()
                except Exception as e:
                    logger.error(f"Error listing procedures: {e}")
        
            return jsonify({
                'success': True,
                'procedures': procedures,
                'supports_procedures': supports_procedures,
                'db_type': app.config['DB_TYPE'],
                'handler': app.config['CURRENT_HANDLER_NAME']
            })
        
        except Exception as e:
            logger.error(f"✗ API call failed: /api/db/{db_name}/procedures - {e}")
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/db/<db_name>/procedure/<procedure_name>/code', methods=['GET'])
    def api_get_procedure_code_from_list(db_name, procedure_name):
        """JSON API: Get procedure definition from database-level list"""
        try:
            app.config['HANDLER'].switch_db(db_name)
        
            if hasattr(app.config['HANDLER'], 'get_procedure_definition'):
                code = app.config['HANDLER'].get_procedure_definition(procedure_name)
                if code:
                    return jsonify({
                        'success': True,
                        'code': code
                    })
                else:
                    return jsonify({
                        'success': False,
                        'error': 'Procedure not found'
                    }), 404
        
            return jsonify({
                'success': False,
                'error': 'Not supported'
            }), 400
        
        except Exception as e:
            logger.error(f"API get procedure code error: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/db/<db_name>/procedure/drop', methods=['POST'])
    def api_drop_procedure_from_list(db_name):
        """JSON API: Drop procedure from database-level list"""
        try:
            app.config['HANDLER'].switch_db(db_name)
        
            data = request.get_json()
            procedure_name = data.get('procedure_name')
            is_function = data.get('is_function', False)
        
            if not procedure_name:
                return jsonify({
                    'success': False,
                    'error': 'Procedure name is required'
                }), 400
        
            if hasattr(app.config['HANDLER'], 'drop_procedure'):
                app.config['HANDLER'].drop_procedure(procedure_name, is_function)
                return jsonify({
                    'success': True,
                    'message': f'{"Function" if is_function else "Procedure"} {procedure_name} dropped successfully'
                })
        
            return jsonify({
                'success': False,
                'error': 'Not supported'
            }), 400
        
        except Exception as e:
            logger.error(f"API drop procedure error: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500
        
    @app.route('/api/query', methods=['GET', 'POST'])
    def api_global_query():
        """JSON API: Global query console"""
        try:
            if request.method == 'GET':
                logger.debug("✅ API call: GET /api/query")
    
                current_db = app.config['HANDLER'].current_db
    
                return jsonify({
                    'success': True,
                    'db_type': app.config['DB_TYPE'],
                    'handler': app.config['CURRENT_HANDLER_NAME'],
                    'current_db': current_db
                })

            elif request.method == 'POST':
                logger.debug("✅ API call: POST /api/query")

                data = request.get_json()
                query = data.get('query', '').strip()
    
                if not query:
                    return jsonify({
                        'success': False,
                        'error': 'Query is required'
                    }), 400
    
                current_db = app.config['HANDLER'].current_db
                error = None
                result = None

                if app.config['DB_TYPE'] == 'sql':
                    # === SQL: Handle multi-statement queries ===
                    statements = [s.strip() for s in query.split(';') if s.strip()]
                    results = []
        
                    for stmt in statements:
                        stmt_upper = stmt.upper()
                
                        # ✅ Check if it's a procedure call
                        is_procedure = (
                            stmt_upper.startswith('CALL ') or 
                            stmt_upper.startswith('EXEC ') or 
                            stmt_upper.startswith('EXECUTE ')
                        )
                
                        logger.debug(f"Statement: {stmt[:50]}... Is procedure: {is_procedure}")

                        try:
                            if is_procedure:
                                # Execute as procedure
                                if not current_db:
                                    error = "No database selected. Use: CREATE DATABASE name; or USE database_name;"
                                    break
                        
                                logger.debug("Executing as procedure")
                                proc_result = app.config['HANDLER'].execute_procedure(stmt)
                                logger.debug(f"Raw procedure result: {proc_result}")
                        
                                # Format using helper
                                formatted = format_procedure_result(proc_result)
                                logger.debug(f"Formatted procedure result: {formatted}")
                        
                                # Add result_type to the data
                                result_with_type = {
                                    'result': formatted['data'],
                                    'result_type': formatted['type'],
                                    'rows_affected': formatted.get('rows_affected', 0)
                                }
                                results.append(result_with_type)
                        
                            # === 1. CREATE DATABASE ===
                            elif stmt_upper.startswith('CREATE DATABASE'):
                                match = re.match(r'CREATE\s+DATABASE\s+([a-zA-Z][a-zA-Z0-9_]*)', stmt, re.I)
                                if not match:
                                    error = "Invalid CREATE DATABASE syntax."
                                    break
                                db_name = match.group(1)
                                if db_name in app.config['HANDLER'].list_dbs():
                                    error = f"Database '{db_name}' already exists."
                                    break
                                app.config['HANDLER'].create_db(db_name)
                                app.config['HANDLER'].switch_db(db_name)
                                current_db = db_name
                                results.append({"status": f"Database '{db_name}' created and selected."})
                
                            # === 2. DROP DATABASE ===
                            elif stmt_upper.startswith('DROP DATABASE'):
                                match = re.match(r'DROP\s+DATABASE\s+([a-zA-Z][a-zA-Z0-9_]*)', stmt, re.I)
                                if not match:
                                    error = "Invalid DROP DATABASE syntax."
                                    break
                                db_name = match.group(1)
                                if db_name not in app.config['HANDLER'].list_dbs():
                                    error = f"Database '{db_name}' does not exist."
                                    break
                                if current_db == db_name:
                                    error = "Cannot drop current database. Switch to another database first."
                                    break
                                app.config['HANDLER'].delete_db(db_name)
                                results.append({"status": f"Database '{db_name}' dropped."})
                
                            # === 3. USE DATABASE ===
                            elif stmt_upper.startswith('USE '):
                                match = re.match(r'USE\s+([a-zA-Z][a-zA-Z0-9_]*)', stmt, re.I)
                                if not match:
                                    error = "Invalid USE syntax. Usage: USE database_name;"
                                    break
                                db_name = match.group(1)
                                if db_name not in app.config['HANDLER'].list_dbs():
                                    error = f"Database '{db_name}' does not exist."
                                    break
                                app.config['HANDLER'].switch_db(db_name)
                                current_db = db_name
                                results.append({"status": f"Switched to database '{db_name}'."})
                
                            # === 4. NORMAL SQL QUERIES ===
                            else:
                                if not current_db:
                                    error = "No database selected. Use: CREATE DATABASE name; or USE database_name;"
                                    break
                                    
                                with app.config['HANDLER']._get_connection() as conn:
                                    exec_result = conn.execute(text(stmt))
                        
                                    if stmt_upper.startswith('SELECT') or stmt_upper.startswith('SHOW') or stmt_upper.startswith('DESCRIBE'):
                                        rows = [dict(row._mapping) for row in exec_result.fetchall()]
                                        results.append(rows)
                                    else:
                                        conn.commit()
                                        results.append({"rows_affected": exec_result.rowcount})
            
                        except Exception as e:
                            error = f"Error in statement '{stmt[:50]}...': {str(e)}"
                            logger.error(f"Query error: {str(e)}")
                            break
        
                    if not error:
                        result = results if results else [{"status": "Query executed successfully."}]
                    
                    return jsonify({
                        'success': True if not error else False,
                        'result': result,
                        'error': error,
                        'current_db': current_db
                    })
    
                else:
                    # === NoSQL: Handle multiple commands/queries ===
                    lines = [line.strip() for line in query.split(';') if line.strip()]
                    results = []

                    for line in lines:
                        try:
                            # ✅ FIX: Check database-level commands FIRST
                            line_upper = line.upper()
                        
                            # Database commands that don't need a selected database
                            if line_upper.startswith('CREATE DATABASE'):
                                match = re.match(r'CREATE\s+DATABASE\s+([a-zA-Z][a-zA-Z0-9_]*)', line, re.I)
                                if not match:
                                    error = "Invalid CREATE DATABASE syntax."
                                    break
                                db_name = match.group(1)
                                if db_name in app.config['HANDLER'].list_dbs():
                                    error = f"Database '{db_name}' already exists."
                                    break
                                app.config['HANDLER'].create_db(db_name)
                                app.config['HANDLER'].switch_db(db_name)
                                current_db = db_name
                                results.append({"status": f"Database '{db_name}' created and selected."})
                                continue

                            elif line_upper.startswith('USE '):
                                match = re.match(r'USE\s+([a-zA-Z][a-zA-Z0-9_]*)', line, re.I)
                                if not match:
                                    error = "Invalid USE syntax. Usage: USE database_name;"
                                    break
                                db_name = match.group(1)
                                if db_name not in app.config['HANDLER'].list_dbs():
                                    error = f"Database '{db_name}' does not exist."
                                    break
                                app.config['HANDLER'].switch_db(db_name)
                                current_db = db_name
                                results.append({"status": f"Switched to database '{db_name}'."})
                                continue

                            elif line_upper.startswith('DROP DATABASE'):
                                match = re.match(r'DROP\s+DATABASE\s+([a-zA-Z][a-zA-Z0-9_]*)', line, re.I)
                                if not match:
                                    error = "Invalid DROP DATABASE syntax."
                                    break
                                db_name = match.group(1)
                                if db_name not in app.config['HANDLER'].list_dbs():
                                    error = f"Database '{db_name}' does not exist."
                                    break
                                if current_db == db_name:
                                    error = "Cannot drop current database. Switch to another database first."
                                    break
                                app.config['HANDLER'].delete_db(db_name)
                                results.append({"status": f"Database '{db_name}' dropped."})
                                continue

                            elif line_upper == 'SHOW DATABASES':
                                dbs = app.config['HANDLER'].list_dbs()
                                results.append([{"database": db} for db in dbs])
                                continue

                            # ✅ ALL OTHER COMMANDS: Pass to handler's execute_query
                            # This includes SHOW TABLES, CREATE COLLECTION, INSERT, SELECT, etc.
                            if not current_db:
                                error = "No database selected. Use: USE database_name;"
                                break

                            try:
                                query_result = app.config['HANDLER'].execute_query(line)
                                formatted_result = format_nosql_result(query_result, app.config['HANDLER'])

                                # Extract status messages from single-item lists
                                if isinstance(formatted_result, list) and len(formatted_result) == 1:
                                    if isinstance(formatted_result[0], dict) and 'status' in formatted_result[0]:
                                        results.append(formatted_result[0])
                                    else:
                                        results.append(formatted_result)
                                else:
                                    results.append(formatted_result)
                            except Exception as query_error:
                                error = f"Query execution failed: {str(query_error)}"
                                logger.error(f"NoSQL query error: {str(query_error)}")
                                break
                            
                        except Exception as e:
                            error = f"Error happened: {str(e)}"
                            logger.error(f"NoSQL query error: {str(e)}")
                            break
                        
                    # Set result only if no errors
                    if not error:
                        result = results if results else [{"status": "Commands executed successfully."}]
                    
                    return jsonify({
                        'success': not error,
                        'result': result,
                        'error': error,
                        'current_db': current_db
                    })

        except Exception as e:
            logger.error(f"❌ API call failed: /api/query - {e}")
            return jsonify({'success': False, 'error': str(e)}), 500
        
    # ===== USER MANAGEMENT JSON API ROUTES (for React) =====

    @app.route('/api/db/<db_name>/users', methods=['GET'])
    def api_db_users(db_name):
        """JSON API: Get users for database"""
        try:
            logger.debug(f"✓ API call: GET /api/db/{db_name}/users")
        
            app.config['HANDLER'].switch_db(db_name)
            handler = app.config['HANDLER']
        
            # Check if handler supports user management
            supports_users = hasattr(handler, 'supports_user_management') and handler.supports_user_management()
        
            users = []
            if supports_users:
                try:
                    users = handler.list_users()
                except Exception as e:
                    logger.error(f"Error listing users: {str(e)}")
        
            # Check if handler requires credentials for users
            requires_credentials = True  # Default to True for security
            if hasattr(handler, 'requires_credentials'):
                requires_credentials = handler.requires_credentials()
            
            return jsonify({
                'success': True,
                'users': users,
                'supports_users': supports_users,
                'requires_credentials': requires_credentials,
                'db_type': app.config['DB_TYPE'],
                'handler': app.config['CURRENT_HANDLER_NAME']
            })
        
        except Exception as e:
            logger.error(f"✗ API call failed: /api/db/{db_name}/users - {e}")
            return jsonify({'success': False, 'error': str(e)}), 500
        
    @app.route('/api/db/<db_name>/users/create', methods=['POST'])
    def api_create_user(db_name):
        """JSON API: Create new user"""
        try:
            logger.debug(f"✓ API call: POST /api/db/{db_name}/users/create")
        
            app.config['HANDLER'].switch_db(db_name)
            handler = app.config['HANDLER']
        
            if not handler.supports_user_management():
                return jsonify({'success': False, 'error': 'User management not supported'}), 400
        
            data = request.get_json()
            username = data.get('username')
            password = data.get('password', '')
            privileges = data.get('privileges', [])
        
            # ✅ DIAGNOSTIC LOGGING
            logger.info(f"=" * 80)
            logger.info(f"API CREATE USER DEBUG")
            logger.info(f"Username: {username}")
            logger.info(f"Password: {'<set>' if password else '<empty>'}")
            logger.info(f"Privileges received: {privileges}")
            logger.info(f"Privileges type: {type(privileges)}")
            logger.info(f"Privileges repr: {repr(privileges)}")
            logger.info(f"=" * 80)
        
            if not username:
                return jsonify({'success': False, 'error': 'Username is required'}), 400
        
            try:
                handler.create_user(username, password, privileges)
                logger.debug(f"API: Created user {username}")
                return jsonify({
                    'success': True,
                    'message': f'User {username} created successfully'
                })
            except Exception as e:
                logger.error(f"Create user error: {str(e)}")
                return jsonify({'success': False, 'error': str(e)}), 500
            
        except Exception as e:
            logger.error(f"✗ API call failed: /api/db/{db_name}/users/create - {e}")
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/db/<db_name>/users/delete', methods=['POST'])
    def api_delete_user(db_name):
        """JSON API: Delete user"""
        try:
            logger.debug(f"✓ API call: POST /api/db/{db_name}/users/delete")
        
            app.config['HANDLER'].switch_db(db_name)
            handler = app.config['HANDLER']
        
            if not handler.supports_user_management():
                return jsonify({'success': False, 'error': 'User management not supported'}), 400
        
            data = request.get_json()
            username = data.get('username')
        
            # ✅ DIAGNOSTIC LOGGING
            logger.info(f"=" * 80)
            logger.info(f"API DELETE USER DEBUG")
            logger.info(f"Username: {username}")
            logger.info(f"Handler type: {type(handler).__name__}")
            logger.info(f"Current DB: {handler.current_db}")
            logger.info(f"=" * 80)
        
            if not username:
                return jsonify({'success': False, 'error': 'Username is required'}), 400
        
            try:
                handler.delete_user(username)
                logger.debug(f"API: Deleted user {username}")
                return jsonify({
                    'success': True,
                    'message': f'User {username} deleted successfully'
                })
            except Exception as e:
                logger.error(f"Delete user error: {str(e)}")
                logger.exception("Full traceback:")
                return jsonify({'success': False, 'error': str(e)}), 500
            
        except Exception as e:
            logger.error(f"✗ API call failed: /api/db/{db_name}/users/delete - {e}")
            return jsonify({'success': False, 'error': str(e)}), 500
    
    @app.route('/api/db/<db_name>/users/update', methods=['POST'])
    def api_update_user(db_name):
        """JSON API: Update user"""
        try:
            logger.debug(f"✓ API call: POST /api/db/{db_name}/users/update")
        
            app.config['HANDLER'].switch_db(db_name)
            handler = app.config['HANDLER']
        
            if not handler.supports_user_management():
                return jsonify({'success': False, 'error': 'User management not supported'}), 400
        
            data = request.get_json()
            username = data.get('username')
            password = data.get('password', '')
            privileges = data.get('privileges', [])
        
            if not username:
                return jsonify({'success': False, 'error': 'Username is required'}), 400
        
            try:
                handler.update_user(username, password, privileges)
                logger.debug(f"API: Updated user {username}")
                return jsonify({
                    'success': True,
                    'message': f'User {username} updated successfully'
                })
            except Exception as e:
                logger.error(f"Update user error: {str(e)}")
                return jsonify({'success': False, 'error': str(e)}), 500
            
        except Exception as e:
            logger.error(f"✗ API call failed: /api/db/{db_name}/users/update - {e}")
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/db/<db_name>/users/<username>/privileges', methods=['GET'])
    def api_get_user_privileges(db_name, username):
        """JSON API: Get user privileges"""
        try:
            logger.debug(f"✓ API call: GET /api/db/{db_name}/users/{username}/privileges")
        
            app.config['HANDLER'].switch_db(db_name)
            handler = app.config['HANDLER']
        
            try:
                privileges = handler.get_user_privileges(username)
                return jsonify({
                    'success': True,
                    'privileges': privileges,
                    'username': username
                })
            except Exception as e:
                logger.error(f"Error getting privileges: {str(e)}")
                return jsonify({'success': False, 'error': str(e)}), 500
        
        except Exception as e:
            logger.error(f"✗ API call failed: /api/db/{db_name}/users/{username}/privileges - {e}")
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/db/<db_name>/users/<username>/connection', methods=['GET'])
    def api_get_user_connection(db_name, username):
        """JSON API: Get user connection info"""
        try:
            logger.debug(f"✓ API call: GET /api/db/{db_name}/users/{username}/connection")
        
            app.config['HANDLER'].switch_db(db_name)
            handler = app.config['HANDLER']
        
            try:
                conn_info = handler.get_user_connection_info(username)
                return jsonify({
                    'success': True,
                    'connection_string': conn_info['connection_string'],
                    'test_code': conn_info['test_code'],
                    'notes': conn_info.get('notes', [])
                })
            except Exception as e:
                logger.error(f"Error getting connection info: {str(e)}")
                return jsonify({'success': False, 'error': str(e)}), 500
        
        except Exception as e:
            logger.error(f"✗ API call failed: /api/db/{db_name}/users/{username}/connection - {e}")
            return jsonify({'success': False, 'error': str(e)}), 500
    
    @app.route('/api/db/<db_name>/nosql_query', methods=['POST'])
    def api_nosql_db_query(db_name):
        """JSON API: Execute NoSQL query in database context - NO VALIDATION"""
        try:
            logger.debug(f"✅ API call: POST /api/db/{db_name}/nosql_query")

            # Ensure we're in NoSQL mode
            if app.config['DB_TYPE'] != 'nosql':
                return jsonify({
                    'success': False,
                    'error': 'This endpoint is for NoSQL databases only'
                }), 400

            app.config['HANDLER'].switch_db(db_name)
    
            data = request.get_json()
            query = data.get('query', '').strip()

            if not query:
                return jsonify({'success': False, 'error': 'Query is required'}), 400

            try:
                # ✅ CRITICAL: Pass query directly with NO preprocessing
                result = app.config['HANDLER'].execute_query(query)

                logger.debug(f"API: Executed NoSQL query in {db_name}")
    
                # ✅ Format result for display
                formatted_result = format_nosql_result(result, app.config['HANDLER'])
    
                return jsonify({
                    'success': True,
                    'result': formatted_result
                })

            except Exception as e:
                error_msg = f"Query execution failed: {str(e)}"
                logger.error(error_msg)
                return jsonify({'success': False, 'error': error_msg}), 500

        except Exception as e:
            logger.error(f"❌ API call failed: /api/db/{db_name}/nosql_query - {e}")
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/collection/<db_name>/<collection_name>/query', methods=['POST'])
    def api_collection_query(db_name, collection_name):
        """JSON API: Execute query for specific collection - NO VALIDATION"""
        try:
            logger.debug(f"✅ API call: POST /api/collection/{db_name}/{collection_name}/query")

            if app.config['DB_TYPE'] != 'nosql':
                return jsonify({
                    'success': False,
                    'error': 'This endpoint is for NoSQL collections only'
                }), 400

            app.config['HANDLER'].switch_db(db_name)

            data = request.get_json()
            query = data.get('query', '').strip()

            if not query:
                return jsonify({'success': False, 'error': 'Query is required'}), 400

            try:
                # ✅ Pass query directly - let handler deal with it
                result = app.config['HANDLER'].execute_query(query)
    
                logger.debug(f"API: Executed query on collection {collection_name}")

                # ✅ Format result
                formatted_result = format_nosql_result(result, app.config['HANDLER'])
    
                return jsonify({
                    'success': True,
                    'result': formatted_result
                })

            except Exception as e:
                error_msg = f"Query execution failed: {str(e)}"
                logger.error(error_msg)
                return jsonify({'success': False, 'error': error_msg}), 500

        except Exception as e:
            logger.error(f"❌ API call failed: /api/collection/{db_name}/{collection_name}/query - {e}")
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/collection/<db_name>/<collection_name>', methods=['GET'])
    def api_collection_details(db_name, collection_name):
        """JSON API: Get collection details with documents"""
        try:
            logger.debug(f"✅ API call: GET /api/collection/{db_name}/{collection_name}")
        
            # Ensure we're in NoSQL mode
            if app.config['DB_TYPE'] != 'nosql':
                return jsonify({
                    'success': False,
                    'error': 'This endpoint is for NoSQL collections only'
                }), 400
        
            app.config['HANDLER'].switch_db(db_name)
        
            # Get pagination params
            page = request.args.get('page', 1, type=int)
            per_page = request.args.get('per_page', 20, type=int)
        
            # Get the primary key name from handler
            primary_key = app.config['HANDLER'].get_primary_key_name()
        
            # Get all documents
            all_documents = app.config['HANDLER'].read(collection_name)
        
            # Get all unique keys (excluding primary key, we'll add it separately)
            try:
                all_keys = app.config['HANDLER'].get_all_keys(collection_name)
                # Add primary key at the beginning
                if primary_key not in all_keys:
                    all_keys.insert(0, primary_key)
            except Exception as e:
                all_keys = [primary_key]
                logger.error(f"Keys fetch error: {e}")
        
            total_docs = len(all_documents)
            total_pages = (total_docs + per_page - 1) // per_page
        
            # Paginate
            start = (page - 1) * per_page
            end = start + per_page
            documents = all_documents[start:end]
        
            # ✅ FIX: Clean up documents - use only ONE ID field
            cleaned_documents = []
            for doc in documents:
                clean_doc = {}
            
                # Add primary key first
                if primary_key in doc:
                    clean_doc[primary_key] = doc[primary_key]
            
                # Add other fields (skip alternate ID fields)
                for key, value in doc.items():
                    if key != primary_key and key not in ['_id', 'doc_id']:
                        clean_doc[key] = value
                    elif key == primary_key:
                        continue  # Already added
            
                cleaned_documents.append(clean_doc)
        
            return jsonify({
                'success': True,
                'documents': cleaned_documents,
                'keys': all_keys,
                'primary_key': primary_key,
                'total_docs': total_docs,
                'page': page,
                'per_page': per_page,
                'total_pages': total_pages
            })
        
        except Exception as e:
            logger.error(f"❌ API call failed: /api/collection/{db_name}/{collection_name} - {e}")
            return jsonify({'success': False, 'error': str(e)}), 500
        
    @app.route('/api/db/<db_name>/create_collection', methods=['POST'])
    def api_create_collection(db_name):
        """JSON API: Create new collection (NoSQL only)"""
        try:
            logger.debug(f"✅ API call: POST /api/db/{db_name}/create_collection")
        
            # Ensure we're in NoSQL mode
            if app.config['DB_TYPE'] != 'nosql':
                return jsonify({
                    'success': False,
                    'error': 'This endpoint is for NoSQL databases only'
                }), 400
        
            app.config['HANDLER'].switch_db(db_name)

            data = request.get_json()
            collection_name = data.get('collection_name', '')
        
            # Validate collection name
            if not collection_name or not re.match(r'^[a-zA-Z][a-zA-Z0-9_]*$', collection_name):
                return jsonify({
                    'success': False,
                    'error': 'Collection name must start with a letter, contain only letters, numbers, underscores.'
                }), 400
        
            if collection_name in app.config['HANDLER'].list_tables():
                return jsonify({
                    'success': False,
                    'error': 'Collection name already exists.'
                }), 400
        
            try:
                app.config['HANDLER'].create_collection(collection_name)
                logger.debug(f"API: Created collection {collection_name} in {db_name}")

                return jsonify({
                    'success': True,
                    'message': f'Collection {collection_name} created successfully',
                    'collection_name': collection_name
                })
        
            except Exception as e:
                logger.error(f"Create collection error: {str(e)}")
                return jsonify({
                    'success': False,
                    'error': f'Failed to create collection: {str(e)}'
                }), 500
        
        except Exception as e:
            logger.error(f"❌ API call failed: /api/db/{db_name}/create_collection - {e}")
            return jsonify({'success': False, 'error': str(e)}), 500
        
    @app.route('/api/db/<db_name>/collection/<collection_name>/delete', methods=['POST'])
    def api_delete_collection(db_name, collection_name):
        """JSON API: Delete a collection (NoSQL only)"""
        try:
            logger.debug(f"✅ API call: POST /api/db/{db_name}/collection/{collection_name}/delete")
        
            # Ensure we're in NoSQL mode
            if app.config['DB_TYPE'] != 'nosql':
                return jsonify({
                    'success': False,
                    'error': 'This endpoint is for NoSQL collections only'
                }), 400
        
            app.config['HANDLER'].switch_db(db_name)
            app.config['HANDLER'].delete_table(collection_name)
        
            logger.debug(f"API: Deleted collection {collection_name} from {db_name}")
        
            return jsonify({
                'success': True,
                'message': f'Collection {collection_name} deleted successfully'
            })
    
        except Exception as e:
            logger.error(f"❌ API call failed: /api/db/{db_name}/collection/{collection_name}/delete - {e}")
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/sign_out', methods=['POST'])
    def api_sign_out():
        """JSON API: Sign out from current handler"""
        try:
            data = request.get_json()
            handler_name = data.get('handler_name')
        
            logger.debug(f"✅ API call: POST /api/sign_out - handler={handler_name}")
        
            if not handler_name:
                return jsonify({'success': False, 'error': 'Handler name is required'}), 400
        
            # Get the actual handler
            handler = app.config['HANDLER']
            actual_handler = handler.handler if hasattr(handler, 'handler') else handler
        
            # Verify it's the right handler
            if not hasattr(actual_handler, 'DB_NAME') or actual_handler.DB_NAME != handler_name:
                return jsonify({'success': False, 'error': 'Handler mismatch'}), 400
        
            # Clear credentials
            if hasattr(actual_handler, 'clear_credentials'):
                actual_handler.clear_credentials()
                logger.debug(f"API: Cleared credentials for {handler_name}")
            
                return jsonify({
                    'success': True,
                    'message': f'Signed out from {handler_name} successfully'
                })
        
            return jsonify({
                'success': False,
                'error': 'Handler does not support sign out'
            }), 400
    
        except Exception as e:
            logger.error(f"❌ API call failed: /api/sign_out - {e}")
            return jsonify({'success': False, 'error': str(e)}), 500
        
    @app.route('/api/check_credentials', methods=['GET'])
    def api_check_credentials():
        handler = app.config['HANDLER']
        logger.debug(f"Checking credentials for handler: {app.config['CURRENT_HANDLER_NAME']}")
        
        try:
            # Get the actual handler (unwrap if needed)
            actual_handler = handler.handler if hasattr(handler, 'handler') else handler
            
            # ✅ FIX: Check if handler actually NEEDS credentials (has credential management capability)
            handler_supports_credentials = False
            needs = False
            
            if hasattr(actual_handler, 'get_credential_status'):
                status = actual_handler.get_credential_status()
                logger.debug(f"Handler credential status: {status}")
                
                # ✅ KEY FIX: A handler "supports credentials" if it can ever need them
                # Check if this handler type has credential storage methods
                handler_supports_credentials = (
                    hasattr(actual_handler, 'validate_and_store_credentials') and
                    hasattr(actual_handler, 'clear_credentials') and
                    hasattr(actual_handler, '_load_credentials')  # This is the telltale sign
                )
                
                needs = bool(status.get('needs_credentials', False))
            else:
                # Handler doesn't have credential management at all
                logger.debug("Handler does not have get_credential_status method")
                
            logger.debug(f"Final needs_credentials: {needs}, supports: {handler_supports_credentials}")

            return jsonify({
                'success': True,
                'needs_credentials': needs,
                'handler_supports_credentials': handler_supports_credentials,  # ✅ Based on actual capability
                'handler': app.config['CURRENT_HANDLER_NAME']
            })
        except Exception as e:
            logger.error(f"Credential check failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return jsonify({
                'success': False, 
                'error': str(e),
                'needs_credentials': False,
                'handler_supports_credentials': False
            }), 500
        
    @app.route('/api/handler_credentials/<handler_name>', methods=['POST'])
    def api_handler_credentials(handler_name):
        """JSON API: Validate and store credentials for a handler"""
        try:
            data = request.get_json()
            username = data.get('username', '')
            password = data.get('password', '')
            
            logger.debug(f"✅ API call: POST /api/handler_credentials/{handler_name}")
            logger.debug(f"   Username: {username}")
            logger.debug(f"   Password: {'<set>' if password else '<empty>'}")
            
            # Get the current handler
            handler = app.config['HANDLER']
            
            # Get the actual handler (unwrap if needed)
            actual_handler = handler.handler if hasattr(handler, 'handler') else handler
            
            # Verify it's the correct handler
            if not hasattr(actual_handler, 'DB_NAME') or actual_handler.DB_NAME != handler_name:
                return jsonify({
                    'success': False,
                    'message': f'Handler mismatch. Expected {handler_name}, got {actual_handler.DB_NAME if hasattr(actual_handler, "DB_NAME") else "unknown"}'
                }), 400
            
            # Validate credentials
            if not hasattr(actual_handler, 'validate_and_store_credentials'):
                return jsonify({
                    'success': False,
                    'message': f'{handler_name} does not support credential storage'
                }), 400
            
            result = actual_handler.validate_and_store_credentials(username, password)
            
            logger.debug(f"   Validation result: {result}")
            
            return jsonify(result)
            
        except Exception as e:
            logger.error(f"❌ API call failed: /api/handler_credentials/{handler_name} - {e}")
            import traceback
            logger.error(traceback.format_exc())
            return jsonify({
                'success': False,
                'message': str(e)
            }), 500
        
    @app.route('/api/collection/<db_name>/<collection_name>/document', methods=['POST'])
    def api_add_document(db_name, collection_name):
        """JSON API: Add document to collection (NoSQL only)"""
        try:
            logger.debug(f"✅ API call: POST /api/collection/{db_name}/{collection_name}/document")
        
            # Ensure we're in NoSQL mode
            if app.config['DB_TYPE'] != 'nosql':
                return jsonify({
                    'success': False,
                    'error': 'This endpoint is for NoSQL collections only'
                }), 400
        
            app.config['HANDLER'].switch_db(db_name)
        
            data = request.get_json()
            document = data.get('document', {})
        
            if not document:
                return jsonify({
                    'success': False,
                    'error': 'Document data is required'
                }), 400
            
            # Log what we received from frontend
            logger.debug(f"Received document data: {document}")
            for key, value in document.items():
                logger.debug(f"  {key}: {value} (type: {type(value).__name__})")
        
            try:
                doc_id = app.config['HANDLER'].insert(collection_name, document)
                logger.debug(f"API: Inserted document with ID {doc_id} into {collection_name}")
            
                return jsonify({
                    'success': True,
                    'message': 'Document added successfully',
                    'doc_id': doc_id
                })
        
            except Exception as e:
                logger.error(f"Insert document error: {str(e)}")
                return jsonify({
                    'success': False,
                    'error': f'Failed to add document: {str(e)}'
                }), 500
    
        except Exception as e:
            logger.error(f"❌ API call failed: /api/collection/{db_name}/{collection_name}/document - {e}")
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/collection/<db_name>/<collection_name>/document/<doc_id>', methods=['PUT'])
    def api_update_document(db_name, collection_name, doc_id):
        """JSON API: Update document in collection (NoSQL only)"""
        try:
            logger.debug(f"✅ API call: PUT /api/collection/{db_name}/{collection_name}/document/{doc_id}")
        
            # Ensure we're in NoSQL mode
            if app.config['DB_TYPE'] != 'nosql':
                return jsonify({
                    'success': False,
                    'error': 'This endpoint is for NoSQL collections only'
                }), 400
        
            app.config['HANDLER'].switch_db(db_name)
        
            data = request.get_json()
            document = data.get('document', {})
        
            if not document:
                return jsonify({
                    'success': False,
                    'error': 'Document data is required'
                }), 400
        
            try:
                # Convert doc_id to correct type
                if app.config['CURRENT_HANDLER_NAME'] == 'TinyDB':
                    doc_id = int(doc_id)  
            
                app.config['HANDLER'].update(collection_name, doc_id, document)
                logger.debug(f"API: Updated document {doc_id} in {collection_name}")
            
                return jsonify({
                    'success': True,
                    'message': 'Document updated successfully'
                })
        
            except Exception as e:
                logger.error(f"Update document error: {str(e)}")
                return jsonify({
                    'success': False,
                    'error': f'Failed to update document: {str(e)}'
                }), 500
    
        except Exception as e:
            logger.error(f"❌ API call failed: /api/collection/{db_name}/{collection_name}/document/{doc_id} - {e}")
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/collection/<db_name>/<collection_name>/document/<doc_id>/delete', methods=['POST'])
    def api_delete_document(db_name, collection_name, doc_id):
        """JSON API: Delete document from collection (NoSQL only)"""
        try:
            logger.debug(f"✅ API call: POST /api/collection/{db_name}/{collection_name}/document/{doc_id}/delete")
        
            # Ensure we're in NoSQL mode
            if app.config['DB_TYPE'] != 'nosql':
                return jsonify({
                    'success': False,
                    'error': 'This endpoint is for NoSQL collections only'
                }), 400
        
            app.config['HANDLER'].switch_db(db_name)
        
            try:
                # Convert doc_id to correct type
                if app.config['CURRENT_HANDLER_NAME'] == 'TinyDB':
                    doc_id = int(doc_id)  # TinyDB uses integer doc_id
            
                app.config['HANDLER'].delete(collection_name, doc_id)
                logger.debug(f"API: Deleted document {doc_id} from {collection_name}")
            
                return jsonify({
                    'success': True,
                    'message': 'Document deleted successfully'
                })
        
            except Exception as e:
                logger.error(f"Delete document error: {str(e)}")
                return jsonify({
                    'success': False,
                    'error': f'Failed to delete document: {str(e)}'
                }), 500
    
        except Exception as e:
            logger.error(f"❌ API call failed: /api/collection/{db_name}/{collection_name}/document/{doc_id}/delete - {e}")
            return jsonify({'success': False, 'error': str(e)}), 500
        
    @app.route('/api/collection/<db_name>/<collection_name>/chart_data', methods=['GET'])
    def api_collection_chart_data(db_name, collection_name):
        """JSON API: Get chart data for collection (NoSQL only)"""
        try:
            logger.debug(f"✅ API call: GET /api/collection/{db_name}/{collection_name}/chart_data")
        
            # Ensure we're in NoSQL mode
            if app.config['DB_TYPE'] != 'nosql':
                return jsonify({
                    'success': False,
                    'error': 'This endpoint is for NoSQL collections only'
                }), 400
        
            app.config['HANDLER'].switch_db(db_name)
        
            # Fetch ALL documents (no pagination for charts)
            all_data = app.config['HANDLER'].read(collection_name)
        
            # Get the primary key name from handler
            primary_key = app.config['HANDLER'].get_primary_key_name()
        
            # Get all unique keys (excluding primary key, we'll add it separately)
            try:
                all_keys = app.config['HANDLER'].get_all_keys(collection_name)
                # Add primary key at the beginning if not already there
                if primary_key not in all_keys:
                    all_keys.insert(0, primary_key)
            except Exception as e:
                all_keys = [primary_key]
                logger.error(f"Keys fetch error: {e}")
        
            # ✅ FIX: Clean up data - use only ONE ID field
            cleaned_data = []
            for doc in all_data:
                clean_doc = {}
            
                # Add primary key first
                if primary_key in doc:
                    clean_doc[primary_key] = doc[primary_key]
            
                # Add other fields (skip alternate ID fields)
                for key, value in doc.items():
                    if key != primary_key and key not in ['_id', 'doc_id']:
                        clean_doc[key] = value
                    elif key == primary_key:
                        continue  # Already added
            
                cleaned_data.append(clean_doc)
        
            return jsonify({
                'success': True,
                'data': cleaned_data,
                'keys': all_keys,
                'total': len(cleaned_data)
            })
        
        except Exception as e:
            logger.error(f"Chart data fetch error: {str(e)}")
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500
        
    @app.route('/api/autocomplete/history', methods=['POST'])
    def api_autocomplete_history():
        """
        JSON API: Get autocomplete suggestions from query history with word prediction.
        Now supports matching individual commands within multi-line queries!
        """
        try:
            data = request.get_json()
            partial_query = data.get('query', '').strip()
            handler_name = app.config['CURRENT_HANDLER_NAME']
            limit = data.get('limit', 5)
            
            if not partial_query or len(partial_query) < 2:
                return jsonify({
                    'success': True,
                    'suggestions': [],
                    'next_words': []
                })
            
            # Get suggestions from history (now returns dict with suggestions and next_words)
            result = query_history_manager.get_realtime_suggestions(
                handler_name, 
                partial_query, 
                limit
            )
            
            suggestions = result.get('suggestions', [])
            next_words = result.get('next_words', [])
            
            # Convert suggestions from objects to strings (frontend expects strings)
            # But keep the most relevant info - prioritize individual commands
            suggestion_strings = []
            seen = set()
            
            for s in suggestions:
                if isinstance(s, dict):
                    query_text = s.get('query', '')
                    suggestion_type = s.get('type', 'unknown')
                    
                    # Avoid duplicates
                    if query_text and query_text not in seen:
                        suggestion_strings.append(query_text)
                        seen.add(query_text)
                else:
                    # Fallback for legacy format
                    if s and s not in seen:
                        suggestion_strings.append(s)
                        seen.add(s)
            
            logger.debug(f"Autocomplete: Found {len(suggestion_strings)} suggestions, {len(next_words)} next words for '{partial_query[:50]}'")
            
            return jsonify({
                'success': True,
                'suggestions': suggestion_strings,
                'next_words': next_words
            })
            
        except Exception as e:
            logger.error(f"Autocomplete history error: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return jsonify({
                'success': False,
                'suggestions': [],
                'next_words': []
            })


    # Optional: Add a new endpoint to get command statistics
    @app.route('/api/query-stats/<handler_name>', methods=['GET'])
    def get_query_stats(handler_name):
        """Get statistics about query/command usage for a specific handler"""
        try:
            stats = query_history_manager.get_command_statistics(handler_name)
            
            return jsonify({
                'success': True,
                'handler': handler_name,
                'stats': stats
            })
            
        except Exception as e:
            logger.error(f"Query stats error: {e}")
            return jsonify({
                'success': False,
                'error': str(e)
            })
        
    @app.route('/api/databases/search', methods=['GET'])
    def api_search_databases():
        """JSON API: Search all databases (server-side)"""
        try:
            search_term = request.args.get('q', '').strip().lower()
            page = request.args.get('page', 1, type=int)
            per_page = request.args.get('per_page', 10, type=int)
        
            all_dbs = app.config['HANDLER'].list_dbs()
        
            if search_term:
                filtered = [db for db in all_dbs if search_term in db.lower()]
            else:
                filtered = all_dbs
        
            total = len(filtered)
            total_pages = (total + per_page - 1) // per_page
        
            # Paginate results
            start = (page - 1) * per_page
            end = start + per_page
            paginated = filtered[start:end]
        
            return jsonify({
                'success': True,
                'databases': paginated,
                'total': total,
                'page': page,
                'per_page': per_page,
                'total_pages': total_pages
            })
        except Exception as e:
            logger.error(f"Search databases error: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/db/<db_name>/tables/search', methods=['GET'])
    def api_search_tables(db_name):
        """JSON API: Search all tables/collections (server-side)"""
        try:
            search_term = request.args.get('q', '').strip().lower()
            page = request.args.get('page', 1, type=int)
            per_page = request.args.get('per_page', 10, type=int)
        
            app.config['HANDLER'].switch_db(db_name)
            all_tables = app.config['HANDLER'].list_tables()
        
            if app.config['DB_TYPE'] == 'sql':
                if search_term:
                    filtered = [t for t in all_tables if search_term in t.lower()]
                else:
                    filtered = all_tables
            
                total = len(filtered)
                total_pages = (total + per_page - 1) // per_page
            
                start = (page - 1) * per_page
                end = start + per_page
                paginated = filtered[start:end]
            
                return jsonify({
                    'success': True,
                    'tables': paginated,
                    'total': total,
                    'page': page,
                    'per_page': per_page,
                    'total_pages': total_pages,
                    'db_type': 'sql'
                })
            else:
                # NoSQL - get collection stats
                collection_stats = []
                for coll in all_tables:
                    try:
                        count = app.config['HANDLER'].count_documents(coll)
                        collection_stats.append({'name': coll, 'count': count})
                    except Exception as e:
                        logger.error(f"Error counting {coll}: {e}")
                        collection_stats.append({'name': coll, 'count': 0})
            
                if search_term:
                    filtered = [c for c in collection_stats if search_term in c['name'].lower()]
                else:
                    filtered = collection_stats
            
                total = len(filtered)
                total_pages = (total + per_page - 1) // per_page
            
                start = (page - 1) * per_page
                end = start + per_page
                paginated = filtered[start:end]
            
                return jsonify({
                    'success': True,
                    'collections': paginated,
                    'total': total,
                    'page': page,
                    'per_page': per_page,
                    'total_pages': total_pages,
                    'db_type': 'nosql'
                })
    
        except Exception as e:
            logger.error(f"Search tables error: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/table/<db_name>/<table_name>/search', methods=['GET'])
    def api_search_table_rows(db_name, table_name):
        """JSON API: Search all rows in a table (server-side with pagination)"""
        try:
            search_term = request.args.get('q', '').strip().lower()
            search_fields_param = request.args.get('fields', '')
            page = request.args.get('page', 1, type=int)
            per_page = request.args.get('per_page', 20, type=int)
        
            app.config['HANDLER'].switch_db(db_name)
        
            # Get ALL rows (this is unavoidable for searching)
            all_rows = app.config['HANDLER'].read(table_name)
        
            if not search_term:
                # No search - just paginate
                total = len(all_rows)
                total_pages = (total + per_page - 1) // per_page
                start = (page - 1) * per_page
                end = start + per_page
                paginated = all_rows[start:end]
            
                return jsonify({
                    'success': True,
                    'rows': paginated,
                    'total': total,
                    'page': page,
                    'per_page': per_page,
                    'total_pages': total_pages
                })
        
            # Parse selected fields
            selected_fields = set()
            if search_fields_param:
                selected_fields = set(search_fields_param.split(','))
        
            # Filter rows
            filtered_rows = []
            for row in all_rows:
                if not selected_fields:
                    if any(search_term in str(val).lower() for val in row.values()):
                        filtered_rows.append(row)
                else:
                    if any(search_term in str(row.get(field, '')).lower() for field in selected_fields):
                        filtered_rows.append(row)
        
            # Paginate filtered results
            total = len(filtered_rows)
            total_pages = (total + per_page - 1) // per_page
            start = (page - 1) * per_page
            end = start + per_page
            paginated = filtered_rows[start:end]
        
            return jsonify({
                'success': True,
                'rows': paginated,
                'total': total,
                'page': page,
                'per_page': per_page,
                'total_pages': total_pages
            })
    
        except Exception as e:
            logger.error(f"Search table rows error: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/collection/<db_name>/<collection_name>/search', methods=['GET'])
    def api_search_collection_docs(db_name, collection_name):
        """JSON API: Search all documents (server-side with pagination)"""
        try:
            search_term = request.args.get('q', '').strip().lower()
            search_fields_param = request.args.get('fields', '')
            page = request.args.get('page', 1, type=int)
            per_page = request.args.get('per_page', 20, type=int)
        
            app.config['HANDLER'].switch_db(db_name)
        
            # Get ALL documents
            all_docs = app.config['HANDLER'].read(collection_name)
        
            if not search_term:
                # No search - just paginate
                total = len(all_docs)
                total_pages = (total + per_page - 1) // per_page
                start = (page - 1) * per_page
                end = start + per_page
                paginated = all_docs[start:end]
                cleaned = format_nosql_result(paginated, app.config['HANDLER'])
            
                return jsonify({
                    'success': True,
                    'documents': cleaned,
                    'total': total,
                    'page': page,
                    'per_page': per_page,
                    'total_pages': total_pages
                })
        
            # Parse selected fields
            selected_fields = set()
            if search_fields_param:
                selected_fields = set(search_fields_param.split(','))
        
            # Filter documents
            filtered_docs = []
            for doc in all_docs:
                if not selected_fields:
                    if any(search_term in str(val).lower() for val in doc.values()):
                        filtered_docs.append(doc)
                else:
                    if any(search_term in str(doc.get(field, '')).lower() for field in selected_fields):
                        filtered_docs.append(doc)
        
            # Paginate filtered results
            total = len(filtered_docs)
            total_pages = (total + per_page - 1) // per_page
            start = (page - 1) * per_page
            end = start + per_page
            paginated = filtered_docs[start:end]
            cleaned = format_nosql_result(paginated, app.config['HANDLER'])
        
            return jsonify({
                'success': True,
                'documents': cleaned,
                'total': total,
                'page': page,
                'per_page': per_page,
                'total_pages': total_pages
            })
    
        except Exception as e:
            logger.error(f"Search collection docs error: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500
        
    @app.route('/api/query/history/session', methods=['GET', 'POST', 'DELETE'])
    def api_session_query_history():
        """Manage session-based query history - ONLY shows queries from current session"""
        try:
            # Generate session ID from request header
            session_id = request.headers.get('X-Session-ID', 'default')
        
            if request.method == 'GET':
                # Get context and handler
                context = request.args.get('context', 'global')
                handler_name = app.config['CURRENT_HANDLER_NAME']
            
                logger.debug(f"📜 GET session history - Session: {session_id}, Handler: {handler_name}")
            
                # ✅ CRITICAL: Get ONLY session queries for THIS specific handler
                queries = query_history_manager.get_session_queries(session_id, handler_name)
            
                # Filter out USE queries if not in global context
                if context != 'global':
                    queries = [q for q in queries if not is_use_query(q)]
            
                logger.debug(f"📜 Returning {len(queries)} session queries for {handler_name}")
            
                return jsonify({
                    'success': True,
                    'queries': queries,
                    'handler': handler_name,
                    'context': context,
                    'session_id': session_id
                })
        
            elif request.method == 'POST':
                # Add query to session history
                data = request.get_json()
                query = data.get('query', '').strip()
            
                if not query:
                    return jsonify({'success': False, 'error': 'Query is required'}), 400
            
                # ✅ CRITICAL: Use CURRENT handler name, not generic db_type
                handler_name = app.config['CURRENT_HANDLER_NAME']
            
                logger.debug(f"➕ Adding query to session history - Handler: {handler_name}, Session: {session_id}")
                logger.debug(f"   Query: {query[:100]}...")
            
                # Add to both permanent and session history
                query_history_manager.add_query(query, handler_name, session_id)
            
                logger.debug(f"✅ Query added successfully")
            
                return jsonify({
                    'success': True,
                    'message': 'Query added to history',
                    'handler': handler_name
                })
        
            elif request.method == 'DELETE':
                # Clear session history
                query_history_manager.clear_session(session_id)
            
                return jsonify({
                    'success': True,
                    'message': 'Session history cleared'
                })
    
        except Exception as e:
            logger.error(f"❌ Session query history error: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/query/history/permanent', methods=['GET'])
    def api_permanent_query_history():
        """Get permanent query history for specific handler (deduplicated)"""
        try:
            handler_name = app.config['CURRENT_HANDLER_NAME']
            limit = request.args.get('limit', 100, type=int)
        
            logger.debug(f"📚 GET permanent history - Handler: {handler_name}")
        
            queries = query_history_manager.get_permanent_queries(handler_name, limit)
        
            return jsonify({
                'success': True,
                'queries': queries,
                'handler': handler_name,
                'total': len(queries)
            })
    
        except Exception as e:
            logger.error(f"❌ Permanent query history error: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/query/history/search', methods=['GET'])
    def api_search_query_history():
        """Search through permanent query history for specific handler"""
        try:
            handler_name = app.config['CURRENT_HANDLER_NAME']
            search_term = request.args.get('q', '').lower().strip()
            limit = request.args.get('limit', 50, type=int)
        
            if not search_term:
                return jsonify({
                    'success': True,
                    'queries': [],
                    'message': 'No search term provided'
                })
        
            logger.debug(f"🔍 Search history - Handler: {handler_name}, Term: '{search_term}'")
        
            matching_queries = query_history_manager.search_queries(
                handler_name, search_term, limit
            )
        
            logger.debug(f"🔍 Found {len(matching_queries)} matching queries")
        
            return jsonify({
                'success': True,
                'queries': matching_queries,
                'handler': handler_name,
                'search_term': search_term
            })
    
        except Exception as e:
            logger.error(f"❌ Query history search error: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/query/history/handlers', methods=['GET'])
    def api_query_history_handlers():
        """Get list of all handlers with query history"""
        try:
            handlers = query_history_manager.get_all_handlers()
        
            return jsonify({
                'success': True,
                'handlers': handlers
            })
    
        except Exception as e:
            logger.error(f"❌ Get handlers error: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500
        
    @app.route('/api/db/<db_name>/connection_info', methods=['GET'])
    def api_get_connection_info(db_name):
        """JSON API: Get connection info for database"""
        try:
            logger.debug(f"✅ API call: GET /api/db/{db_name}/connection_info")
            
            app.config['HANDLER'].switch_db(db_name)
            handler = app.config['HANDLER']
            
            # Get connection info from handler
            conn_info = handler.get_connection_info(db_name)
            
            return jsonify({
                'success': True,
                'connection_string': conn_info['connection_string'],
                'test_code': conn_info['test_code'],
                'notes': conn_info.get('notes', [])
            })
            
        except Exception as e:
            logger.error(f"❌ API call failed: /api/db/{db_name}/connection_info - {e}")
            return jsonify({'success': False, 'error': str(e)}), 500
        
    def _parse_check_to_validation(check_expr, column_name):
        """
        Convert SQL CHECK constraint to NoSQL validation rules format.
        ENHANCED: Handles all common SQL constraint patterns
        
        Supported patterns:
            - Numeric: age > 18, price >= 100, quantity <= 1000
            - String length: CHAR_LENGTH(name) > 3, LENGTH(title) <= 50
            - Enum: status IN ('active', 'pending', 'closed')
            - Pattern: email LIKE '%@%.%'
            - NOT NULL: column IS NOT NULL
        """
        rules = {}
        
        # Store original expression for final fallback type detection
        original_expr = check_expr
        
        # Handle both quoted and unquoted column names
        check_expr = re.sub(rf'[`"\']?{re.escape(column_name)}[`"\']?\s*', '', check_expr, count=1)
        check_expr = check_expr.strip()
        
        logger.debug(f"[CHECK Parser] Parsing: '{check_expr}' for column '{column_name}'")
        
        # 1. NOT NULL constraint
        if 'IS NOT NULL' in check_expr.upper():
            rules['required'] = True
            logger.debug(f"[CHECK Parser] Found: required=True")
            # Don't set type yet - let other patterns determine it
        
        # 2. IN clause (enum values) - CHECK THIS FIRST before numeric comparisons
        in_match = re.search(r'IN\s*\(\s*([^)]+)\s*\)', check_expr, re.IGNORECASE)
        if in_match:
            values_str = in_match.group(1)
            # Handle both quoted and unquoted values
            enum_values = [v.strip().strip('\'"') for v in values_str.split(',') if v.strip()]
            rules['enum'] = enum_values
            # Infer type from first value
            if enum_values:
                first_val = enum_values[0]
                try:
                    int(first_val)
                    rules['bsonType'] = ['int', 'long']
                except:
                    rules['bsonType'] = 'string'
            logger.debug(f"[CHECK Parser] Found: enum={enum_values}, type={rules.get('bsonType')}")
        
        # 3. Numeric comparisons (>, >=, <, <=)
        # Must handle >= before > to avoid false matches
        has_numeric_constraint = False
        if '>=' in check_expr:
            match = re.search(r'>=\s*([0-9.]+)', check_expr)
            if match:
                val = float(match.group(1)) if '.' in match.group(1) else int(match.group(1))
                rules['minimum'] = val
                rules['bsonType'] = ['int', 'long', 'double', 'decimal']
                has_numeric_constraint = True
                logger.debug(f"[CHECK Parser] Found: minimum={val}")
        elif '>' in check_expr:
            match = re.search(r'>\s*([0-9.]+)', check_expr)
            if match:
                val = float(match.group(1)) if '.' in match.group(1) else int(match.group(1))
                # Strict inequality: > 18 means >= 19 for integers
                rules['minimum'] = val + (0.01 if isinstance(val, float) else 1)
                rules['bsonType'] = ['int', 'long', 'double', 'decimal']
                has_numeric_constraint = True
                logger.debug(f"[CHECK Parser] Found: minimum={rules['minimum']} (strict >)")
        
        if '<=' in check_expr:
            match = re.search(r'<=\s*([0-9.]+)', check_expr)
            if match:
                val = float(match.group(1)) if '.' in match.group(1) else int(match.group(1))
                rules['maximum'] = val
                if 'bsonType' not in rules:
                    rules['bsonType'] = ['int', 'long', 'double', 'decimal']
                has_numeric_constraint = True
                logger.debug(f"[CHECK Parser] Found: maximum={val}")
        elif '<' in check_expr:
            match = re.search(r'<\s*([0-9.]+)', check_expr)
            if match:
                val = float(match.group(1)) if '.' in match.group(1) else int(match.group(1))
                rules['maximum'] = val - (0.01 if isinstance(val, float) else 1)
                if 'bsonType' not in rules:
                    rules['bsonType'] = ['int', 'long', 'double', 'decimal']
                has_numeric_constraint = True
                logger.debug(f"[CHECK Parser] Found: maximum={rules['maximum']} (strict <)")
        
        # 4. String length constraints via LENGTH() or CHAR_LENGTH()
        # Pattern: CHAR_LENGTH(name) > 3
        length_match = re.search(
            r'(?:LENGTH|CHAR_LENGTH)\s*\([^)]+\)\s*([><=]+)\s*(\d+)',
            check_expr,
            re.IGNORECASE
        )
        if length_match:
            operator = length_match.group(1)
            length_val = int(length_match.group(2))
            
            if '>=' in operator:
                rules['minLength'] = length_val
            elif '>' in operator:
                rules['minLength'] = length_val + 1  # Strict inequality
            elif '<=' in operator:
                rules['maxLength'] = length_val
            elif '<' in operator:
                rules['maxLength'] = length_val - 1  # Strict inequality
            
            if 'bsonType' not in rules:
                rules['bsonType'] = 'string'
            logger.debug(f"[CHECK Parser] Found: length constraint minLength={rules.get('minLength')} maxLength={rules.get('maxLength')}")
        
        # 5. Pattern matching (LIKE operator) - convert to regex
        like_match = re.search(r"LIKE\s+'([^']+)'", check_expr, re.IGNORECASE)
        if like_match:
            like_pattern = like_match.group(1)
            # Convert SQL LIKE to regex pattern
            # % → .* (any characters)
            # _ → . (single character)
            regex_pattern = like_pattern.replace('%', '.*').replace('_', '.')
            regex_pattern = f"^{regex_pattern}$"  # Anchor to match entire string
            rules['pattern'] = regex_pattern
            if 'bsonType' not in rules:
                rules['bsonType'] = 'string'
            logger.debug(f"[CHECK Parser] Found: pattern={regex_pattern}")
        
        # 6. BETWEEN operator
        between_match = re.search(r'BETWEEN\s+([0-9.]+)\s+AND\s+([0-9.]+)', check_expr, re.IGNORECASE)
        if between_match:
            min_val = float(between_match.group(1)) if '.' in between_match.group(1) else int(between_match.group(1))
            max_val = float(between_match.group(2)) if '.' in between_match.group(2) else int(between_match.group(2))
            rules['minimum'] = min_val
            rules['maximum'] = max_val
            rules['bsonType'] = ['int', 'long', 'double', 'decimal']
            has_numeric_constraint = True
            logger.debug(f"[CHECK Parser] Found: BETWEEN {min_val} AND {max_val}")
        
        # 7. FINAL FALLBACK: If we only have 'required' with no type, default to string
        # This ensures compatibility but shouldn't happen if constraints are well-formed
        if 'required' in rules and 'bsonType' not in rules:
            rules['bsonType'] = 'string'
            logger.debug(f"[CHECK Parser] Defaulted to string type for required-only constraint")
        
        logger.debug(f"[CHECK Parser] Final rules: {rules}")
        return rules if rules else None
        
    # ===== IMPORT/EXPORT API ROUTES =====

    @app.route('/api/db/<db_name>/export', methods=['POST'])
    def api_export_database(db_name):
        """JSON API: Export entire database"""
        try:
            data = request.get_json()
            format_type = data.get('format', 'json')  # 'json' or 'sql'
            
            logger.debug(f"✅ API call: POST /api/db/{db_name}/export - format={format_type}")
            
            app.config['HANDLER'].switch_db(db_name)
            handler = app.config['HANDLER']
            
            if format_type == 'sql':
                # SQL export - only for SQL databases
                if app.config['DB_TYPE'] != 'sql':
                    return jsonify({
                        'success': False,
                        'error': 'SQL export only available for SQL databases'
                    }), 400
                
                # Build SQL dump
                sql_content = []
                
                # Add database creation
                sql_content.append(f"-- Database Export: {db_name}")
                sql_content.append(f"-- Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}")
                sql_content.append(f"-- Handler: {app.config['CURRENT_HANDLER_NAME']}")
                sql_content.append("")
                sql_content.append(f"CREATE DATABASE IF NOT EXISTS {db_name};")
                sql_content.append(f"USE {db_name};")
                sql_content.append("")
                
                # Get all tables
                tables = handler.list_tables()
                
                for table in tables:
                    sql_content.append(f"-- Table: {table}")
                    
                    # Get table schema
                    schema = handler.get_table_schema(table)
                    
                    # âœ… CRITICAL: Get table data FIRST to detect which columns need SERIAL
                    rows = handler.read(table)
                    
                    # Build CREATE TABLE statement
                    actual_handler = handler.handler if hasattr(handler, 'handler') else handler
                    
                    # âœ… CRITICAL FIX: For PostgreSQL, we need to quote identifiers in CHECK constraints
                    db_handler_name = actual_handler.DB_NAME if hasattr(actual_handler, 'DB_NAME') else 'SQLite'
                    
                    if db_handler_name == 'PostgreSQL':
                        # Build column definitions with special handling for CHECK constraints
                        columns_def = []
                        
                        # âœ… CRITICAL: Detect which columns are actually inserted (have data)
                        has_data = len(rows) > 0
                        columns_with_data = set()
                        if has_data:
                            # Check which columns appear in the actual data
                            for row in rows:
                                columns_with_data.update(row.keys())
                        
                        for col in schema:
                            col_name = col['name']
                            col_type = col['type']
                            
                            # CRITICAL FIX: If this is a PRIMARY KEY column with NO data, use SERIAL
                            is_pk_without_data = col.get('pk') and (not has_data or col_name not in columns_with_data)

                            # DEBUG
                            logger.debug(f"Table {table}, Column {col_name}: is_pk={col.get('pk')}, has_data={has_data}, in_data={col_name in columns_with_data}, will_use_SERIAL={is_pk_without_data}")
                            
                            if is_pk_without_data:
                                # Convert to SERIAL for auto-generation
                                if 'BIGINT' in col_type.upper():
                                    col_def = f'"{col_name}" BIGSERIAL PRIMARY KEY'
                                elif 'SMALLINT' in col_type.upper():
                                    col_def = f'"{col_name}" SMALLSERIAL PRIMARY KEY'
                                else:
                                    col_def = f'"{col_name}" SERIAL PRIMARY KEY'
                            else:
                                # Build base column definition WITHOUT CHECK constraint
                                col_def = f'"{col_name}" {col_type}'
                                
                                if col.get('pk'):
                                    col_def += " PRIMARY KEY"
                                else:
                                    if col.get('notnull'):
                                        col_def += " NOT NULL"
                                    if col.get('unique'):
                                        col_def += " UNIQUE"
                            
                                # âœ… Add CHECK constraint with properly quoted column name
                                if col.get('check_constraint'):
                                    check_expr = col['check_constraint']
                                    
                                    # Ensure column name in CHECK is properly quoted
                                    import re
                                    quoted_check = re.sub(
                                        r'["\']?' + re.escape(col_name) + r'["\']?',
                                        f'"{col_name}"',
                                        check_expr
                                    )
                                    col_def += f' CHECK ({quoted_check})'
                            
                            columns_def.append(col_def)
                    else:
                        columns_def = actual_handler.build_column_definitions(schema, quote=False)
                    
                    sql_content.append(f"DROP TABLE IF EXISTS {table};")
                    sql_content.append(f"CREATE TABLE {table} (")
                    sql_content.append("  " + ",\n  ".join(columns_def))
                    sql_content.append(");")
                    sql_content.append("")
                    
                    # NOW insert the data (rows variable is already defined above)
                    if rows:
                        for row in rows:
                            # Build INSERT statement
                            columns = [col['name'] for col in schema if not col.get('autoincrement')]
                            values = []
                            
                            for col_name in columns:
                                val = row.get(col_name)
                                if val is None:
                                    values.append('NULL')
                                elif isinstance(val, str):
                                    # Escape single quotes
                                    escaped = val.replace("'", "''")
                                    values.append(f"'{escaped}'")
                                elif isinstance(val, bool):
                                    values.append('TRUE' if val else 'FALSE')
                                else:
                                    values.append(str(val))
                            
                            cols_str = ', '.join(columns)
                            vals_str = ', '.join(values)
                            sql_content.append(f"INSERT INTO {table} ({cols_str}) VALUES ({vals_str});")
                    
                    sql_content.append("")
                
                # Export triggers if supported
                if hasattr(handler, 'supports_triggers') and handler.supports_triggers():
                    triggers = handler.list_triggers()
                    if triggers:
                        sql_content.append("-- Triggers")
                        for trigger in triggers:
                            sql_content.append(f"-- Trigger: {trigger['name']}")
                            sql_content.append(trigger.get('sql', ''))
                            sql_content.append("")
                
                # Export procedures if supported
                if hasattr(handler, 'supports_procedures') and handler.supports_procedures():
                    procedures = handler.list_procedures()
                    if procedures:
                        sql_content.append("-- Procedures")
                        for proc in procedures:
                            if hasattr(handler, 'get_procedure_definition'):
                                proc_def = handler.get_procedure_definition(proc['name'])
                                if proc_def:
                                    sql_content.append(f"-- {proc['type']}: {proc['name']}")
                                    sql_content.append(proc_def)
                                    sql_content.append("")
                
                return jsonify({
                    'success': True,
                    'content': '\n'.join(sql_content),
                    'filename': f"{db_name}_export.sql",
                    'format': 'sql'
                })
            
            else:  # JSON format
                # Generic JSON export (works for both SQL and NoSQL)
                export_data = {
                    'metadata': {
                        'database_name': db_name,
                        'export_date': time.strftime('%Y-%m-%d %H:%M:%S'),
                        'db_type': app.config['DB_TYPE'],
                        'handler': app.config['CURRENT_HANDLER_NAME'],
                        'version': '1.0'
                    },
                    'tables': []
                }
                
                tables = handler.list_tables()
                
                for table in tables:
                    table_data = {
                        'name': table,
                        'schema': [],
                        'data': [],
                        'constraints': {},
                        'triggers': [],
                        'indexes': []
                    }
                    
                    # Get schema (SQL only)
                    if app.config['DB_TYPE'] == 'sql':
                        schema = handler.get_table_schema(table)
                        for col in schema:
                            col_export = {
                                'name': col['name'],
                                'type': col['type'],
                                'nullable': not col.get('notnull', False),
                                'primary_key': col.get('pk', False),
                                'autoincrement': col.get('autoincrement', False),
                                'unique': col.get('unique', False),
                                'check_constraint': None
                            }
                            
                            # ✅ Export CHECK constraint in normalized format
                            if col.get('check_constraint'):
                                check_expr = col['check_constraint']
                                # Store raw SQL expression for SQL imports
                                col_export['check_constraint'] = check_expr
                                
                                # ✅ Also add parsed rules for NoSQL compatibility
                                parsed_rules = _parse_check_to_validation(check_expr, col['name'])
                                if parsed_rules:
                                    col_export['validation_rules'] = parsed_rules
                            
                            table_data['schema'].append(col_export)
                    
                    # Get data
                    rows = handler.read(table)
                    table_data['data'] = rows
                    
                    # ✅ ENHANCED: Get validation rules/check constraints with normalization
                    if hasattr(handler, 'supports_check_constraints') and handler.supports_check_constraints():
                        if hasattr(handler, 'get_check_constraints'):
                            checks = handler.get_check_constraints(table)
                            if checks:
                                # ✅ Normalize validation rules for cross-DB compatibility
                                normalized_checks = []
                                for check in checks:
                                    normalized = {
                                        'column': check.get('column'),
                                        'expression': check.get('expression')
                                    }
                                    
                                    # ✅ Parse to structured rules for SQL import compatibility
                                    if check.get('expression'):
                                        parsed = _parse_validation_expression(check['expression'])
                                        if parsed:
                                            normalized['validation_rules'] = parsed
                                    
                                    normalized_checks.append(normalized)
                                
                                table_data['constraints']['check'] = normalized_checks
                    
                    # Get triggers for this table
                    if hasattr(handler, 'supports_triggers') and handler.supports_triggers():
                        triggers = handler.list_triggers(table)
                        for trigger in triggers:
                            table_data['triggers'].append({
                                'name': trigger['name'],
                                'timing': trigger.get('timing'),
                                'event': trigger.get('event'),
                                'body': trigger.get('sql')
                            })
                    
                    export_data['tables'].append(table_data)
                
                # Add procedures (database-level)
                if hasattr(handler, 'supports_procedures') and handler.supports_procedures():
                    procedures = handler.list_procedures()
                    export_data['procedures'] = []
                    for proc in procedures:
                        proc_data = {
                            'name': proc['name'],
                            'type': proc.get('type'),
                            'definition': None
                        }
                        if hasattr(handler, 'get_procedure_definition'):
                            proc_data['definition'] = handler.get_procedure_definition(proc['name'])
                        export_data['procedures'].append(proc_data)
                
                return jsonify({
                    'success': True,
                    'content': json.dumps(export_data, indent=2, default=str),
                    'filename': f"{db_name}_export.json",
                    'format': 'json'
                })
        
        except Exception as e:
            logger.error(f"❌ Export failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return jsonify({'success': False, 'error': str(e)}), 500


    @app.route('/api/db/<db_name>/table/<table_name>/export', methods=['POST'])
    def api_export_table(db_name, table_name):
        """JSON API: Export single table"""
        try:
            data = request.get_json()
            format_type = data.get('format', 'json')
            
            logger.debug(f"✅ API call: POST /api/db/{db_name}/table/{table_name}/export - format={format_type}")
            
            app.config['HANDLER'].switch_db(db_name)
            handler = app.config['HANDLER']
            
            if format_type == 'sql':
                if app.config['DB_TYPE'] != 'sql':
                    return jsonify({
                        'success': False,
                        'error': 'SQL export only available for SQL databases'
                    }), 400
                
                sql_content = []
                sql_content.append(f"-- Table Export: {table_name}")
                sql_content.append(f"-- Database: {db_name}")
                sql_content.append(f"-- Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}")
                sql_content.append("")
                
                # Get schema
                schema = handler.get_table_schema(table_name)

                # Get data
                rows = handler.read(table_name)

                # BUILD CREATE TABLE
                actual_handler = handler.handler if hasattr(handler, 'handler') else handler
                db_handler_name = actual_handler.DB_NAME if hasattr(actual_handler, 'DB_NAME') else 'SQLite'

                # âœ… CRITICAL FIX: For PostgreSQL, quote identifiers in CHECK constraints
                if db_handler_name == 'PostgreSQL':
                    columns_def = []
                    
                    # âœ… CRITICAL: Detect which columns are actually inserted (have data)
                    has_data = len(rows) > 0
                    columns_with_data = set()
                    if has_data:
                        for row in rows:
                            columns_with_data.update(row.keys())
                    
                    for col in schema:
                        col_name = col['name']
                        col_type = col['type']
                        
                        # âœ… CRITICAL FIX: If this is a PRIMARY KEY column with NO data, use SERIAL
                        is_pk_without_data = col.get('pk') and (not has_data or col_name not in columns_with_data)
                        
                        if is_pk_without_data:
                            # Convert to SERIAL for auto-generation
                            if 'BIGINT' in col_type.upper():
                                col_def = f'"{col_name}" BIGSERIAL PRIMARY KEY'
                            elif 'SMALLINT' in col_type.upper():
                                col_def = f'"{col_name}" SMALLSERIAL PRIMARY KEY'
                            else:
                                col_def = f'"{col_name}" SERIAL PRIMARY KEY'
                        else:
                            # Build base column definition WITHOUT CHECK constraint
                            col_def = f'"{col_name}" {col_type}'
                            
                            if col.get('pk'):
                                col_def += " PRIMARY KEY"
                            else:
                                if col.get('notnull'):
                                    col_def += " NOT NULL"
                                if col.get('unique'):
                                    col_def += " UNIQUE"
                        
                            # âœ… Add CHECK constraint with properly quoted column name
                            if col.get('check_constraint'):
                                check_expr = col['check_constraint']
                                
                                import re
                                quoted_check = re.sub(
                                    r'["\']?' + re.escape(col_name) + r'["\']?',
                                    f'"{col_name}"',
                                    check_expr
                                )
                                col_def += f' CHECK ({quoted_check})'
                        
                        columns_def.append(col_def)
                else:
                    columns_def = actual_handler.build_column_definitions(schema, quote=False)
                
                sql_content.append(f"DROP TABLE IF EXISTS {table_name};")
                sql_content.append(f"CREATE TABLE {table_name} (")
                sql_content.append("  " + ",\n  ".join(columns_def))
                sql_content.append(");")
                sql_content.append("")
                
                # Get data
                rows = handler.read(table_name)
                
                if rows:
                    for row in rows:
                        columns = [col['name'] for col in schema if not col.get('autoincrement')]
                        values = []
                        
                        for col_name in columns:
                            val = row.get(col_name)
                            if val is None:
                                values.append('NULL')
                            elif isinstance(val, str):
                                escaped = val.replace("'", "''")
                                values.append(f"'{escaped}'")
                            elif isinstance(val, bool):
                                values.append('TRUE' if val else 'FALSE')
                            else:
                                values.append(str(val))
                        
                        cols_str = ', '.join(columns)
                        vals_str = ', '.join(values)
                        sql_content.append(f"INSERT INTO {table_name} ({cols_str}) VALUES ({vals_str});")
                
                sql_content.append("")
                
                # Triggers
                if hasattr(handler, 'supports_triggers') and handler.supports_triggers():
                    triggers = handler.list_triggers(table_name)
                    if triggers:
                        sql_content.append("-- Triggers")
                        for trigger in triggers:
                            sql_content.append(trigger.get('sql', ''))
                            sql_content.append("")
                
                return jsonify({
                    'success': True,
                    'content': '\n'.join(sql_content),
                    'filename': f"{table_name}_export.sql",
                    'format': 'sql'
                })
            
            else:  # JSON
                export_data = {
                    'metadata': {
                        'table_name': table_name,
                        'database_name': db_name,
                        'export_date': time.strftime('%Y-%m-%d %H:%M:%S'),
                        'db_type': app.config['DB_TYPE'],
                        'version': '1.0'
                    },
                    'schema': [],
                    'data': [],
                    'constraints': {},
                    'triggers': []
                }
                
                # Schema
                if app.config['DB_TYPE'] == 'sql':
                    schema = handler.get_table_schema(table_name)
                    for col in schema:
                        export_data['schema'].append({
                            'name': col['name'],
                            'type': col['type'],
                            'nullable': not col.get('notnull', False),
                            'primary_key': col.get('pk', False),
                            'autoincrement': col.get('autoincrement', False),
                            'unique': col.get('unique', False),
                            'check_constraint': col.get('check_constraint')
                        })
                
                # Data
                rows = handler.read(table_name)
                export_data['data'] = rows
                
                # ✅ ENHANCED: Get validation rules/check constraints with normalization
                if hasattr(handler, 'supports_check_constraints') and handler.supports_check_constraints():
                    if hasattr(handler, 'get_check_constraints'):
                        checks = handler.get_check_constraints(table_name)
                        if checks:
                            # ✅ Normalize validation rules for cross-DB compatibility
                            normalized_checks = []
                            for check in checks:
                                normalized = {
                                    'column': check.get('column'),
                                    'expression': check.get('expression')
                                }
                                
                                # ✅ Parse to structured rules for SQL import compatibility
                                if check.get('expression'):
                                    parsed = _parse_validation_expression(check['expression'])
                                    if parsed:
                                        normalized['validation_rules'] = parsed
                                
                                normalized_checks.append(normalized)
                            
                            export_data['constraints']['check'] = normalized_checks
                
                # Triggers
                if hasattr(handler, 'supports_triggers') and handler.supports_triggers():
                    triggers = handler.list_triggers(table_name)
                    for trigger in triggers:
                        export_data['triggers'].append({
                            'name': trigger['name'],
                            'timing': trigger.get('timing'),
                            'event': trigger.get('event'),
                            'body': trigger.get('sql')
                        })
                
                return jsonify({
                    'success': True,
                    'content': json.dumps(export_data, indent=2, default=str),
                    'filename': f"{table_name}_export.json",
                    'format': 'json'
                })
        
        except Exception as e:
            logger.error(f"❌ Table export failed: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500
        
    def _clean_sql_for_import(sql_content, target_db_name):
        """
        Clean SQL content for import:
        - Remove CREATE DATABASE statements
        - Remove USE statements
        - Remove database name prefixes
        - Keep only table-level operations
        """
        import re
        
        lines = sql_content.split('\n')
        cleaned_lines = []
        
        for line in lines:
            line_upper = line.strip().upper()
            
            # Skip database-level commands
            if any(cmd in line_upper for cmd in [
                'CREATE DATABASE', 'DROP DATABASE', 'USE ', 'SHOW DATABASES'
            ]):
                logger.debug(f"Skipping line: {line[:80]}...")
                continue
            
            # Remove database name prefixes from table references
            # Pattern: database_name.table_name -> table_name
            line = re.sub(r'\b\w+\.(\w+)\b', r'\1', line)
            
            cleaned_lines.append(line)
        
        return '\n'.join(cleaned_lines)
    
    def _infer_schema_from_data(data_rows, table_name):
        """
        Infer table schema from data rows (for NoSQL imports that don't have schema)
        Returns a generic schema definition
        """
        if not data_rows or len(data_rows) == 0:
            return []
        
        # Get all unique keys from all rows
        all_keys = set()
        for row in data_rows:
            all_keys.update(row.keys())
        
        # Build schema by analyzing data types
        schema = []
        for key in sorted(all_keys):
            # Skip internal IDs from NoSQL
            if key in ['_id', 'doc_id']:
                continue
            
            # Sample values to determine type
            sample_values = []
            for row in data_rows[:10]:  # Sample first 10 rows
                if key in row and row[key] is not None:
                    sample_values.append(row[key])
            
            # Infer type from samples
            inferred_type = 'VARCHAR(255)'  # Default
            if sample_values:
                first_val = sample_values[0]
                if isinstance(first_val, bool):
                    inferred_type = 'BOOLEAN'
                elif isinstance(first_val, int):
                    # Check if values are large
                    if any(abs(v) > 2147483647 for v in sample_values if isinstance(v, int)):
                        inferred_type = 'BIGINT'
                    else:
                        inferred_type = 'INTEGER'
                elif isinstance(first_val, float):
                    inferred_type = 'DOUBLE'
                elif isinstance(first_val, str):
                    # Check max length
                    max_len = max(len(str(v)) for v in sample_values)
                    if max_len > 255:
                        inferred_type = 'TEXT'
                    else:
                        inferred_type = f'VARCHAR({max(255, max_len + 50)})'
            
            # Check if field is always present (NOT NULL)
            field_present_count = sum(1 for row in data_rows if key in row and row[key] is not None)
            is_not_null = field_present_count == len(data_rows)
            
            # Note: We'll normalize the type later in _create_table_from_schema
            # For now, use standard SQL types that are widely recognized
            schema.append({
                'name': key,
                'type': inferred_type,
                'primary_key': False,
                'nullable': not is_not_null,
                'unique': False,
                'autoincrement': False,
                'check_constraint': None
            })
        
        # ✅ Add auto-increment primary key if no ID field exists
        if not any(col['name'].lower() in ['id', '_id', 'doc_id'] for col in schema):
            schema.insert(0, {
                'name': 'id',
                'type': 'INTEGER',
                'primary_key': True,
                'nullable': False,
                'unique': True,
                'autoincrement': True,
                'check_constraint': None
            })
        
        logger.info(f"Inferred schema for {table_name}: {[col['name'] for col in schema]}")
        return schema
    
    def _normalize_datatype(col_type, handler):
        """
        Normalize column datatype to one supported by the target handler.
        If type is not recognized, default to TEXT/VARCHAR.
        Removes unsupported modifiers like TINYINT(1) -> TINYINT or INTEGER.
        """
        actual_handler = handler.handler if hasattr(handler, 'handler') else handler
        
        # Get supported types from handler
        supported_types = []
        if hasattr(handler, 'get_supported_types'):
            supported_types = [t.upper() for t in handler.get_supported_types()]
        
        # Extract base type and modifier from type string
        col_type_upper = col_type.upper().strip()
        base_type = col_type_upper.split('(')[0].strip()
        has_modifier = '(' in col_type_upper
        
        # Common type mappings with modifier handling
        type_mapping = {
            'INT': 'INTEGER',
            'INTEGER': 'INT',           # ← Crucial! PostgreSQL → MySQL
            'BIGINT': 'BIGINT',
            'BOOLEAN': 'TINYINT(1)',    
            'TIMESTAMPTZ': 'DATETIME',  # Common in PostgreSQL
            'UUID': 'VARCHAR(36)',
            'BOOL': 'BOOLEAN',
            'STRING': 'VARCHAR',
            'CHAR': 'VARCHAR',
            'NUMERIC': 'DECIMAL',
            'FLOAT': 'DOUBLE',
            'DATETIME': 'TIMESTAMP',
            'LONGTEXT': 'TEXT',
            'MEDIUMTEXT': 'TEXT',
            'TINYTEXT': 'TEXT',
            'TINYINT': 'SMALLINT',  # TINYINT(1) commonly used for booleans
            'BIGSERIAL': 'BIGINT',
            'SERIAL': 'INTEGER',
        }
        
        # Try exact match first (with modifier)
        if base_type in supported_types:
            # Base type is supported - check if modifier is valid
            if has_modifier:
                # Some types don't support modifiers (like TINYINT in DuckDB)
                # Try without modifier first
                if base_type in ['TINYINT', 'SMALLINT', 'BIGINT', 'INTEGER', 'BOOLEAN', 'TEXT', 'BLOB', 'TIMESTAMP', 'DATE', 'TIME']:
                    # These types typically don't take modifiers, return without it
                    return base_type
                else:
                    # Keep modifier for types that support it (VARCHAR, DECIMAL, etc.)
                    return col_type
            else:
                return col_type
        
        # Try to map the base type
        if base_type in type_mapping:
            mapped_type = type_mapping[base_type]
            if mapped_type in supported_types:
                # Check if we should preserve modifiers
                if has_modifier and mapped_type in ['VARCHAR', 'CHAR', 'DECIMAL', 'NUMERIC']:
                    # These types typically support modifiers
                    length_part = col_type[col_type.find('('):]
                    return f"{mapped_type}{length_part}"
                else:
                    return mapped_type
        
        # Special case: TINYINT(1) is often used for booleans
        if base_type == 'TINYINT' and has_modifier:
            if 'BOOLEAN' in supported_types:
                logger.info(f"Converting {col_type} to BOOLEAN")
                return 'BOOLEAN'
            elif 'SMALLINT' in supported_types:
                logger.info(f"Converting {col_type} to SMALLINT (modifier removed)")
                return 'SMALLINT'
            elif 'INTEGER' in supported_types:
                return 'INTEGER'
        
        # Default fallback to TEXT or VARCHAR
        logger.warning(f"Unknown datatype '{col_type}' - defaulting to TEXT/VARCHAR")
        if 'TEXT' in supported_types:
            return 'TEXT'
        elif 'VARCHAR' in supported_types:
            return 'VARCHAR(255)'
        else:
            # Last resort - strip modifier and hope for the best
            result_type = base_type
            
            # ✅ MySQL: Ensure VARCHAR has length
            actual_handler = handler.handler if hasattr(handler, 'handler') else handler
            if hasattr(actual_handler, 'DB_NAME') and actual_handler.DB_NAME == 'MySQL':
                if result_type.upper() == 'VARCHAR' or result_type.upper().startswith('VARCHAR'):
                    if '(' not in result_type:
                        result_type = 'VARCHAR(255)'
                        logger.info(f"MySQL: Added default length to VARCHAR -> {result_type}")
            
            return result_type

    def _create_table_from_schema(handler, table_name, schema, conn=None):
        """
        Create table from generic schema definition
        Handles conversion to handler-specific syntax
        """
        actual_handler = handler.handler if hasattr(handler, 'handler') else handler
        
        # ✅ CRITICAL: Check if handler has its own table creation method
        if hasattr(actual_handler, 'create_table_with_constraints'):
            logger.debug(f"Using handler-specific table creation for {table_name}")
            return actual_handler.create_table_with_constraints(table_name, schema, conn)
        
        # Get database type
        db_type_name = None
        if hasattr(actual_handler, 'DB_NAME'):
            db_type_name = actual_handler.DB_NAME
                
        # Quote table name properly
        if hasattr(actual_handler, '_quote_identifier'):
            quoted_table = actual_handler._quote_identifier(table_name)
        else:
            quoted_table = f"`{table_name}`"
        
        # # Check if table already exists
        # existing_tables = handler.list_tables()
        # if table_name in existing_tables:
        #     logger.debug(f"Table {table_name} already exists, skipping creation")
        #     return
        
        # Build column definitions
        columns_def = []
        
        # ✅ CRITICAL FIX: Detect COMPOSITE PRIMARY KEY vs mistaken FK marking
        pk_columns = [col for col in schema if col.get('primary_key') or col.get('pk')]
        has_composite_pk = len(pk_columns) > 1

        if has_composite_pk:
            logger.info(f"✅ Detected COMPOSITE PRIMARY KEY in {table_name}: {[c['name'] for c in pk_columns]}")
            # DO NOT modify the schema - keep all pk=True columns as they are
            # We'll add a composite PRIMARY KEY clause at the end instead
        
        # ✅ CRITICAL FIX: Count PRIMARY KEY columns FIRST to detect composite keys
        pk_columns = [col for col in schema if col.get('primary_key') or col.get('pk')]
        has_composite_pk = len(pk_columns) > 1
        
        if has_composite_pk:
            logger.info(f"✅ Detected COMPOSITE PRIMARY KEY in {table_name}: {[c['name'] for c in pk_columns]}")
        
        for col in schema:
            col_type_original = col['type']
            col_name_raw = col['name']
            
            # Normalize datatype to one supported by target handler
            col_type = _normalize_datatype(col_type_original, handler)
            if col_type != col_type_original:
                logger.info(f"Normalized type for {col_name_raw}: {col_type_original} -> {col_type}")
            
            # ✅ MySQL: Ensure VARCHAR has length
            if db_type_name == 'MySQL':
                col_type_upper = col_type.upper()
                if col_type_upper == 'VARCHAR' or (col_type_upper.startswith('VARCHAR') and '(' not in col_type):
                    col_type = 'VARCHAR(255)'
                    logger.info(f"MySQL: Added default length to VARCHAR for column {col_name_raw}")
            
            # ✅ MySQL: TEXT/BLOB cannot be AUTO_INCREMENT or PRIMARY KEY
            if db_type_name == 'MySQL' and col.get('autoincrement'):
                if col_type.upper() in ('TEXT', 'BLOB', 'MEDIUMTEXT', 'LONGTEXT', 'TINYTEXT'):
                    logger.warning(f"MySQL: Converting {col_type} to INT for AUTO_INCREMENT column {col_name_raw}")
                    col_type = 'INT'
            
            # Quote column name
            if hasattr(actual_handler, '_quote_identifier'):
                col_name = actual_handler._quote_identifier(col_name_raw)
            else:
                col_name = f'"{col_name_raw}"'
            
            col_def = f"{col_name} {col_type}"
            
            # ✅ FIXED: Check BOTH 'primary_key' and 'pk' fields
            is_primary = col.get('primary_key') or col.get('pk')
            
            # ✅ CRITICAL FIX: If composite PK, do NOT add PRIMARY KEY to individual columns
            if is_primary and not has_composite_pk:
                if col.get('autoincrement'):
                    # ✅ CRITICAL FIX: Handle autoincrement per database
                    if db_type_name == 'PostgreSQL':
                        col_def = f"{col_name} SERIAL PRIMARY KEY"
                    elif db_type_name == 'MySQL':
                        col_def = f"{col_name} {col_type} AUTO_INCREMENT PRIMARY KEY"
                    elif db_type_name == 'DuckDB':
                        # DuckDB autoincrement handling (your existing code)
                        seq_name = f"{table_name}_{col_name_raw}_seq"
                        
                        if conn:
                            quoted_seq = actual_handler._quote_identifier(seq_name)
                            try:
                                check_result = conn.execute(text(
                                    f"SELECT COUNT(*) FROM duckdb_sequences() WHERE sequence_name = '{seq_name}'"
                                ))
                                seq_exists = check_result.scalar() > 0
                                
                                if not seq_exists:
                                    conn.execute(text(f"CREATE SEQUENCE {quoted_seq} START 1"))
                                    logger.debug(f"Created sequence {seq_name}")
                                else:
                                    logger.debug(f"Sequence {seq_name} already exists, skipping creation")
                            except Exception as seq_err:
                                logger.error(f"Failed to handle sequence {seq_name}: {seq_err}")
                                try:
                                    conn.execute(text(f"CREATE SEQUENCE {quoted_seq} START 1"))
                                except:
                                    pass
                        
                        col_def = f"{col_name} {col_type} DEFAULT nextval('main.{seq_name}') PRIMARY KEY"
                    elif db_type_name == 'SQLite':
                        col_def = f"{col_name} {col_type} PRIMARY KEY AUTOINCREMENT"
                    else:
                        col_def = f"{col_name} {col_type} PRIMARY KEY"
                else:
                    col_def = f"{col_name} {col_type} PRIMARY KEY"
            else:
                # Non-primary key column
                if col.get('autoincrement'):
                    # (your existing autoincrement handling for non-PK columns)
                    if db_type_name == 'PostgreSQL':
                        col_def = f"{col_name} SERIAL UNIQUE NOT NULL"
                    elif db_type_name == 'MySQL':
                        col_def = f"{col_name} {col_type} AUTO_INCREMENT UNIQUE NOT NULL"
                    elif db_type_name == 'DuckDB':
                        # DuckDB sequence handling
                        seq_name = f"{table_name}_{col_name_raw}_seq"
                        
                        if conn:
                            quoted_seq = actual_handler._quote_identifier(seq_name)
                            try:
                                check_result = conn.execute(text(
                                    f"SELECT COUNT(*) FROM duckdb_sequences() WHERE sequence_name = '{seq_name}'"
                                ))
                                seq_exists = check_result.scalar() > 0
                                
                                if not seq_exists:
                                    conn.execute(text(f"CREATE SEQUENCE {quoted_seq} START 1"))
                                    logger.debug(f"Created sequence {seq_name}")
                            except Exception as seq_err:
                                logger.error(f"Failed to handle sequence {seq_name}: {seq_err}")
                                try:
                                    conn.execute(text(f"CREATE SEQUENCE {quoted_seq} START 1"))
                                except:
                                    pass
                        
                        col_def = f"{col_name} {col_type} DEFAULT nextval('main.{seq_name}') UNIQUE NOT NULL"
                    else:
                        col_def = f"{col_name} {col_type}"
                else:
                    if not col.get('nullable'):
                        col_def += " NOT NULL"
                    # ✅ CRITICAL FIX: Don't add UNIQUE to composite PK columns
                    if col.get('unique') and not is_primary:
                        col_def += " UNIQUE"
            
            # Add CHECK constraint if present
            # (your existing CHECK constraint code)
            if col.get('check_constraint'):
                check_expr = col['check_constraint']
                
                # ✅ CRITICAL: Convert CHAR_LENGTH to LENGTH for SQLite
                if db_type_name == 'SQLite':
                    check_expr = check_expr.replace('char_length(', 'length(')
                    check_expr = check_expr.replace('CHAR_LENGTH(', 'LENGTH(')
                
                # MySQL CHECK cleaning
                if db_type_name == 'MySQL':
                    mysql_check = re.sub(r'::\s*[a-zA-Z_][a-zA-Z0-9_]*(?:\s*\[\s*\])?', '', check_expr)
                    mysql_check = re.sub(r'::[^\s\),\]]+', '', mysql_check)
                    
                    if 'ARRAY[' in mysql_check or '= ANY' in mysql_check.upper():
                        array_match = re.search(r'ARRAY\s*\[\s*(.*?)\s*\]', mysql_check, re.DOTALL | re.IGNORECASE)
                        if array_match:
                            values = re.findall(r"'([^']*)'", array_match.group(1))
                            if values:
                                mysql_in = "IN (" + ", ".join([f"'{v}'" for v in values]) + ")"
                                mysql_check = re.sub(
                                    r'=\s*ANY\s*\(\s*\(?\s*ARRAY\s*\[.*?\]\s*\)?\s*\)',
                                    mysql_in,
                                    mysql_check,
                                    flags=re.DOTALL | re.IGNORECASE
                                )
                    
                    mysql_check = mysql_check.replace(f'"{col_name_raw}"', col_name_raw)
                    mysql_check = mysql_check.replace(f'`{col_name_raw}`', col_name_raw)
                    
                    col_def += f' CHECK ({mysql_check})'
                    logger.debug(f"✅ Added MySQL CHECK constraint to {col_name_raw}: {mysql_check}")
                else:
                    col_def += f" CHECK ({check_expr})"
                    logger.debug(f"✅ Added CHECK constraint to {col_name_raw}: {check_expr}")
            
            columns_def.append(col_def)
        
        # ✅ CRITICAL FIX: Add composite PRIMARY KEY clause if needed
        if has_composite_pk:
            pk_col_names = [col['name'] for col in pk_columns]
            if hasattr(actual_handler, '_quote_identifier'):
                quoted_pk_cols = ', '.join([actual_handler._quote_identifier(name) for name in pk_col_names])
            else:
                quoted_pk_cols = ', '.join([f'"{name}"' for name in pk_col_names])
            
            composite_pk_clause = f"PRIMARY KEY ({quoted_pk_cols})"
            columns_def.append(composite_pk_clause)
            logger.info(f"✅ Added composite PRIMARY KEY clause: {composite_pk_clause}")
        
        # Create table with proper syntax
        col_def_str = ', '.join(columns_def)
        create_sql = f"CREATE TABLE IF NOT EXISTS {quoted_table} ({col_def_str})"
        
        logger.info(f"Creating table with SQL: {create_sql}")
        
        try:
            if conn:
                conn.execute(text(create_sql))
            else:
                with handler._get_connection() as connection:
                    connection.execute(text(create_sql))
                    connection.commit()
            logger.info(f"✅ Successfully created table {table_name}")
        except Exception as e:
            logger.error(f"❌ Failed to create table {table_name}: {e}")
            raise
        
    def _convert_sql_for_handler(sql_content, handler):
        """
        Convert SQL syntax to match the target handler's requirements.
        Handles differences like AUTOINCREMENT vs sequences.
        """
        actual_handler = handler.handler if hasattr(handler, 'handler') else handler
        db_handler_name = actual_handler.DB_NAME if hasattr(actual_handler, 'DB_NAME') else 'SQLite'
        
        if db_handler_name == 'DuckDB':
            # DuckDB doesn't support AUTOINCREMENT keyword
            # Convert: "id" INTEGER PRIMARY KEY AUTOINCREMENT
            # To: "id" INTEGER PRIMARY KEY (sequence handled separately)
            import re
            
            # Remove AUTOINCREMENT from PRIMARY KEY columns
            sql_content = re.sub(
                r'PRIMARY KEY AUTOINCREMENT',
                'PRIMARY KEY',
                sql_content,
                flags=re.IGNORECASE
            )
            
            # Also handle standalone AUTOINCREMENT (non-PK columns)
            sql_content = re.sub(
                r'\s+AUTOINCREMENT(?=\s|,|\))',
                '',
                sql_content,
                flags=re.IGNORECASE
            )
        
        return sql_content
    
    def _parse_validation_expression(expression):
        """
        Parse validation expression string into structured validation rules
        Handles CHECK constraint expressions from exports
        
        Examples:
        - '"age" > 18' OR 'age > 18' -> {'minimum': 19, 'bsonType': ['int', 'long', 'double', 'decimal']}
        - '"name" IS NOT NULL' -> {'required': True}
        - 'status IN (\'active\', \'pending\')' -> {'enum': ['active', 'pending']}
        - 'LENGTH(name) > 3' -> {'minLength': 4, 'bsonType': 'string'}
        """
        rules = {}
        
        logger.debug(f"[Validation Parser] Parsing: '{expression}'")
        
        # Normalize expression - remove quotes around column names
        # Pattern: "colname" or 'colname' or `colname`
        normalized = re.sub(r'["`\'](\w+)["`\']', r'\1', expression)
        normalized = normalized.strip()
        
        logger.debug(f"[Validation Parser] Normalized: '{normalized}'")
        
        # 1. NOT NULL constraint
        if 'IS NOT NULL' in normalized.upper():
            rules['required'] = True
            rules['bsonType'] = 'string'  # Default assumption
            logger.debug("[Validation Parser] → required=True")
            return rules
        
        # 2. IN clause (enum) - must check BEFORE numeric comparisons
        in_match = re.search(r'IN\s*\(\s*([^)]+)\s*\)', normalized, re.IGNORECASE)
        if in_match:
            values_str = in_match.group(1)
            # Extract values - handle both quoted and unquoted
            enum_values = []
            for val in re.findall(r"['\"]([^'\"]+)['\"]|(\w+)", values_str):
                enum_values.append(val[0] if val[0] else val[1])
            
            if enum_values:
                rules['enum'] = enum_values
                # Try to infer type from first value
                try:
                    int(enum_values[0])
                    rules['bsonType'] = ['int', 'long']
                except:
                    rules['bsonType'] = 'string'
                logger.debug(f"[Validation Parser] → enum={enum_values}")
                return rules
        
        # 3. String length via LENGTH() or CHAR_LENGTH()
        length_match = re.search(
            r'(?:LENGTH|CHAR_LENGTH)\s*\(\s*\w+\s*\)\s*([><=]+)\s*(\d+)',
            normalized,
            re.IGNORECASE
        )
        if length_match:
            operator = length_match.group(1)
            length_val = int(length_match.group(2))
            
            if '>=' in operator:
                rules['minLength'] = length_val
            elif '>' in operator:
                rules['minLength'] = length_val + 1
            elif '<=' in operator:
                rules['maxLength'] = length_val
            elif '<' in operator:
                rules['maxLength'] = length_val - 1
            
            rules['bsonType'] = 'string'
            logger.debug(f"[Validation Parser] → length constraint: {rules}")
            return rules
        
        # 4. Numeric comparisons (>, >=, <, <=)
        # Check for >= and <= before > and < to avoid false matches
        if '>=' in normalized:
            match = re.search(r'>=\s*([0-9.]+)', normalized)
            if match:
                val = float(match.group(1)) if '.' in match.group(1) else int(match.group(1))
                rules['minimum'] = val
                rules['bsonType'] = ['int', 'long', 'double', 'decimal']
                logger.debug(f"[Validation Parser] → minimum={val}")
        elif '>' in normalized:
            match = re.search(r'>\s*([0-9.]+)', normalized)
            if match:
                val = float(match.group(1)) if '.' in match.group(1) else int(match.group(1))
                # Strict inequality - add 1 for integers, 0.01 for floats
                rules['minimum'] = val + (0.01 if isinstance(val, float) else 1)
                rules['bsonType'] = ['int', 'long', 'double', 'decimal']
                logger.debug(f"[Validation Parser] → minimum={rules['minimum']} (from >)")
        
        if '<=' in normalized:
            match = re.search(r'<=\s*([0-9.]+)', normalized)
            if match:
                val = float(match.group(1)) if '.' in match.group(1) else int(match.group(1))
                rules['maximum'] = val
                if 'bsonType' not in rules:
                    rules['bsonType'] = ['int', 'long', 'double', 'decimal']
                logger.debug(f"[Validation Parser] → maximum={val}")
        elif '<' in normalized:
            match = re.search(r'<\s*([0-9.]+)', normalized)
            if match:
                val = float(match.group(1)) if '.' in match.group(1) else int(match.group(1))
                rules['maximum'] = val - (0.01 if isinstance(val, float) else 1)
                if 'bsonType' not in rules:
                    rules['bsonType'] = ['int', 'long', 'double', 'decimal']
                logger.debug(f"[Validation Parser] → maximum={rules['maximum']} (from <)")
        
        # 5. BETWEEN operator
        between_match = re.search(r'BETWEEN\s+([0-9.]+)\s+AND\s+([0-9.]+)', normalized, re.IGNORECASE)
        if between_match:
            min_val = float(between_match.group(1)) if '.' in between_match.group(1) else int(between_match.group(1))
            max_val = float(between_match.group(2)) if '.' in between_match.group(2) else int(between_match.group(2))
            rules['minimum'] = min_val
            rules['maximum'] = max_val
            rules['bsonType'] = ['int', 'long', 'double', 'decimal']
            logger.debug(f"[Validation Parser] → BETWEEN {min_val} AND {max_val}")
        
        logger.debug(f"[Validation Parser] Final rules: {rules}")
        return rules if rules else None
    
    def _validation_to_check(validation_rules, column_name):
        """
        Convert NoSQL validation rules to SQL CHECK constraint expression.
        ENHANCED: Database-agnostic output, handles all validation types
        
        Outputs generic SQL that works across databases (uses standard SQL functions)
        """
        constraints = []
        
        bson_type = validation_rules.get('bsonType')
        # Handle unknown types gracefully - assume string if not recognized
        recognized_numeric_types = ['int', 'long', 'double', 'decimal']
        is_numeric = (isinstance(bson_type, list) and 
                    any(t in recognized_numeric_types for t in bson_type) or 
                    bson_type in recognized_numeric_types)
        is_string = (bson_type == 'string' or 
                    (isinstance(bson_type, str) and bson_type not in recognized_numeric_types))
        
        logger.debug(f"[Validation→CHECK] Converting for '{column_name}': {validation_rules}")
        logger.debug(f"[Validation→CHECK] Type detection: is_numeric={is_numeric}, is_string={is_string}")
        
        # ✅ CRITICAL FIX: Detect which database we're using to use correct function
        handler = app.config['HANDLER']
        actual_handler = handler.handler if hasattr(handler, 'handler') else handler
        db_handler_name = actual_handler.DB_NAME if hasattr(actual_handler, 'DB_NAME') else 'SQLite'
        
        # ✅ SQLite uses LENGTH(), others use CHAR_LENGTH()
        length_func = 'LENGTH' if db_handler_name == 'SQLite' else 'CHAR_LENGTH'
        
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
                constraints.append(f'{length_func}({column_name}) >= {int(min_val)}')
                logger.debug(f"[Validation→CHECK] Added: {length_func} >= {int(min_val)}")
        
        if 'maximum' in validation_rules:
            max_val = validation_rules['maximum']
            if is_numeric:
                constraints.append(f'{column_name} <= {max_val}')
                logger.debug(f"[Validation→CHECK] Added: <= {max_val}")
            elif is_string:
                constraints.append(f'{length_func}({column_name}) <= {int(max_val)}')
                logger.debug(f"[Validation→CHECK] Added: {length_func} <= {int(max_val)}")
        
        # 3. String length constraints (explicit)
        if 'minLength' in validation_rules:
            constraints.append(f'{length_func}({column_name}) >= {validation_rules["minLength"]}')
            logger.debug(f"[Validation→CHECK] Added: minLength={validation_rules['minLength']}")
        
        if 'maxLength' in validation_rules:
            constraints.append(f'{length_func}({column_name}) <= {validation_rules["maxLength"]}')
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

    @app.route('/api/db/<db_name>/import', methods=['POST'])
    def api_import_database(db_name):
        """JSON API: Import database from SQL or JSON"""
        try:
            data = request.get_json()
            content = data.get('content')
            format_type = data.get('format', 'json')
            
            if not content:
                return jsonify({'success': False, 'error': 'No content provided'}), 400
            
            logger.debug(f"✅ API call: POST /api/db/{db_name}/import - format={format_type}")
            
            app.config['HANDLER'].switch_db(db_name)
            handler = app.config['HANDLER']
            
            if format_type == 'sql':
                # SQL import - execute as transaction
                if app.config['DB_TYPE'] != 'sql':
                    return jsonify({
                        'success': False,
                        'error': 'SQL import only available for SQL databases'
                    }), 400
                
                # ✅ Clean SQL content - remove database-specific commands
                cleaned_content = _clean_sql_for_import(content, db_name)

                # ✅ Convert SQL syntax for target handler (e.g., AUTOINCREMENT for DuckDB)
                cleaned_content = _convert_sql_for_handler(cleaned_content, handler)
                
                # Split into statements
                statements = [s.strip() for s in cleaned_content.split(';') if s.strip()]
                
                try:
                    # Get handler type to choose transaction strategy
                    actual_handler = handler.handler if hasattr(handler, 'handler') else handler
                    db_handler_name = actual_handler.DB_NAME if hasattr(actual_handler, 'DB_NAME') else 'SQLite'
                    
                    # ✅ Use different transaction strategies based on database
                    if db_handler_name in ['DuckDB', 'PostgreSQL']:
                        with handler.engine.begin() as conn:
                            executed_count = 0
                            i = 0
                            while i < len(statements):
                                stmt = statements[i].strip()
                                if not stmt or stmt.startswith('--'):
                                    i += 1
                                    continue
                                
                                stmt_upper = stmt.upper()
                                if any(skip in stmt_upper for skip in ['CREATE DATABASE', 'DROP DATABASE', 'USE ']):
                                    logger.debug(f"Skipping database-level command: {stmt[:50]}...")
                                    i += 1
                                    continue
                                
                                # ← Insert the new guard here →
                                if stmt.strip() == '$function$' or stmt.strip().startswith('$$') and not stmt_upper.startswith('CREATE'):
                                    logger.debug("Skipping dangling dollar-quote terminator from function")
                                    i += 1
                                    continue
                                
                                # Handle statements one by one
                                if stmt_upper.startswith('CREATE TABLE'):
                                    if actual_handler.DB_NAME == 'PostgreSQL':
                                        try:
                                            modified_create = handler.handler.upgrade_create_table_to_serial(stmt)
                                            conn.execute(text(modified_create))
                                            logger.debug("Successfully created/upgraded table with SERIAL")
                                        except Exception as upgrade_err:
                                            err_str = str(upgrade_err).lower()
                                            if 'duplicate' in err_str or 'already exists' in err_str:
                                                logger.info(f"Table already exists (likely from previous import), skipping CREATE: {upgrade_err}")
                                                # Table exists — safe to continue with INSERTs
                                            else:
                                                logger.warning(f"PostgreSQL SERIAL upgrade failed, trying original: {upgrade_err}")
                                                try:
                                                    conn.execute(text(stmt))
                                                except Exception as original_err:
                                                    if 'already exists' not in str(original_err).lower():
                                                        raise original_err
                                                    logger.info("Original CREATE also skipped (table exists)")
                                    else:
                                        conn.execute(text(stmt))
                                    executed_count += 1
                                else:
                                    # All other statements (INSERT, DROP, etc.)
                                    conn.execute(text(stmt))
                                    executed_count += 1
                                
                                i += 1
                    else:
                        # Other databases: Use explicit BEGIN/COMMIT
                        with handler._get_connection() as conn:
                            conn.execute(text("BEGIN"))
                            
                            try:
                                executed_count = 0
                                for stmt in statements:
                                    if stmt.startswith('--') or not stmt.strip():
                                        continue
                                    
                                    stmt_upper = stmt.strip().upper()
                                    if any(skip in stmt_upper for skip in [
                                        'CREATE DATABASE', 'DROP DATABASE', 'USE '
                                    ]):
                                        logger.debug(f"Skipping database-level command: {stmt[:50]}...")
                                        continue
                                    
                                    try:
                                        conn.execute(text(stmt))
                                        executed_count += 1
                                    except Exception as stmt_error:
                                        logger.error(f"Statement failed: {stmt[:100]}")
                                        raise stmt_error
                                
                                conn.commit()
                            except Exception as e:
                                conn.execute(text("ROLLBACK"))
                                raise e
                    
                    return jsonify({
                        'success': True,
                        'message': f'Imported {executed_count} statements successfully'
                    })

                except Exception as e:
                    logger.error(f"Import failed: {e}")
                    return jsonify({
                        'success': False,
                        'error': f'Import failed: {str(e)}'
                    }), 500
            
            else:  # JSON import
                try:
                    import_data = json.loads(content)
                    logger.info(f"JSON Import started - DB_TYPE: {app.config['DB_TYPE']}, Handler class: {handler.__class__.__name__}")
                except json.JSONDecodeError as e:
                    return jsonify({
                        'success': False,
                        'error': f'Invalid JSON: {str(e)}'
                    }), 400
                
                try:
                    # ✅ PERFECT MATCH: Your exports are single-table objects with metadata/data
                    tables_to_import = []
                    
                    if isinstance(import_data, dict) and 'metadata' in import_data and 'data' in import_data:
                        # Your exact export format — single table with metadata
                        table_obj = import_data.copy()
                        # Extract table name from metadata
                        table_name = table_obj['metadata'].get('table_name', 'imported_table')
                        table_obj['name'] = table_name
                        tables_to_import = [table_obj]
                        logger.info(f"🎉 Recognized your single-table export format: '{table_name}' with {len(table_obj.get('data', []))} documents")
                    elif isinstance(import_data, list):
                        tables_to_import = import_data
                        logger.info(f"Detected array of {len(tables_to_import)} tables")
                    elif 'tables' in import_data:
                        tables_to_import = import_data['tables']
                        logger.info(f"Found {len(tables_to_import)} tables in 'tables' key")
                    else:
                        logger.warning(f"Unrecognized JSON structure: top-level keys = {list(import_data.keys())}")
                        return jsonify({
                            'success': False,
                            'error': 'Unsupported JSON export format — expected metadata/data structure'
                        }), 400
                    
                    logger.info(f"🎉 Ready to import {len(tables_to_import)} table(s)")
                    
                    # For SQL databases, use transactions
                    if app.config['DB_TYPE'] == 'sql':
                        # Get handler type to choose transaction strategy
                        actual_handler = handler.handler if hasattr(handler, 'handler') else handler
                        db_handler_name = actual_handler.DB_NAME if hasattr(actual_handler, 'DB_NAME') else 'SQLite'
                        
                        # Use different transaction strategies based on database
                        if db_handler_name in ['DuckDB', 'PostgreSQL']:
                            # DuckDB/PostgreSQL: Use engine.begin()
                            with handler.engine.begin() as conn:
                                for table_data in tables_to_import:
                                    table_name = table_data['name']
                                    
                                    # CRITICAL: For PostgreSQL, always use lowercase table names for consistency
                                    if db_handler_name == 'PostgreSQL':
                                        table_name = table_name.lower()
                                        table_data['name'] = table_name  # Update in place for consistency
                                        
                                    # Check if table already exists
                                    existing_tables = handler.list_tables()
                                    if table_name in existing_tables:
                                        logger.warning(f"Table {table_name} already exists, dropping and recreating")
                                        # Drop the existing table to allow reimport
                                        try:
                                            if hasattr(actual_handler, '_quote_identifier'):
                                                quoted_table = actual_handler._quote_identifier(table_name)
                                            else:
                                                quoted_table = f'"{table_name}"'
                                            conn.execute(text(f"DROP TABLE IF EXISTS {quoted_table}"))
                                            logger.info(f"Dropped existing table {table_name}")
                                        except Exception as drop_err:
                                            logger.error(f"Failed to drop existing table {table_name}: {drop_err}")
                                            continue
                                    
                                    # ✅ FIX: Create table with proper schema handling
                                    if table_data.get('schema') and len(table_data.get('schema', [])) > 0:
                                        # Normalize all datatypes in schema before creating table
                                        normalized_schema = []
                                        for col in table_data['schema']:
                                            col_copy = col.copy()
                                            original_type = col['type']
                                            normalized_type = _normalize_datatype(original_type, handler)
                                            col_copy['type'] = normalized_type
                                            if original_type != normalized_type:
                                                logger.info(f"Normalized type for {col['name']}: {original_type} -> {normalized_type}")
                                            normalized_schema.append(col_copy)
                                        _create_table_from_schema(handler, table_name, normalized_schema, conn)
                                    else:
                                        # ✅ FIX: No schema provided (NoSQL export) - infer from data
                                        if table_data.get('data') and len(table_data['data']) > 0:
                                            inferred_schema = _infer_schema_from_data(table_data['data'], table_name)
                                            _create_table_from_schema(handler, table_name, inferred_schema, conn)
                                    
                                    # ✅ FIX: Quote table and column names for INSERT
                                    if hasattr(handler, 'handler') and hasattr(handler.handler, '_quote_identifier'):
                                        actual_handler = handler.handler
                                        quoted_table = actual_handler._quote_identifier(table_name)
                                    else:
                                        quoted_table = f"`{table_name}`"
                                    
                                    # Insert data - SKIP NoSQL-specific ID fields
                                    for row in table_data.get('data', []):
                                        # ✅ CRITICAL FIX: Remove NoSQL-specific ID fields
                                        clean_row = {k: v for k, v in row.items() 
                                                if k not in ['_id', 'doc_id']}
                                        
                                        if not clean_row:
                                            continue
                                        
                                        # ✅ CRITICAL FIX: Serialize nested objects/arrays for SQL
                                        serialized_row = {}
                                        for k, v in clean_row.items():
                                            if v is None:
                                                serialized_row[k] = None
                                            elif isinstance(v, (dict, list)):
                                                # Convert nested structures to JSON string
                                                serialized_row[k] = json.dumps(v)
                                            else:
                                                serialized_row[k] = v
                                        
                                        # ✅ FIX: Quote table and column names for INSERT
                                        columns = list(serialized_row.keys())
                                        if hasattr(handler, 'handler') and hasattr(handler.handler, '_quote_identifier'):
                                            actual_handler = handler.handler
                                            quoted_cols = ', '.join([actual_handler._quote_identifier(k) for k in columns])
                                        else:
                                            quoted_cols = ', '.join([f"`{k}`" for k in columns])
                                        
                                        placeholders = ', '.join([f':{k}' for k in columns])
                                        insert_stmt = f"INSERT INTO {quoted_table} ({quoted_cols}) VALUES ({placeholders})"
                                        conn.execute(text(insert_stmt), serialized_row)
                                    
                                    # ✅ FIXED: Import triggers WITHIN the same transaction
                                    if hasattr(handler, 'supports_triggers') and handler.supports_triggers():
                                        for trigger in table_data.get('triggers', []):
                                            try:
                                                trigger_name = trigger['name']
                                                trigger_timing = trigger.get('timing', 'AFTER')
                                                trigger_event = trigger.get('event', 'INSERT')
                                                trigger_body = trigger.get('body', '')
                                                
                                                # ✅ Extract body if wrapped in BEGIN...END
                                                if trigger_body.strip().upper().startswith('BEGIN'):
                                                    match = re.search(r'BEGIN\s+(.*?)\s+END', trigger_body, re.DOTALL | re.IGNORECASE)
                                                    if match:
                                                        trigger_body = match.group(1).strip()
                                                
                                                # ✅ Convert trigger syntax for target database
                                                actual_handler = handler.handler if hasattr(handler, 'handler') else handler
                                                if hasattr(actual_handler, 'convert_trigger_syntax'):
                                                    trigger_body = actual_handler.convert_trigger_syntax(
                                                        trigger_body, trigger_event, table_name
                                                    )
                                                
                                                # ✅ CRITICAL: Use transaction-aware method if available
                                                if hasattr(actual_handler, 'create_trigger_in_transaction'):
                                                    actual_handler.create_trigger_in_transaction(
                                                        conn, trigger_name, table_name, trigger_timing, trigger_event, trigger_body
                                                    )
                                                else:
                                                    # Fallback: Regular method (may commit)
                                                    # For databases without transaction-aware triggers, accept the commit
                                                    logger.warning(f"Handler lacks create_trigger_in_transaction, using regular create_trigger")
                                                    handler.create_trigger(
                                                        trigger_name, table_name, trigger_timing, trigger_event, trigger_body
                                                    )
                                                
                                                logger.info(f"✅ Imported trigger: {trigger_name}")
                                            except Exception as trig_err:
                                                logger.warning(f"⚠️ Failed to import trigger {trigger.get('name')}: {trig_err}")
                                                
                                    # ✅ CRITICAL: Apply CHECK constraints from NoSQL validation rules
                                    check_constraints_to_apply = []

                                    if table_data.get('constraints', {}).get('check'):
                                        # Format 1: constraints.check array (from NoSQL exports)
                                        for check in table_data['constraints']['check']:
                                            col_name = check.get('column')
                                            
                                            # ✅ ADD DEBUG LOGGING
                                            logger.debug(f"[Validation→CHECK] Converting for '{col_name}': {check}")
                                            
                                            # ✅ NEW: Try validation_rules first (parsed format)
                                            validation_rules = check.get('validation_rules')
                                            if validation_rules:
                                                logger.debug(f"[Validation→CHECK] Type detection: is_numeric={validation_rules.get('bsonType')}, is_string={validation_rules.get('bsonType') == 'string'}")
                                                check_expr = _validation_to_check(validation_rules, col_name)
                                                if check_expr:
                                                    check_constraints_to_apply.append({
                                                        'column': col_name,
                                                        'expression': check_expr
                                                    })
                                                    logger.debug(f"Prepared CHECK for {col_name}: {check_expr}")
                                            # ✅ NEW: Also try parsing expression field directly
                                            elif check.get('expression'):
                                                # Parse the expression to get validation rules
                                                parsed = _parse_validation_expression(check['expression'])
                                                if parsed:
                                                    check_expr = _validation_to_check(parsed, col_name)
                                                    if check_expr:
                                                        check_constraints_to_apply.append({
                                                            'column': col_name,
                                                            'expression': check_expr
                                                        })
                                                        logger.debug(f"Prepared CHECK from expression for {col_name}: {check_expr}")
                                    
                                    # Apply all collected CHECK constraints
                                    if check_constraints_to_apply:
                                        logger.info(f"Attempting to apply {len(check_constraints_to_apply)} CHECK constraints to {table_name}")
                                        
                                        # Check if handler supports CHECK constraints
                                        if hasattr(handler, 'supports_check_constraints') and handler.supports_check_constraints():
                                            successful = 0
                                            failed = 0
                                            
                                            for check_info in check_constraints_to_apply:
                                                logger.info(f"🔥 PROCESSING CONSTRAINT FOR COLUMN '{check_info['column']}'")
                                                logger.info(f"Expression: {check_info['expression']}")

                                                try:
                                                    # Loudly announce what we're checking
                                                    logger.info("Checking if handler has add_check_constraint_to_existing_table...")
                                                    if hasattr(handler, 'add_check_constraint_to_existing_table'):
                                                        logger.info("YES – method found! Calling it now...")
                                                        # ✅ CRITICAL FIX: Pass the connection so CHECK uses same transaction
                                                        actual_handler = handler.handler if hasattr(handler, 'handler') else handler
                                                        actual_handler.add_check_constraint_to_existing_table(
                                                            table_name,
                                                            check_info['column'],
                                                            check_info['expression'],
                                                            conn  # Pass the active connection
                                                        )
                                                        logger.info(f"🎉 CALL SUCCEEDED for {check_info['column']}")
                                                        successful += 1
                                                    else:
                                                        logger.warning("⚠️ add_check_constraint_to_existing_table NOT found on handler")

                                                    if hasattr(handler, 'create_check_constraint'):
                                                        logger.info("Trying create_check_constraint as fallback...")
                                                        # Note: create_check_constraint might not support conn param
                                                        # This is usually for table recreation, not ALTER
                                                        handler.create_check_constraint(
                                                            table_name,
                                                            check_info['column'],
                                                            check_info['expression']
                                                        )
                                                        logger.info(f"🎉 Fallback call succeeded for {check_info['column']}")
                                                        successful += 1

                                                except Exception as check_err:
                                                    failed += 1
                                                    logger.error(f"💥 EXCEPTION CAUGHT for {check_info['column']}: {type(check_err).__name__}: {check_err}")
                                                    import traceback
                                                    logger.error("Full traceback:")
                                                    logger.error(traceback.format_exc())

                                            logger.info(f"🏁 Constraint application complete: {successful} succeeded, {failed} failed")
                                            
                                            if successful > 0:
                                                logger.info(f"✅ Successfully applied {successful}/{len(check_constraints_to_apply)} CHECK constraints")
                                            if failed > 0:
                                                logger.warning(f"⚠️ Failed to apply {failed}/{len(check_constraints_to_apply)} CHECK constraints")
                                        else:
                                            logger.warning(f"⚠️ Handler does not support CHECK constraints - skipping {len(check_constraints_to_apply)} constraints")
                                
                                # ✅ FIXED: Import procedures with cross-DB conversion
                                if hasattr(handler, 'supports_procedures') and handler.supports_procedures():
                                    for proc in import_data.get('procedures', []):
                                        try:
                                            proc_def = proc.get('definition', '')
                                            if not proc_def:
                                                continue
                                            
                                            proc_name = proc.get('name')
                                            proc_type = proc.get('type', 'PROCEDURE')
                                            
                                            # ✅ CRITICAL: Fix RETURNS TABLE syntax - remove table.column prefixes
                                            # Bad: RETURNS TABLE(students.name TEXT) → Good: RETURNS TABLE(name TEXT)
                                            def fix_returns_table(match):
                                                inside = match.group(1)
                                                # Remove table prefixes: table.column → column
                                                fixed = re.sub(r'\b\w+\.(\w+)', r'\1', inside)
                                                return f'RETURNS TABLE({fixed})'
                                            
                                            proc_def = re.sub(
                                                r'RETURNS\s+TABLE\s*\((.*?)\)',
                                                fix_returns_table,
                                                proc_def,
                                                flags=re.IGNORECASE
                                            )
                                            
                                            # ONLY remove PostgreSQL type casts — this is all we need!
                                            proc_def = re.sub(r'::[A-Z]+(::[A-Z]+)?', '', proc_def)
                                            proc_def = re.sub(r'::+', '', proc_def)  # clean any leftover ::
                                            
                                            # Optional: fix assignment for triggers (safe and harmless)
                                            proc_def = proc_def.replace(':=', '=')
                                            
                                            # ✅ Convert procedure syntax for target database
                                            actual_handler = handler.handler if hasattr(handler, 'handler') else handler
                                            if hasattr(actual_handler, 'convert_procedure_syntax'):
                                                # Let handler convert syntax (e.g., PROCEDURE → FUNCTION)
                                                converted_def = actual_handler.convert_procedure_syntax(
                                                    proc_def, proc_name, proc_type
                                                )
                                                handler.execute_procedure(converted_def)
                                            else:
                                                # No conversion support - try as-is
                                                handler.execute_procedure(proc_def)
                                            
                                            logger.info(f"✅ Imported {proc_type}: {proc_name}")
                                        except Exception as proc_err:
                                            logger.warning(f"⚠️ Failed to import procedure {proc.get('name')}: {proc_err}")
                                
                                # Transaction commits automatically on successful exit
                                # Rollback happens automatically on exception - no explicit ROLLBACK needed
                            
                        else:
                            # Other databases: Use explicit BEGIN/COMMIT
                            with handler._get_connection() as conn:
                                conn.execute(text("BEGIN"))
                                
                                try:
                                    for table_data in tables_to_import:
                                            table_name = table_data['name']
                                    
                                            # ✅ FIX: Create table with proper schema handling
                                            if table_data.get('schema') and len(table_data.get('schema', [])) > 0:
                                                # Normalize all datatypes in schema before creating table
                                                normalized_schema = []
                                                for col in table_data['schema']:
                                                    col_copy = col.copy()
                                                    original_type = col['type']
                                                    normalized_type = _normalize_datatype(original_type, handler)
                                                    col_copy['type'] = normalized_type
                                                    if original_type != normalized_type:
                                                        logger.info(f"Normalized type for {col['name']}: {original_type} -> {normalized_type}")
                                                    normalized_schema.append(col_copy)
                                                _create_table_from_schema(handler, table_name, normalized_schema, conn)
                                            else:
                                                # ✅ FIX: No schema provided (NoSQL export) - infer from data
                                                if table_data.get('data') and len(table_data['data']) > 0:
                                                    inferred_schema = _infer_schema_from_data(table_data['data'], table_name)
                                                    _create_table_from_schema(handler, table_name, inferred_schema, conn)
                                            
                                            # ✅ FIX: Quote table and column names for INSERT
                                            if hasattr(handler, 'handler') and hasattr(handler.handler, '_quote_identifier'):
                                                actual_handler = handler.handler
                                                quoted_table = actual_handler._quote_identifier(table_name)
                                            else:
                                                quoted_table = f"`{table_name}`"
                                            
                                            # Insert data - SKIP NoSQL-specific ID fields
                                            for row in table_data.get('data', []):
                                                # ✅ CRITICAL FIX: Remove NoSQL-specific ID fields
                                                clean_row = {k: v for k, v in row.items() 
                                                        if k not in ['_id', 'doc_id']}
                                                
                                                if not clean_row:
                                                    continue
                                                
                                                # ✅ CRITICAL FIX: Serialize nested objects/arrays for SQL
                                                serialized_row = {}
                                                for k, v in clean_row.items():
                                                    if v is None:
                                                        serialized_row[k] = None
                                                    elif isinstance(v, (dict, list)):
                                                        # Convert nested structures to JSON string
                                                        serialized_row[k] = json.dumps(v)
                                                    else:
                                                        serialized_row[k] = v
                                                
                                                # ✅ FIX: Quote table and column names for INSERT
                                                columns = list(serialized_row.keys())
                                                if hasattr(handler, 'handler') and hasattr(handler.handler, '_quote_identifier'):
                                                    actual_handler = handler.handler
                                                    quoted_cols = ', '.join([actual_handler._quote_identifier(k) for k in columns])
                                                else:
                                                    quoted_cols = ', '.join([f"`{k}`" for k in columns])
                                                
                                                placeholders = ', '.join([f':{k}' for k in columns])
                                                insert_stmt = f"INSERT INTO {quoted_table} ({quoted_cols}) VALUES ({placeholders})"
                                                conn.execute(text(insert_stmt), serialized_row)
                                            
                                            # ✅ FIXED: Import triggers WITHIN the same transaction
                                            if hasattr(handler, 'supports_triggers') and handler.supports_triggers():
                                                for trigger in table_data.get('triggers', []):
                                                    try:
                                                        trigger_name = trigger['name']
                                                        trigger_timing = trigger.get('timing', 'AFTER')
                                                        trigger_event = trigger.get('event', 'INSERT')
                                                        trigger_body = trigger.get('body', '')
                                                        
                                                        # ✅ Extract body if wrapped in BEGIN...END
                                                        if trigger_body.strip().upper().startswith('BEGIN'):
                                                            match = re.search(r'BEGIN\s+(.*?)\s+END', trigger_body, re.DOTALL | re.IGNORECASE)
                                                            if match:
                                                                trigger_body = match.group(1).strip()
                                                        
                                                        # ✅ Convert trigger syntax for target database
                                                        actual_handler = handler.handler if hasattr(handler, 'handler') else handler
                                                        if hasattr(actual_handler, 'convert_trigger_syntax'):
                                                            trigger_body = actual_handler.convert_trigger_syntax(
                                                                trigger_body, trigger_event, table_name
                                                            )
                                                        
                                                        # ✅ CRITICAL: Use transaction-aware method if available
                                                        if hasattr(actual_handler, 'create_trigger_in_transaction'):
                                                            actual_handler.create_trigger_in_transaction(
                                                                conn, trigger_name, table_name, trigger_timing, trigger_event, trigger_body
                                                            )
                                                        else:
                                                            # Fallback: Regular method (may commit)
                                                            # For databases without transaction-aware triggers, accept the commit
                                                            logger.warning(f"Handler lacks create_trigger_in_transaction, using regular create_trigger")
                                                            handler.create_trigger(
                                                                trigger_name, table_name, trigger_timing, trigger_event, trigger_body
                                                            )
                                                        
                                                        logger.info(f"✅ Imported trigger: {trigger_name}")
                                                    except Exception as trig_err:
                                                        logger.warning(f"⚠️ Failed to import trigger {trigger.get('name')}: {trig_err}")
                                                        
                                            # ✅ CRITICAL: Apply CHECK constraints from NoSQL validation rules
                                            check_constraints_to_apply = []

                                            if table_data.get('constraints', {}).get('check'):
                                                # Format 1: constraints.check array (from NoSQL exports)
                                                for check in table_data['constraints']['check']:
                                                    col_name = check.get('column')
                                                    
                                                    # ✅ NEW: Try validation_rules first (parsed format)
                                                    validation_rules = check.get('validation_rules')
                                                    if validation_rules:
                                                        check_expr = _validation_to_check(validation_rules, col_name)
                                                        if check_expr:
                                                            check_constraints_to_apply.append({
                                                                'column': col_name,
                                                                'expression': check_expr
                                                            })
                                                            logger.debug(f"Prepared CHECK for {col_name}: {check_expr}")
                                                    # ✅ NEW: Also try parsing expression field directly
                                                    elif check.get('expression'):
                                                        # Parse the expression to get validation rules
                                                        parsed = _parse_validation_expression(check['expression'])
                                                        if parsed:
                                                            check_expr = _validation_to_check(parsed, col_name)
                                                            if check_expr:
                                                                check_constraints_to_apply.append({
                                                                    'column': col_name,
                                                                    'expression': check_expr
                                                                })
                                                                logger.debug(f"Prepared CHECK from expression for {col_name}: {check_expr}")
                                            
                                            # ✅ CRITICAL FIX: For MySQL/SQLite, commit data BEFORE attempting CHECK constraints
                                            if db_handler_name in ['MySQL', 'SQLite']:
                                                # Commit current transaction to persist data
                                                conn.commit()
                                                logger.debug(f"Committed data transaction for {db_handler_name}")
                                            
                                            # Apply all collected CHECK constraints
                                            if check_constraints_to_apply:
                                                logger.info(f"Attempting to apply {len(check_constraints_to_apply)} CHECK constraints to {table_name}")
                                                
                                                # Check if handler supports CHECK constraints
                                                if hasattr(handler, 'supports_check_constraints') and handler.supports_check_constraints():
                                                    successful = 0
                                                    failed = 0
                                                    
                                                    for check_info in check_constraints_to_apply:
                                                        logger.info(f"🔥 PROCESSING CONSTRAINT FOR COLUMN '{check_info['column']}'")
                                                        logger.info(f"Expression: {check_info['expression']}")

                                                        try:
                                                            # Loudly announce what we're checking
                                                            logger.info("Checking if handler has add_check_constraint_to_existing_table...")
                                                            if hasattr(handler, 'add_check_constraint_to_existing_table'):
                                                                logger.info("YES – method found! Calling it now...")
                                                                actual_handler = handler.handler if hasattr(handler, 'handler') else handler
                                                                
                                                                # ✅ CRITICAL FIX: For MySQL and SQLite, DON'T pass conn - let them create their own
                                                                if db_handler_name in ['MySQL', 'SQLite']:
                                                                    actual_handler.add_check_constraint_to_existing_table(
                                                                        table_name,
                                                                        check_info['column'],
                                                                        check_info['expression']
                                                                        # No conn parameter - will create new connection
                                                                    )
                                                                else:
                                                                    # Other databases: use existing transaction
                                                                    actual_handler.add_check_constraint_to_existing_table(
                                                                        table_name,
                                                                        check_info['column'],
                                                                        check_info['expression'],
                                                                        conn
                                                                    )
                                                                logger.info(f"🎉 CALL SUCCEEDED for {check_info['column']}")
                                                                successful += 1
                                                            else:
                                                                logger.warning("⚠️ add_check_constraint_to_existing_table NOT found on handler")

                                                            if hasattr(handler, 'create_check_constraint'):
                                                                logger.info("Trying create_check_constraint as fallback...")
                                                                # Note: create_check_constraint might not support conn param
                                                                # This is usually for table recreation, not ALTER
                                                                handler.create_check_constraint(
                                                                    table_name,
                                                                    check_info['column'],
                                                                    check_info['expression']
                                                                )
                                                                logger.info(f"🎉 Fallback call succeeded for {check_info['column']}")
                                                                successful += 1

                                                        except Exception as check_err:
                                                            failed += 1
                                                            logger.error(f"💥 EXCEPTION CAUGHT for {check_info['column']}: {type(check_err).__name__}: {check_err}")
                                                            import traceback
                                                            logger.error("Full traceback:")
                                                            logger.error(traceback.format_exc())

                                                    logger.info(f"🏁 Constraint application complete: {successful} succeeded, {failed} failed")
                                                    
                                                    if successful > 0:
                                                        logger.info(f"✅ Successfully applied {successful}/{len(check_constraints_to_apply)} CHECK constraints")
                                                    if failed > 0:
                                                        logger.warning(f"⚠️ Failed to apply {failed}/{len(check_constraints_to_apply)} CHECK constraints")
                                                else:
                                                    logger.warning(f"⚠️ Handler does not support CHECK constraints - skipping {len(check_constraints_to_apply)} constraints")
                                        
                                             # ✅ MINIMAL & RELIABLE: Import procedures — only remove PostgreSQL casts
                                            if hasattr(handler, 'supports_procedures') and handler.supports_procedures():
                                                for proc in import_data.get('procedures', []):
                                                    try:
                                                        proc_def = proc.get('definition', '').strip()
                                                        if not proc_def:
                                                            continue
                                                        
                                                        proc_name = proc.get('name')
                                                        proc_type = proc.get('type', 'PROCEDURE')
                                                        
                                                        # ✅ NEW: Fix RETURNS TABLE syntax - remove table prefixes from column names
                                                        # Pattern: RETURNS TABLE(table.col TYPE, ...) → RETURNS TABLE(col TYPE, ...)
                                                        proc_def = re.sub(
                                                            r'RETURNS\s+TABLE\s*\((.*?)\)',
                                                            lambda m: 'RETURNS TABLE(' + re.sub(r'\w+\.(\w+)', r'\1', m.group(1)) + ')',
                                                            proc_def,
                                                            flags=re.IGNORECASE | re.DOTALL
                                                        )
                                                        
                                                        # ONLY remove PostgreSQL type casts — this is all we need!
                                                        proc_def = re.sub(r'::[A-Z]+(::[A-Z]+)?', '', proc_def)
                                                        proc_def = re.sub(r'::+', '', proc_def)  # clean any leftover ::
                                                        
                                                        # Optional: fix assignment for triggers (safe and harmless)
                                                        proc_def = proc_def.replace(':=', '=')
                                                        
                                                        # Let the handler convert if it wants (e.g. for DuckDB → SQLite differences)
                                                        actual_handler = handler.handler if hasattr(handler, 'handler') else handler
                                                        if hasattr(actual_handler, 'convert_procedure_syntax'):
                                                            converted_def = actual_handler.convert_procedure_syntax(
                                                                proc_def, proc_name, proc_type
                                                            )
                                                        else:
                                                            converted_def = proc_def
                                                        
                                                        handler.execute_procedure(converted_def)
                                                        logger.info(f"✅ Imported {proc_type}: {proc_name}")
                                                    except Exception as proc_err:
                                                        logger.warning(f"⚠️ Failed to import procedure {proc.get('name')}: {proc_err}")
                                                    
                                            conn.commit()
                            
                                except Exception as e:
                                    conn.execute(text("ROLLBACK"))
                                    raise e
                    
                    else:  # NoSQL
                        logger.info(f"🎉 Starting NoSQL JSON import for database {db_name}")
                        logger.info(f"Found {len(tables_to_import)} tables/collections in import data")
                        for table_data in tables_to_import:
                            collection_name = table_data['name']
                            logger.info(f"Processing collection: {collection_name} with {len(table_data.get('data', []))} documents")
                            
                            # Create collection WITHOUT validation first
                            try:
                                handler.create_collection(collection_name)
                            except Exception as create_err:
                                logger.debug(f"Collection {collection_name} might already exist: {create_err}")
                            
                            # Insert documents
                            primary_key = handler.get_primary_key_name() if hasattr(handler, 'get_primary_key_name') else None
                            inserted_count = 0
                            for doc in table_data.get('data', []):
                                clean_doc = doc.copy()
                                
                                # Remove NoSQL-specific ID fields
                                if primary_key and primary_key in clean_doc:
                                    del clean_doc[primary_key]
                                if '_id' in clean_doc and clean_doc['_id'] is None:
                                    del clean_doc['_id']
                                
                                if not clean_doc:
                                    logger.debug(f"Skipped empty document in {collection_name}")
                                    continue
                                
                                try:
                                    handler.insert(collection_name, clean_doc)
                                    inserted_count += 1
                                    logger.debug(f"Inserted document into {collection_name} (fields: {list(clean_doc.keys())})")
                                except Exception as insert_err:
                                    logger.warning(f"Failed to insert document into {collection_name}: {insert_err}")
                            
                            logger.info(f"Finished importing {inserted_count} documents into collection {collection_name}")
                            
                            # ✅ CRITICAL: Apply validation rules AFTER data import (SINGLE APPLICATION)
                            check_constraints = table_data.get('constraints', {}).get('check', [])
                            if check_constraints and hasattr(handler, 'apply_validation_rules'):
                                logger.info(f"Found {len(check_constraints)} validation rules to apply to {collection_name}")
                                
                                validation_rules = {}
                                for constraint in check_constraints:
                                    col_name = constraint.get('column')
                                    expression = constraint.get('expression', '')
                                    
                                    if col_name and expression:
                                        parsed = _parse_validation_expression(expression)
                                        if parsed:
                                            validation_rules[col_name] = parsed
                                            logger.debug(f"Collected rules for {col_name}: {parsed}")

                                if validation_rules:
                                    try:
                                        logger.info(f"About to apply {len(validation_rules)} validation rules:")
                                        for field, rules in validation_rules.items():
                                            logger.info(f"  {field}: {rules}")
                                        
                                        handler.apply_validation_rules(collection_name, validation_rules)
                                        logger.info(f"✅ Applied all {len(validation_rules)} merged validation rules to {collection_name}")
                                    except Exception as val_err:
                                        logger.warning(f"⚠️ Could not apply merged validation rules: {val_err}")
                                        logger.warning(f"   Reason: Existing data may violate these constraints")
                    
                    return jsonify({
                        'success': True,
                        'message': 'Import completed successfully'
                    })
                
                except Exception as e:
                    logger.error(f"Import failed: {e}")
                    import traceback
                    logger.error(traceback.format_exc())
                    return jsonify({
                        'success': False,
                        'error': f'Import failed: {str(e)}'
                    }), 500
        
        except Exception as e:
            logger.error(f"❌ Import failed: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500


    @app.route('/api/db/<db_name>/table/<table_name>/import', methods=['POST'])
    def api_import_table(db_name, table_name):
        """JSON API: Import table from SQL or JSON"""
        try:
            data = request.get_json()
            content = data.get('content')
            format_type = data.get('format', 'json')
            
            if not content:
                return jsonify({'success': False, 'error': 'No content provided'}), 400
            
            logger.debug(f"✅ API call: POST /api/db/{db_name}/table/{table_name}/import")
            
            app.config['HANDLER'].switch_db(db_name)
            handler = app.config['HANDLER']
            
            if format_type == 'sql':
                if app.config['DB_TYPE'] != 'sql':
                    return jsonify({
                        'success': False,
                        'error': 'SQL import only available for SQL databases'
                    }), 400
                
                statements = [s.strip() for s in content.split(';') if s.strip()]
                
                try:
                    actual_handler = handler.handler if hasattr(handler, 'handler') else handler
                    db_handler_name = actual_handler.DB_NAME if hasattr(actual_handler, 'DB_NAME') else 'SQLite'
                    
                    if db_handler_name in ['DuckDB', 'PostgreSQL']:
                        # Use implicit transaction via engine.begin() — no explicit BEGIN needed
                        with handler.engine.begin() as conn:
                            for stmt in statements:
                                if not stmt or stmt.startswith('--'):
                                    continue
                                # Optional: add PostgreSQL SERIAL upgrade here if desired for single table
                                # (but since single-table SQL import is usually native, skip for simplicity)
                                conn.execute(text(stmt))
                    else:
                        # Other SQL databases — explicit transaction
                        with handler._get_connection() as conn:
                            conn.execute(text("BEGIN"))
                            try:
                                for stmt in statements:
                                    if stmt and not stmt.startswith('--'):
                                        conn.execute(text(stmt))
                                conn.commit()
                            except Exception as inner_e:
                                conn.execute(text("ROLLBACK"))
                                raise inner_e
                    
                    return jsonify({
                        'success': True,
                        'message': 'Table imported successfully!'
                    })
                
                except Exception as e:
                    logger.error(f"Single table SQL import failed: {e}")
                    return jsonify({
                        'success': False,
                        'error': f'Import failed: {str(e)}'
                    }), 500
            
            else:  # JSON
                try:
                    import_data = json.loads(content)
                    logger.info(f"JSON Import started - DB_TYPE: {app.config['DB_TYPE']}, Handler class: {handler.__class__.__name__}")
                except json.JSONDecodeError as e:
                    return jsonify({
                        'success': False,
                        'error': f'Invalid JSON: {str(e)}'
                    }), 400
                
                try:
                    # Perfect match for your single-table export format
                    if isinstance(import_data, dict) and 'metadata' in import_data and 'data' in import_data:
                        table_data = import_data.copy()
                        # Extract name from metadata, fall back to requested name
                        imported_name = table_data['metadata'].get('table_name', table_name)
                        table_data['name'] = imported_name
                        if imported_name != table_name:
                            logger.info(f"Importing table '{imported_name}' as requested name '{table_name}'")
                        logger.info(f"🎉 Loaded single-table JSON: '{imported_name}' with {len(table_data.get('data', []))} documents")
                    else:
                        return jsonify({
                            'success': False,
                            'error': 'Invalid single-table JSON — expected metadata and data keys'
                        }), 400
                    
                    handler = app.config['HANDLER']
                    actual_handler = handler.handler if hasattr(handler, 'handler') else handler
                    
                    if app.config['DB_TYPE'] == 'sql':
                        # Use same robust transaction as full import
                        if actual_handler.DB_NAME in ['DuckDB', 'PostgreSQL']:
                            with handler.engine.begin() as conn:
                                # Optional: drop existing table? Or skip if exists?
                                # For now, let's overwrite — drop first
                                conn.execute(text(f'DROP TABLE IF EXISTS "{table_name.lower()}"'))
                                
                                schema = table_data.get('schema', [])
                                if schema:
                                    # Normalize datatypes in schema before creating table
                                    normalized_schema = []
                                    for col in schema:
                                        col_copy = col.copy()
                                        col_copy['type'] = _normalize_datatype(col['type'], handler)
                                        normalized_schema.append(col_copy)
                                    schema = normalized_schema
                                    
                                    if actual_handler.DB_NAME == 'PostgreSQL':
                                        # Build with SERIAL upgrade
                                        columns_def = actual_handler.build_column_definitions(schema, quote=False)
                                        col_str = ', '.join(columns_def)
                                        # Force lowercase table name for compatibility
                                        create_sql = f'CREATE TABLE "{table_name.lower()}" ({col_str})'
                                        conn.execute(text(create_sql))
                                    else:
                                        # DuckDB/etc — use handler
                                        _create_table_from_schema(handler, table_name, schema, conn)
                                else:
                                    # Infer schema from data
                                    if table_data.get('data'):
                                        inferred = _infer_schema_from_data(table_data['data'], table_name)
                                        _create_table_from_schema(handler, table_name, inferred, conn)
                                
                                # Insert data
                                quoted_table = actual_handler._quote_identifier(table_name.lower()) if hasattr(actual_handler, '_quote_identifier') else f'"{table_name}"'
                                for row in table_data.get('data', []):
                                    clean_row = {k: v for k, v in row.items() if k not in ['_id', 'doc_id']}
                                    if not clean_row:
                                        continue
                                    serialized_row = {}
                                    for k, v in clean_row.items():
                                        serialized_row[k] = json.dumps(v) if isinstance(v, (dict, list)) else v
                                    
                                    columns = list(serialized_row.keys())
                                    quoted_cols = ', '.join([actual_handler._quote_identifier(c) if hasattr(actual_handler, '_quote_identifier') else f'"{c}"' for c in columns])
                                    placeholders = ', '.join([f':{c}' for c in columns])
                                    insert_sql = f"INSERT INTO {quoted_table} ({quoted_cols}) VALUES ({placeholders})"
                                    conn.execute(text(insert_sql), serialized_row)
                        else:
                            # Other SQL — explicit transaction
                            with handler._get_connection() as conn:
                                conn.execute(text("BEGIN"))
                                try:
                                    conn.execute(text(f'DROP TABLE IF EXISTS "{table_name}"'))
                                    # Similar creation/insertion logic...
                                    # (reuse same as above for simplicity)
                                    conn.commit()
                                except:
                                    conn.execute(text("ROLLBACK"))
                                    raise
                    else:
                        # NoSQL
                        handler.create_collection(table_name)
                        for doc in table_data.get('data', []):
                            clean_doc = {k: v for k, v in doc.items() if k not in ['_id', 'doc_id']}
                            handler.insert(table_name, clean_doc)
                        
                        # ✅ Apply validation rules AFTER data import
                        check_constraints = table_data.get('constraints', {}).get('check', [])
                        if check_constraints and hasattr(handler, 'apply_validation_rules'):
                            validation_rules = {}
                            for constraint in check_constraints:
                                col_name = constraint.get('column')
                                expression = constraint.get('expression', '')
                                
                                if col_name and expression:
                                    parsed = _parse_validation_expression(expression)
                                    if parsed:
                                        validation_rules[col_name] = parsed
                                        logger.debug(f"Collected rules for {col_name}: {parsed}")

                            if validation_rules:
                                try:
                                    logger.info(f"About to apply {len(validation_rules)} validation rules:")
                                    for field, rules in validation_rules.items():
                                        logger.info(f"  {field}: {rules}")
                                    
                                    handler.apply_validation_rules(table_name, validation_rules)
                                    logger.info(f"✅ Applied all {len(validation_rules)} merged validation rules to {table_name}")
                                except Exception as val_err:
                                    logger.warning(f"⚠️ Could not apply merged validation rules: {val_err}")
                                    logger.warning(f"   Reason: Existing data may violate these constraints")
                        
                        # # ✅ NEW: Apply validation rules AFTER data import
                        # check_constraints = table_data.get('constraints', {}).get('check', [])
                        # if check_constraints and hasattr(handler, 'apply_validation_rules'):
                        #     validation_rules = {}
                        #     for constraint in check_constraints:
                        #         col_name = constraint.get('column')
                        #         if col_name:
                        #             validation_rules[col_name] = {
                        #                 'expression': constraint.get('expression')
                        #             }
                            
                        #     if validation_rules:
                        #         try:
                        #             handler.apply_validation_rules(table_name, validation_rules)
                        #             logger.info(f"✅ Applied validation rules to {table_name}")
                        #         except Exception as val_err:
                        #             logger.warning(f"⚠️ Could not apply validation rules: {val_err}")
                    
                    return jsonify({
                        'success': True,
                        'message': 'Table imported successfully!'
                    })
                
                except Exception as e:
                    logger.error(f"Single table JSON import failed: {e}")
                    import traceback
                    logger.error(traceback.format_exc())
                    return jsonify({
                        'success': False,
                        'error': f'Import failed: {str(e)}'
                    }), 500
        
        except Exception as e:
            logger.error(f"❌ Table import failed: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500
        
    # ===== VIEWS MANAGEMENT API ROUTES =====
    @app.route('/api/db/<db_name>/views', methods=['GET'])
    def api_list_views(db_name):
        """JSON API: List all views in database"""
        try:
            logger.debug(f"✅ API call: GET /api/db/{db_name}/views")
            
            app.config['HANDLER'].switch_db(db_name)
            handler = app.config['HANDLER']
            
            # Check if handler supports views
            supports_views = False
            views = []
            
            if hasattr(handler, 'supports_views'):
                supports_views = handler.supports_views()
                if supports_views and hasattr(handler, 'list_views'):
                    views = handler.list_views()
            
            return jsonify({
                'success': True,
                'views': views,
                'supports_views': supports_views,
                'db_type': app.config['DB_TYPE'],
                'handler': app.config['CURRENT_HANDLER_NAME']
            })
            
        except Exception as e:
            logger.error(f"❌ API call failed: /api/db/{db_name}/views - {e}")
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/db/<db_name>/views/create', methods=['POST'])
    def api_create_view(db_name):
        """JSON API: Create new view"""
        try:
            logger.debug(f"✅ API call: POST /api/db/{db_name}/views/create")
            
            app.config['HANDLER'].switch_db(db_name)
            handler = app.config['HANDLER']
            
            if not hasattr(handler, 'create_view'):
                return jsonify({'success': False, 'error': 'Views not supported'}), 400
            
            data = request.get_json()
            view_name = data.get('view_name')
            view_query = data.get('view_query')
            
            if not view_name or not view_query:
                return jsonify({'success': False, 'error': 'View name and query are required'}), 400
            
            try:
                handler.create_view(view_name, view_query)
                logger.debug(f"API: Created view {view_name}")
                return jsonify({
                    'success': True,
                    'message': f'View {view_name} created successfully'
                })
            except Exception as e:
                logger.error(f"Create view error: {str(e)}")
                return jsonify({'success': False, 'error': str(e)}), 500
                
        except Exception as e:
            logger.error(f"❌ API call failed: /api/db/{db_name}/views/create - {e}")
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/db/<db_name>/views/delete', methods=['POST'])
    def api_delete_view(db_name):
        """JSON API: Delete view"""
        try:
            logger.debug(f"✅ API call: POST /api/db/{db_name}/views/delete")
            
            app.config['HANDLER'].switch_db(db_name)
            handler = app.config['HANDLER']
            
            if not hasattr(handler, 'drop_view'):
                return jsonify({'success': False, 'error': 'Views not supported'}), 400
            
            data = request.get_json()
            view_name = data.get('view_name')
            
            if not view_name:
                return jsonify({'success': False, 'error': 'View name is required'}), 400
            
            try:
                handler.drop_view(view_name)
                logger.debug(f"API: Deleted view {view_name}")
                return jsonify({
                    'success': True,
                    'message': f'View {view_name} deleted successfully'
                })
            except Exception as e:
                logger.error(f"Delete view error: {str(e)}")
                return jsonify({'success': False, 'error': str(e)}), 500
                
        except Exception as e:
            logger.error(f"❌ API call failed: /api/db/{db_name}/views/delete - {e}")
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/db/<db_name>/view/<view_name>/definition', methods=['GET'])
    def api_get_view_definition(db_name, view_name):
        """JSON API: Get view definition"""
        try:
            logger.debug(f"✅ API call: GET /api/db/{db_name}/view/{view_name}/definition")
            
            app.config['HANDLER'].switch_db(db_name)
            handler = app.config['HANDLER']
            
            if not hasattr(handler, 'get_view_definition'):
                return jsonify({'success': False, 'error': 'Views not supported'}), 400
            
            try:
                definition = handler.get_view_definition(view_name)
                return jsonify({
                    'success': True,
                    'definition': definition
                })
            except Exception as e:
                logger.error(f"Get view definition error: {str(e)}")
                return jsonify({'success': False, 'error': str(e)}), 500
                
        except Exception as e:
            logger.error(f"❌ API call failed: /api/db/{db_name}/view/{view_name}/definition - {e}")
            return jsonify({'success': False, 'error': str(e)}), 500

    # ===== PARTITIONS MANAGEMENT API ROUTES =====
    @app.route('/api/db/<db_name>/partitions/support', methods=['GET'])
    def api_check_partitions_support(db_name):
        """JSON API: Check if partitions are supported"""
        try:
            logger.debug(f"✅ API call: GET /api/db/{db_name}/partitions/support")
            
            app.config['HANDLER'].switch_db(db_name)
            handler = app.config['HANDLER']
            
            supports_partitions = False
            if hasattr(handler, 'supports_partitions'):
                supports_partitions = handler.supports_partitions()
            
            return jsonify({
                'success': True,
                'supports_partitions': supports_partitions
            })
            
        except Exception as e:
            logger.error(f"❌ API call failed: /api/db/{db_name}/partitions/support - {e}")
            return jsonify({'success': False, 'error': str(e)}), 500
        
    @app.route('/api/db/<db_name>/partitions/capabilities', methods=['GET'])
    def api_partition_capabilities(db_name):
        try:
            logger.debug(f"✅ API call: GET /api/db/{db_name}/partitions/capabilities")

            app.config['HANDLER'].switch_db(db_name)
            handler = app.config['HANDLER']

            return jsonify({
                'success': True,
                'capabilities': {
                    'list': getattr(handler, 'supports_partition_listing', lambda: False)(),
                    'create': getattr(handler, 'supports_partition_creation', lambda: False)(),
                    'delete': getattr(handler, 'supports_partition_deletion', lambda: False)()
                }
            })

        except Exception as e:
            logger.error(f"❌ API call failed: /partitions/capabilities - {e}")
            return jsonify({'success': False, 'error': str(e)}), 500


    @app.route('/api/db/<db_name>/table/<table_name>/partitions', methods=['GET'])
    def api_list_partitions(db_name, table_name):
        """JSON API: List partitions for a table"""
        try:
            logger.debug(f"✅ API call: GET /api/db/{db_name}/table/{table_name}/partitions")
            
            app.config['HANDLER'].switch_db(db_name)
            handler = app.config['HANDLER']
            
            if not hasattr(handler, 'list_partitions'):
                return jsonify({'success': False, 'error': 'Partitions not supported'}), 400
            
            partitions = handler.list_partitions(table_name)
            
            return jsonify({
                'success': True,
                'partitions': partitions
            })
            
        except Exception as e:
            logger.error(f"❌ API call failed: /api/db/{db_name}/table/{table_name}/partitions - {e}")
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/db/<db_name>/table/<table_name>/partitions/create', methods=['POST'])
    def api_create_partition(db_name, table_name):
        """JSON API: Create partition for table"""
        try:
            logger.debug(f"✅ API call: POST /api/db/{db_name}/table/{table_name}/partitions/create")
            
            app.config['HANDLER'].switch_db(db_name)
            handler = app.config['HANDLER']
            
            if not hasattr(handler, 'create_partition'):
                return jsonify({'success': False, 'error': 'Partitions not supported'}), 400
            
            data = request.get_json()
            partition_config = data.get('partition_config')
            
            if not partition_config:
                return jsonify({'success': False, 'error': 'Partition configuration is required'}), 400
            
            try:
                handler.create_partition(table_name, partition_config)
                return jsonify({
                    'success': True,
                    'message': 'Partition created successfully'
                })
            except Exception as e:
                logger.error(f"Create partition error: {str(e)}")
                return jsonify({'success': False, 'error': str(e)}), 500
                
        except Exception as e:
            logger.error(f"❌ API call failed: /api/db/{db_name}/table/{table_name}/partitions/create - {e}")
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/db/<db_name>/table/<table_name>/partitions/delete', methods=['POST'])
    def api_delete_partition(db_name, table_name):
        """JSON API: Delete partition"""
        try:
            logger.debug(f"✅ API call: POST /api/db/{db_name}/table/{table_name}/partitions/delete")
            
            app.config['HANDLER'].switch_db(db_name)
            handler = app.config['HANDLER']
            
            if not hasattr(handler, 'drop_partition'):
                return jsonify({'success': False, 'error': 'Partitions not supported'}), 400
            
            data = request.get_json()
            partition_name = data.get('partition_name')
            
            if not partition_name:
                return jsonify({'success': False, 'error': 'Partition name is required'}), 400
            
            try:
                handler.drop_partition(table_name, partition_name)
                return jsonify({
                    'success': True,
                    'message': f'Partition {partition_name} deleted successfully'
                })
            except Exception as e:
                logger.error(f"Delete partition error: {str(e)}")
                return jsonify({'success': False, 'error': str(e)}), 500
                
        except Exception as e:
            logger.error(f"❌ API call failed: /api/db/{db_name}/table/{table_name}/partitions/delete - {e}")
            return jsonify({'success': False, 'error': str(e)}), 500
        
    return app